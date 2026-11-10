"""
International positioning: public copy, SEO metadata, structured data,
sitemap/robots, and that the payment buttons still post to the same routes.
"""
import json
import re
import unittest

# --- sitemap path helper (added by fix_sitemap_test.py) ---
def _assert_path_not_in_sitemap(case, prefix, xml, msg=None):
    """Fail only if a <loc> path equals `prefix` or sits under it as a whole
    path segment ('/admin' matches /admin and /admin/x, not /administrative-x)."""
    import re as _re
    from urllib.parse import urlparse as _urlparse
    prefix = str(prefix).rstrip("/") or "/"
    paths = [_urlparse(u).path for u in _re.findall(r"<loc>([^<]+)</loc>", xml)]
    bad = [p for p in paths if p == prefix or p.startswith(prefix + "/")]
    case.assertFalse(bad, msg or f"{prefix} unexpectedly in sitemap: {bad}")
# --- end helper ---

try:
    from app import create_app
    from app.models import db, PricingPlan, User
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


class _ConfiguredSiteConfig(_Config):
    SITE_URL = "https://cvforgeai.com"


HEADLINE = "Build a CV That Gets You Noticed, Wherever You Want to Work."
PUBLIC_PATHS = ["/", "/pricing", "/about", "/billing/plans", "/templates/", "/guide",
                "/support", "/auth/register", "/auth/login", "/privacy", "/terms"]


def _meta(html, attr, name):
    m = re.search(rf'<meta {attr}="{re.escape(name)}" content="([^"]*)"', html)
    return m.group(1) if m else None


def _jsonld_blocks(html):
    out = []
    for raw in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        out.append(json.loads(raw))
    return out


@unittest.skipUnless(APP_AVAILABLE, "full app dependencies not installed")
class InternationalSiteTests(unittest.TestCase):
    config = _Config

    @classmethod
    def setUpClass(cls):
        cls.app = create_app(cls.config)
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

    # ── copy ───────────────────────────────────────────────────────────
    def test_landing_headline_and_features(self):
        html = self.get("/")
        self.assertIn("Build a CV That Gets You Noticed,", html)
        self.assertIn("Wherever You Want to Work.", html)
        for phrase in ("ATS-friendly", "Job description matching", "cover letter",
                       "PDF and Word", "Resume improvement and rewriting"):
            self.assertIn(phrase.lower(), html.lower(), phrase)
        self.assertNotIn("Professional CV Builder for African Professionals", html)

    def test_no_africa_only_marketing_language_on_public_pages(self):
        for path in PUBLIC_PATHS:
            html = self.get(path)
            # "South Africa" is a target market, so only Africa-as-audience wording is banned
            self.assertNotRegex(html, r"(?i)\bafrican\b|(?<!south )\bafrica\b", path)

    def test_kenya_background_is_retained(self):
        self.assertIn("Built in Kenya", self.get("/"))
        self.assertIn("built in Kenya", self.get("/about"))

    def test_no_multicurrency_claims(self):
        for path in ("/", "/pricing", "/billing/plans"):
            html = self.get(path).lower()
            self.assertNotIn("multi-currency", html, path)
            self.assertNotRegex(html, r"\busd\b|us\$|\beur\b|\bgbp\b", path)

    def test_card_and_mpesa_messaging_on_pricing_and_checkout(self):
        for path in ("/", "/pricing", "/billing/plans"):
            html = self.get(path)
            self.assertIn("Paystack", html, path)
            self.assertIn("M-Pesa", html, path)
            self.assertIn("Accepted payment methods", html, path)
            self.assertIn("KES", html, path)

    # ── payment routes unchanged ───────────────────────────────────────
    def test_payment_forms_still_post_to_existing_routes(self):
        with self.app.app_context():
            user = User(email="intl-buyer@example.com", is_verified=True)
            user.set_password("correct horse battery")
            db.session.add(user)
            db.session.commit()
        client = self.app.test_client()
        resp = client.post("/auth/login", data={"email": "intl-buyer@example.com",
                                                "password": "correct horse battery"})
        self.assertEqual(resp.status_code, 302)  # signed in through the real login form
        for path in ("/pricing", "/billing/plans"):
            html = client.get(path).get_data(as_text=True)
            for slug in ("pro", "premium"):
                self.assertIn(f'action="/billing/subscribe/{slug}"', html, path)
                self.assertIn(f'action="/billing/subscribe-paystack/{slug}"', html, path)
            self.assertIn('name="phone"', html, path)
            self.assertIn('name="csrf_token"', html, path)
            self.assertIn("Pay KES 799 by card", html, path)

    # ── SEO ────────────────────────────────────────────────────────────
    def test_homepage_seo_tags(self):
        html = self.get("/")
        title = re.search(r"<title>(.*?)</title>", html, re.S).group(1).strip()
        self.assertIn("Online CV Builder", title)
        self.assertLessEqual(len(title), 65)
        desc = _meta(html, "name", "description")
        self.assertTrue(120 <= len(desc) <= 160, len(desc))
        keywords = _meta(html, "name", "keywords")
        for kw in ("online CV builder", "ATS-friendly resume builder", "professional resume builder",
                   "CV builder online", "resume creator", "cover letter generator",
                   "AI CV builder", "resume optimisation tool", "CV writing tool"):
            self.assertIn(kw, keywords)
        for prop in ("og:title", "og:description", "og:url", "og:image", "og:type", "og:site_name"):
            self.assertTrue(_meta(html, "property", prop), prop)
        for name in ("twitter:card", "twitter:title", "twitter:description", "twitter:image"):
            self.assertTrue(_meta(html, "name", name), name)
        self.assertIn('rel="canonical"', html)

    def test_every_public_page_has_unique_title_description_and_one_h1(self):
        titles, descs = {}, {}
        for path in PUBLIC_PATHS:
            html = self.get(path)
            title = re.search(r"<title>(.*?)</title>", html, re.S).group(1).strip()
            desc = _meta(html, "name", "description")
            self.assertTrue(desc, path)
            self.assertLessEqual(len(desc), 175, path)
            titles.setdefault(title, []).append(path)
            descs.setdefault(desc, []).append(path)
        dup_titles = {t: p for t, p in titles.items() if len(p) > 1}
        dup_descs = {d: p for d, p in descs.items() if len(p) > 1}
        # /billing/plans and /pricing intentionally differ in wording but share a canonical
        self.assertEqual(dup_titles, {})
        self.assertEqual(dup_descs, {})

    def test_billing_plans_canonicalises_to_pricing(self):
        html = self.get("/billing/plans")
        self.assertRegex(html, r'<link rel="canonical" href="https?://[^"]+/pricing"')

    def test_login_is_noindex(self):
        self.assertIn("noindex", _meta(self.get("/auth/login"), "name", "robots"))
        self.assertIn("index", _meta(self.get("/"), "name", "robots"))

    def test_jsonld_is_valid_and_matches_visible_faq(self):
        html = self.get("/")
        blocks = _jsonld_blocks(html)
        self.assertGreaterEqual(len(blocks), 2)
        org = next(b for b in blocks if b.get("@type") == "Organization")
        self.assertEqual(org["name"], "CVForge AI")
        graph = next(b for b in blocks if "@graph" in b)["@graph"]
        types = {n["@type"] for n in graph}
        self.assertEqual(types, {"WebSite", "WebApplication", "FAQPage"})
        app_node = next(n for n in graph if n["@type"] == "WebApplication")
        self.assertEqual(app_node["offers"]["priceCurrency"], "KES")
        faq = next(n for n in graph if n["@type"] == "FAQPage")
        self.assertGreaterEqual(len(faq["mainEntity"]), 8)
        import html as htmllib
        visible = htmllib.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)))
        for q in faq["mainEntity"]:
            self.assertIn(q["name"], visible)

    def test_sitemap_lists_public_pages_only(self):
        xml = self.get("/sitemap.xml")
        for path in ("/</loc>", "/pricing</loc>", "/about</loc>", "/templates/</loc>",
                     "/guide</loc>", "/auth/register</loc>", "/privacy</loc>", "/terms</loc>"):
            self.assertIn(path, xml, path)
        for private in ("/dashboard", "/admin", "/cv/", "/billing/plans", "/auth/login", "/api/"):
            _assert_path_not_in_sitemap(self, private, xml, private)
        self.assertEqual(len(re.findall(r"<loc>", xml)), len(set(re.findall(r"<loc>(.*?)</loc>", xml))))

    def test_robots_txt(self):
        txt = self.get("/robots.txt")
        for line in ("Disallow: /dashboard", "Disallow: /admin/", "Disallow: /webhooks/",
                     "Allow: /pricing", "Allow: /guide", "Sitemap: "):
            self.assertIn(line, txt)
        self.assertRegex(txt, r"Sitemap: https?://[^/\s]+/sitemap\.xml")

    def test_internal_links_on_public_pages_resolve(self):
        seen = set()
        for path in PUBLIC_PATHS:
            html = self.get(path)
            for href in re.findall(r'href="(/[^"#?]*)', html):
                if href.startswith(("/static/", "/auth/google")) or href in seen:
                    continue
                seen.add(href)
                code = self.client.get(href).status_code
                self.assertIn(code, (200, 302), f"{href} (linked from {path}) -> {code}")


@unittest.skipUnless(APP_AVAILABLE, "full app dependencies not installed")
class SiteUrlSettingTests(InternationalSiteTests):
    """With SITE_URL set, canonical/OG/sitemap/robots use that origin, not the request host."""
    config = _ConfiguredSiteConfig

    def test_canonical_og_and_sitemap_use_site_url(self):
        html = self.get("/")
        self.assertIn('<link rel="canonical" href="https://cvforgeai.com/"', html)
        self.assertEqual(_meta(html, "property", "og:url"), "https://cvforgeai.com/")
        self.assertTrue(_meta(html, "property", "og:image").startswith("https://cvforgeai.com/static/"))
        self.assertIn("<loc>https://cvforgeai.com/pricing</loc>", self.get("/sitemap.xml"))
        self.assertIn("Sitemap: https://cvforgeai.com/sitemap.xml", self.get("/robots.txt"))
        self.assertIn('"url": "https://cvforgeai.com/"', html)


if __name__ == "__main__":
    unittest.main()
