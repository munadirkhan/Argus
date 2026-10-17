"""Crop a 1920x1080 UI screenshot into Devpost's 3:2 thumbnail.

Devpost shows the thumbnail small in the project gallery, so the hero crop
(orb + prophecy) reads better there than the whole interface. Both are
produced; pick per use.

    python scripts/make_thumbnail.py [source.png]
"""
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    ROOT, "web", "evidence", "terminal", "terminal-prophecy-1920.png")
OUT = os.path.join(ROOT, "web", "evidence", "thumbnail")

VOID = (5, 4, 7)          # the UI's own background, so bars read as intentional

# Hero crop, 3:2: orb centred with the prophecy under it. Bounds are chosen to
# sit between panels so no panel is sliced mid-border.
HERO = (375, 140, 1050, 700)


def save(img: Image.Image, name: str) -> None:
    path = os.path.join(OUT, name + ".jpg")
    img.resize((1200, 800), Image.LANCZOS).save(path, "JPEG", quality=92, optimize=True)
    print("%-26s 1200x800 (3:2)  %.2f MB" % (name, os.path.getsize(path) / 1e6))


def main() -> None:
    img = Image.open(SRC).convert("RGB")
    if img.size != (1920, 1080):
        print("note: expected 1920x1080, got %dx%d" % img.size)
    os.makedirs(OUT, exist_ok=True)
    w, h = img.size

    # Full interface: pad to 3:2 rather than crop, so nothing is cut off.
    canvas = Image.new("RGB", (w, round(w / 1.5)), VOID)
    canvas.paste(img, (0, (canvas.height - h) // 2))
    save(canvas, "argus-thumbnail-full")

    x, y, cw, ch = HERO
    assert abs(cw / ch - 1.5) < 1e-6, "hero crop is not 3:2"
    save(img.crop((x, y, x + cw, y + ch)), "argus-thumbnail-hero")


if __name__ == "__main__":
    main()
