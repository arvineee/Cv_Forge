"""User manual: PDF build, public routes, dashboard prompt and one-time emailing."""
import unittest

try:
    from app import create_app
    from app.models import db, User, UserSettings, Notification
    APP = True
except ImportError:
    APP = False

from tests.test_app_smoke import _TestConfig


class ManualPdfTests(unittest.TestCase):
    def test_pdf_builds_with_branding(self):
        from app.services.manual_pdf import build_manual_pdf
        data = build_manual_pdf("https://example.com")
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertLess(len(data), 600_000)          # logo is downscaled
        self.assertGreaterEqual(data.count(b"/Type /Page\n") + data.count(b"/Type /Page "), 5)


@unittest.skipUnless(APP, "full app dependencies not installed")
class ManualAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cfg = type("C", (_TestConfig,), {"MAIL_USERNAME": "x", "MAIL_DEFAULT_SENDER": "x@y.z",
                                         "MAIL_SUPPRESS_SEND": True, "TESTING": True})
        cls.app = create_app(cfg)
        with cls.app.app_context():
            db.create_all()
            for i, (nl, ver) in enumerate([(True, True), (False, True), (True, False), (True, True)]):
                u = User(email=f"u{i}@x.co", first_name="U", is_verified=ver); u.set_password("pw123456")
                db.session.add(u); db.session.flush()
                db.session.add(UserSettings(user_id=u.id, email_newsletter=nl))
            db.session.commit()
        cls.client = cls.app.test_client()

    def test_public_page_and_pdf(self):
        self.assertEqual(self.client.get("/guide").status_code, 200)
        r = self.client.get("/guide/download")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "application/pdf")
        self.assertIn("attachment", r.headers["Content-Disposition"])

    def test_emailing_is_once_only_and_respects_optout(self):
        from app.services.manual_mailing import send_manual_emails
        with self.app.app_context():
            self.assertEqual(send_manual_emails(dry_run=True)["total"], 2)  # opted out + unverified excluded
            r1 = send_manual_emails()
            self.assertEqual((r1["sent"], r1["failed"]), (2, 0))
            r2 = send_manual_emails()
            self.assertEqual(r2["total"], 0)
            self.assertEqual(Notification.query.filter_by(title="Your CVForge AI user manual").count(), 2)

    def test_dashboard_shows_prompt(self):
        with self.app.app_context():
            uid = User.query.filter_by(email="u0@x.co").first().id
        with self.client.session_transaction() as s:
            s["_user_id"] = str(uid); s["_fresh"] = True
        html = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn("Download the manual (PDF)", html)
        self.assertIn("User Guide", html)


if __name__ == "__main__":
    unittest.main()
