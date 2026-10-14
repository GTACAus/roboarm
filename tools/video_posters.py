#!/usr/bin/env python3
"""Stop videos downloading until they are played, and give each one a poster picture.

    python tools/video_posters.py          (from the repo root; needs Chrome or Edge)

For every <video> on a top-level page whose file exists and that has no poster yet: grabs a frame a second in
(with headless Chrome, as a small .webp named <video>-poster.webp), sets poster= to it and preload="none".
Then a page opens without fetching any video; the video downloads only when someone presses play.
Videos that have not been recorded yet (missing files) are left alone: their pages show a picture instead.
"""
import glob
import http.server
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8767
BROWSERS = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "google-chrome", "chromium"]
finished = threading.Event()

GRAB = """<!doctype html><meta charset="utf-8"><body><script>
const videos = %s;
(async () => {
  for (const name of videos) {
    const v = document.createElement('video'); v.muted = true; v.preload = 'auto'; v.src = '/' + name;
    await new Promise((ok, no) => { v.onloadedmetadata = ok; v.onerror = no; }).catch(() => null);
    v.currentTime = Math.min(1, (v.duration || 2) / 3);
    await new Promise(ok => { v.onseeked = ok; setTimeout(ok, 8000); });
    const w = Math.min(960, v.videoWidth || 960), c = document.createElement('canvas');
    c.width = w; c.height = Math.round(w * (v.videoHeight || 540) / (v.videoWidth || 960));
    c.getContext('2d').drawImage(v, 0, 0, c.width, c.height);
    const blob = await new Promise(r => c.toBlob(r, 'image/webp', 0.7));
    await fetch('/save/' + name.replace(/\\.mp4$/, '-poster.webp'), { method: 'POST', body: blob });
  }
  await fetch('/done', { method: 'POST' });
})();
</script>"""


class Handler(http.server.SimpleHTTPRequestHandler):
    page = ""

    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/grab.html"):
            body = self.page.encode()
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path == "/done":
            finished.set()
        elif self.path.startswith("/save/") and self.path.endswith("-poster.webp"):
            name = os.path.basename(self.path)
            open(os.path.join(ROOT, name), "wb").write(body)
            print(f"  {name}: {len(body) / 1e3:.0f} KB")
        self.send_response(204); self.end_headers()


def main():
    os.chdir(ROOT)
    pages, need = {}, set()
    for page in sorted(glob.glob("*.html")):
        s = open(page, encoding="utf-8").read()
        pages[page] = s
        for m in re.finditer(r"<video\b[^>]*>.*?</video>", s, re.S):
            src = re.search(r'src="([^"]+\.mp4)"', m.group(0))
            if src and os.path.exists(src.group(1)) and "poster=" not in m.group(0)[:m.group(0).index(">")]:
                need.add(src.group(1))
    need = sorted(n for n in need if not os.path.exists(n[:-4] + "-poster.webp"))
    if need:
        Handler.page = GRAB % json.dumps(need)
        server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        exe = next(b for b in BROWSERS if os.path.isfile(b) or shutil.which(b))
        profile = tempfile.mkdtemp(prefix="posters-")
        proc = subprocess.Popen([exe, "--headless=new", "--autoplay-policy=no-user-gesture-required", "--no-first-run",
                                 "--user-data-dir=" + profile, f"http://127.0.0.1:{PORT}/grab.html"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        finished.wait(600)
        proc.terminate(); proc.wait(); server.shutdown()
        shutil.rmtree(profile, ignore_errors=True)
    # poster + preload="none" on each video with a file and no poster yet
    for page, s in pages.items():
        def fix(m):
            tag = m.group(0)
            src = re.search(r'src="([^"]+\.mp4)"', m.group(0) + m.string[m.end():m.end() + 400])
            if not src or not os.path.exists(src.group(1)) or "poster=" in tag:
                return tag
            poster = src.group(1)[:-4] + "-poster.webp"
            if not os.path.exists(poster):
                return tag
            tag = re.sub(r'\s*preload="[^"]*"', "", tag)
            return tag[:-1].rstrip() + f' preload="none" poster="{poster}">'
        new = re.sub(r"<video\b[^>]*>", fix, s)
        if new != s:
            open(page, "w", encoding="utf-8", newline="").write(new)
            print(f"updated {page}")


if __name__ == "__main__":
    main()
