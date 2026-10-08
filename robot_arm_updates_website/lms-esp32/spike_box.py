#!/usr/bin/env python3
"""The LEGO Education SPIKE Prime (45678) storage box: the yellow tub and its white lid, without
the sorting trays or stickers.

    python3 spike_box.py      -> out/spike-box-tub.glb, out/spike-box-lid.glb

LEGO gives the box as 41.3 x 30.3 x 15.5 cm. The shape follows product photos: a tub tapering in
toward its foot, a wide rolled rim with grab handles on the two short ends, and a white lid that
drops inside the rim, its top a flat border round a raised panel with a shallow outlined centre.
Wall thicknesses and the taper are estimates.

Frame: metres, y up, the tub's footprint centred on the origin, its foot on y = 0; the long side
runs along x. The lid is written in place, resting on the rim.
"""
import math
import os

import glb

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

YELLOW = (0.98, 0.79, 0.02, 1)          # LEGO Education box yellow
WHITE = (0.95, 0.95, 0.93, 1)           # the lid
N = 160                                 # points round each loop
WALL = 2.5                              # mm

# heights (mm)
FOOT, RIM_UNDER, RIM_TOP = 8.0, 136.0, 148.0
LID_EDGE, LID_BORDER, LID_PANEL = 139.0, 149.5, 155.0     # lid: bottom of its edge, border, raised panel


def loop(a, b, y, handle=0.0, lift=0.0, n=8):
    """A rounded rectangle (superellipse, exponent n) of half-sizes a (x) and b (z) at height y.
    `handle` pushes the middle of each short end out by that much, for the rim's grab handles, and
    `lift` raises it there, so the handles arch up a little."""
    pts = []
    for i in range(N):
        t = 2 * math.pi * i / N
        c, s = math.cos(t), math.sin(t)
        x = a * math.copysign(abs(c) ** (2 / n), c)
        z = b * math.copysign(abs(s) ** (2 / n), s)
        if handle:
            k = max(0.0, 1 - (z / 80.0) ** 2) ** 1.5            # smooth bump over |z| < 80 mm
            x += math.copysign(handle * k, x)
            pts.append((x, y + lift * k, z))
            continue
        pts.append((x, y, z))
    return pts


def band(l0, l1):
    """Quads between two loops of the same point count."""
    out = []
    for i in range(N):
        j = (i + 1) % N
        out += [(l0[i], l0[j], l1[j]), (l0[i], l1[j], l1[i])]
    return out


def cap(l, y):
    """Fan a loop to its centre (a flat floor or lid panel)."""
    c = (0.0, y, 0.0)
    return [(c, l[(i + 1) % N], l[i]) for i in range(N)]


def strip(*loops):
    out = []
    for l0, l1 in zip(loops, loops[1:]):
        out += band(l0, l1)
    return out


def tub():
    """The grab handles are the rim pushed out 18 mm at each short end and arched up 3 mm, with a
    deeper lip hanging from their outer edge and finger room between it and the wall."""
    H, L = 18.0, 3.0                                          # handle reach past the rim, and rise
    outer = [loop(170, 123, 0),                               # foot
             loop(170, 123, FOOT),
             loop(176, 129, FOOT),                            # body starts just outside the foot
             loop(188, 140.5, RIM_UNDER - 6),                 # wall, tapering out
             loop(188, 140.5, RIM_UNDER),
             loop(188.5, 151.5, RIM_UNDER, H),                # rim underside, out over the handles
             loop(189, 151.5, RIM_UNDER, H, 0.0),
             loop(188.5, 151.5, RIM_UNDER - 4, H + 0.5),      # handle lip hangs a little lower
             loop(188.5, 151.5, RIM_TOP, H, L),               # rim edge
             loop(186.5, 149.5, RIM_TOP + 1.2, H * 0.92, L),  # rolled top of the rim
             loop(181.5, 134, RIM_TOP)]                       # rim's inner edge: the lid drops in here
    inner = [outer[-1],
             loop(181.5, 134, LID_EDGE - 1.5),                # ledge the lid rests on
             loop(178.5, 131, LID_EDGE - 1.5),
             loop(176 - WALL, 129 - WALL, FOOT + WALL),       # inside of the wall down to the floor
             ]
    tris = strip(*outer) + strip(*inner) + cap(inner[-1], FOOT + WALL) + cap(outer[0], 0)
    return tris


def lid():
    """Sits inside the rim on its ledge: a flat border just proud of the rim, a sloped step up to
    the raised panel, and a shallow outlined rectangle in the middle of the panel."""
    G = 0.7                                                   # depth of the centre outline groove
    outer = [loop(180.5, 133, LID_EDGE),                      # edge, inside the rim
             loop(180.5, 133, LID_BORDER - 0.6),
             loop(179.5, 132, LID_BORDER),
             loop(166, 118.5, LID_BORDER),                    # flat border
             loop(160, 112.5, LID_PANEL),                     # step up to the raised panel
             loop(124, 80, LID_PANEL),                        # outlined centre
             loop(123, 79, LID_PANEL - G),
             loop(121, 77, LID_PANEL - G),
             loop(120, 76, LID_PANEL)]
    inner = [loop(180.5 - WALL, 133 - WALL, LID_EDGE),
             loop(180.5 - WALL, 133 - WALL, LID_BORDER - WALL)]
    tris = strip(*outer) + cap(outer[-1], LID_PANEL)
    tris += band(outer[0], inner[0]) + strip(*inner) + cap(inner[-1], LID_BORDER - WALL)
    return tris


def metres(tris):
    return [tuple((x / 1000, y / 1000, z / 1000) for x, y, z in t) for t in tris]


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for name, fn, colour in (("spike-box-tub", tub, YELLOW), ("spike-box-lid", lid, WHITE)):
        tris = metres(fn())
        glb.write_glb(os.path.join(OUT, name + ".glb"), [(name, colour, tris)], "lms-esp32 spike_box.py")
        xs = [p[0] for t in tris for p in t]; ys = [p[1] for t in tris for p in t]; zs = [p[2] for t in tris for p in t]
        print(f"wrote out/{name}.glb: {len(tris)} triangles, "
              f"{(max(xs) - min(xs)) * 1000:.0f} x {(max(zs) - min(zs)) * 1000:.0f} mm, {min(ys) * 1000:.0f}-{max(ys) * 1000:.0f} mm up")
