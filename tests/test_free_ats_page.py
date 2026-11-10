"""Public free ATS checker page: SEO markup, results, validation, privacy headers, rate limit."""
import html as htmllib
import json
import re
import unittest

from tests.test_ats_lite import GOOD, JD, POOR

try:
    from app import create_app
    from app.models import db
    APP_AVAILABLE = True
except ImportError:
    APP_AVAILABLE = False


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


def _visible(html):
    return htmllib.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)))


def _meta(html, name):
    m = re.search(rf'<meta name="{name}" content="([^"]*)"', html)
    return htmllib.unescape(m.group(1)) if m else None


BANNED = re.compile(r"(?i)\bafrican\b|(?<!south )\bafrica\b|\busd\b|us\$|\beur\b|\bgbp\b|multi-currency|\bguarantee[sd]?\b")


@unittest.skipUnless(APP_AVAILABLE, "full app dependencies not installed")
class FreeAtsPageTests(unittest.TestCase):
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

    def setUp(self):
        from app.routes import free_ats
        free_ats._hits.clear()

    def post(self, cv, jd=""):
        return self.client.post("/free-ats-checker", data={"cv_text": cv, "job_description": jd})

    def test_get_page_seo_and_form(self):
        resp = self.client.get("/free-ats-checker")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertEqual(len(re.findall(r"<h1", html)), 1)
        self.assertIn("Free ATS Resume Checker", html)
        self.assertIn("index", _meta(html, "robots"))
        self.assertNotIn("noindex", _meta(html, "robots"))
        self.assertTrue(120 <= len(_meta(html, "description")) <= 160)
        self.assertIn('name="cv_text"', html)
        self.assertIn('name="job_description"', html)
        self.assertIn('rel="canonical"', html)
        blocks = [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]
        graph = next(b for b in blocks if "@graph" in b)["@graph"]
        self.assertEqual({n["@type"] for n in graph}, {"WebApplication", "BreadcrumbList", "FAQPage"})
        text = _visible(html)
        for item in next(n for n in graph if n["@type"] == "FAQPage")["mainEntity"]:
            self.assertIn(item["name"], text)
            self.assertIn(item["acceptedAnswer"]["text"], text)
        self.assertIsNone(BANNED.search(text))

    def test_good_cv_result(self):
        resp = self.post(GOOD, JD)
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("noindex", _meta(html, "robots"))
        self.assertEqual(resp.headers.get("Cache-Control"), "no-store")
        text = _visible(html)
        self.assertIn("Strong", text)
        self.assertRegex(text, r"9\d out of 100")
        self.assertIn("Job keyword match", text)
        for term in ("kubernetes", "terraform"):
            self.assertIn(term, text)
        self.assertIn("src=free-ats", html)            # sign-up link carries the source for later measurement
        self.assertIn("daniel.kim@example.com", html)  # the visitor's text is echoed back into the form only
        self.assertIsNone(BANNED.search(text))

    def test_poor_cv_lists_every_fix(self):
        html = self.post(POOR).get_data(as_text=True)
        text = _visible(html)
        self.assertIn("Early draft", text)
        self.assertIn("No email address found", text)
        self.assertIn("Show the other", text)           # fixes beyond the first three are tucked into a details block
        self.assertNotIn("Job keyword match", text)

    def test_validation_errors(self):
        for cv in ("", "too short to check"):
            resp = self.post(cv)
            self.assertEqual(resp.status_code, 400)
            self.assertIn("noindex", _meta(resp.get_data(as_text=True), "robots"))
        resp = self.post(GOOD, "y" * 15001)
        self.assertEqual(resp.status_code, 400)

    def test_rate_limit_returns_429_after_the_hourly_cap(self):
        from app.routes import free_ats
        for _ in range(free_ats.CHECKS_PER_HOUR):
            self.assertEqual(self.post(GOOD).status_code, 200)
        resp = self.post(GOOD)
        self.assertEqual(resp.status_code, 429)
        self.assertIn("create a free account", resp.get_data(as_text=True))

    def test_discoverable(self):
        self.assertTrue(re.search(r"/free-ats-checker</loc>", self.client.get("/sitemap.xml").get_data(as_text=True)))
        self.assertIn("Allow: /free-ats-checker", self.client.get("/robots.txt").get_data(as_text=True))
        self.assertIn('href="/free-ats-checker"', self.client.get("/").get_data(as_text=True))
        self.assertIn('href="/free-ats-checker"', self.client.get("/cv-examples/accountant").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
