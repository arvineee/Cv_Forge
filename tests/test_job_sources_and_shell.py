"""Admin-managed job sources, DB-backed sync, and the redesigned app shell."""
import json
import unittest
from unittest import mock

try:
    from app import create_app
    from app.models import db, User, JobFeedSource, JobOpportunity, Notification
    from app.services import job_discovery as jd
    APP_AVAILABLE = True
except ImportError:  # pragma: no cover
    APP_AVAILABLE = False


class _Cfg:
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    DEBUG = False
    GEMINI_API_KEY = ""
    UPLOAD_FOLDER = "/tmp/cvforge-test-uploads"
    VISITOR_TRACKING_ASYNC = False
    JOB_FEEDS_JSON = ""
    JOB_FEED_ALLOWED_DOMAINS = ""


RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>Clinical Officer</title><link>https://careers.example.org/1</link><guid>g1</guid>
<description>&lt;p&gt;Nairobi hospital role&lt;/p&gt;</description><pubDate>Mon, 16 Nov 2026 08:00:00 GMT</pubDate></item>
<item><title>Nurse</title><link>https://careers.example.org/2</link><guid>g2</guid><description>Ward nurse</description></item>
</channel></rss>"""


class _Resp:
    def __init__(self, body=RSS, status=200):
        self.status_code, self._body = status, body

    def iter_content(self, _size):
        yield self._body


def _public(*_a, **_k):
    return [(2, 1, 6, "", ("93.184.216.34", 443))]


@unittest.skipUnless(APP_AVAILABLE, "full app dependencies not installed")
class JobSourcesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app(_Cfg)
        cls.app.config["TESTING"] = True
        with cls.app.app_context():
            db.create_all()
            admin = User(email="admin@example.com", is_admin=True, is_verified=True, plan="premium")
            admin.set_password("pw-pw-pw-pw")
            member = User(email="member@example.com", is_verified=True)
            member.set_password("pw-pw-pw-pw")
            db.session.add_all([admin, member])
            db.session.commit()
            db.session.add(Notification(user_id=admin.id, title="New jobs", message="m", action_url="/career/jobs?q=x"))
            db.session.commit()

    def setUp(self):
        with self.app.app_context():
            JobOpportunity.query.delete()
            JobFeedSource.query.delete()
            db.session.commit()

    def login(self, email="admin@example.com"):
        client = self.app.test_client()
        resp = client.post("/auth/login", data={"email": email, "password": "pw-pw-pw-pw"})
        self.assertEqual(resp.status_code, 302)
        return client

    # ── access control ────────────────────────────────────────────────
    def test_non_admin_is_forbidden(self):
        self.assertEqual(self.login("member@example.com").get("/admin/job-sources").status_code, 403)

    def test_anonymous_is_redirected(self):
        self.assertEqual(self.app.test_client().get("/admin/job-sources").status_code, 302)

    # ── url normalising ───────────────────────────────────────────────
    def test_normalize_feed_url(self):
        self.assertEqual(jd.normalize_feed_url("careers.example.org/rss"), "https://careers.example.org/rss")
        for bad in ("", "http://example.org/rss", "https://user:pw@example.org/rss", "https://localhost/rss"):
            with self.assertRaises(ValueError, msg=bad):
                jd.normalize_feed_url(bad)

    # ── add / test / sync / toggle / delete ───────────────────────────
    @mock.patch("app.services.job_discovery.requests.get", return_value=_Resp())
    @mock.patch("app.services.job_discovery.socket.getaddrinfo", side_effect=_public)
    def test_add_source_imports_listings_without_env(self, _dns, _get):
        client = self.login()
        resp = client.post("/admin/job-sources", data={
            "action": "add", "url": "https://careers.example.org/rss.xml", "name": "Example Careers",
            "country": "Kenya", "location": "Nairobi", "sync_now": "1"}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        with self.app.app_context():
            src = JobFeedSource.query.one()
            self.assertEqual((src.name, src.last_status, src.last_entry_count), ("Example Careers", "ok", 2))
            jobs = JobOpportunity.query.order_by(JobOpportunity.title).all()
            self.assertEqual([j.title for j in jobs], ["Clinical Officer", "Nurse"])
            self.assertEqual({j.country for j in jobs}, {"Kenya"})
            self.assertEqual(jobs[0].location, "Nairobi")
        page = client.get("/admin/job-sources").get_data(as_text=True)
        self.assertIn("Example Careers", page)
        self.assertIn("Healthy", page)

    @mock.patch("app.services.job_discovery.requests.get", return_value=_Resp(b"<html>not a feed</html>"))
    @mock.patch("app.services.job_discovery.socket.getaddrinfo", side_effect=_public)
    def test_bad_feed_is_rejected_unless_forced(self, _dns, _get):
        client = self.login()
        client.post("/admin/job-sources", data={"action": "add", "url": "https://careers.example.org/x"})
        with self.app.app_context():
            self.assertEqual(JobFeedSource.query.count(), 0)
        client.post("/admin/job-sources", data={"action": "add", "url": "https://careers.example.org/x", "force": "1"})
        with self.app.app_context():
            self.assertEqual(JobFeedSource.query.count(), 1)

    @mock.patch("app.services.job_discovery.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("10.0.0.5", 443))])
    def test_private_addresses_are_never_fetched(self, _dns):
        self.assertFalse(jd.check_feed("https://intranet.example.org/rss")["ok"])

    @mock.patch("app.services.job_discovery.requests.get", return_value=_Resp())
    @mock.patch("app.services.job_discovery.socket.getaddrinfo", side_effect=_public)
    def test_toggle_pauses_sync_and_delete_removes(self, _dns, _get):
        client = self.login()
        client.post("/admin/job-sources", data={"action": "add", "url": "https://careers.example.org/rss.xml"})
        with self.app.app_context():
            sid = JobFeedSource.query.one().id
        client.post("/admin/job-sources", data={"action": "toggle", "id": sid})
        with self.app.app_context():
            self.assertFalse(JobFeedSource.query.get(sid).is_active)
            self.assertEqual(jd.sync_job_feeds()["feeds"], 0)  # paused sources are not fetched
        client.post("/admin/job-sources", data={"action": "delete", "id": sid})
        with self.app.app_context():
            self.assertEqual(JobFeedSource.query.count(), 0)

    def test_unknown_action_is_a_400_and_missing_source_a_404(self):
        client = self.login()
        self.assertEqual(client.post("/admin/job-sources", data={"action": "nope", "id": "999"}).status_code, 404)

    # ── legacy .env support ───────────────────────────────────────────
    @mock.patch("app.services.job_discovery.requests.get", return_value=_Resp())
    @mock.patch("app.services.job_discovery.socket.getaddrinfo", side_effect=_public)
    def test_env_feeds_still_sync_and_can_be_imported(self, _dns, _get):
        feeds = json.dumps([{"name": "Env Feed", "url": "https://careers.example.org/env.xml", "country": "Kenya"}])
        self.app.config.update(JOB_FEEDS_JSON=feeds, JOB_FEED_ALLOWED_DOMAINS="careers.example.org")
        try:
            with self.app.app_context():
                self.assertEqual(jd.sync_job_feeds()["created"], 2)
                self.assertEqual(jd.import_env_sources(), 1)
                self.assertEqual(jd.import_env_sources(), 0)  # idempotent
                feeds_now, _ = jd._load_feed_config()
                self.assertEqual(len(feeds_now), 1)  # DB copy wins, no double fetch
            page = self.login().get("/admin/job-sources").get_data(as_text=True)
            self.assertIn("Env Feed", page)
        finally:
            self.app.config.update(JOB_FEEDS_JSON="", JOB_FEED_ALLOWED_DOMAINS="")

    # ── shell + pages ─────────────────────────────────────────────────
    def test_dashboard_and_shell_render(self):
        client = self.login()
        html = client.get("/dashboard").get_data(as_text=True)
        for text in ("Application pipeline", "Latest vacancies", "Find Jobs", "Job search", "main-content"):
            self.assertIn(text, html, text)
        self.assertIn('aria-current="page"', html)
        self.assertIn("Job Sources", html)  # admin-only sidebar link
        self.assertIn("side-count", html)  # unread job notification badge
        member_html = self.login("member@example.com").get("/dashboard").get_data(as_text=True)
        self.assertNotIn("Job Sources", member_html)

    def test_job_pages_render(self):
        client = self.login()
        for path in ("/career/jobs", "/career/applications", "/career/job-alerts", "/admin/", "/admin/job-sources"):
            self.assertEqual(client.get(path).status_code, 200, path)

    def test_dashboard_pages_are_noindex(self):
        html = self.login().get("/dashboard").get_data(as_text=True)
        self.assertIn('content="noindex, nofollow"', html)

    def test_manifest_robots_and_landing_seo(self):
        client = self.app.test_client()
        manifest = client.get("/manifest.webmanifest")
        self.assertEqual(manifest.status_code, 200)
        self.assertEqual(json.loads(manifest.data)["display"], "standalone")
        robots = client.get("/robots.txt").get_data(as_text=True)
        self.assertIn("Disallow: /career/", robots)
        home = client.get("/").get_data(as_text=True)
        self.assertIn('rel="manifest"', home)
        self.assertIn("css/app.css?v=", home)
        self.assertEqual(home.count("google-adsense-account"), 1)
        for path in ("/pricing", "/about", "/guide", "/templates/", "/privacy", "/terms", "/cv-examples/"):
            page = client.get(path)
            self.assertEqual(page.status_code, 200, path)
            self.assertIn("pub-nav", page.get_data(as_text=True), path)


if __name__ == "__main__":
    unittest.main()
