"""SEO keyword coverage that runs without Flask: it reads site_content and the
page templates directly. It pins the same rules tests/test_international.py
checks on rendered pages, so a bad edit fails fast."""
import os
import re
import unittest
from types import SimpleNamespace

from tests._load import load

sc = load("app/services/site_content.py", "site_content_seo_test")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T = os.path.join(ROOT, "app", "templates")

PUBLIC_TEMPLATES = ["landing.html", "pricing.html", "about.html", "billing/plans.html",
                    "templates_gallery/public.html", "guide/index.html", "support/index.html",
                    "auth/register.html", "auth/login.html", "privacy.html", "terms.html"]

ORIGINAL_KEYWORDS = ("online CV builder", "ATS-friendly resume builder", "professional resume builder",
                     "CV builder online", "resume creator", "cover letter generator",
                     "AI CV builder", "resume optimisation tool", "CV writing tool")
TARGET_KEYWORDS = ("CV maker", "CV creator", "CV generator", "resume maker", "resume generator",
                   "resume builder online", "AI resume builder", "AI CV generator", "CV templates",
                   "resume templates", "make a CV online")


def _block(name, html):
    m = re.search(r"\{%\s*block " + name + r"\s*%\}(.*?)\{%\s*endblock\s*%\}", html, re.S)
    return m.group(1).strip() if m else None


def _read(rel):
    with open(os.path.join(T, rel), encoding="utf-8") as fh:
        return fh.read()


class SeoKeywordTests(unittest.TestCase):
    def test_home_title_and_description_limits(self):
        self.assertIn("Online CV Builder", sc.HOME_TITLE)
        self.assertLessEqual(len(sc.HOME_TITLE), 65)
        self.assertTrue(120 <= len(sc.HOME_DESCRIPTION) <= 160, len(sc.HOME_DESCRIPTION))
        for kw in ("CV builder", "resume maker", "CV generator"):
            self.assertIn(kw.lower(), sc.HOME_TITLE.lower())

    def test_keywords_keep_originals_and_add_targets(self):
        for kw in ORIGINAL_KEYWORDS + TARGET_KEYWORDS:
            self.assertIn(kw, sc.SEO_KEYWORDS)
        terms = [t.strip().lower() for t in sc.SEO_KEYWORDS.split(",")]
        self.assertEqual(len(terms), len(set(terms)), "duplicate keyword phrases")

    def test_landing_template_matches_constants(self):
        html = _read("landing.html")
        self.assertEqual(_block("title", html), sc.HOME_TITLE)
        self.assertEqual(_block("meta_description", html), sc.HOME_DESCRIPTION)
        base = _read("base.html")
        self.assertEqual(_block("title", base), sc.HOME_TITLE)
        self.assertEqual(_block("meta_description", base), sc.HOME_DESCRIPTION)
        self.assertIn("{{ seo_keywords }}", _block("meta_keywords", base))

    def test_public_page_titles_and_descriptions_unique_and_sized(self):
        base = _read("base.html")
        titles, descs = {}, {}
        for rel in PUBLIC_TEMPLATES:
            html = _read(rel)
            title = _block("title", html) or _block("title", base)
            desc = _block("meta_description", html) or _block("meta_description", base)
            self.assertTrue(title and desc, rel)
            self.assertLessEqual(len(title), 65, f"{rel}: title {len(title)} chars")
            self.assertLessEqual(len(desc), 175, f"{rel}: description {len(desc)} chars")
            titles.setdefault(title, []).append(rel)
            descs.setdefault(desc, []).append(rel)
        self.assertEqual({t: p for t, p in titles.items() if len(p) > 1}, {})
        self.assertEqual({d: p for d, p in descs.items() if len(p) > 1}, {})

    def test_page_specific_keywords_are_wired(self):
        for rel, var in (("pricing.html", "pricing_keywords"), ("templates_gallery/public.html", "templates_keywords"),
                         ("auth/register.html", "register_keywords"), ("guide/index.html", "guide_keywords")):
            self.assertIn("{{ " + var + " }}", _block("meta_keywords", _read(rel)), rel)
        self.assertIn("CV templates", sc.TEMPLATES_KEYWORDS)
        self.assertIn("how to make a CV", sc.GUIDE_KEYWORDS)

    def test_faqs_cover_new_search_terms_and_stay_compliant(self):
        questions = [q for q, _ in sc.LANDING_FAQS]
        self.assertGreaterEqual(len(questions), 8)
        self.assertEqual(len(questions), len(set(questions)))
        joined = " ".join(q + " " + a for q, a in sc.LANDING_FAQS).lower()
        for phrase in ("free cv maker", "cv generator", "resume generator", "templates", "cv maker"):
            self.assertIn(phrase, joined)
        # honesty rules from site_content.py's header
        self.assertNotRegex(joined, r"guarantee[sd]?\b(?! about)")
        self.assertNotIn("100% free", joined)

    def test_banned_wording_absent_in_new_copy(self):
        # Scan the copy itself (not code comments, which legitimately mention the rules).
        copy = [_read("landing.html"), sc.HOME_TITLE, sc.HOME_DESCRIPTION, sc.SEO_KEYWORDS,
                sc.TEMPLATES_KEYWORDS, sc.PRICING_KEYWORDS, sc.REGISTER_KEYWORDS, sc.GUIDE_KEYWORDS]
        copy += [q + " " + a for q, a in sc.LANDING_FAQS + sc.PRICING_FAQS]
        for rel in ("pricing.html", "templates_gallery/public.html", "auth/register.html", "guide/index.html"):
            copy.append(_block("title", _read(rel)) + " " + _block("meta_description", _read(rel)))
        text = " ".join(copy).lower()
        self.assertNotRegex(text, r"(?i)\bafrican\b|(?<!south )\bafrica\b")
        self.assertNotRegex(text, r"\busd\b|us\$|\beur\b|\bgbp\b|multi-currency")

    def test_jsonld_graph_shape_unchanged(self):
        plans = [SimpleNamespace(display_price=799), SimpleNamespace(display_price=1499)]
        ld = sc.landing_jsonld("https://example.com", plans, "https://example.com/pricing", "https://example.com/logo.png")
        graph = ld["@graph"]
        self.assertEqual({n["@type"] for n in graph}, {"WebSite", "WebApplication", "FAQPage"})
        app = next(n for n in graph if n["@type"] == "WebApplication")
        self.assertEqual(app["offers"]["priceCurrency"], "KES")
        self.assertIn("CV generator", app["keywords"])
        self.assertIn("Cover letter generator", app["featureList"])
        faq = next(n for n in graph if n["@type"] == "FAQPage")
        self.assertEqual(len(faq["mainEntity"]), len(sc.LANDING_FAQS))


if __name__ == "__main__":
    unittest.main()
