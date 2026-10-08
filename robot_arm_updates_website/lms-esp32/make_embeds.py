#!/usr/bin/env python3
"""Package the models the step pages use as .js files, so the pages also work when opened straight from disk
(file:///...), where browsers refuse to fetch the .glb/.stl files.

    python3 make_embeds.py      -> out/<model>.js   (gzip + base64, unpacked in the page)

Run it again after ./build.sh changes a model.
"""
import base64
import gzip
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
MODELS = ["lms-esp32.glb", "emg.glb", "case-base.stl", "spike-hub.glb"]

for name in MODELS:
    with open(os.path.join(OUT, name), "rb") as f:
        packed = base64.b64encode(gzip.compress(f.read(), 9, mtime=0)).decode("ascii")
    js = os.path.join(OUT, name.rsplit(".", 1)[0] + ".js")
    with open(js, "w", encoding="ascii", newline="\n") as f:
        f.write("// %s, gzip + base64: made by make_embeds.py, do not edit\n" % name)
        f.write("(window.MODELS = window.MODELS || {})[%r] = %r;\n" % (name, packed))
    print("%-16s -> %-14s %8d bytes" % (name, os.path.basename(js), os.path.getsize(js)))
