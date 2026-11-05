"""
Photo upload tests. Flask-free: loads photo_service by file path.
"""
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import types
import unittest

from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_module_names = ("app", "app.services", "app.services.photo_service",
                 "app.services.pdf_service")
_original_modules = {name: sys.modules.get(name) for name in _module_names}


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


photo = _load("photo_service", "app/services/photo_service.py")

# Make `from app.services.photo_service import ...` work inside pdf_service
# without importing the full Flask app.
_pkg = types.ModuleType("app"); _pkg.__path__ = []
_svc = types.ModuleType("app.services"); _svc.__path__ = []
sys.modules.setdefault("app", _pkg)
sys.modules.setdefault("app.services", _svc)
sys.modules["app.services.photo_service"] = photo
pdf = _load("pdf_service", "app/services/pdf_service.py")
for _name, _module in _original_modules.items():
    if _module is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _module


def _jpeg_bytes(size=(1200, 800), exif=True):
    img = Image.new("RGB", size, (200, 120, 90))
    buf = io.BytesIO()
    kwargs = {}
    if exif:
        ex = Image.Exif()
        ex[0x010F] = "TestCameraMake"  # a metadata tag we expect to be stripped
        kwargs["exif"] = ex.tobytes()
    img.save(buf, "JPEG", **kwargs)
    return buf.getvalue()


class ProcessPhoto(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)

    def test_jpeg_is_cropped_to_square_and_resized(self):
        name = photo.process_photo(io.BytesIO(_jpeg_bytes((1200, 800))), self.dir)
        with Image.open(os.path.join(self.dir, name)) as out:
            self.assertEqual(out.format, "JPEG")
            self.assertEqual(out.size, (photo.OUTPUT_SIZE, photo.OUTPUT_SIZE))

    def test_metadata_is_stripped(self):
        src = _jpeg_bytes(exif=True)
        self.assertIn(b"TestCameraMake", src)  # sanity: the source really has it
        name = photo.process_photo(io.BytesIO(src), self.dir)
        with open(os.path.join(self.dir, name), "rb") as f:
            self.assertNotIn(b"TestCameraMake", f.read())

    def test_png_is_accepted(self):
        buf = io.BytesIO()
        Image.new("RGBA", (300, 300), (1, 2, 3, 255)).save(buf, "PNG")
        name = photo.process_photo(io.BytesIO(buf.getvalue()), self.dir)
        self.assertTrue(name.endswith(".jpg"))

    def test_non_image_bytes_rejected(self):
        with self.assertRaises(photo.PhotoRejected):
            photo.process_photo(io.BytesIO(b"%PDF-1.4 not an image"), self.dir)

    def test_gif_rejected_even_though_it_is_an_image(self):
        buf = io.BytesIO()
        Image.new("RGB", (50, 50)).save(buf, "GIF")
        with self.assertRaises(photo.PhotoRejected) as ctx:
            photo.process_photo(io.BytesIO(buf.getvalue()), self.dir)
        self.assertIn("JPEG or PNG", str(ctx.exception))

    def test_empty_upload_rejected(self):
        with self.assertRaises(photo.PhotoRejected):
            photo.process_photo(io.BytesIO(b""), self.dir)

    def test_oversize_upload_rejected(self):
        original = photo.MAX_BYTES
        photo.MAX_BYTES = 100
        self.addCleanup(setattr, photo, "MAX_BYTES", original)
        with self.assertRaises(photo.PhotoRejected):
            photo.process_photo(io.BytesIO(_jpeg_bytes()), self.dir)

    def test_huge_pixel_count_rejected(self):
        original = photo.MAX_PIXELS
        photo.MAX_PIXELS = 1000
        self.addCleanup(setattr, photo, "MAX_PIXELS", original)
        with self.assertRaises(photo.PhotoRejected):
            photo.process_photo(io.BytesIO(_jpeg_bytes((200, 200))), self.dir)


class DeletePhoto(unittest.TestCase):
    def test_path_traversal_is_refused(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True)
        outside = os.path.join(os.path.dirname(d), "keep-me.txt")
        with open(outside, "w") as f:
            f.write("x")
        self.addCleanup(lambda: os.path.exists(outside) and os.remove(outside))
        photo.delete_photo(d, "../keep-me.txt")
        self.assertTrue(os.path.exists(outside))

    def test_missing_file_is_ignored(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True)
        photo.delete_photo(d, "does-not-exist.jpg")  # must not raise


class CirclePhoto(unittest.TestCase):
    def test_corners_transparent_centre_opaque(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True)
        src = os.path.join(d, "src.jpg")
        with open(src, "wb") as f:
            f.write(_jpeg_bytes((400, 400), exif=False))
        with Image.open(photo.circle_png(src)) as opened:
            out = opened.convert("RGBA")
        self.assertEqual(out.getpixel((2, 2))[3], 0)                 # corner transparent
        self.assertEqual(out.getpixel((200, 200))[3], 255)           # centre opaque


class PdfWithPhoto(unittest.TestCase):
    def test_sidebar_pdf_renders_with_photo(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True)
        name = photo.process_photo(io.BytesIO(_jpeg_bytes()), d)
        data = {"personal_info": {"full_name": "Photo Person", "email": "p@example.com"},
                "skills": ["Python"], "photo_file": os.path.join(d, name)}
        path = pdf.PDFService(theme="sidebar-navy").generate_from_dict(data)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        with open(path, "rb") as f:
            self.assertEqual(f.read(5), b"%PDF-")

    def test_header_band_pdf_renders_with_photo(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True)
        name = photo.process_photo(io.BytesIO(_jpeg_bytes()), d)
        data = {"personal_info": {"full_name": "Band Person", "email": "b@example.com"},
                "skills": ["Python"], "photo_file": os.path.join(d, name)}
        path = pdf.PDFService(theme="header-band-burgundy").generate_from_dict(data)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        with open(path, "rb") as f:
            self.assertEqual(f.read(5), b"%PDF-")

    def test_non_sidebar_layout_ignores_photo_without_error(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True)
        name = photo.process_photo(io.BytesIO(_jpeg_bytes()), d)
        data = {"personal_info": {"full_name": "Photo Person"},
                "photo_file": os.path.join(d, name)}
        path = pdf.PDFService(theme="modern").generate_from_dict(data)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        self.assertTrue(os.path.getsize(path) > 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
