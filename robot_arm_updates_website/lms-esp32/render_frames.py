#!/usr/bin/env python3
"""Render the step players' frames from the 3D pages, so the instruction cards show light images instead of
a live 3D model.

    python render_frames.py            -> frames/wiring/<1-3>/*.webp + manifest.js (from wiring-steps-3d.html, one folder per cable colour set)
                                          frames/hub/*.webp + manifest.js         (from hub-buttons-3d.html)
    python render_frames.py hub        -> just one of them

Each 3D page, opened with ?render, draws every step from 19 angles (and the moves between steps) and posts
the images here. Needs Chrome or Edge, and the internet (three.js comes from a CDN). Run it again after a
model or a step changes.
"""
import http.server
import os
import shutil
import subprocess
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8766
PAGES = {"wiring": "wiring-steps-3d.html", "hub": "hub-buttons-3d.html"}
BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "google-chrome", "chromium", "chromium-browser",
]

finished = threading.Event()
saved = []


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=HERE, **k)

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path == "/done":
            finished.set()
        elif self.path.startswith("/save/frames/"):
            rel = os.path.normpath(self.path[len("/save/"):])
            dest = os.path.join(HERE, rel)
            if not dest.startswith(os.path.join(HERE, "frames") + os.sep):
                self.send_response(403); self.end_headers(); return
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(body)
            saved.append(len(body))
        self.send_response(204)
        self.end_headers()


def browser():
    for b in BROWSERS:
        if os.path.isfile(b) or shutil.which(b):
            return b
    sys.exit("Chrome or Edge not found")


def render(name):
    finished.clear(); saved.clear()
    out = os.path.join(HERE, "frames", name)
    shutil.rmtree(out, ignore_errors=True)
    profile = tempfile.mkdtemp(prefix="render-")
    url = "http://127.0.0.1:%d/%s?render" % (PORT, PAGES[name])
    proc = subprocess.Popen([browser(), "--headless=new", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
                             "--user-data-dir=" + profile, "--no-first-run", "--window-size=1000,800", url],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ok = finished.wait(900)
    proc.terminate(); proc.wait()
    shutil.rmtree(profile, ignore_errors=True)
    if not ok:
        sys.exit("%s: timed out after %d frames" % (name, len(saved)))
    print("%-7s %4d files  %7.0f KB" % (name, len(saved), sum(saved) / 1024))


if __name__ == "__main__":
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    for n in sys.argv[1:] or list(PAGES):
        render(n)
    server.shutdown()
