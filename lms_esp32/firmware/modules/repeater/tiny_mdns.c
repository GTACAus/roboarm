// Minimal mDNS responder (RFC 6762) for one IPv4 hostname on one interface.
//
// Answers "<host>.local" with an A record, and asserts there is no IPv6
// address with an NSEC record. Without that negative answer, browsers wait
// seconds for an AAAA reply before using the IPv4 one. Nothing else: no
// probing, service discovery, or querying.

#include "tiny_mdns.h"

#include <ctype.h>
#include <string.h>
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "lwip/sockets.h"

#define MDNS_PORT 5353
#define MDNS_GROUP "224.0.0.251"
#define TTL_S 120
#define TYPE_A 1
#define TYPE_AAAA 28
#define TYPE_NSEC 47
#define TYPE_ANY 255
#define CLASS_IN_FLUSH 0x8001 // IN with the cache-flush bit: we own this name
#define NAME_MAX_LEN 64

static const char *TAG = "mdns";
static uint8_t host_name[NAME_MAX_LEN]; // wire format, lowercase
static int host_name_len;
static uint32_t host_ip; // network byte order
static int sock = -1;
static struct sockaddr_in group_addr;

// Encode "host" + ".local" into DNS wire format.
static void encode_name(const char *host)
{
    int n = 0;
    host_name[n++] = strlen(host);
    for (const char *c = host; *c; c++) host_name[n++] = tolower((unsigned char)*c);
    memcpy(&host_name[n], "\x05local", 7); // includes the root label's 0
    host_name_len = n + 7;
}

// Read a possibly compressed name at off into out (lowercased wire format).
// Returns the offset just past the name in the packet, or -1 if malformed.
static int read_name(const uint8_t *p, int len, int off, uint8_t *out, int *out_len)
{
    int end = -1, n = 0, jumps = 0;
    for (;;) {
        if (off >= len) return -1;
        uint8_t l = p[off];
        if ((l & 0xC0) == 0xC0) {
            if (off + 1 >= len || ++jumps > 8) return -1;
            if (end < 0) end = off + 2;
            off = ((l & 0x3F) << 8) | p[off + 1];
            continue;
        }
        if ((l & 0xC0) || n + l + 1 > NAME_MAX_LEN || off + 1 + l > len) return -1;
        out[n++] = l;
        if (l == 0) break;
        for (int i = 0; i < l; i++) out[n++] = tolower(p[off + 1 + i]);
        off += l + 1;
    }
    *out_len = n;
    return end >= 0 ? end : off + 1;
}

static int put16(uint8_t *b, int n, uint16_t v)
{
    b[n] = v >> 8;
    b[n + 1] = v;
    return n + 2;
}

// Append our A record, or an NSEC saying A is the only type this name has.
static int put_record(uint8_t *b, int n, uint16_t type)
{
    memcpy(&b[n], host_name, host_name_len);
    n += host_name_len;
    n = put16(b, n, type);
    n = put16(b, n, CLASS_IN_FLUSH);
    n = put16(b, n, TTL_S >> 16);
    n = put16(b, n, TTL_S & 0xFFFF);
    if (type == TYPE_A) {
        n = put16(b, n, 4);
        memcpy(&b[n], &host_ip, 4);
        return n + 4;
    }
    n = put16(b, n, host_name_len + 3);
    memcpy(&b[n], host_name, host_name_len); // "next name" is ourselves
    n += host_name_len;
    b[n++] = 0;    // type bitmap window 0
    b[n++] = 1;    // bitmap length
    b[n++] = 0x40; // bit for type 1 (A) only
    return n;
}

// Build a response: `first` goes in the answer section, the other record in
// the additional section, so either lookup is settled by one packet. qd/qd_len
// copy the original question section back for legacy unicast queries.
static int build_response(uint8_t *b, uint16_t id, uint16_t first, const uint8_t *qd, int qd_len,
                          uint16_t qd_count)
{
    int n = put16(b, 0, id);
    n = put16(b, n, 0x8400); // response, authoritative
    n = put16(b, n, qd_count);
    n = put16(b, n, 1);
    n = put16(b, n, 0);
    n = put16(b, n, 1);
    // Copying from offset 12 keeps any compression pointers in qd valid.
    memcpy(&b[n], qd, qd_len);
    n += qd_len;
    n = put_record(b, n, first);
    return put_record(b, n, first == TYPE_A ? TYPE_NSEC : TYPE_A);
}

static void handle_query(const uint8_t *q, int len, const struct sockaddr_in *src)
{
    if (len < 12 || (q[2] & 0xF8)) return; // too short, a response, or not a standard query
    int qd_count = (q[4] << 8) | q[5];
    int off = 12;
    bool want_a = false, want_aaaa = false;
    for (int i = 0; i < qd_count; i++) {
        uint8_t name[NAME_MAX_LEN];
        int name_len;
        off = read_name(q, len, off, name, &name_len);
        if (off < 0 || off + 4 > len) return;
        uint16_t type = (q[off] << 8) | q[off + 1];
        off += 4;
        if (name_len != host_name_len || memcmp(name, host_name, name_len)) continue;
        want_a |= type == TYPE_A || type == TYPE_ANY;
        want_aaaa |= type == TYPE_AAAA;
    }
    if (!want_a && !want_aaaa) return;

    // Legacy resolvers query from a port other than 5353 and expect a direct
    // reply with their ID and question; everyone else gets the multicast answer.
    bool legacy = ntohs(src->sin_port) != MDNS_PORT;
    uint8_t resp[256];
    int qd_len = legacy ? off - 12 : 0;
    if (12 + qd_len + 2 * (host_name_len * 2 + 16) > (int)sizeof(resp)) return;
    int n = build_response(resp, legacy ? (q[0] << 8) | q[1] : 0, want_a ? TYPE_A : TYPE_NSEC,
                           &q[12], qd_len, legacy ? qd_count : 0);
    const struct sockaddr_in *dst = legacy ? src : &group_addr;
    sendto(sock, resp, n, 0, (const struct sockaddr *)dst, sizeof(*dst));
}

static void announce(void)
{
    uint8_t resp[256];
    int n = build_response(resp, 0, TYPE_A, NULL, 0, 0);
    sendto(sock, resp, n, 0, (const struct sockaddr *)&group_addr, sizeof(group_addr));
}

static void mdns_task(void *arg)
{
    announce();
    vTaskDelay(pdMS_TO_TICKS(1000));
    announce(); // RFC 6762 asks for at least two announcements
    uint8_t buf[512];
    for (;;) {
        struct sockaddr_in src;
        socklen_t src_len = sizeof(src);
        int len = recvfrom(sock, buf, sizeof(buf), 0, (struct sockaddr *)&src, &src_len);
        if (len > 0) handle_query(buf, len, &src);
    }
}

void tiny_mdns_start(const char *host, uint32_t ip)
{
    if (sock >= 0) return;
    encode_name(host);
    host_ip = ip;
    group_addr = (struct sockaddr_in){
        .sin_family = AF_INET,
        .sin_port = htons(MDNS_PORT),
        .sin_addr.s_addr = inet_addr(MDNS_GROUP),
    };

    sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    int one = 1;
    setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));
    struct sockaddr_in any = {.sin_family = AF_INET, .sin_port = htons(MDNS_PORT)};
    // Join the group only on our interface, so other networks' mDNS chatter
    // never reaches this task.
    struct ip_mreq mreq = {.imr_multiaddr.s_addr = group_addr.sin_addr.s_addr, .imr_interface.s_addr = ip};
    struct in_addr ifaddr = {.s_addr = ip};
    uint8_t ttl = 255; // required by RFC 6762
    if (bind(sock, (struct sockaddr *)&any, sizeof(any)) < 0 ||
        setsockopt(sock, IPPROTO_IP, IP_ADD_MEMBERSHIP, &mreq, sizeof(mreq)) < 0 ||
        setsockopt(sock, IPPROTO_IP, IP_MULTICAST_IF, &ifaddr, sizeof(ifaddr)) < 0 ||
        setsockopt(sock, IPPROTO_IP, IP_MULTICAST_TTL, &ttl, sizeof(ttl)) < 0) {
        ESP_LOGE(TAG, "socket setup failed (errno %d)", errno);
        close(sock);
        sock = -1;
        return;
    }
    xTaskCreate(mdns_task, "mdns", 3072, NULL, 2, NULL);
}
