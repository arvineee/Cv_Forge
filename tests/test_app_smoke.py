"""
Application-level checks. These need the full dependency set from
requirements.txt, so they are skipped when the Flask extensions are missing
(for example in a bare local Python). CI installs everything and runs them.
"""
import unittest
from urllib.parse import parse_qs, urlsplit

try:
    from app import create_app
    from app.models import db, PricingPlan, User
    APP_AVAILABLE = True
except ImportError:
    APP_AVAILABLE = False


class _TestConfig:
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


@unittest.skipUnless(APP_AVAILABLE, "full app dependencies not installed")
class AppSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app(_TestConfig)
        cls.app.config["TESTING"] = True
        with cls.app.app_context():
            db.create_all()
        cls.client = cls.app.test_client()

    def test_security_headers_present(self):
        resp = self.client.get("/")
        self.assertEqual(resp.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(resp.headers.get("X-Content-Type-Options"), "nosniff")

    def setUp(self):
        with self.client.session_transaction() as session:
            session.clear()

    def test_upload_requires_login(self):
        resp = self.client.post("/cv/upload", data={})
        self.assertIn(resp.status_code, (302, 401))

    def test_guest_plan_selection_returns_to_login_with_safe_path(self):
        resp = self.client.get("/billing/continue/pro")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/auth/login?next=%2Fbilling%2Fcontinue%2Fpro", resp.headers["Location"])

    def test_registration_preserves_internal_return_path(self):
        resp = self.client.get("/auth/register?next=%2Fbilling%2Fcontinue%2Fpro")
        self.assertIn('name="next" value="/billing/continue/pro"', resp.get_data(as_text=True))

    def test_registration_rejects_protocol_relative_return_path(self):
        resp = self.client.get("/auth/register?next=%2F%2Fevil.example")
        self.assertNotIn('name="next"', resp.get_data(as_text=True))

    def test_verification_returns_to_login_with_safe_path(self):
        with self.app.app_context():
            user = User(email="conversion-verification@example.com",
                        verification_token="conversion-verification-token")
            db.session.add(user)
            db.session.commit()

        resp = self.client.get(
            "/auth/verify/conversion-verification-token?next=/billing/continue/pro"
        )
        self.assertEqual(resp.status_code, 302)
        location = urlsplit(resp.headers["Location"])
        self.assertEqual(location.path, "/auth/login")
        self.assertEqual(parse_qs(location.query).get("next"), ["/billing/continue/pro"])

    def test_authenticated_plan_selection_opens_chosen_plan(self):
        with self.app.app_context():
            user = User(email="conversion-plan@example.com", is_verified=True)
            plan = PricingPlan(slug="conversion-pro", name="Conversion Pro", price_kes=100,
                               billing_period="month", is_active=True)
            db.session.add_all([user, plan])
            db.session.commit()
            user_id = user.id

        with self.client.session_transaction() as session:
            session.clear()
            session["_user_id"] = str(user_id)
            session["_fresh"] = True

        resp = self.client.get("/billing/continue/conversion-pro")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.headers["Location"], "/billing/plans?plan=conversion-pro")

        pricing = self.client.get(resp.headers["Location"])
        self.assertEqual(pricing.status_code, 200)
        self.assertIn('x-data="{open: true}"', pricing.get_data(as_text=True))

    def test_no_server_errors_on_public_pages(self):
        for path in ("/", "/auth/login", "/pricing"):
            resp = self.client.get(path)
            self.assertLess(resp.status_code, 500, path)


if __name__ == "__main__":
    unittest.main()
