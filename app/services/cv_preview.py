"""
CVForge AI - CV preview renderer (pay-to-download teaser)

Renders the user's *real* CV (same PDF pipeline as the paid download) as a
single image that sells the product without giving the file away:

  * the top of page 1 (name, title, header design, start of the summary)
    stays sharp so the CV looks professional and worth paying for
  * contact details (email, phone, links) are masked in the data BEFORE the
    PDF is generated, so they never exist in the preview image at all
  * everything below the header is pixelated + blurred into the pixels, so
    removing a CSS overlay in dev tools reveals nothing
  * a diagonal watermark is tiled across the whole page

Rasterising uses PyMuPDF when installed, otherwise falls back to poppler's
`pdftoppm`. Results are cached on disk (keyed by resume id + updated_at +
template) so repeat views of the review page cost nothing.
"""
import hashlib
import io
import logging
import math
import os
import re
import shutil
import subprocess
import tempfile
import time

from PIL import Image, ImageDraw, ImageFilter, ImageFont

log = logging.getLogger(__name__)

# Bump to invalidate every cached preview after changing the look below.
PREVIEW_VERSION = "v1"

RENDER_DPI = 110          # ~910px wide for A4: crisp header, unreadable once blurred
SHARP_UNTIL = 0.30        # top 30% of page 1 stays fully sharp
BLUR_FULL_AT = 0.40       # fully blurred from 40% down (soft ramp in between)
WATERMARK_TEXT = "CVFORGE \u00b7 PREVIEW"
CACHE_MAX_AGE_SECONDS = 24 * 3600


class PreviewUnavailable(RuntimeError):
    """Raised when a preview can't be produced; callers should fall back."""


# --------------------------------------------------------------------------
# Masking contact details (done on the data, before the PDF exists)
# --------------------------------------------------------------------------
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _mask_email(v: str) -> str:
    local, _, domain = v.partition("@")
    tld = domain.rsplit(".", 1)[-1] if "." in domain else ""
    return f"{local[:1]}\u2022\u2022\u2022@\u2022\u2022\u2022" + (f".{tld}" if tld else "")


def _mask_phone(v: str) -> str:
    return f"{v.strip()[:4]} \u2022\u2022\u2022 \u2022\u2022\u2022"


def _mask_url(v: str) -> str:
    host = re.sub(r"^https?://(www\.)?", "", v.strip()).split("/")[0]
    return f"{host}/\u2022\u2022\u2022" if host else "\u2022\u2022\u2022"


def _mask_personal_info(info):
    if not isinstance(info, dict):
        return info
    out = {}
    for key, val in info.items():
        k = str(key).lower()
        if not isinstance(val, str) or not val.strip():
            out[key] = val
        elif "email" in k or _EMAIL_RE.match(val.strip()):
            out[key] = _mask_email(val.strip())
        elif any(p in k for p in ("phone", "mobile", "tel", "whatsapp")):
            out[key] = _mask_phone(val)
        elif any(p in k for p in ("linkedin", "website", "github", "portfolio",
                                  "url", "link", "twitter", "behance")):
            out[key] = _mask_url(val)
        elif "address" in k:
            out[key] = "\u2022\u2022\u2022"
        else:
            out[key] = val
    return out


class _MaskedResume:
    """Read-through proxy over a Resume with contact details masked.

    Only used to feed PDFService.generate(); it is never added to the DB
    session, so the real row cannot be modified by accident."""

    def __init__(self, resume):
        self._resume = resume

    def __getattr__(self, name):
        return getattr(self._resume, name)

    @property
    def references(self):
        return None  # reference contacts are private; not needed in a teaser

    def to_dict(self):
        data = self._resume.to_dict()
        data["personal_info"] = _mask_personal_info(data.get("personal_info"))
        return data


# --------------------------------------------------------------------------
# PDF -> image
# --------------------------------------------------------------------------
def _rasterize_first_page(pdf_path: str) -> Image.Image:
    try:
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz  # older PyMuPDF import name
        doc = fitz.open(pdf_path)
        try:
            pix = doc[0].get_pixmap(dpi=RENDER_DPI)
            return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
        finally:
            doc.close()
    except ImportError:
        pass

    if not shutil.which("pdftoppm"):
        raise PreviewUnavailable("Install PyMuPDF (pip install pymupdf) to render previews")
    out_dir = tempfile.mkdtemp(prefix="cvprev_")
    try:
        prefix = os.path.join(out_dir, "p")
        subprocess.run(
            ["pdftoppm", "-png", "-r", str(RENDER_DPI), "-f", "1", "-l", "1",
             "-singlefile", pdf_path, prefix],
            check=True, capture_output=True, timeout=30,
        )
        with Image.open(prefix + ".png") as im:
            return im.convert("RGB")
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


# --------------------------------------------------------------------------
# Image treatment
# --------------------------------------------------------------------------
def _font(size: int):
    for name in ("DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf", "LiberationSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def _blur_lower_page(img: Image.Image) -> Image.Image:
    w, h = img.size
    small = img.resize((max(1, w // 5), max(1, h // 5)), Image.BILINEAR)
    soft = small.resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(4))

    y0, y1 = int(h * SHARP_UNTIL), int(h * BLUR_FULL_AT)
    col = Image.new("L", (1, h), 0)
    px = col.load()
    for y in range(h):
        if y >= y1:
            px[0, y] = 255
        elif y > y0:
            px[0, y] = int(255 * (y - y0) / max(1, y1 - y0))
    mask = col.resize((w, h), Image.NEAREST)
    return Image.composite(soft, img, mask)


def _tile_watermark(img: Image.Image) -> Image.Image:
    w, h = img.size
    d = int(math.hypot(w, h)) + 20
    layer = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    font = _font(max(18, w // 24))
    text_w = draw.textlength(WATERMARK_TEXT, font=font)
    step_x = text_w + w // 7
    step_y = max(60, w // 6)
    row = 0
    y = 0
    while y < d:
        x = -step_x + (step_x / 2 if row % 2 else 0)
        while x < d:
            draw.text((x, y), WATERMARK_TEXT, font=font, fill=(30, 64, 175, 30))
            x += step_x
        y += step_y
        row += 1
    layer = layer.rotate(30, resample=Image.BICUBIC)
    left, top = (d - w) // 2, (d - h) // 2
    layer = layer.crop((left, top, left + w, top + h))
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def _treat(img: Image.Image) -> bytes:
    img = _blur_lower_page(img)
    img = _tile_watermark(img)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80, optimize=True, progressive=True)
    return buf.getvalue()


# --------------------------------------------------------------------------
# Cache + public entry point
# --------------------------------------------------------------------------
def _cache_dir() -> str:
    path = os.path.join(tempfile.gettempdir(), "cvforge_previews")
    os.makedirs(path, exist_ok=True)
    return path


def _prune_cache(folder: str) -> None:
    cutoff = time.time() - CACHE_MAX_AGE_SECONDS
    try:
        for name in os.listdir(folder):
            fp = os.path.join(folder, name)
            if os.path.isfile(fp) and os.path.getmtime(fp) < cutoff:
                os.remove(fp)
    except OSError:
        pass


def build_preview(resume) -> bytes:
    """Return JPEG bytes of the masked/blurred/watermarked first page."""
    stamp = getattr(resume, "updated_at", None)
    key = hashlib.sha1(
        f"{PREVIEW_VERSION}:{resume.id}:{stamp}:{getattr(resume, 'template_id', None)}".encode()
    ).hexdigest()
    folder = _cache_dir()
    cached = os.path.join(folder, f"{key}.jpg")
    if os.path.isfile(cached):
        with open(cached, "rb") as fh:
            return fh.read()

    from app.services.pdf_service import PDFService  # local import: heavy module

    pdf_path = PDFService().generate(_MaskedResume(resume))
    try:
        page = _rasterize_first_page(pdf_path)
    finally:
        try:
            os.remove(pdf_path)
        except OSError:
            pass

    data = _treat(page)
    tmp = cached + f".{os.getpid()}.tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, cached)
    _prune_cache(folder)
    return data
