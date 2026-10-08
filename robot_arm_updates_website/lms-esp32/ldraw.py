#!/usr/bin/env python3
"""Turn an LDraw part into a glTF model for the assembly viewer.

    LDRAWDIR=~/ldraw python3 ldraw.py      -> out/spike-hub.glb   (45601, the SPIKE Prime large hub)
    python3 ldraw.py PART.dat OUT.glb [MAIN_COLOUR]

Fetches the part and every subpart and primitive it uses from the official LDraw library
(library.ldraw.org, CC BY 4.0) into ldraw/, flattens it to triangles, and writes one mesh per
colour. The hub is Philippe Hurbain's model, prints included (port letters, arrows, Bluetooth).

Output frame matches the KiCad exports: metres, y up. LDraw units are 0.4 mm with y pointing
down, so (x, y, z) LDU -> (0.4x, -0.4y, -0.4z) mm, a half turn about x.
"""
import os
import sys
import urllib.request

import glb

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "ldraw")
LIB = "https://library.ldraw.org/library/official/"
LDU = 0.0004                      # metres per LDraw unit
WHITE = 15                        # the hub's main colour (16 in the file means "the part's colour")


def fetch(name):
    """Path of an LDraw file in the cache. On first use it is copied from a local LDraw library
    ($LDRAWDIR, e.g. the unzipped complete.zip) or, failing that, downloaded file by file
    (the server rate-limits that, so prefer LDRAWDIR)."""
    name = name.lower().replace("\\", "/")
    for sub in ("parts/", "p/"):
        path = os.path.join(CACHE, sub, name)
        if os.path.exists(path):
            return path
    lib = os.environ.get("LDRAWDIR")
    for sub in ("parts/", "p/") if lib else ():
        src = os.path.join(lib, sub, name)
        if os.path.exists(src):
            path = os.path.join(CACHE, sub, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "wb").write(open(src, "rb").read())
            return path
    for sub in ("parts/", "p/"):
        try:
            req = urllib.request.Request(LIB + sub + name, headers={"User-Agent": "lms-esp32-models"})
            data = urllib.request.urlopen(req, timeout=30).read()
        except Exception:
            continue
        if data.lstrip().startswith(b"<"):
            continue                  # an HTML error page
        path = os.path.join(CACHE, sub, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "wb").write(data)
        return path
    raise SystemExit(f"LDraw file not found: {name}")


def colours():
    """LDraw colour code -> (r, g, b, a) in sRGB 0..1, from LDConfig.ldr."""
    path = os.path.join(CACHE, "LDConfig.ldr")
    lib = os.environ.get("LDRAWDIR")
    if not os.path.exists(path) and lib:
        os.makedirs(CACHE, exist_ok=True)
        open(path, "wb").write(open(os.path.join(lib, "LDConfig.ldr"), "rb").read())
    if not os.path.exists(path):
        os.makedirs(CACHE, exist_ok=True)
        req = urllib.request.Request(LIB + "LDConfig.ldr", headers={"User-Agent": "lms-esp32-models"})
        open(path, "wb").write(urllib.request.urlopen(req, timeout=30).read())
    out = {}
    for line in open(path, encoding="utf-8", errors="ignore"):
        t = line.split()
        if len(t) > 2 and t[1] == "!COLOUR":
            kv = {t[i]: t[i + 1] for i in range(2, len(t) - 1)}
            v = kv["VALUE"].lstrip("#")
            a = int(kv.get("ALPHA", "255")) / 255
            out[int(kv["CODE"])] = (int(v[0:2], 16) / 255, int(v[2:4], 16) / 255, int(v[4:6], 16) / 255, a)
    return out


def mul(a, b):
    """Compose two affine transforms given as (3x3 rows, translation)."""
    (ra, ta), (rb, tb) = a, b
    r = [[sum(ra[i][k] * rb[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    t = [sum(ra[i][k] * tb[k] for k in range(3)) + ta[i] for i in range(3)]
    return r, t


def apply(m, p):
    r, t = m
    return tuple(sum(r[i][k] * p[k] for k in range(3)) + t[i] for i in range(3))


def flatten(name, m, colour, out, depth=0):
    """Append (colour, (p0, p1, p2)) for every triangle in `name`, transformed by m."""
    if depth > 30:
        return
    for line in open(fetch(name), encoding="utf-8", errors="ignore"):
        t = line.split()
        if not t or t[0] not in ("1", "3", "4"):
            continue
        c = int(t[1])
        c = colour if c == 16 else c
        v = list(map(float, t[2:14] if t[0] == "1" else t[2:2 + 3 * int(t[0])]))
        if t[0] == "1":
            sub = (([v[3:6], v[6:9], v[9:12]], v[0:3]))
            flatten(" ".join(t[14:]), mul(m, sub), c, out, depth + 1)
            continue
        pts = [apply(m, v[i:i + 3]) for i in range(0, len(v), 3)]
        out.append((c, (pts[0], pts[1], pts[2])))
        if t[0] == "4":
            out.append((c, (pts[0], pts[2], pts[3])))


def write_glb(path, tris, palette):
    """One primitive per LDraw colour, converted from LDraw units to metres, y up."""
    groups = {}
    for c, tri in tris:
        groups.setdefault(c, []).append(tuple((x * LDU, -y * LDU, -z * LDU) for x, y, z in tri))
    glb.write_glb(path, [(f"ldraw_{c}", palette.get(c, (0.5, 0.5, 0.5, 1)), ts) for c, ts in sorted(groups.items())],
                  "lms-esp32 ldraw.py")


if __name__ == "__main__":
    part = sys.argv[1] if len(sys.argv) > 1 else "45601.dat"
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "out", "spike-hub.glb")
    main = int(sys.argv[3]) if len(sys.argv) > 3 else WHITE
    tris = []
    flatten(part, ([[1, 0, 0], [0, 1, 0], [0, 0, 1]], [0, 0, 0]), main, tris)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    write_glb(out, tris, colours())
    print(f"wrote {os.path.relpath(out, HERE)}: {len(tris)} triangles, {len({c for c, _ in tris})} colours")
