"""CV example pages: content rules (no Flask needed) and rendered pages (full app)."""
import html as htmllib
import json
import re
import unittest

from tests._load import load

try:
    from app import create_app
    from app.models import db
    APP_AVAILABLE = True
except ImportError:
    APP_AVAILABLE = False

ce = load("app/services/cv_examples.py", "cv_examples_under_test")
BANNED_REGION = re.compile(r"(?i)\bafrican\b|(?<!south )\bafrica\b")
BANNED_MONEY = re.compile(r"(?i)\busd\b|us\$|\beur\b|\bgbp\b|\bkes\b|multi-currency|[$€£]")
GUARANTEE = re.compile(r"(?i)\bguarantee[sd]?\b|\b100% (free|success)\b")


def _all_copy(ex):
    s = ex["sample"]
    parts = [ex["role"], ex["short"], ex["seo_title"], ex["seo_desc"], ex["card"], ex["intro"],
             s["name"], s["headline"], s["summary"], *s["credentials"], *s["skills"], *ex["tips"]]
    for job in s["experience"]:
        parts += [job["title"], job["org"], job["dates"], *job["bullets"]]
    for q, a in ex["faqs"]:
        parts += [q, a]
    return " ".join(parts)


class CvExamplesContentTests(unittest.TestCase):
    def test_enough_examples_with_unique_slugs_titles_and_descriptions(self):
        ex = ce.all_examples()
        self.assertGreaterEqual(len(ex), 9)
        for field in ("slug", "seo_title", "seo_desc", "role"):
            values = [e[field] for e in ex]
            self.assertEqual(len(values), len(set(values)), field)
        for e in ex:
            self.assertRegex(e["slug"], r"^[a-z0-9]+(-[a-z0-9]+)*$")
            self.assertLessEqual(len(e["seo_title"]), 65, e["slug"])
            self.assertTrue(120 <= len(e["seo_desc"]) <= 160, f'{e["slug"]}: {len(e["seo_desc"])}')

    def test_each_example_is_complete(self):
        for e in ce.all_examples():
            s = e["sample"]
            self.assertGreaterEqual(len(s["experience"]), 2, e["slug"])
            for job in s["experience"]:
                self.assertGreaterEqual(len(job["bullets"]), 3, e["slug"])
            self.assertGreaterEqual(len(s["skills"]), 6, e["slug"])
            self.assertGreaterEqual(len(e["tips"]), 4, e["slug"])
            self.assertGreaterEqual(len(e["faqs"]), 2, e["slug"])
            self.assertTrue(len(s["summary"]) > 80 and len(e["intro"]) > 80, e["slug"])
            for q, a in e["faqs"]:
                self.assertTrue(q.endswith("?") and len(a) > 60, e["slug"])

    def test_copy_follows_site_content_rules(self):
        for e in ce.all_examples():
            text = _all_copy(e)
            self.assertIsNone(BANNED_REGION.search(text), e["slug"])
            self.assertIsNone(BANNED_MONEY.search(text), e["slug"])
            self.assertIsNone(GUARANTEE.search(text), e["slug"])

    def test_related_links_exclude_self_and_are_stable(self):
        for e in ce.all_examples():
            rel = ce.related(e["slug"])
            self.assertEqual(len(rel), 4)
            self.assertNotIn(e["slug"], [r["slug"] for r in rel])
            self.assertEqual(rel, ce.related(e["slug"]))
        self.assertIsNone(ce.get_example("nope"))
        self.assertTrue(ce.DISCLAIMER.lower().startswith("this is an example"))


class _Config:
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    DEBUG = False
    GEMINI_API_KEY = ""
    LIPANA_API_KEY = ""
    INTASEND_SECRET_KEY = ""
    UPLOAD_FOLDER = "/tmp/cvforge-test-uploads"
    SITE_URL = ""


def _jsonld(html):
    return [json.loads(raw) for raw in
            re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]


def _visible(html):
    return htmllib.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)))


@unittest.skipUnless(APP_AVAILABLE, "full app dependencies not installed")
class CvExamplePagesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app(_Config)
        cls.app.config["TESTING"] = True
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        db.create_all()
        runner = cls.app.test_cli_runner()
        runner.invoke(args=["seed-plans"])
        runner.invoke(args=["seed-templates"])
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.drop_all()
        cls.ctx.pop()

    def get(self, path):
        resp = self.client.get(path)
        self.assertEqual(resp.status_code, 200, path)
        return resp.get_data(as_text=True)

    def test_index_lists_every_example(self):
        html = self.get("/cv-examples/")
        self.assertEqual(len(re.findall(r"<h1", html)), 1)
        for e in ce.all_examples():
            self.assertIn(f'href="/cv-examples/{e["slug"]}"', html)
        self.assertIn('rel="canonical"', html)

    def test_every_detail_page_has_metadata_content_and_one_h1(self):
        for e in ce.all_examples():
            path = f'/cv-examples/{e["slug"]}'
            html = self.get(path)
            title = re.search(r"<title>(.*?)</title>", html, re.S).group(1).strip()
            self.assertEqual(htmllib.unescape(title), e["seo_title"], path)
            self.assertIn(f'content="{e["seo_desc"]}"', html, path)
            self.assertEqual(len(re.findall(r"<h1", html)), 1, path)
            self.assertRegex(html, rf'<link rel="canonical" href="[^"]*{re.escape(path)}"', path)
            text = _visible(html)
            self.assertIn(e["sample"]["summary"], text, path)
            self.assertIn(ce.DISCLAIMER, text, path)
            self.assertIn("/auth/register", html, path)

    def test_structured_data_matches_visible_faq(self):
        for e in ce.all_examples():
            html = self.get(f'/cv-examples/{e["slug"]}')
            graph = next(b for b in _jsonld(html) if "@graph" in b)["@graph"]
            self.assertEqual({n["@type"] for n in graph}, {"BreadcrumbList", "FAQPage"})
            faq = next(n for n in graph if n["@type"] == "FAQPage")
            text = _visible(html)
            self.assertEqual(len(faq["mainEntity"]), len(e["faqs"]))
            for item in faq["mainEntity"]:
                self.assertIn(item["name"], text)
                self.assertIn(item["acceptedAnswer"]["text"], text)
            crumbs = next(n for n in graph if n["@type"] == "BreadcrumbList")["itemListElement"]
            self.assertEqual([c["position"] for c in crumbs], [1, 2, 3])

    def test_sitemap_and_robots_include_examples(self):
        sitemap = self.get("/sitemap.xml")
        locs = re.findall(r"<loc>([^<]+)</loc>", sitemap)
        self.assertEqual(len(locs), len(set(locs)))
        self.assertTrue(any(l.endswith("/cv-examples/") for l in locs))
        for e in ce.all_examples():
            self.assertTrue(any(l.endswith(f'/cv-examples/{e["slug"]}') for l in locs), e["slug"])
        self.assertIn("Allow: /cv-examples", self.get("/robots.txt"))

    def test_unknown_example_is_404(self):
        self.assertEqual(self.client.get("/cv-examples/not-a-job").status_code, 404)

    def test_homepage_links_to_examples_and_all_links_resolve(self):
        home = self.get("/")
        self.assertIn('href="/cv-examples/"', home)
        for e in ce.all_examples():
            html = self.get(f'/cv-examples/{e["slug"]}')
            for href in set(re.findall(r'href="(/[^"#?]*)"', html)):
                if href.startswith("/static/"):
                    continue
                self.assertIn(self.client.get(href).status_code, (200, 301, 302, 308), f'{e["slug"]} -> {href}')

    def test_rendered_pages_follow_copy_rules(self):
        pages = ["/cv-examples/"] + [f'/cv-examples/{e["slug"]}' for e in ce.all_examples()]
        for path in pages:
            text = _visible(self.get(path))
            self.assertIsNone(BANNED_REGION.search(text), path)
            self.assertIsNone(GUARANTEE.search(text), path)


if __name__ == "__main__":
    unittest.main()
