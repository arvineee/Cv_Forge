"""
Layout template tests. Loads the PDF service and template catalogue by file
path, so these run without Flask or the database installed.
"""
import importlib.util
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _load(name, rel_path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pdf = _load("pdf_service", "app/services/pdf_service.py")
catalog = _load("template_catalog", "app/services/template_catalog.py")


def _sample(n_jobs=2):
    jobs = [{
        "job_title": f"Role {i}", "company": f"Company {i}", "location": "Nairobi",
        "start_date": "Jan 2020", "end_date": "Dec 2021",
        "achievements": ["Delivered a measurable result", "Led a team of five",
                         "Reduced costs by 12% through process changes"],
    } for i in range(n_jobs)]
    return {
        "personal_info": {"full_name": "Test Person", "job_title": "Analyst",
                          "email": "test@example.com", "phone": "+254 700 000 000",
                          "location": "Nairobi"},
        "professional_summary": "Analyst with a track record of delivering results.",
        "work_experience": jobs,
        "education": [{"degree": "BSc", "institution": "Example University", "year": "2019"}],
        "skills": ["Excel", "SQL", "Reporting"],
        "languages": ["English"],
    }


def _page_count(path):
    with open(path, "rb") as f:
        data = f.read()
    return len(re.findall(rb"/Type\s*/Page\b", data))


class CatalogConsistency(unittest.TestCase):
    def test_every_new_template_has_a_layout(self):
        for t in catalog.LAYOUT_TEMPLATES:
            with self.subTest(slug=t["slug"]):
                self.assertIn(t["slug"], pdf.SLUG_TO_THEME)
                self.assertIn(pdf.SLUG_TO_THEME[t["slug"]], pdf.THEMES)

    def test_new_slugs_are_unique(self):
        slugs = [t["slug"] for t in catalog.LAYOUT_TEMPLATES]
        self.assertEqual(len(slugs), len(set(slugs)))


class PreviewImages(unittest.TestCase):
    """Every template has a gallery preview, so no card is left blank."""
    FOLDER = os.path.join(ROOT, "app", "static", "templates")

    def test_every_template_has_a_preview_png(self):
        for slug in pdf.SLUG_TO_THEME:
            with self.subTest(slug=slug):
                self.assertTrue(os.path.isfile(os.path.join(self.FOLDER, f"{slug}.png")),
                                f"run tools/build_thumbnails.py to create {slug}.png")


class LayoutRendering(unittest.TestCase):
    LAYOUTS = ["modern", "centred", "bands", "sidebar-navy", "sidebar-slate",
               "header-band-burgundy", "header-band-forest",
               "timeline-teal", "timeline-indigo"]

    def _render(self, theme, data):
        path = pdf.PDFService(theme=theme).generate_from_dict(data)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        with open(path, "rb") as f:
            self.assertEqual(f.read(5), b"%PDF-")
        return path

    def test_normal_cv_renders_in_every_layout(self):
        for theme in self.LAYOUTS:
            with self.subTest(theme=theme):
                path = self._render(theme, _sample(2))
                self.assertEqual(_page_count(path), 1)

    def test_long_cv_spans_multiple_pages_in_every_layout(self):
        for theme in self.LAYOUTS:
            with self.subTest(theme=theme):
                path = self._render(theme, _sample(18))
                self.assertGreater(_page_count(path), 1)

    def test_sparse_cv_renders_without_optional_sections(self):
        for theme in self.LAYOUTS:
            with self.subTest(theme=theme):
                self._render(theme, {"personal_info": {"full_name": "Only Name"}})

    def test_many_skills_do_not_crash_sidebar(self):
        data = _sample(2)
        data["skills"] = [f"Skill number {i}" for i in range(60)]
        for theme in ["sidebar-navy", "sidebar-slate"]:
            with self.subTest(theme=theme):
                self._render(theme, data)

    def test_long_unbroken_url_renders_in_sidebar(self):
        data = _sample(2)
        data["personal_info"]["linkedin"] = "https://www.linkedin.com/in/" + "a" * 120
        self._render("sidebar-navy", data)

    def test_empty_input_renders(self):
        for theme in self.LAYOUTS:
            with self.subTest(theme=theme):
                self._render(theme, {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
