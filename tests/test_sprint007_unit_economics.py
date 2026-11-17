"""Sprint 007 unit-economics report safeguards."""
import unittest

try:
    from app.services.unit_economics import build_unit_economics_report
    from app import create_app
    from app.models import db
    AVAILABLE = True
except ImportError:
    AVAILABLE = False


class Config:
    SECRET_KEY = "sprint007-test"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False
    TESTING = True


@unittest.skipUnless(AVAILABLE, "Flask application dependencies unavailable")
class UnitEconomicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app(Config)

    def setUp(self):
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_report_keeps_unknown_costs_explicit_and_currency_split(self):
        report = build_unit_economics_report(30)
        self.assertEqual(report["gross_by_currency"], [])
        self.assertEqual(report["provider_breakdown"], [])
        self.assertEqual(report["ai_requests"], 0)
        self.assertEqual(report["token_coverage_pct"], 0)
        self.assertTrue(any("acquisition spend" in x for x in report["unknown_costs"]))
        self.assertTrue(any("AI provider costs" in x for x in report["unknown_costs"]))

    def test_invalid_window_defaults_to_30_days(self):
        self.assertEqual(build_unit_economics_report(365)["days"], 30)


if __name__ == "__main__":
    unittest.main()
