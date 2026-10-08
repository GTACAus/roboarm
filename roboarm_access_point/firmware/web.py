# The board's Wi-Fi access point, web server and live (WebSocket) link to the iPad page.
#
# Started only when the hub asks for it (see PROTOCOL.md). Every web address and DNS name
# leads here, so joining the Wi-Fi pops up a landing page, like hotel Wi-Fi.
# Page files are stored gzipped in /www and sent a piece at a time, so the hub link never stalls.

import network
import socket
import utime
import os
import ubinascii
try:
    import hashlib
except ImportError:
    import uhashlib as hashlib

try:
    from config import WIFI_NAME   # each board's own name, set with: python tools/upload.py --name "GTAC 12"
except ImportError:
    WIFI_NAME = "GTAC 6"           # the network name students look for
WIFI_PASSWORD = "robotarm"     # at least 8 characters; must match the printed QR codes (robot_arm_updates_website/wifi-qr)
ADDRESS = "10.10.10.10"        # the remote's web address (private: never cached from the internet)
WWW = "/www/"
FILES = {"/app.js": ("app.js.gz", "application/javascript"),
         "/style.css": ("style.css.gz", "text/css"),
         "/blockly.js": ("blockly.js.gz", "application/javascript"),
         "/figtree.woff2": ("figtree.woff2", "font/woff2"),     # already compressed: sent as is
         "/logo.png": ("logo.png", "image/png")}
MAX_LIVE = 4                   # live page connections kept at once
PAGE_TIMEOUT_MS = 3000         # the page counts as open while it has spoken within this time
FORGET_MS = 15000              # a device whose page has been closed this long gets the sign-in pop-up again next time
APPLE_OK = b"<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>"
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def parse(text):
    """'m=00300&x=1' -> {'m': '00300', 'x': '1'}"""
    d = {}
    for part in text.split("&"):
        if "=" in part:
            k, v = part.split("=", 1)
            d[k] = v
    return d


def ws_frame(text):
    data = text.encode()
    n = len(data)
    head = bytes((0x81, n)) if n < 126 else bytes((0x81, 126, n >> 8, n & 255))
    return head + data


def dns_reply(q, ip):
    """Answer any DNS question with our own address."""
    if len(q) < 12:
        return None
    end = 12
    while end < len(q) and q[end]:
        end += q[end] + 1
    end += 5
    if end > len(q):
        return None
    return (q[:2] + b"\x81\x80" + q[4:6] + q[4:6] + b"\x00\x00\x00\x00" + q[12:end]
            + b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04" + bytes(int(n) for n in ip.split(".")))


class Web:
    def __init__(self, on_message):
        """on_message(dict) -> reply text. Called for every message from a page."""
        self.on_message = on_message
        self.last_message = utime.ticks_add(utime.ticks_ms(), -PAGE_TIMEOUT_MS - 1)
        self.accepted = {}         # device -> when its page last spoke; these are told "the network is fine"
        self.last_forget = utime.ticks_ms()
        self.live = []             # [socket, unread bytes]
        self.sending = []          # [socket, open file, bytes waiting]

        ap = network.WLAN(network.AP_IF)
        ap.active(True)
        ap.config(essid=WIFI_NAME, password=WIFI_PASSWORD, authmode=3)
        try:
            ap.ifconfig((ADDRESS, "255.255.255.0", ADDRESS, ADDRESS))
        except Exception as e:
            print("Could not set the address:", e)
        self.ap = ap
        self.server = socket.socket()
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(("0.0.0.0", 80))
        self.server.listen(4)
        self.server.setblocking(False)
        self.dns = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.dns.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.dns.bind(("0.0.0.0", 53))
        self.dns.setblocking(False)
        print("Wi-Fi on:", WIFI_NAME, "-> http://" + ADDRESS)

    def stop(self):
        for item in self.live + self.sending:
            self._close(item[0])
        for item in self.sending:
            try:
                item[1].close()
            except Exception:
                pass
        self.live = []
        self.sending = []
        for s in (self.server, self.dns):
            self._close(s)
        self.ap.active(False)
        print("Wi-Fi off")

    def page_open(self):
        return utime.ticks_diff(utime.ticks_ms(), self.last_message) < PAGE_TIMEOUT_MS

    # ---------- everything below runs a little at a time from poll()
    def poll(self):
        try:
            q, who = self.dns.recvfrom(512)
            r = dns_reply(q, ADDRESS)
            if r:
                self.dns.sendto(r, who)
        except OSError:
            pass
        try:
            client, addr = self.server.accept()
        except OSError:
            client = None
        if client is not None:
            keep = False
            try:
                client.settimeout(0.2)
                keep = self._answer(client, client.recv(700).decode(), addr[0])
            except Exception:
                pass
            if not keep:
                self._close(client)
        self._read_live()
        self._pump()
        now = utime.ticks_ms()
        if utime.ticks_diff(now, self.last_forget) > 1000:
            self.last_forget = now
            for d in [d for d, t in self.accepted.items() if utime.ticks_diff(now, t) > FORGET_MS]:
                del self.accepted[d]          # page closed: the pop-up shows again when it reconnects

    def _answer(self, client, request, device):
        lines = request.split("\r\n")
        parts = lines[0].split(" ")
        full = parts[1] if len(parts) > 1 else "/"
        path = full if full.startswith("/s?") else full.split("?")[0]   # file names ignore ?v=... version tags
        host = ""
        key = ""
        for h in lines[1:]:
            low = h.lower()
            if low.startswith("host:"):
                host = h[5:].strip().split(":")[0].lower()
            elif low.startswith("sec-websocket-key:"):
                key = h.split(":", 1)[1].strip()

        if path.startswith("/ws") and key:
            accept = ubinascii.b2a_base64(hashlib.sha1((key + WS_GUID).encode()).digest()).strip().decode()
            client.write(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                          "Sec-WebSocket-Accept: %s\r\n\r\n" % accept).encode())
            client.setblocking(False)
            if len(self.live) >= MAX_LIVE:
                self._drop_live(self.live[0])
            self.live.append([client, b"", device])
            self._accept(device)
            return True
        if path.startswith("/s?"):
            self._accept(device)
            body = self._message(path[3:]).encode()
            client.write(("HTTP/1.0 200 OK\r\nCache-Control: no-store\r\nContent-Length: %d\r\n\r\n" % len(body)).encode() + body)
            return False
        if path in FILES:
            name, kind = FILES[path]
            return self._send_file(client, name, kind, "no-cache" if path in ("/app.js", "/style.css") else "max-age=86400")
        if path.startswith("/media/") and path.endswith(".svg") and "/" not in path[7:] and ".." not in path:
            return self._send_file(client, "media/" + path[7:] + ".gz", "image/svg+xml", "max-age=86400")
        if host == ADDRESS and (path == "/" or path.startswith("/index")):
            self._accept(device)
            self.last_message = utime.ticks_ms()
            return self._send_file(client, "index.html.gz", "text/html", "no-cache")
        if path.startswith("/favicon"):
            client.write(b"HTTP/1.0 404 Not Found\r\nContent-Length: 0\r\n\r\n")
            return False
        apple = "hotspot-detect" in path or host.endswith("apple.com")
        android = "generate_204" in path or "gen_204" in path
        probe = apple or android or "connecttest" in path or "ncsi" in path or path.endswith("success.txt")
        if device in self.accepted and apple:
            client.write(("HTTP/1.0 200 OK\r\nContent-Type: text/html\r\nContent-Length: %d\r\n\r\n" % len(APPLE_OK)).encode() + APPLE_OK)
            return False
        if device in self.accepted and android:
            client.write(b"HTTP/1.0 204 No Content\r\nContent-Length: 0\r\n\r\n")
            return False
        if probe:                                   # the phone's "is there internet?" check: the sign-in pop-up
            return self._send_file(client, "landing.html.gz", "text/html", "no-cache")
        # Any other web page (any address, any path) goes to the remote
        client.write(("HTTP/1.0 302 Found\r\nLocation: http://%s/\r\nCache-Control: no-store\r\nContent-Length: 0\r\n\r\n" % ADDRESS).encode())
        return False

    def _accept(self, device):
        self.accepted[device] = utime.ticks_ms()
        if len(self.accepted) > 20:
            oldest = min(self.accepted, key=lambda d: self.accepted[d])
            del self.accepted[oldest]

    def _message(self, text):
        self.last_message = utime.ticks_ms()
        return self.on_message(parse(text)) or ""

    def _send_file(self, client, name, kind, cache):
        try:
            size = os.stat(WWW + name)[6]
            f = open(WWW + name, "rb")
        except OSError:
            client.write(b"HTTP/1.0 404 Not Found\r\nContent-Length: 0\r\n\r\n")
            return False
        gz = "Content-Encoding: gzip\r\n" if name.endswith(".gz") else ""
        client.write(("HTTP/1.0 200 OK\r\nContent-Type: %s\r\n%sContent-Length: %d\r\n"
                      "Cache-Control: %s\r\n\r\n" % (kind, gz, size, cache)).encode())
        client.setblocking(False)
        self.sending.append([client, f, b""])
        return True

    def _pump(self):
        """Send the next piece of every file being downloaded."""
        for item in list(self.sending):
            sock, f, waiting = item
            if not waiting:
                waiting = f.read(2048)
                if not waiting:
                    f.close()
                    self._close(sock)
                    self.sending.remove(item)
                    continue
            try:
                n = sock.write(waiting)
            except OSError as e:
                if e.args and e.args[0] in (11, 115, 119):   # busy: try again next time
                    n = 0
                else:
                    f.close()
                    self._close(sock)
                    self.sending.remove(item)
                    continue
            item[2] = waiting[n or 0:]

    # ---------- live links
    def broadcast(self, text):
        if self.live:
            frame = ws_frame(text)
            for item in list(self.live):
                try:
                    item[0].write(frame)
                except Exception:
                    self._drop_live(item)

    def _drop_live(self, item):
        self._close(item[0])
        if item in self.live:
            self.live.remove(item)

    def _read_live(self):
        for item in list(self.live):
            sock = item[0]
            try:
                data = sock.recv(256)
            except OSError:
                data = None
            if data is not None:
                if not data:
                    self._drop_live(item)
                    continue
                item[1] += data
            buf = item[1]
            while len(buf) >= 2:
                op = buf[0] & 0x0F
                n = buf[1] & 0x7F
                start = 2
                if n == 126:
                    if len(buf) < 4:
                        break
                    n = (buf[2] << 8) | buf[3]
                    start = 4
                elif n == 127:
                    self._drop_live(item)
                    buf = b""
                    break
                mask = start
                if buf[1] & 0x80:
                    start += 4
                if len(buf) < start + n:
                    break
                body = bytearray(buf[start:start + n])
                if buf[1] & 0x80:
                    for i in range(n):
                        body[i] ^= buf[mask + (i & 3)]
                buf = buf[start + n:]
                if op == 1:                               # a message from the page
                    self._accept(item[2])
                    reply = self._message(bytes(body).decode())
                    if reply:
                        try:
                            sock.write(ws_frame(reply))
                        except Exception:
                            self._drop_live(item)
                            buf = b""
                            break
                elif op == 8:                             # the page closed the link
                    self._drop_live(item)
                    buf = b""
                    break
                elif op == 9:                             # ping
                    try:
                        sock.write(bytes((0x8A, n)) + body)
                    except Exception:
                        pass
            item[1] = buf

    @staticmethod
    def _close(s):
        try:
            s.close()
        except Exception:
            pass
