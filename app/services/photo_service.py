"""
CVForge AI - Profile photo handling for CVs.

Privacy and safety choices:
- The file's real format is checked by Pillow, not the filename or extension.
- Only JPEG and PNG are accepted, with a size cap and a pixel cap (guards
  against decompression bombs).
- Every photo is re-encoded as a square JPEG. This strips EXIF and other
  metadata, such as GPS location.
- Stored under a random name, never the user's filename.

No Flask imports here, so this module can be tested on its own.
"""
import io
import os
import secrets

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 5 * 1024 * 1024          # 5 MB upload cap
MAX_PIXELS = 6000 * 6000             # reject absurdly large images
OUTPUT_SIZE = 400                    # square side length, px
ALLOWED_FORMATS = {"JPEG", "PNG"}


class PhotoRejected(Exception):
    """Raised with a user-facing message when a photo can't be used."""


def process_photo(stream, dest_dir: str) -> str:
    """
    Validate, crop, and re-encode an uploaded photo into dest_dir.
    Returns the stored filename (not the full path).
    """
    raw = stream.read(MAX_BYTES + 1)
    if not raw:
        raise PhotoRejected("The file is empty.")
    if len(raw) > MAX_BYTES:
        raise PhotoRejected("Photo is too large. Please use one under 5 MB.")

    try:
        probe = Image.open(io.BytesIO(raw))
        fmt = probe.format
        width, height = probe.size
        probe.verify()  # checks structure without decoding everything
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise PhotoRejected("That file isn't a valid image. Please upload a JPEG or PNG.")

    if fmt not in ALLOWED_FORMATS:
        raise PhotoRejected("Please upload a JPEG or PNG photo.")
    if width * height > MAX_PIXELS:
        raise PhotoRejected("That image is too large. Please use a smaller photo.")

    img = Image.open(io.BytesIO(raw))
    img = ImageOps.exif_transpose(img).convert("RGB")

    side = min(img.size)
    left = (img.width - side) // 2
    top = (img.height - side) // 2
    img = img.crop((left, top, left + side, top + side))
    img = img.resize((OUTPUT_SIZE, OUTPUT_SIZE), Image.LANCZOS)

    os.makedirs(dest_dir, exist_ok=True)
    filename = f"{secrets.token_hex(16)}.jpg"
    img.save(os.path.join(dest_dir, filename), "JPEG", quality=88, optimize=True)
    return filename


def delete_photo(dest_dir: str, filename: str) -> None:
    """Remove a stored photo. Ignores files that are already gone."""
    if not filename or os.path.basename(filename) != filename:
        return  # refuse anything that isn't a bare filename
    try:
        os.remove(os.path.join(dest_dir, filename))
    except FileNotFoundError:
        pass


def circle_png(path: str, size: int = 400) -> io.BytesIO:
    """Return a PNG of the photo cropped to a circle, with a transparent surround."""
    img = Image.open(path).convert("RGB").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size * 4, size * 4), 0)
    from PIL import ImageDraw
    ImageDraw.Draw(mask).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    mask = mask.resize((size, size), Image.LANCZOS)
    out = img.convert("RGBA")
    out.putalpha(mask)
    buf = io.BytesIO()
    out.save(buf, "PNG")
    buf.seek(0)
    return buf
