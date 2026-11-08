"""Regression tests for bugs found in the full code review."""
import unittest
from datetime import datetime, timedelta, timezone


class Cfg:
    SECRET_KEY = "x"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False
    TESTING = True
    UPLOAD_FOLDER = "/tmp/cvforge-test-uploads"
    GEMINI_FREE_USER_DAILY_LIMIT = 50
    GEMINI_DAILY_LIMIT = 1000
    LIPANA_WEBHOOK_SECRET = ""
    INTASEND_WEBHOOK_CHALLENGE = "c"
    SESSION_COOKIE_SECURE = False
    MAIL_USERNAME = None


class ReviewFixTests(unittest.TestCase):
    def setUp(self):
        from app import create_app
        from app.models import db, User, Resume, PricingPlan, Subscription
        self.db = db
        self.app = create_app(Cfg)
        with self.app.app_context():
            db.create_all()
            a = User(email="a@x.com", is_verified=True); a.set_password("password1")
            b = User(email="b@x.com", is_verified=True); b.set_password("password1")
            db.session.add_all([a, b]); db.session.flush()
            db.session.add(PricingPlan(slug="pro", name="Pro", price_kes=100, billing_period="month"))
            db.session.add(Subscription(user_id=a.id, plan="pro", amount=100,
                                        status="pending", payment_reference="REF1"))
            a.reset_token = "tok"
            a.reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=1)
            r = Resume(user_id=b.id, title="OTHER USERS CV", personal_info={})
            mine = Resume(user_id=a.id, title="mine", personal_info={},
                          work_experience=[
                              {"job_title": "First", "company": "A", "achievements": ["first bullet"]},
                              {"job_title": "Second", "company": "B", "achievements": ["second bullet"]}])
            db.session.add_all([r, mine]); db.session.commit()
            self.a, self.b, self.other_resume, self.mine = a.id, b.id, r.id, mine.id
        self.client = self.app.test_client()

    def login(self, uid):
        with self.client.session_transaction() as s:
            s["_user_id"] = str(uid); s["_fresh"] = True

    def test_reset_password_link_works(self):
        self.assertEqual(self.client.get("/auth/reset-password/tok").status_code, 200)

    def test_lipana_webhook_fails_closed_without_secret(self):
        from app.models import User
        resp = self.client.post("/webhooks/lipana", json={
            "event": "payment.success", "data": {"reference": "REF1"}})
        self.assertEqual(resp.status_code, 503)
        with self.app.app_context():
            self.assertEqual(self.db.session.get(User, self.a).plan, "free")

    def test_late_failed_webhook_does_not_undo_active_subscription(self):
        from app.models import Subscription
        from app.routes.webhooks import _handle_payment_success, _handle_payment_failed
        with self.app.app_context():
            self.assertTrue(_handle_payment_success({"reference": "REF1"}))
            _handle_payment_failed({"reference": "REF1"})
            sub = Subscription.query.filter_by(payment_reference="REF1").first()
            self.assertEqual(sub.status, "active")

    def test_success_without_reference_is_rejected(self):
        from app.routes.webhooks import _handle_payment_success
        with self.app.app_context():
            self.assertFalse(_handle_payment_success({}))

    def test_ats_does_not_store_or_show_another_users_resume(self):
        import app.routes.ats as ats
        from app.models import ATSReport

        class Fake:
            def ats_check(self, **kw):
                return {"ats_score": 50, "grade": "C"}
        self.addCleanup(setattr, ats, "get_ai_service", ats.get_ai_service)
        ats.get_ai_service = lambda: Fake()
        self.login(self.a)
        self.client.post("/ats/check", data={"resume_id": self.other_resume, "job_description": "x"})
        with self.app.app_context():
            rep = ATSReport.query.filter_by(user_id=self.a).first()
            self.assertIsNone(rep.resume_id)
            page = self.client.get(f"/ats/report/{rep.id}")
            self.assertNotIn(b"OTHER USERS CV", page.data)

    def test_to_dict_includes_awards_and_custom_sections(self):
        from app.models import Resume
        with self.app.app_context():
            d = self.db.session.get(Resume, self.mine).to_dict()
            self.assertIn("awards", d)
            self.assertIn("custom_sections", d)

    def test_wizard_enhance_targets_the_clicked_role(self):
        """Original bug: 'enhance' on the 2nd role improved the 1st role's text."""
        import app.routes.cv as cvr
        seen = {}

        class Fake:
            def assist_section(self, section, context, resume=None, user_id=None):
                seen["context"] = context
                return "improved"
        self.addCleanup(setattr, cvr, "get_ai_service", cvr.get_ai_service)
        cvr.get_ai_service = lambda: Fake()
        self.login(self.a)
        resp = self.client.post(f"/cv/wizard/{self.mine}/work_experience", data={
            "action": "enhance:1",
            "job_title": ["First", "Second"], "company": ["A", "B"],
            "location": ["", ""], "start_date": ["", ""], "end_date": ["", ""],
            "achievements": ["first bullet", "second bullet"],
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn("second bullet", seen["context"])
        self.assertNotIn("first bullet", seen["context"])

    def test_visit_tracking_redacts_tokens(self):
        from app.services.visitor_tracking import _redact_path, _clean_referrer
        self.assertEqual(_redact_path("/auth/reset-password/secret"), "/auth/reset-password/<redacted>")
        self.assertNotIn("secret", _clean_referrer("https://x.com/auth/verify/secret"))
        self.assertEqual(_redact_path("/pricing"), "/pricing")


if __name__ == "__main__":
    unittest.main()
