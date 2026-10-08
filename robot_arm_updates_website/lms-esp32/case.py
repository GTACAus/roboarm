#!/usr/bin/env python3
"""Split GTAC-Science's LMS-ESP32 case (thingiverse.com/thing:7032044, CC BY-SA) into its three
printed parts and move each to where it sits around the board, for the assembly viewer.

    python3 case.py [path/to/case.stl]   -> out/case-base.stl, case-lid.stl, case-button.stl

The STL holds three separate bodies laid out for printing:
  base    x -62.45..-2.45, y -23.25..21.75, z 0..16.55 (60 x 45 mm box, 1 mm side walls, 1.5 mm floor)
  lid     x 2.45..62.45, printed upside down
  button  a 3.2 x 6.6 x 3 mm RST cap (1 mm flange inside, 2 mm plug through the wall window)

Output frame is the viewer's (mm): X = board x, Y = up from the board's underside, Z = board y.
The base's four LEGO holes (48 x 32 mm) line up with the board's, its USB-C and RST windows are in
the end wall at the board's top edge, and the notch in the long wall clears the HUB box header.
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "case", "LMS_ESP32_case_GTAC.stl")
OUT = os.path.join(HERE, "out")

FLOOR = 1.5          # base floor thickness: the board's underside rests on it
CX0, CY0 = -5.95, 20.68   # case (x, y) of board (0, 0): board holes (3.9, 3.9) on case holes (-9.85, 16.78)


def base(p):
    cx, cy, cz = p
    return (CY0 - cy, cz - FLOOR, CX0 - cx)


def lid(p):
    """Flip the lid right way up (180 degrees about x) onto the base's 16.55 mm rim."""
    lx, ly, lz = p
    return base((lx - 64.9, -ly, 16.55 + 1.55 - lz))


def button(p):
    """Turn the cap onto its side in the end wall's RST window (y 4.74..11.35, z 3.29..6.3):
    flange resting on the switch plunger, plug standing 0.6 mm proud of the wall."""
    bx, by, bz = p
    return base((bz - 4.9, by - 15.635 + 8.05, 4.8 - (bx - 16.93)))


def read_stl(path):
    d = open(path, "rb").read()
    n = struct.unpack("<I", d[80:84])[0]
    tris = []
    for i in range(n):
        v = struct.unpack("<12f", d[84 + 50 * i:84 + 50 * i + 48])
        tris.append((v[3:6], v[6:9], v[9:12]))
    return tris


def write_stl(path, tris):
    with open(path, "wb") as fh:
        fh.write(b"LMS-ESP32 case part, from GTAC-Science thing:7032044 (CC BY-SA)".ljust(80, b" "))
        fh.write(struct.pack("<I", len(tris)))
        for a, b_, c in tris:
            u = [b_[k] - a[k] for k in range(3)]
            w = [c[k] - a[k] for k in range(3)]
            n = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
            fh.write(struct.pack("<12fH", *n, *a, *b_, *c, 0))


if __name__ == "__main__":
    tris = read_stl(sys.argv[1] if len(sys.argv) > 1 else SRC)
    parts = {"base": [], "lid": [], "button": []}
    for t in tris:
        x, y, z = t[0]
        if x < 0:
            parts["base"].append([base(p) for p in t])
        elif 15 < x < 19 and 12 < y < 19.5 and z <= 3.05 and all(q[0] < 19 for q in t):
            parts["button"].append([button(p) for p in t])
        else:
            parts["lid"].append([lid(p) for p in t])
    os.makedirs(OUT, exist_ok=True)
    for name, ts in parts.items():
        path = os.path.join(OUT, f"case-{name}.stl")
        write_stl(path, ts)
        lo = [round(min(p[k] for t in ts for p in t), 2) for k in range(3)]
        hi = [round(max(p[k] for t in ts for p in t), 2) for k in range(3)]
        print(f"wrote out/case-{name}.stl  {len(ts)} triangles  {lo} .. {hi}")
