// MicroPython module `repeater`: shares the uplink network (STA) through the
// board's hotspot (AP) with NAT, all in C so forwarding never waits on Python.
//
//   repeater.start(ssid, password, hostname)  after both WLAN interfaces are active
//   repeater.hold(True / False)               no scans or reconnects while True
//   repeater.status()                         (uplink up, RSSI, failed attempts, held)
//   repeater.info()                           (up, rssi, chan, 2nd chan, HT40?, rx bytes,
//                                              tx bytes) for the diagnostics page
//
// While the uplink is up, hotspot clients are given its DNS server and get
// real internet. While it is down they are given the hotspot's own address as
// DNS, so the board's captive-portal DNS answers. Leases are short so clients
// pick up the change within about a minute.

#include <string.h>
#include "py/runtime.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_netif_net_stack.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "lwip/netif.h"
#include "tiny_mdns.h"

#define QUICK_RETRIES 3                    // retry after 1 s this many times, then back off
#define BACKOFF_STEP_US (5 * 1000000)       // 5 s, 10 s, ... up to BACKOFF_MAX_US
#define BACKOFF_MAX_US (60 * 1000000)
#define LEASE_MINUTES 2                     // clients renew every minute

static const char *TAG = "repeater";
static esp_netif_t *sta_netif;
static esp_netif_t *ap_netif;
static wifi_config_t sta_cfg;
static char uplink_ssid[33];
static uint32_t ap_ip;
static esp_timer_handle_t retry_timer;
static volatile bool started, held, up, scanning, user_scanning;
static volatile int failures;

// Byte counters on the uplink interface, for the diagnostics page. Each is
// written by one task only (Wi-Fi RX task / lwIP thread), so no locking on the
// packet path; reads re-read until stable (64-bit stores aren't atomic here).
static volatile uint64_t rx_bytes, tx_bytes;
static netif_input_fn orig_input;
static netif_linkoutput_fn orig_output;

static IRAM_ATTR err_t count_input(struct pbuf *p, struct netif *n)
{
    rx_bytes += p->tot_len;
    return orig_input(p, n);
}

static IRAM_ATTR err_t count_output(struct netif *n, struct pbuf *p)
{
    tx_bytes += p->tot_len;
    return orig_output(n, p);
}

// Wrap the uplink netif's input/output once it exists, to count forwarded bytes.
static void hook_counters(void)
{
    struct netif *n = esp_netif_get_netif_impl(sta_netif);
    if (!n || n->input == count_input) return;
    orig_input = n->input;
    orig_output = n->linkoutput;
    n->input = count_input;
    n->linkoutput = count_output;
}

static uint64_t read_u64(volatile uint64_t *v)
{
    uint64_t a, b;
    do {
        a = *v;
        b = *v;
    } while (a != b);
    return a;
}

// Give hotspot clients this DNS server (network byte order) from now on.
static void offer_dns(uint32_t dns_ip)
{
    esp_netif_dns_info_t dns = {.ip.type = ESP_IPADDR_TYPE_V4, .ip.u_addr.ip4.addr = dns_ip};
    uint8_t offer = 1;
    esp_netif_dhcps_stop(ap_netif);
    esp_netif_set_dns_info(ap_netif, ESP_NETIF_DNS_MAIN, &dns);
    esp_netif_dhcps_option(ap_netif, ESP_NETIF_OP_SET, ESP_NETIF_DOMAIN_NAME_SERVER, &offer, sizeof(offer));
    esp_netif_dhcps_start(ap_netif);
}

static void retry_later(void);

// Scan every channel for the uplink; join_strongest() runs when it's done.
// The hotspot pauses for the ~1.5 s scan, so never while held.
static void scan(void)
{
    if (held) return;
    wifi_scan_config_t cfg = {
        .ssid = (uint8_t *)uplink_ssid,
        .scan_type = WIFI_SCAN_TYPE_ACTIVE,
        .scan_time.active = {.min = 60, .max = 120},
    };
    scanning = esp_wifi_scan_start(&cfg, false) == ESP_OK;
    if (!scanning) retry_later();
}

static void retry_cb(void *arg)
{
    scan();
}

// 1 s for the first few failures, then 5 s, 10 s, ... 60 s, so a missing
// network doesn't keep pausing the hotspot.
static void retry_later(void)
{
    if (held) return; // hold(False) reconnects
    failures++;
    int64_t wait = 1000000;
    if (failures > QUICK_RETRIES) {
        wait = (int64_t)(failures - QUICK_RETRIES) * BACKOFF_STEP_US;
        if (wait > BACKOFF_MAX_US) wait = BACKOFF_MAX_US;
    }
    esp_timer_stop(retry_timer);
    esp_timer_start_once(retry_timer, wait);
}

// Lock onto the strongest node by BSSID and channel, so a network with
// several access points never leaves us on a distant one.
static void join_strongest(void)
{
    scanning = false;
    uint16_t total = 0;
    esp_wifi_scan_get_ap_num(&total);
    wifi_ap_record_t rec, best;
    bool found = false;
    for (int i = 0; i < total; i++) {
        if (esp_wifi_scan_get_ap_record(&rec) != ESP_OK) break;
        if (strcmp((char *)rec.ssid, uplink_ssid)) continue;
        if (!found || rec.rssi > best.rssi) {
            best = rec;
            found = true;
        }
    }
    esp_wifi_clear_ap_list();
    if (!found) {
        ESP_LOGW(TAG, "%s not found", uplink_ssid);
        retry_later();
        return;
    }
    if (held) return;
    sta_cfg.sta.bssid_set = true;
    memcpy(sta_cfg.sta.bssid, best.bssid, sizeof(sta_cfg.sta.bssid));
    sta_cfg.sta.channel = best.primary;
    esp_wifi_set_config(WIFI_IF_STA, &sta_cfg);
    esp_wifi_connect();
}

static void on_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_SCAN_DONE) {
        if (user_scanning) {
            return; // leave the records for repeater.scan()'s blocking caller
        } else if (scanning) {
            join_strongest();
        } else {
            esp_wifi_clear_ap_list(); // someone else's scan, or one we stopped
        }
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        if (up) {
            up = false;
            offer_dns(ap_ip); // offline: back to the captive portal
            ESP_LOGW(TAG, "Uplink lost (reason %d)", ((wifi_event_sta_disconnected_t *)data)->reason);
        }
        retry_later();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        up = true;
        failures = 0;
        hook_counters();
        esp_netif_dns_info_t dns;
        if (esp_netif_get_dns_info(sta_netif, ESP_NETIF_DNS_MAIN, &dns) == ESP_OK && dns.ip.u_addr.ip4.addr) {
            offer_dns(dns.ip.u_addr.ip4.addr);
        }
        esp_netif_napt_enable(ap_netif);
        ESP_LOGI(TAG, "Uplink up, sharing internet");
    }
}

static mp_obj_t repeater_start(mp_obj_t ssid_in, mp_obj_t pass_in, mp_obj_t host_in)
{
    if (started) return mp_const_none;
    size_t ssid_len, pass_len;
    const char *ssid = mp_obj_str_get_data(ssid_in, &ssid_len);
    const char *pass = mp_obj_str_get_data(pass_in, &pass_len);
    const char *host = mp_obj_str_get_str(host_in);
    if (ssid_len < 1 || ssid_len > 32 || pass_len > 63 || (pass_len && pass_len < 8)) {
        mp_raise_ValueError(MP_ERROR_TEXT("bad uplink name or password"));
    }
    sta_netif = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    ap_netif = esp_netif_get_handle_from_ifkey("WIFI_AP_DEF");
    esp_netif_ip_info_t ip;
    if (!sta_netif || !ap_netif || esp_netif_get_ip_info(ap_netif, &ip) != ESP_OK) {
        mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("activate both WLAN interfaces first"));
    }
    ap_ip = ip.ip.addr;

    memcpy(uplink_ssid, ssid, ssid_len);
    uplink_ssid[ssid_len] = 0;
    memset(&sta_cfg, 0, sizeof(sta_cfg));
    memcpy(sta_cfg.sta.ssid, ssid, ssid_len);
    memcpy(sta_cfg.sta.password, pass, pass_len);
    sta_cfg.sta.threshold.authmode = pass_len ? WIFI_AUTH_WPA_PSK : WIFI_AUTH_OPEN;

    // Latency: modem sleep adds tens to hundreds of ms, so keep it off. HT40
    // (40 MHz channels) roughly doubles throughput where the band allows it;
    // it falls back to 20 MHz when the router or channel does not. Config stays
    // in RAM: no flash writes (which stall both cores) when we set the chosen
    // node before each connect.
    esp_wifi_set_storage(WIFI_STORAGE_RAM);
    esp_wifi_set_ps(WIFI_PS_NONE);
    esp_wifi_set_bandwidth(WIFI_IF_STA, WIFI_BW_HT40);
    esp_wifi_set_bandwidth(WIFI_IF_AP, WIFI_BW_HT40);

    uint32_t lease = LEASE_MINUTES;
    esp_netif_dhcps_stop(ap_netif);
    esp_netif_dhcps_option(ap_netif, ESP_NETIF_OP_SET, ESP_NETIF_IP_ADDRESS_LEASE_TIME, &lease, sizeof(lease));
    offer_dns(ap_ip); // captive until the uplink is up
    tiny_mdns_start(host, ap_ip);

    const esp_timer_create_args_t timer_args = {.callback = retry_cb, .name = "repeater"};
    esp_timer_create(&timer_args, &retry_timer);
    esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_event, NULL);
    esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_event, NULL);
    started = true;
    scan();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_3(repeater_start_obj, repeater_start);

// While held (the arm page is open) the uplink is left alone: no scans, which
// would pause the hotspot, and no reconnects. Releasing reconnects if needed.
static mp_obj_t repeater_hold(mp_obj_t flag)
{
    bool h = mp_obj_is_true(flag);
    if (!started || h == held) return mp_const_none;
    held = h;
    if (h) {
        esp_timer_stop(retry_timer);
        if (scanning) {
            scanning = false;
            esp_wifi_scan_stop();
        }
    } else if (!up) {
        failures = 0;
        scan();
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(repeater_hold_obj, repeater_hold);

static mp_obj_t repeater_status(void)
{
    int rssi = 0;
    if (up) esp_wifi_sta_get_rssi(&rssi);
    mp_obj_t items[4] = {mp_obj_new_bool(up), MP_OBJ_NEW_SMALL_INT(rssi), MP_OBJ_NEW_SMALL_INT(failures),
                         mp_obj_new_bool(held)};
    return mp_obj_new_tuple(4, items);
}
static MP_DEFINE_CONST_FUN_OBJ_0(repeater_status_obj, repeater_status);

// Richer link + throughput facts for the diagnostics page:
// (up, rssi, channel, second channel, HT40 in use, phy, rx bytes, tx bytes).
// phy: 4=11n, 3=11g, 2=11b, 0=unknown.
static mp_obj_t repeater_info(void)
{
    int rssi = 0, chan = 0, second = 0, phy = 0;
    bool ht40 = false;
    if (up) {
        wifi_ap_record_t ap;
        if (esp_wifi_sta_get_ap_info(&ap) == ESP_OK) {
            rssi = ap.rssi;
            chan = ap.primary;
            second = ap.second;   // 0 none, 1 above, 2 below
            phy = ap.phy_11n ? 4 : ap.phy_11g ? 3 : ap.phy_11b ? 2 : 0;
        }
        wifi_bandwidth_t bw;
        if (esp_wifi_get_bandwidth(WIFI_IF_STA, &bw) == ESP_OK) ht40 = bw == WIFI_BW_HT40;
    }
    mp_obj_t items[8] = {mp_obj_new_bool(up), MP_OBJ_NEW_SMALL_INT(rssi), MP_OBJ_NEW_SMALL_INT(chan),
                         MP_OBJ_NEW_SMALL_INT(second), mp_obj_new_bool(ht40), MP_OBJ_NEW_SMALL_INT(phy),
                         mp_obj_new_int_from_ull(read_u64(&rx_bytes)),
                         mp_obj_new_int_from_ull(read_u64(&tx_bytes))};
    return mp_obj_new_tuple(8, items);
}
static MP_DEFINE_CONST_FUN_OBJ_0(repeater_info_obj, repeater_info);

// A blocking all-SSID scan for the debug page, via esp_wifi directly
// (MicroPython's WLAN.scan() returns nothing in this AP+STA build). Returns a
// list of (ssid, rssi, channel), strongest first. Blocks ~2 s and briefly
// takes the radio off-channel, so forwarded traffic pauses - debug use only.
#define MAX_SCAN 24
static mp_obj_t repeater_scan(void)
{
    wifi_scan_config_t cfg = {
        .scan_type = WIFI_SCAN_TYPE_ACTIVE,
        .scan_time.active = {.min = 100, .max = 150},
    };
    user_scanning = true;
    esp_err_t err = esp_wifi_scan_start(&cfg, true); // block until done
    uint16_t found = 0;
    esp_wifi_scan_get_ap_num(&found);               // how many the radio actually heard
    static wifi_ap_record_t recs[MAX_SCAN];
    uint16_t n = MAX_SCAN;
    esp_err_t gerr = esp_wifi_scan_get_ap_records(&n, recs);
    if (err != ESP_OK || gerr != ESP_OK) n = 0;
    ESP_LOGI(TAG, "scan: connected=%d start=%s ap_num=%u returned=%u get=%s", up,
             esp_err_to_name(err), found, n, esp_err_to_name(gerr));
    esp_wifi_clear_ap_list();
    user_scanning = false;

    mp_obj_t list = mp_obj_new_list(0, NULL);
    for (int i = 0; i < n; i++) {
        if (recs[i].ssid[0] == 0) continue; // hidden
        mp_obj_t item[3] = {
            mp_obj_new_str((const char *)recs[i].ssid, strlen((const char *)recs[i].ssid)),
            MP_OBJ_NEW_SMALL_INT(recs[i].rssi), MP_OBJ_NEW_SMALL_INT(recs[i].primary)};
        mp_obj_list_append(list, mp_obj_new_tuple(3, item));
    }
    return list;
}
static MP_DEFINE_CONST_FUN_OBJ_0(repeater_scan_obj, repeater_scan);

static const mp_rom_map_elem_t repeater_globals_table[] = {
    {MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_repeater)},
    {MP_ROM_QSTR(MP_QSTR_start), MP_ROM_PTR(&repeater_start_obj)},
    {MP_ROM_QSTR(MP_QSTR_hold), MP_ROM_PTR(&repeater_hold_obj)},
    {MP_ROM_QSTR(MP_QSTR_status), MP_ROM_PTR(&repeater_status_obj)},
    {MP_ROM_QSTR(MP_QSTR_info), MP_ROM_PTR(&repeater_info_obj)},
    {MP_ROM_QSTR(MP_QSTR_scan), MP_ROM_PTR(&repeater_scan_obj)},
};
static MP_DEFINE_CONST_DICT(repeater_globals, repeater_globals_table);

const mp_obj_module_t repeater_module = {
    .base = {&mp_type_module},
    .globals = (mp_obj_dict_t *)&repeater_globals,
};
MP_REGISTER_MODULE(MP_QSTR_repeater, repeater_module);
