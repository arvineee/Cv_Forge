"""
Application-level checks. These need the full dependency set from
requirements.txt, so they are skipped when the Flask extensions are missing
(for example in a bare local Python). CI installs everything and runs them.
"""
import unittest

try:
    from app import create_app
    from app.models import db
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

    def test_upload_requires_login(self):
        resp = self.client.post("/cv/upload", data={})
        self.assertIn(resp.status_code, (302, 401))

    def test_no_server_errors_on_public_pages(self):
        for path in ("/", "/auth/login", "/pricing"):
            resp = self.client.get(path)
            self.assertLess(resp.status_code, 500, path)


if __name__ == "__main__":
    unittest.main()
