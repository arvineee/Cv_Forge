"""
Build the site icon set from app/static/logo.png (the full logo).

Writes into app/static/:
  favicon.ico          real multi-size icon (16-256 px), square, shield emblem
  icon-192.png, icon-512.png, apple-touch-icon.png (180)
  og-default.jpg       1200x630 social-share image (full logo)

Run from the project root:  python tools/build_icons.py
The emblem crop box is in logo.png pixel coordinates; adjust EMBLEM_BOX if
you ever change the logo.
"""
import os
from PIL import Image

STATIC = os.path.join(os.path.dirname(__file__), "..", "app", "static")
LOGO = os.path.join(STATIC, "logo.png")
EMBLEM_BOX = (152, 170, 572, 590)  # square around the shield, in 1408x768 logo coords


def main():
    logo = Image.open(LOGO).convert("RGB")
    emblem = logo.crop(EMBLEM_BOX)
    emblem.resize((256, 256), Image.LANCZOS).save(
        os.path.join(STATIC, "favicon.ico"), format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    for name, size in (("icon-192.png", 192), ("icon-512.png", 512), ("apple-touch-icon.png", 180)):
        emblem.resize((size, size), Image.LANCZOS).save(os.path.join(STATIC, name), optimize=True)

    # 1200x630: full logo, cropped to the share-card ratio around its centre
    w, h = logo.size
    target = 1200 / 630
    if int(h * target) <= w:
        new_w = int(h * target)
        box = ((w - new_w) // 2, 0, (w - new_w) // 2 + new_w, h)
    else:  # logo is narrower than the card ratio: trim top and bottom instead
        new_h = int(w / target)
        box = (0, (h - new_h) // 2, w, (h - new_h) // 2 + new_h)
    og = logo.crop(box).resize((1200, 630), Image.LANCZOS)
    og.save(os.path.join(STATIC, "og-default.jpg"), quality=85, optimize=True)


if __name__ == "__main__":
    main()
