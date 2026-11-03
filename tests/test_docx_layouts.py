"""
Word output tests. Flask-free: loads the services by file path.
The LibreOffice test is skipped when soffice isn't installed.
"""
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

from docx import Document
from docx.oxml.ns import qn
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


_pkg = types.ModuleType("app"); _pkg.__path__ = []
_svc = types.ModuleType("app.services"); _svc.__path__ = []
sys.modules.setdefault("app", _pkg)
sys.modules.setdefault("app.services", _svc)
sys.modules["app.services.photo_service"] = _load("photo_service", "app/services/photo_service.py")
sys.modules["app.services.pdf_service"] = _load("pdf_service", "app/services/pdf_service.py")
docx_svc = _load("docx_service", "app/services/docx_service.py")

SAMPLE = {
    "personal_info": {"full_name": "Amina W. Otieno", "job_title": "Sales Supervisor",
                      "email": "amina@example.com", "phone": "+254 700 000 000",
                      "location": "Nairobi, Kenya"},
    "professional_summary": "Sales supervisor with five years of experience.",
    "work_experience": [{"job_title": "Sales Supervisor", "company": "Example Retail Ltd",
                         "start_date": "Jan 2022", "end_date": "Present",
                         "achievements": ["Led a team of 6", "Grew sales 32%"]}],
    "education": [{"degree": "BBA Marketing", "institution": "Example University", "year": "2019"}],
    "skills": ["Team leadership", "Inventory control"],
    "languages": ["English", "Swahili"],
}

THEMES = ["modern", "centred", "bands", "sidebar-navy", "sidebar-slate",
          "header-band-burgundy", "header-band-forest", "timeline-teal", "timeline-indigo"]


def _all_text(doc):
    """Text from body paragraphs and from every table cell."""
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                parts += [p.text for p in cell.paragraphs]
    return "\n".join(parts)


def _photo_file(folder):
    buf = io.BytesIO()
    Image.new("RGB", (600, 400), (30, 120, 90)).save(buf, "JPEG")
    path = os.path.join(folder, "photo.jpg")
    with open(path, "wb") as f:
        f.write(buf.getvalue())
    return path


class WordOutput(unittest.TestCase):
    def _generate(self, theme, data=None):
        path = docx_svc.DOCXService(theme=theme).generate_from_dict(data or SAMPLE)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return Document(path)

    def test_every_theme_produces_a_word_file_with_the_name(self):
        for theme in THEMES:
            with self.subTest(theme=theme):
                doc = self._generate(theme)
                self.assertIn("Amina W. Otieno", _all_text(doc))

    def test_sidebar_uses_a_two_column_table_with_shaded_left_cell(self):
        doc = self._generate("sidebar-navy")
        self.assertEqual(len(doc.tables), 1)
        row = doc.tables[0].rows[0]
        self.assertEqual(len(row.cells), 2)
        shd = row.cells[0]._tc.tcPr.find(qn("w:shd"))
        self.assertIsNotNone(shd)
        self.assertEqual(shd.get(qn("w:fill")), "1E3A5F")

    def test_header_band_is_a_shaded_full_width_table(self):
        doc = self._generate("header-band-burgundy")
        self.assertEqual(len(doc.tables), 1)
        shd = doc.tables[0].rows[0].cells[0]._tc.tcPr.find(qn("w:shd"))
        self.assertEqual(shd.get(qn("w:fill")), "7F1D1D")

    def test_timeline_entries_have_left_rules(self):
        doc = self._generate("timeline-teal")
        bordered = [p for p in doc.paragraphs
                    if p._p.pPr is not None and p._p.pPr.find(qn("w:pBdr")) is not None]
        self.assertTrue(len(bordered) >= 3)

    def test_photo_is_embedded_in_sidebar_and_band(self):
        folder = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, folder, True)
        data = dict(SAMPLE, photo_file=_photo_file(folder))
        for theme in ["sidebar-navy", "header-band-burgundy"]:
            with self.subTest(theme=theme):
                doc = self._generate(theme, data)
                self.assertGreaterEqual(len(doc.inline_shapes), 1)

    def test_no_photo_means_no_picture(self):
        doc = self._generate("sidebar-navy")
        self.assertEqual(len(doc.inline_shapes), 0)

    def test_every_table_cell_has_a_paragraph(self):
        for theme in ["sidebar-navy", "header-band-burgundy"]:
            with self.subTest(theme=theme):
                doc = self._generate(theme)
                for table in doc.tables:
                    for row in table.rows:
                        for cell in row.cells:
                            self.assertGreaterEqual(len(cell.paragraphs), 1)

    def test_empty_input_renders(self):
        for theme in THEMES:
            with self.subTest(theme=theme):
                self._generate(theme, {})


@unittest.skipUnless(shutil.which("soffice"), "LibreOffice not installed")
class WordOpensInLibreOffice(unittest.TestCase):
    def test_sidebar_and_timeline_convert_to_pdf(self):
        out_dir = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, out_dir, True)
        for theme in ["sidebar-navy", "timeline-teal"]:
            path = docx_svc.DOCXService(theme=theme).generate_from_dict(SAMPLE)
            self.addCleanup(lambda p=path: os.path.exists(p) and os.remove(p))
            subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", out_dir, path],
                           check=True, capture_output=True, timeout=180)
            pdf_path = os.path.join(out_dir, os.path.basename(path).replace(".docx", ".pdf"))
            with open(pdf_path, "rb") as f:
                self.assertEqual(f.read(5), b"%PDF-")


if __name__ == "__main__":
    unittest.main(verbosity=2)
