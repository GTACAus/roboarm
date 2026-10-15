# The board's Wi-Fi: its own hotspot, the uplink that gives the hotspot internet, the web
# server and the live (WebSocket) link to the iPad page.
#
# The hotspot is always on. The C module `repeater` joins the uplink network and shares its
# internet with the hotspot (NAT), so the iPad can browse and drive the arm on one network.
# While the arm page is open the uplink is left alone (no scans, which would pause the hotspot).
# If the uplink is down, the iPad is given this board as its DNS server and every web address
# leads here, so joining the Wi-Fi pops up a landing page, like hotel Wi-Fi.
# Page files are frozen into the firmware (www_data.py) and sent a piece at a time, so the
# hub link never stalls.

import gc
import network
import socket
import utime
import ubinascii
import esp32
import repeater
from www_data import FILES as WWW_FILES
try:
    import hashlib
except ImportError:
    import uhashlib as hashlib

# Each board's Wi-Fi settings live only in config.py on the board, written by
# tools/provision.py; none are built into the firmware.
try:
    import config
except ImportError:
    config = None
WIFI_NAME = getattr(config, "WIFI_NAME", None)            # the network name students look for, e.g. "GTAC 7"
WIFI_PASSWORD = getattr(config, "WIFI_PASSWORD", None)    # at least 8 characters; must match the QR codes
UPLINK_NAME = getattr(config, "UPLINK_NAME", None)        # the network whose internet is shared (None: no internet)
UPLINK_PASSWORD = getattr(config, "UPLINK_PASSWORD", "")
SIMULATE = getattr(config, "SIMULATE", False)             # a test board with a simulated hub
HOSTNAME = "gtac"              # the remote is also at http://gtac.local (every board, on its own hotspot)
ADDRESS = "10.10.10.10"        # the remote's web address (private: never cached from the internet)
FILES = {"/app.js": ("app.js.gz", "application/javascript"),
         "/style.css": ("style.css.gz", "text/css"),
         "/blockly.js": ("blockly.js.gz", "application/javascript"),
         "/figtree.woff2": ("figtree.woff2", "font/woff2"),     # already compressed: sent as is
         "/logo.png": ("logo.png", "image/png")}
MAX_LIVE = 4                   # live page connections kept at once
PAGE_TIMEOUT_MS = 3000         # the page counts as open while it has spoken within this time
FORGET_MS = 15000              # a device whose page has been closed this long gets the sign-in pop-up again next time
STALL_MS = 10000               # a download or live link with no progress this long is closed (its device has gone)
MAX_SENDING = 8                # downloads at once; the oldest is dropped past this
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


def esc(text):
    """Escape a value for HTML."""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _json(text):
    """Escape a string for inside a JSON double-quoted value."""
    out = ""
    for c in text:
        if c == '"' or c == "\\":
            out += "\\" + c
        elif c < " ":
            out += "\\u%04x" % ord(c)
        else:
            out += c
    return out


def _dur(s):
    d, h, m = s // 86400, s % 86400 // 3600, s % 3600 // 60
    if d:
        return "%dd %dh" % (d, h)
    if h:
        return "%dh %dm" % (h, m)
    return "%dm %ds" % (m, s % 60)


def stats_page(info):
    """Diagnostics page for the board. `info` is a plain dict (see Web._stats_info),
    so this is easy to test."""
    phy = {4: "802.11n", 3: "802.11g", 2: "802.11b"}.get(info.get("phy", 0), "-")
    width = "40 MHz (HT40)" if info.get("ht40") else "20 MHz"
    mb = lambda b: "%.1f MB" % (b / 1e6) if b < 1e9 else "%.2f GB" % (b / 1e9)
    if info["uplink"]:
        if info["up"]:
            link = "connected, %d dBm" % info["rssi"]
        else:
            link = "not connected (retries: %d)" % info["fails"]
        rows = [("Uplink network", esc(info["uplink"])),
                ("Uplink status", link),
                ("Signal (RSSI)", "%d dBm" % info["rssi"] if info["up"] else "-"),
                ("Radio", "%s, channel %s, %s" % (phy, info["channel"], width) if info["up"] else "-"),
                ("Transmit power", "%s dBm" % info["txpower"] if info["txpower"] is not None else "-"),
                ("Board address on uplink", info["sta_ip"] or "-"),
                ("Internet to clients", "on hold (arm page open)" if info["held"] else
                 ("shared" if info["up"] else "waiting for uplink")),
                ("Throughput now", "down %.1f / up %.1f Mbps" % (info["down"], info["up_mbps"])),
                ("Data (down / up)", "%s / %s" % (mb(info["rx"]), mb(info["tx"])))]
    else:
        rows = [("Uplink network", "none (internet sharing off)")]
    hub = info.get("hub")
    if hub is not None:
        rows.append(("Hub link", "connected" if hub["connected"] else "not connected (check the cable in port A)"))
        bat = hub["battery"]
        if bat:
            pct, mv, age = bat
            rows.append(("Hub battery", "%d%% (%.2f V), %s ago%s" % (
                pct, mv / 1000, _dur(age), " - charge soon" if pct < 20 else "")))
        else:
            rows.append(("Hub battery", "not reported (hub program too old, or its hub can't say)"))
    rows += [("Hotspot", esc(info["ap_ssid"]) + " on channel %s" % info["channel"]),
             ("Hotspot address", info["ap_ip"]),
             ("Clients connected", "-" if info["clients"] is None else str(info["clients"])),
             ("Chip temperature", "%d C" % info["temp"] if info["temp"] is not None else "-"),
             ("Uptime", _dur(info["uptime_s"]))]
    if info["ram_free"] is not None:
        rows.append(("Free RAM (now / lowest)", "%d / %d KB" % (info["ram_free"] // 1024, info["ram_min"] // 1024)))
    else:
        rows.append(("Free memory", "%d KB" % (info["mem_free"] // 1024)))
    if info["sim"]:
        rows.append(("Mode", "SIMULATION (no real arm)"))
    table = "".join("<tr><td>%s</td><td>%s</td></tr>" % (k, v) for k, v in rows)
    clients = "".join("<li>%s</li>" % esc(m) for m in info["macs"])
    return (
        "<!doctype html><html><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        "<title>%s diagnostics</title><style>"
        "body{font:15px/1.5 system-ui,sans-serif;margin:0 auto;padding:16px;max-width:460px;color:#18181b}"
        "h1{font-size:19px}h2{font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:#71717a;margin:18px 0 6px}"
        "table{width:100%%;border-collapse:collapse}td{padding:4px 2px;border-top:1px solid #e4e4e7;vertical-align:top}"
        "td:first-child{color:#71717a;width:48%%}ul{margin:4px 0;padding-left:20px;color:#52525b}"
        "button{margin-top:10px;padding:8px 14px;border:0;border-radius:8px;background:#18181b;color:#fff;font:inherit}"
        "a{color:#2563eb}"
        "@media(prefers-color-scheme:dark){body{background:#09090b;color:#f4f4f5}"
        "td{border-color:#27272a}button{background:#f4f4f5;color:#18181b}}"
        "</style></head><body>"
        "<h1>%s</h1>"
        "<h2>Status</h2><table>%s</table>"
        "%s"
        "<h2>Nearby networks</h2>"
        "<button id=scanbtn onclick=doScan()>Scan for Wi-Fi</button>"
        "<p id=scannote style='color:#71717a;font-size:13px;margin:6px 0'>"
        "Debug only. Scanning pauses the internet for a moment.</p>"
        "<table><tbody id=scanres></tbody></table>"
        "<p><a href=/stats>Refresh</a> &middot; <a href=/>Arm page</a></p>"
        "<script>"
        "var reloader=setInterval(function(){location.reload()},3000);"
        "function esc(t){return t.replace(/[&<>\"]/g,function(c){"
        "return{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]})}"
        "function doScan(){clearInterval(reloader);"
        "var b=document.getElementById('scanbtn');b.disabled=true;b.textContent='Scanning...';"
        "document.getElementById('scannote').textContent='Scanning (internet paused a moment)...';"
        "fetch('/scan').then(function(r){return r.json()}).then(function(l){"
        "document.getElementById('scanres').innerHTML=l.length?l.map(function(n){"
        "return '<tr><td>'+esc(n.ssid)+'</td><td>'+n.rssi+' dBm</td><td>ch '+n.ch+'</td></tr>'}).join('')"
        ":'<tr><td>No networks found</td></tr>';"
        "b.disabled=false;b.textContent='Scan again';"
        "document.getElementById('scannote').textContent='Auto-refresh paused. Reload the page to resume.';"
        "}).catch(function(){b.disabled=false;b.textContent='Scan failed - retry';});}"
        "</script>"
        "</body></html>"
    ) % (esc(info["ap_ssid"]), esc(info["ap_ssid"]) + " diagnostics", table,
         ("<h2>Client addresses</h2><ul>%s</ul>" % clients) if clients else "")


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
        if not WIFI_NAME or not WIFI_PASSWORD:
            raise ValueError("No Wi-Fi settings on this board: set it up with tools/provision.py")
        self.on_message = on_message
        self.last_message = utime.ticks_add(utime.ticks_ms(), -PAGE_TIMEOUT_MS - 1)
        self.accepted = {}         # device -> when its page last spoke; these are told "the network is fine"
        self.last_forget = utime.ticks_ms()
        self.live = []             # [socket, unread bytes, device, last heard from]
        self.sending = []          # [socket, file data in flash, bytes sent, last progress]
        self.hub_status = None     # set by arm.py: () -> {"connected", "battery"} for /stats

        self.held = False          # uplink on hold (arm page open)
        self.last_rx = self.last_tx = None   # for the live throughput figure on /stats
        self.last_rate_ms = utime.ticks_ms()

        # Seen by the uplink network's router, so each board is identifiable there
        network.hostname(WIFI_NAME.lower().replace(" ", "-"))
        ap = network.WLAN(network.AP_IF)
        ap.active(True)
        ap.config(essid=WIFI_NAME, password=WIFI_PASSWORD, authmode=3)
        try:
            ap.ifconfig((ADDRESS, "255.255.255.0", ADDRESS, ADDRESS))
        except Exception as e:
            print("Could not set the address:", e)
        self.ap = ap
        if UPLINK_NAME:
            # Internet sharing is an extra: if it can't start, the arm's hotspot still works
            try:
                sta = network.WLAN(network.STA_IF)
                sta.active(True)
                repeater.start(UPLINK_NAME, UPLINK_PASSWORD, HOSTNAME)
            except Exception as e:
                print("Internet sharing could not start:", e)
        self.server = socket.socket()
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # The hotspot address only: devices on the uplink network can't reach the arm
        self.server.bind((ADDRESS, 80))
        self.server.listen(4)
        self.server.setblocking(False)
        self.dns = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.dns.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.dns.bind((ADDRESS, 53))
        self.dns.setblocking(False)
        print("Wi-Fi on:", WIFI_NAME, "-> http://" + ADDRESS, "or http://%s.local," % HOSTNAME,
              "internet via %s" % UPLINK_NAME if UPLINK_NAME else "no internet sharing")

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
        hold = self.page_open()
        if hold != self.held:
            self.held = hold
            repeater.hold(hold)          # arm page open: leave the uplink alone
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
            self.live.append([client, b"", device, utime.ticks_ms()])
            self._accept(device)
            return True
        if path.startswith("/s?"):
            self._accept(device)
            body = self._message(path[3:]).encode()
            client.write(("HTTP/1.0 200 OK\r\nCache-Control: no-store\r\nContent-Length: %d\r\n\r\n" % len(body)).encode() + body)
            return False
        if path == "/stats":
            self._accept(device)
            return self._send_html(client, stats_page(self._stats_info()))
        if path == "/scan":
            self._accept(device)
            return self._scan(client)
        if path in FILES:
            name, kind = FILES[path]
            return self._send_file(client, name, kind, "no-cache" if path in ("/app.js", "/style.css") else "max-age=86400")
        if path.startswith("/media/") and path.endswith(".svg") and "/" not in path[7:] and ".." not in path:
            return self._send_file(client, "media/" + path[7:] + ".gz", "image/svg+xml", "max-age=86400")
        if host in (ADDRESS, HOSTNAME + ".local") and (path == "/" or path.startswith("/index")):
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

    def _send_html(self, client, html):
        body = html.encode()
        client.write(("HTTP/1.0 200 OK\r\nContent-Type: text/html\r\nCache-Control: no-store\r\n"
                      "Content-Length: %d\r\n\r\n" % len(body)).encode() + body)
        return False

    def _stats_info(self):
        gc.collect()
        try:
            channel = self.ap.config("channel")
        except Exception:
            channel = "?"
        macs = []
        try:
            for st in self.ap.status("stations"):
                macs.append(ubinascii.hexlify(st[0], ":").decode())
        except Exception:
            pass
        up, rssi, fails, held = repeater.status() if UPLINK_NAME else (False, 0, 0, False)
        chan2 = ht40 = phy = rx = tx = 0
        if UPLINK_NAME:
            try:
                up, rssi, _c, chan2, ht40, phy, rx, tx = repeater.info()
            except Exception:
                pass
        # Live throughput since the last /stats request.
        now = utime.ticks_ms()
        dt = utime.ticks_diff(now, self.last_rate_ms) / 1000
        down = up_mbps = 0.0
        if self.last_rx is not None and dt > 0.2:
            down = max(0, (rx - self.last_rx)) * 8 / dt / 1e6
            up_mbps = max(0, (tx - self.last_tx)) * 8 / dt / 1e6
        self.last_rx, self.last_tx, self.last_rate_ms = rx, tx, now
        sta = network.WLAN(network.STA_IF)
        try:
            sta_ip = sta.ifconfig()[0] if (UPLINK_NAME and sta.active() and sta.isconnected()) else None
        except Exception:
            sta_ip = None
        try:
            txpower = sta.config("txpower")
        except Exception:
            txpower = None
        try:
            temp = esp32.mcu_temperature()
        except Exception:
            temp = None
        try:
            free = sum(r[1] for r in esp32.idf_heap_info(esp32.HEAP_DATA))
            least = sum(r[3] for r in esp32.idf_heap_info(esp32.HEAP_DATA))
        except Exception:
            free = least = None
        return {"ap_ssid": WIFI_NAME, "ap_ip": ADDRESS, "channel": channel,
                "clients": len(macs) if macs else (0 if UPLINK_NAME is not None else None),
                "macs": macs, "uplink": UPLINK_NAME, "up": up, "rssi": rssi, "fails": fails,
                "held": held, "sta_ip": sta_ip, "uptime_s": now // 1000, "mem_free": gc.mem_free(),
                "sim": SIMULATE, "chan2": chan2, "ht40": ht40, "phy": phy, "rx": rx, "tx": tx,
                "down": down, "up_mbps": up_mbps, "txpower": txpower, "temp": temp,
                "ram_free": free, "ram_min": least,
                "hub": self.hub_status() if self.hub_status else None}

    # A user-triggered all-SSID scan (debug page only), via repeater.scan() in
    # the C module - MicroPython's own WLAN.scan() returns nothing in this
    # AP+STA build. Blocks ~2 s and briefly takes the radio off-channel, so the
    # reply is sent when done (the page shows a loading state) and forwarded
    # traffic pauses for a moment. NAT itself keeps running.
    def _scan(self, client):
        try:
            nets = repeater.scan()             # list of (ssid, rssi, channel)
        except Exception:
            nets = []
        best = {}                              # strongest reading per SSID
        for ssid, rssi, ch in nets:
            if not ssid:
                continue
            if ssid not in best or rssi > best[ssid][0]:
                best[ssid] = (rssi, ch)
        order = sorted(best.items(), key=lambda kv: -kv[1][0])
        parts = ['{"ssid":"%s","rssi":%d,"ch":%d}' % (_json(s), r, c) for s, (r, c) in order]
        body = ("[" + ",".join(parts) + "]").encode()
        client.write(("HTTP/1.0 200 OK\r\nContent-Type: application/json\r\nCache-Control: no-store\r\n"
                      "Content-Length: %d\r\n\r\n" % len(body)).encode() + body)
        return False

    def _send_file(self, client, name, kind, cache):
        data = WWW_FILES.get(name)
        if data is None:
            client.write(b"HTTP/1.0 404 Not Found\r\nContent-Length: 0\r\n\r\n")
            return False
        gz = "Content-Encoding: gzip\r\n" if name.endswith(".gz") else ""
        client.write(("HTTP/1.0 200 OK\r\nContent-Type: %s\r\n%sContent-Length: %d\r\n"
                      "Cache-Control: %s\r\n\r\n" % (kind, gz, len(data), cache)).encode())
        client.setblocking(False)
        if len(self.sending) >= MAX_SENDING:
            self._close(self.sending.pop(0)[0])
        self.sending.append([client, memoryview(data), 0, utime.ticks_ms()])   # straight from flash, no copy
        return True

    def _pump(self):
        """Send the next piece of every file being downloaded. A download that makes no
        progress for STALL_MS is dropped: its device left (or slept) without closing the
        connection, and each stuck one would otherwise hold a socket and its buffers for good."""
        now = utime.ticks_ms()
        for item in list(self.sending):
            sock, data, sent, last = item
            if sent >= len(data) or utime.ticks_diff(now, last) > STALL_MS:
                self._close(sock)
                self.sending.remove(item)
                continue
            try:
                n = sock.write(data[sent:sent + 2048])
            except OSError as e:
                if e.args and e.args[0] in (11, 115, 119):   # busy: try again next time
                    n = 0
                else:
                    self._close(sock)
                    self.sending.remove(item)
                    continue
            if n:
                item[2] = sent + n
                item[3] = now

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
        now = utime.ticks_ms()
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
                item[3] = now
            elif utime.ticks_diff(now, item[3]) > STALL_MS:
                self._drop_live(item)        # the page sends every 0.5 s: this one has gone
                continue
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
