"""Sprint 006 acquisition, cohort analytics and retention regressions."""
import unittest
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

try:
    from flask import session
    from app import create_app
    from app.models import (
        db, User, Profile, UserSettings, ActivityLog, PageVisit, Payment,
        Resume, Notification, utcnow,
    )
    from app.services.acquisition_tracking import (
        capture_first_touch, get_signup_attribution,
    )
    from app.services.growth_analytics import build_growth_report
    from app.services.nudge_service import (
        get_nudge_candidates, send_pro_upgrade_nudges, MAX_NUDGES,
    )
    from app.services.conversion_tracking import send_abandoned_cv_reminders
    from app.services.visitor_tracking import _clean_referrer
    APP_AVAILABLE = True
except ImportError:
    APP_AVAILABLE = False


class TestConfig:
    SECRET_KEY = "sprint006-test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    TESTING = True
    GEMINI_API_KEY = ""
    INTASEND_SECRET_KEY = ""
    UPLOAD_FOLDER = "/tmp/cvforge-sprint006-test-uploads"
    VISITOR_TRACKING_ASYNC = False
    MAIL_USERNAME = ""


@unittest.skipUnless(APP_AVAILABLE, "full Flask application dependencies not installed")
class Sprint006GrowthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app(TestConfig)

    def setUp(self):
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.drop_all()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()

    def _user(self, days_old=5, newsletter=True, nudge_count=0):
        user = User(
            email=f"sprint006-{uuid4().hex}@example.test",
            is_verified=True,
            plan="free",
            created_at=utcnow() - timedelta(days=days_old),
        )
        db.session.add(user)
        db.session.flush()
        profile = Profile(user_id=user.id, email_notifications=True)
        settings = UserSettings(
            user_id=user.id, email_newsletter=newsletter,
            nudge_count=nudge_count,
        )
        db.session.add_all([profile, settings])
        db.session.commit()
        return user

    def test_page_visit_referrer_drops_query_and_redacts_secret_paths(self):
        self.assertEqual(
            _clean_referrer("https://search.example/results?q=private&utm_campaign=launch#top"),
            "https://search.example/results",
        )
        self.assertEqual(
            _clean_referrer("https://cvforge.example/auth/reset-password/secret-token?x=1"),
            "https://cvforge.example/auth/reset-password/<redacted>",
        )

    def test_first_touch_utm_is_saved_and_not_overwritten(self):
        with self.app.test_request_context(
            "/?utm_source=linkedin&utm_medium=social&utm_campaign=global_launch"
        ):
            session["_visit_sid"] = "browser-session-006"
            first = capture_first_touch()
            self.assertEqual(first["source"], "linkedin")
            self.assertEqual(first["campaign"], "global_launch")
        # A later campaign click must not overwrite the original first touch.
        with self.app.test_request_context("/?utm_source=search&utm_medium=cpc"):
            session["_cvforge_first_touch"] = first
            session["_visit_sid"] = "browser-session-006"
            self.assertEqual(capture_first_touch()["source"], "linkedin")
            attribution = get_signup_attribution()
            self.assertEqual(attribution["acquisition_medium"], "social")
            self.assertEqual(len(attribution["session_id"]), 32)

    def test_growth_report_uses_completed_cv_and_signup_cohort_payment(self):
        user = self._user(days_old=5)
        old = user.created_at
        db.session.add_all([
            ActivityLog(user_id=user.id, action="register", created_at=old,
                        details={"session_id": "session-a", "acquisition_source": "linkedin",
                                 "acquisition_medium": "social", "acquisition_campaign": "launch"}),
            ActivityLog(user_id=user.id, action="first_cv_started", created_at=old + timedelta(hours=1)),
            ActivityLog(user_id=user.id, action="first_cv_completed", created_at=old + timedelta(days=1)),
            ActivityLog(user_id=user.id, action="login", created_at=old + timedelta(days=2)),
            ActivityLog(user_id=user.id, action="login", created_at=old + timedelta(days=3)),
            PageVisit(path="/", session_id="session-a", created_at=old),
            Payment(user_id=user.id, amount=500, currency="KES", status="success",
                    payment_method="paystack", created_at=old + timedelta(days=2)),
        ])
        db.session.commit()

        report = build_growth_report(7)
        self.assertEqual(report["signups"], 1)
        self.assertEqual(report["activated_users"], 1)
        self.assertEqual(report["paid_customers"], 1)
        self.assertEqual(report["landing_signups"], 1)
        self.assertEqual(report["acquisition_sources"][0]["source"], "linkedin")
        self.assertEqual(report["repeat_active_users"], 1)

    def test_new_user_marketing_email_preference_defaults_off(self):
        user = User(email=f"new-user-{uuid4().hex}@example.test", is_verified=True)
        db.session.add(user)
        db.session.flush()
        settings = UserSettings(user_id=user.id)
        db.session.add(settings)
        db.session.commit()
        self.assertFalse(settings.email_newsletter)

    def test_nudge_cap_is_enforced_per_user(self):
        user = self._user(nudge_count=MAX_NUDGES)
        self.assertNotIn(user.id, [candidate.id for candidate in get_nudge_candidates()])

    def test_successful_nudge_increments_count_and_reports_total(self):
        user = self._user()
        with patch("app.services.email_service.send_pro_nudge_email", return_value=True):
            result = send_pro_upgrade_nudges()
        db.session.refresh(user.settings)
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["sent"], 1)
        self.assertEqual(user.settings.nudge_count, 1)
        self.assertEqual(Notification.query.filter_by(user_id=user.id, type="upgrade").count(), 1)

    def test_failed_nudge_does_not_consume_lifetime_cap(self):
        user = self._user()
        with patch("app.services.email_service.send_pro_nudge_email", return_value=False):
            result = send_pro_upgrade_nudges()
        db.session.refresh(user.settings)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(user.settings.nudge_count, 0)
        self.assertIsNone(user.settings.last_nudge_sent_at)

    def test_service_cv_reminder_ignores_marketing_newsletter_opt_out(self):
        user = self._user(newsletter=False)
        resume = Resume(user_id=user.id, title="Unfinished CV", status="draft")
        db.session.add(resume)
        db.session.flush()
        db.session.add(ActivityLog(
            user_id=user.id, action="cv_started", resource_type="resume",
            resource_id=resume.id, created_at=utcnow() - timedelta(hours=30),
        ))
        db.session.commit()
        with patch("app.services.email_service.send_cv_abandonment_email", return_value=True):
            result = send_abandoned_cv_reminders(stage_hours=(24,), limit=10)
        self.assertEqual(result["sent"], 1)

    def test_delayed_reminder_sends_72h_stage_not_stale_24h_stage(self):
        user = self._user()
        resume = Resume(user_id=user.id, title="Delayed CV", status="draft")
        db.session.add(resume)
        db.session.flush()
        started_at = utcnow() - timedelta(hours=80)
        db.session.add_all([
            ActivityLog(user_id=user.id, action="cv_started", resource_type="resume",
                        resource_id=resume.id, created_at=started_at),
            ActivityLog(user_id=user.id, action="cv_abandonment_email_72h",
                        resource_type="resume", resource_id=resume.id,
                        created_at=utcnow() - timedelta(hours=48)),
        ])
        db.session.commit()
        with patch("app.services.email_service.send_cv_abandonment_email", return_value=True) as sender:
            result = send_abandoned_cv_reminders(stage_hours=(24, 72), limit=10)
        self.assertEqual(result["sent"], 0)
        sender.assert_not_called()

    def test_profile_preferences_separate_marketing_and_unlink_analytics(self):
        user = self._user(newsletter=True)
        db.session.add_all([
            ActivityLog(user_id=user.id, action="register", details={
                "method": "email", "session_id": "hashed-session",
                "acquisition_source": "linkedin", "acquisition_medium": "social",
            }),
            PageVisit(user_id=user.id, path="/dashboard", session_id="hashed-session"),
        ])
        db.session.commit()
        client = self.app.test_client()
        with client.session_transaction() as flask_session:
            flask_session["_user_id"] = str(user.id)
            flask_session["_fresh"] = True
        response = client.post("/dashboard/profile/update", data={
            "email_notifications": "on",
            # marketing and analytics checkboxes are intentionally omitted
        })
        self.assertEqual(response.status_code, 302)
        db.session.refresh(user.settings)
        self.assertTrue(user.profile.email_notifications)
        self.assertFalse(user.settings.email_newsletter)
        self.assertFalse(user.settings.allow_analytics)
        register_event = ActivityLog.query.filter_by(user_id=user.id, action="register").first()
        self.assertEqual(register_event.details, {"method": "email"})
        visit = PageVisit.query.filter_by(path="/dashboard").first()
        self.assertIsNone(visit.user_id)


if __name__ == "__main__":
    unittest.main()
