#!/usr/bin/env python3
"""Turn the robotic arm's BrickLink Studio model (arm/arm-instructions.ldr, exported as LDraw) into a glTF model
for arm-cables-3d.html, the page the motor-cable steps are rendered from.

    python arm_model.py        -> out/arm.glb + out/arm.json

Parts come from the official LDraw library through ldraw.py. Studio's own part numbers are mapped to LDraw's
(the hub, bb1142c01, is LDraw's 45601, which has the port letters); parts that are not in the library (the hub's
battery, and the custom counterweight cube) are left out, and the cube's place is written to out/arm.json so the
page can draw it. Each primitive's material is named "<role>:<colour>", the role being hub, large (the large motor),
elbow, gripper or arm (everything else), so the page can find and light up a part. Same frame as the other models:
metres, y up.
"""
import json
import os

import ldraw

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "arm", "arm-instructions.ldr")
SWAP = {"bb1142c01.dat": ("45601.dat", 15)}          # Studio name -> (LDraw part, main colour)
SKIP = {"55422c01.dat"}                              # inside the hub (its battery)
CUBE = "mb8246344_2025312_091518.dat"                # the custom counterweight cube


def subfiles(path):
    """The MPD's own files: lower-case name -> its lines."""
    files, cur = {}, None
    for line in open(path, encoding="utf-8", errors="ignore"):
        t = line.split()
        if t[:2] == ["0", "FILE"]:
            cur = files.setdefault(" ".join(t[2:]).lower(), [])
        elif t[:2] == ["0", "NOFILE"]:
            cur = None
        elif cur is not None:
            cur.append(line)
    return files


def role_of(name, m):
    """Which part a placed motor is: the large motor, or the elbow / gripper motor by height (the gripper's is higher)."""
    if name == "54675.dat":
        return "large"
    if name == "54696.dat":
        return "gripper" if m[1][1] < -420 else "elbow"
    return None


def walk(lines, m, colour, files, out, places, role="arm"):
    for line in lines:
        t = line.split()
        if not t or t[0] != "1":
            continue
        c = int(t[1]); c = colour if c == 16 else c
        v = list(map(float, t[2:14]))
        sub = mul(m, ([v[3:6], v[6:9], v[9:12]], v[0:3]))
        name = " ".join(t[14:]).lower()
        if name in files:
            walk(files[name], sub, c, files, out, places, role)
        elif name in SKIP:
            continue
        elif name == CUBE:
            places["cube"] = sub
        elif name in SWAP:
            part, main = SWAP[name]
            tris = []
            ldraw.flatten(part, sub, main, tris)
            out += [("hub", tc, tri) for tc, tri in tris]
            places["hub"] = sub
        else:
            r = role_of(name, sub) or role
            tris = []
            ldraw.flatten(name, sub, c, tris)
            out += [(r, tc, tri) for tc, tri in tris]
            if r != role:
                places[r] = sub


mul = ldraw.mul
I = ([[1, 0, 0], [0, 1, 0], [0, 0, 1]], [0, 0, 0])

if __name__ == "__main__":
    files = subfiles(SRC)
    main = files[next(iter(files))]
    tris, places = [], {}
    walk(main, I, 16, files, tris, places)
    pal = ldraw.colours()
    groups = {}
    for r, c, tri in tris:
        groups.setdefault((r, c), []).append(tuple((x * ldraw.LDU, -y * ldraw.LDU, -z * ldraw.LDU) for x, y, z in tri))
    out = os.path.join(HERE, "out", "arm.glb")
    ldraw.glb.write_glb(out, [(f"{r}:{c}", pal.get(c, (0.5, 0.5, 0.5, 1)), ts) for (r, c), ts in sorted(groups.items())],
                        "lms-esp32 arm_model.py")
    # placements in the page's frame (mm, y up): LDraw (x, y, z) LDU -> (0.4x, -0.4y, -0.4z) mm
    # and a rotation R becomes F R F with F = diag(1, -1, -1)
    F = (1, -1, -1)
    js = {k: {"r": [[F[i] * r[i][j] * F[j] for j in range(3)] for i in range(3)],
              "t": [0.4 * t[0], -0.4 * t[1], -0.4 * t[2]]} for k, (r, t) in places.items()}
    json.dump(js, open(os.path.join(HERE, "out", "arm.json"), "w"), indent=1)
    print(f"wrote out/arm.glb: {len(tris)} triangles; places: {', '.join(sorted(places))}")
