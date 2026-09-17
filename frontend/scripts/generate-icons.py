#!/usr/bin/env python3
"""Render the raster icons from app/icon.svg.

app/icon.svg is the source of truth for the mark. This derives favicon.ico and
apple-icon.png from the same geometry rather than from a second drawing, so the
three files cannot quietly disagree about what the logo is.

Rerun after editing icon.svg:

    python3 scripts/generate-icons.py

Needs Pillow (pip install Pillow). It is not a build step — the outputs are
committed, because Vercel's build image has no Python.
"""

import re
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    sys.exit("Pillow is required: pip install Pillow")

APP = Path(__file__).resolve().parent.parent / "app"

# Matches the share cards' ground, so the tab icon and the link preview read as
# the same object.
BG = (28, 27, 26, 255)      # #1c1b1a
INK = (244, 243, 241, 255)  # #f4f3f1

VIEWBOX = 32.0


def geometry():
    """Pull the path, the terminal dot and the stroke width out of icon.svg."""
    svg = (APP / "icon.svg").read_text()

    d = re.search(r'\sd="([^"]+)"', svg)
    circle = re.search(r'<circle[^>]*cx="([\d.]+)"[^>]*cy="([\d.]+)"[^>]*r="([\d.]+)"', svg)
    stroke = re.search(r'stroke-width="([\d.]+)"', svg)
    if not (d and circle and stroke):
        sys.exit("icon.svg no longer has the shape this script expects")

    nums = [float(n) for n in re.findall(r"-?[\d.]+", d.group(1))]
    path = list(zip(nums[0::2], nums[1::2]))
    cx, cy, r = (float(g) for g in circle.groups())
    return path, (cx, cy), r, float(stroke.group(1))


PATH, DOT, DOT_R, STROKE = geometry()


def tile(px, radius_frac=0.0, scale=0.80):
    """The mark on a tile. radius_frac 0 leaves it square for iOS to mask."""
    ss = 8  # supersample, then downscale — Pillow has no antialiased drawing
    n = px * ss
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if radius_frac:
        draw.rounded_rectangle([0, 0, n - 1, n - 1], radius=int(n * radius_frac), fill=BG)
    else:
        draw.rectangle([0, 0, n, n], fill=BG)

    unit = n * scale / VIEWBOX
    offset = (n - VIEWBOX * unit) / 2.0
    place = lambda p: (offset + p[0] * unit, offset + p[1] * unit)

    width = max(1, int(STROKE * unit))
    points = [place(p) for p in PATH]
    draw.line(points, fill=INK, width=width, joint="curve")
    for x, y in points:  # the round caps and joins Pillow will not draw itself
        rad = width / 2.0
        draw.ellipse([x - rad, y - rad, x + rad, y + rad], fill=INK)

    cx, cy = place(DOT)
    rad = DOT_R * unit
    draw.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=INK)

    return img.resize((px, px), Image.LANCZOS)


def main():
    ico = APP / "favicon.ico"
    tile(256, radius_frac=0.22).save(
        ico, format="ICO", sizes=[(s, s) for s in (16, 32, 48, 64, 128, 256)]
    )
    apple = APP / "apple-icon.png"
    tile(180, radius_frac=0.0, scale=0.72).save(apple)
    for path in (ico, apple):
        print(f"wrote {path.relative_to(APP.parent)}")


if __name__ == "__main__":
    main()
