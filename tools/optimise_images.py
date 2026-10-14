#!/usr/bin/env python3
"""Make the site's pictures small: a .webp copy of every PNG/JPEG the pages use, and the pages pointed at it.

    python tools/optimise_images.py          (from the repo root)

For each image a top-level page refers to (in src, poster or href, or in a script, such as the LEGO building
steps in lego-instructions/), writes <name>.webp beside it: at most MAX_W pixels wide, lossy WebP at QUALITY.
That is typically 6 to 25 times smaller. The originals stay, for anything else that links to them. Then the
pages' references are switched to the .webp files, and every <img> but the first on a page gets
loading="lazy" (images on cards that are not showing then load only when their card opens).

Run it again after adding or changing a picture; unchanged ones are skipped.
"""
import glob
import os
import re

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_W, QUALITY = 1600, 80
RASTER = r"[\w\-/ .]+?\.(?:png|jpe?g)"


def webp_for(path):
    """Write path's .webp (if missing or older) and return its name."""
    out = os.path.splitext(path)[0] + ".webp"
    if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(path):
        im = Image.open(path)
        clear = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
        im = im.convert("RGBA" if clear else "RGB")
        if im.width > MAX_W:
            im = im.resize((MAX_W, round(im.height * MAX_W / im.width)), Image.LANCZOS)
        im.save(out, "WEBP", quality=QUALITY, method=4)
        print(f"  {os.path.getsize(path) / 1e3:7.0f} KB -> {os.path.getsize(out) / 1e3:6.0f} KB  {os.path.relpath(out, ROOT)}")
    return out


def main():
    os.chdir(ROOT)
    # the LEGO building steps are shown by a script (arm-instructions-NN.png), so convert the whole folder
    for f in sorted(glob.glob("lego-instructions/*.png")):
        webp_for(f)
    for page in sorted(glob.glob("*.html")):
        s = open(page, encoding="utf-8").read()
        new = s

        def swap(m):
            ref = m.group(0)
            q = ref[0]
            name = ref[1:-1]
            if name.startswith(("http:", "https:", "data:")) or not os.path.exists(name):
                return ref
            return q + os.path.relpath(webp_for(name)).replace(os.sep, "/") + q

        new = re.sub(r'(["\'])' + RASTER + r'\1', swap, new)
        new = new.replace("arm-instructions-${String(currentImage).padStart(2, '0')}.png",
                          "arm-instructions-${String(currentImage).padStart(2, '0')}.webp")
        # lazy-load every <img> after the first, unless it already says how to load
        imgs = list(re.finditer(r"<img\b(?![^>]*\bloading=)", new))
        for m in reversed(imgs[1:]):
            new = new[:m.end()] + ' loading="lazy" decoding="async"' + new[m.end():]
        if new != s:
            open(page, "w", encoding="utf-8", newline="").write(new)
            print(f"updated {page}")


if __name__ == "__main__":
    main()
