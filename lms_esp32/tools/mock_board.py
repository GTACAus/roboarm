"""Try the iPad page on this computer, with a pretend board behind it.

    python tools/mock_board.py            then open http://localhost:8765

Serves app/www the way the board does (gzipped files, the same addresses) and
answers the page's messages (/s?...) like a board with a hub attached: a moving
muscle signal, motors B to F fitted, positions that follow the remote. There is
no WebSocket, so the page uses its fallback and shows "Connected (slow)".
/log shows the last messages the page sent, to check what it asks the board.
"""
import math
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WWW = os.path.join(ROOT, "app", "www")
PORT = 8765
FILES = {"/": ("index.html.gz", "text/html"), "/app.js": ("app.js.gz", "application/javascript"),
         "/style.css": ("style.css.gz", "text/css"), "/blockly.js": ("blockly.js.gz", "application/javascript"),
         "/figtree.woff2": ("figtree.woff2", "font/woff2"), "/logo.png": ("logo.png", "image/png")}
log = []
pos = [0, 90, 180, 270, 45]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path, _, query = self.path.partition("?")
        if path == "/s":
            log.append(time.strftime("%H:%M:%S ") + query)
            del log[:-40]
            fields = dict(p.split("=", 1) for p in query.split("&") if "=" in p)
            for i, d in enumerate(fields.get("m", "00000")[:5]):
                if d != "0":
                    pos[i] = (pos[i] + (5 if d in "123" else -5)) % 360
            muscle = int(50 + 45 * math.sin(time.time() / 2))
            lines = ["m %d" % muscle, "h %d %s 31" % (1 if fields.get("x") == "1" else 0, fields.get("p", "B"))]
            lines += ["p %s %d" % ("BCDEF"[i], p) for i, p in enumerate(pos)]
            return self.reply("\n".join(lines).encode(), "text/plain")
        if path == "/log":
            return self.reply("\n".join(log).encode(), "text/plain")
        if path.startswith("/media/") and path.endswith(".svg"):
            name, kind = "media/" + path[7:] + ".gz", "image/svg+xml"
        elif path in FILES:
            name, kind = FILES[path]
        else:
            self.send_response(404)
            self.end_headers()
            return
        with open(os.path.join(WWW, name), "rb") as f:
            self.reply(f.read(), kind, gz=name.endswith(".gz"))

    def reply(self, body, kind, gz=False):
        self.send_response(200)
        self.send_header("Content-Type", kind)
        if gz:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print("Pretend board: http://localhost:%d  (Ctrl+C to stop)" % PORT)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
