"""Minimal glTF binary writer shared by the generators: one node, one mesh, one primitive per
material, flat normals, colours given in sRGB and stored linear (as glTF wants)."""
import json
import os
import struct


def _lin(c):
    return (c / 12.92) if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def write_glb(path, groups, generator="lms-esp32"):
    """groups: [(name, (r, g, b, a) sRGB 0..1, [(p0, p1, p2), ...] in metres, y up)]."""
    blob, views, accessors, materials, prims = bytearray(), [], [], [], []
    for name, (r, g, b, a), tris in groups:
        if not tris:
            continue
        pos, nrm = [], []
        for p in tris:
            u = [p[1][k] - p[0][k] for k in range(3)]
            w = [p[2][k] - p[0][k] for k in range(3)]
            n = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
            ln = sum(q * q for q in n) ** 0.5 or 1
            n = tuple(q / ln for q in n)
            for q in p:
                pos.append(q)
                nrm.append(n)
        for data, bounds in ((pos, True), (nrm, False)):
            raw = b"".join(struct.pack("<3f", *q) for q in data)
            views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(raw), "target": 34962})
            acc = {"bufferView": len(views) - 1, "componentType": 5126, "count": len(data), "type": "VEC3"}
            if bounds:
                acc["min"] = [min(q[k] for q in data) for k in range(3)]
                acc["max"] = [max(q[k] for q in data) for k in range(3)]
            accessors.append(acc)
            blob += raw
        mat = {"name": name, "doubleSided": True,
               "pbrMetallicRoughness": {"baseColorFactor": [_lin(r), _lin(g), _lin(b), a], "metallicFactor": 0, "roughnessFactor": 0.6}}
        if a < 1:
            mat["alphaMode"] = "BLEND"
        materials.append(mat)
        prims.append({"attributes": {"POSITION": len(accessors) - 2, "NORMAL": len(accessors) - 1}, "material": len(materials) - 1})
    gltf = {"asset": {"version": "2.0", "generator": generator}, "scene": 0, "scenes": [{"nodes": [0]}],
            "nodes": [{"mesh": 0, "name": os.path.splitext(os.path.basename(path))[0]}],
            "meshes": [{"primitives": prims}], "materials": materials,
            "buffers": [{"byteLength": len(blob)}], "bufferViews": views, "accessors": accessors}
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    blob += b"\0" * (-len(blob) % 4)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<3I", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(blob)))
        fh.write(struct.pack("<2I", len(js), 0x4E4F534A) + js)
        fh.write(struct.pack("<2I", len(blob), 0x004E4942) + bytes(blob))
