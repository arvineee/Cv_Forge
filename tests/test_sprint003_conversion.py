"""Sprint 003 conversion event tests (requires the full Flask dependencies)."""
import unittest
from uuid import uuid4

try:
    from app import create_app
    from app.models import db, User, Resume, ActivityLog
    from app.services.conversion_tracking import (
        mark_cv_started, mark_cv_completed, resume_is_complete,
    )
    APP_AVAILABLE = True
except ImportError:
    APP_AVAILABLE = False


class TestConfig:
    SECRET_KEY = "sprint003-test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    TESTING = True
    GEMINI_API_KEY = ""
    LIPANA_API_KEY = ""
    INTASEND_SECRET_KEY = ""
    UPLOAD_FOLDER = "/tmp/cvforge-sprint003-test-uploads"
    VISITOR_TRACKING_ASYNC = False


@unittest.skipUnless(APP_AVAILABLE, "full app dependencies not installed")
class Sprint003ConversionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app(TestConfig)
        with cls.app.app_context():
            db.create_all()

    def setUp(self):
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.user = User(email=f"sprint003-{uuid4().hex}@example.test", is_verified=True)
        db.session.add(self.user)
        db.session.flush()
        self.resume = Resume(user_id=self.user.id, title="Test CV", status="draft")
        db.session.add(self.resume)
        db.session.commit()

    def tearDown(self):
        db.session.rollback()
        self.ctx.pop()

    def test_start_events_are_idempotent(self):
        mark_cv_started(self.user.id, self.resume.id)
        mark_cv_started(self.user.id, self.resume.id)
        db.session.commit()
        self.assertEqual(ActivityLog.query.filter_by(user_id=self.user.id, action="cv_started").count(), 1)
        self.assertEqual(ActivityLog.query.filter_by(user_id=self.user.id, action="first_cv_started").count(), 1)

    def test_completion_requires_contact_and_content(self):
        self.assertFalse(resume_is_complete(self.resume))
        self.resume.personal_info = {"full_name": "A Person", "email": "a@example.test"}
        self.resume.skills = ["Python"]
        self.assertTrue(resume_is_complete(self.resume))

    def test_first_completion_is_recorded_once(self):
        self.resume.personal_info = {"full_name": "A Person", "email": "a@example.test"}
        self.resume.professional_summary = "Experienced professional."
        db.session.commit()
        mark_cv_completed(self.user.id, self.resume)
        mark_cv_completed(self.user.id, self.resume)
        db.session.commit()
        self.assertEqual(ActivityLog.query.filter_by(user_id=self.user.id, action="cv_completed", resource_id=self.resume.id).count(), 1)
        self.assertEqual(ActivityLog.query.filter_by(user_id=self.user.id, action="first_cv_completed").count(), 1)


if __name__ == "__main__":
    unittest.main()
