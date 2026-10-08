"""Build the files that go on the LMS-ESP32 (firmware/www) from the page sources (web/).

    python tools/build.py            gzip the page, prune and bundle Blockly, report sizes
    python tools/build.py --mpy      also compile the firmware to .mpy (needs: pip install mpy-cross==<board's MicroPython version>)

Blockly pruning: only Blockly's core engine is kept. The standard block library, the code generators,
the other languages and the messages for blocks we do not use are left out; our own blocks (web/blocks.js)
are added. Blockly's core itself cannot be made smaller without Blockly's own build tools.
"""
import gzip
import hashlib
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
OUT = os.path.join(ROOT, "firmware", "www")
UNUSED_MESSAGES = ("CONTROLS_", "MATH_", "TEXT_", "LISTS_", "LOGIC_", "COLOUR_")
BUDGET = 400 * 1024          # bytes of page files allowed on the board


def read(path):
    with open(os.path.join(WEB, path), encoding="utf-8") as f:
        return f.read()


def squeeze(text):
    """Safe shrink for our own files: drop leading indentation and empty lines (gzip does the rest)."""
    return "\n".join(line.strip() for line in text.splitlines() if line.strip()) + "\n"


def write_gz(name, data):
    path = os.path.join(OUT, name + ".gz")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    raw = data.encode("utf-8") if isinstance(data, str) else data
    with open(path, "wb") as f:
        f.write(gzip.compress(raw, 9, mtime=0))
    return len(raw), os.path.getsize(path)


def blockly_bundle():
    core = read("vendor/blockly_core.js")
    msgs = read("vendor/blockly_en.js")
    kept = []
    dropped = 0
    for line in msgs.splitlines():
        m = re.match(r'Blockly\.Msg\["([A-Z0-9_]+)"\]', line)
        if m and m.group(1).startswith(UNUSED_MESSAGES):
            dropped += 1
            continue
        kept.append(line)
    print("  Blockly messages: dropped %d for blocks we do not use" % dropped)
    return core + "\n" + "\n".join(kept) + "\n" + squeeze(read("blocks.js"))


def main():
    os.makedirs(OUT, exist_ok=True)
    print("Building", os.path.relpath(OUT, ROOT))
    bundle = blockly_bundle()
    version = hashlib.md5(bundle.encode("utf-8")).hexdigest()[:8]    # new blocks -> new address -> iPads fetch it again
    rows = [("index.html", squeeze(read("index.html"))),
            ("landing.html", squeeze(read("landing.html"))),
            ("style.css", squeeze(re.sub(r"/\*.*?\*/", "", read("style.css"), flags=re.S))),
            ("app.js", squeeze(read("app.js").replace("__BLOCKLY_VERSION__", version))),
            ("blockly.js", bundle)]
    print("  Blockly bundle version", version)
    for svg in sorted(os.listdir(os.path.join(WEB, "vendor", "media"))):
        rows.append(("media/" + svg, read("vendor/media/" + svg)))
    total = 0
    print("  %-26s %10s %10s" % ("file", "size", "gzipped"))
    for src, name in (("vendor/figtree-latin.woff2", "figtree.woff2"), ("gtac-logo.png", "logo.png")):
        with open(os.path.join(WEB, src), "rb") as f:
            data = f.read()
        with open(os.path.join(OUT, name), "wb") as f:
            f.write(data)
        total += len(data)
        print("  %-26s %10d %10s" % (name, len(data), "as is"))
    for name, data in rows:
        raw, gz = write_gz(name, data)
        total += gz
        print("  %-26s %10d %10d" % (name, raw, gz))
    print("  %-26s %10s %10d  (budget %d)" % ("total on the board", "", total, BUDGET))
    if total > BUDGET:
        sys.exit("Too big for the board")

    if "--mpy" in sys.argv:
        fw = os.path.join(ROOT, "firmware")
        for py in ("lump.py", "emg.py", "web.py"):           # main.py must stay .py
            subprocess.check_call([sys.executable, "-m", "mpy_cross", os.path.join(fw, py)])
            print("  compiled", py, "->", py[:-3] + ".mpy")


if __name__ == "__main__":
    main()
