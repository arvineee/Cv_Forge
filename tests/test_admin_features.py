"""Stop-impersonation, plan changes, broadcast sending and pricing-form validation."""
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
    LIPANA_WEBHOOK_SECRET = "s"
    INTASEND_WEBHOOK_CHALLENGE = "c"
    SESSION_COOKIE_SECURE = False
    MAIL_USERNAME = None
    BROADCAST_SYNC = True


class Base(unittest.TestCase):
    def setUp(self):
        from app import create_app
        from app.models import db, User, PricingPlan
        self.db = db
        self.app = create_app(Cfg)
        with self.app.app_context():
            db.create_all()
            admin = User(email="admin@x.com", is_verified=True, is_admin=True)
            user = User(email="user@x.com", is_verified=True)
            for u in (admin, user):
                u.set_password("password1")
            db.session.add_all([admin, user])
            db.session.add_all([
                PricingPlan(slug="free", name="Free", price_kes=0, billing_period="forever"),
                PricingPlan(slug="basic", name="Basic", price_kes=300, billing_period="month"),
                PricingPlan(slug="pro", name="Pro", price_kes=800, billing_period="month"),
            ])
            db.session.commit()
            self.admin_id, self.user_id = admin.id, user.id
        self.client = self.app.test_client()

    def login(self, uid):
        with self.client.session_transaction() as s:
            s["_user_id"] = str(uid)
            s["_fresh"] = True


class ImpersonationTests(Base):
    def test_start_then_stop_returns_to_admin(self):
        self.login(self.admin_id)
        self.client.post(f"/admin/users/{self.user_id}/impersonate")
        with self.client.session_transaction() as s:
            self.assertEqual(s["_user_id"], str(self.user_id))
            self.assertEqual(s["impersonator_id"], self.admin_id)
        page = self.client.get("/dashboard/")
        self.assertIn(b"Stop impersonating", page.data)

        self.client.post("/admin/stop-impersonation")
        with self.client.session_transaction() as s:
            self.assertEqual(s["_user_id"], str(self.admin_id))
            self.assertNotIn("impersonator_id", s)
        self.assertNotIn(b"Stop impersonating", self.client.get("/dashboard/").data)

    def test_stop_without_impersonating_does_nothing(self):
        self.login(self.user_id)
        self.client.post("/admin/stop-impersonation")
        with self.client.session_transaction() as s:
            self.assertEqual(s["_user_id"], str(self.user_id))

    def test_regular_user_cannot_forge_the_marker_to_become_admin(self):
        """The marker only works if it names a real, active admin."""
        self.login(self.user_id)
        with self.client.session_transaction() as s:
            s["impersonator_id"] = self.user_id  # a non-admin
        self.client.post("/admin/stop-impersonation")
        with self.client.session_transaction() as s:
            self.assertEqual(s["_user_id"], str(self.user_id))

    def test_cannot_impersonate_self_or_inactive(self):
        from app.models import User
        self.login(self.admin_id)
        self.client.post(f"/admin/users/{self.admin_id}/impersonate")
        with self.client.session_transaction() as s:
            self.assertNotIn("impersonator_id", s)
        with self.app.app_context():
            self.db.session.get(User, self.user_id).is_active = False
            self.db.session.commit()
        self.client.post(f"/admin/users/{self.user_id}/impersonate")
        with self.client.session_transaction() as s:
            self.assertEqual(s["_user_id"], str(self.admin_id))


class PlanChangeTests(Base):
    def _user(self, plan, days):
        from app.models import User
        u = self.db.session.get(User, self.user_id)
        u.plan = plan
        u.plan_expires_at = datetime.now(timezone.utc) + timedelta(days=days) if plan != "free" else None
        self.db.session.commit()
        return u

    def test_new_purchase(self):
        from app.services.pricing import resolve_plan_change
        with self.app.app_context():
            u = self._user("free", 0)
            plan, exp, kind = resolve_plan_change(u, "pro", 30)
            self.assertEqual((plan, kind), ("pro", "new"))
            self.assertAlmostEqual((exp - datetime.now(timezone.utc)).days, 29, delta=1)

    def test_renewal_stacks_remaining_time(self):
        from app.services.pricing import resolve_plan_change
        with self.app.app_context():
            u = self._user("pro", 10)
            plan, exp, kind = resolve_plan_change(u, "pro", 30)
            self.assertEqual(kind, "renewal")
            self.assertAlmostEqual((exp - datetime.now(timezone.utc)).days, 39, delta=1)

    def test_upgrade_switches_now(self):
        from app.services.pricing import resolve_plan_change
        with self.app.app_context():
            u = self._user("basic", 10)
            plan, exp, kind = resolve_plan_change(u, "pro", 30)
            self.assertEqual((plan, kind), ("pro", "upgrade"))
            self.assertAlmostEqual((exp - datetime.now(timezone.utc)).days, 29, delta=1)

    def test_lower_plan_keeps_higher_and_adds_days(self):
        from app.services.pricing import resolve_plan_change
        with self.app.app_context():
            u = self._user("pro", 10)
            plan, exp, kind = resolve_plan_change(u, "basic", 30)
            self.assertEqual((plan, kind), ("pro", "kept_higher"))
            self.assertAlmostEqual((exp - datetime.now(timezone.utc)).days, 39, delta=1)

    def test_expired_plan_is_treated_as_new(self):
        from app.services.pricing import resolve_plan_change
        with self.app.app_context():
            u = self._user("pro", -3)
            self.assertEqual(resolve_plan_change(u, "basic", 30)[2], "new")

    def test_checkout_blocks_cheaper_plan_while_higher_active(self):
        from app.models import PricingPlan
        from app.services.pricing import purchase_blocker
        with self.app.app_context():
            u = self._user("pro", 10)
            basic = PricingPlan.query.filter_by(slug="basic").first()
            pro = PricingPlan.query.filter_by(slug="pro").first()
            self.assertIn("Renew", purchase_blocker(u, basic))
            self.assertIsNone(purchase_blocker(u, pro))

    def test_webhook_renewal_extends_expiry(self):
        from app.models import User, Subscription
        from app.routes.webhooks import _handle_payment_success
        with self.app.app_context():
            u = self._user("pro", 10)
            self.db.session.add(Subscription(user_id=u.id, plan="pro", amount=800,
                                             status="pending", payment_reference="R1"))
            self.db.session.commit()
            self.assertTrue(_handle_payment_success({"reference": "R1"}))
            exp = self.db.session.get(User, self.user_id).plan_expires_at
            exp = exp.replace(tzinfo=timezone.utc) if exp.tzinfo is None else exp
            self.assertAlmostEqual((exp - datetime.now(timezone.utc)).days, 39, delta=1)

    def test_custom_slug_counts_as_paid(self):
        with self.app.app_context():
            u = self._user("weekly-pass", 5)
            self.assertTrue(u.has_paid_plan)


class BroadcastTests(Base):
    def setUp(self):
        super().setUp()
        import app.services.email_service as es
        original = es.send_broadcast_email
        self.addCleanup(setattr, es, "send_broadcast_email", original)

    def _post(self, **extra):
        data = {"subject": "Hello", "body": "Body text", "audience": "all"}
        data.update(extra)
        return self.client.post("/admin/broadcast", data=data)

    def test_broadcast_sends_and_records_totals(self):
        import app.services.email_service as es
        from app.models import BroadcastEmail
        sent_to = []
        es.send_broadcast_email = lambda user, s, b, conn=None: sent_to.append(user.email) or True
        self.login(self.admin_id)
        resp = self._post()
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(sorted(sent_to), ["admin@x.com", "user@x.com"])
        with self.app.app_context():
            row = BroadcastEmail.query.first()
            self.assertEqual((row.recipient_count, row.failed_count), (2, 0))
            from app.routes.admin import _broadcast_state
            self.assertEqual(_broadcast_state(row), ("done", 2))

    def test_failures_are_counted(self):
        import app.services.email_service as es
        from app.models import BroadcastEmail
        def flaky(user, s, b, conn=None):
            if user.email.startswith("user"):
                raise RuntimeError("smtp down")
            return True
        es.send_broadcast_email = flaky
        self.login(self.admin_id)
        self._post()
        with self.app.app_context():
            row = BroadcastEmail.query.first()
            self.assertEqual((row.recipient_count, row.failed_count), (1, 1))

    def test_second_broadcast_blocked_while_one_is_sending(self):
        from app.models import ActivityLog, BroadcastEmail
        with self.app.app_context():
            row = BroadcastEmail(subject="s", body="b", audience="all")
            self.db.session.add(row); self.db.session.flush()
            self.db.session.add(ActivityLog(action="admin_broadcast_started",
                                            resource_type="broadcast_email",
                                            resource_id=row.id, details={"total": 5}))
            self.db.session.commit()
        self.login(self.admin_id)
        self._post()
        with self.app.app_context():
            self.assertEqual(BroadcastEmail.query.count(), 1)

    def test_status_endpoint(self):
        import app.services.email_service as es
        es.send_broadcast_email = lambda *a, **k: True
        self.login(self.admin_id)
        self._post()
        data = self.client.get("/admin/broadcast/1/status").get_json()
        self.assertEqual((data["state"], data["sent"], data["total"]), ("done", 2, 2))


class PricingFormTests(Base):
    def _form(self, **over):
        f = {"name": "Weekly", "slug": "weekly", "price_kes": "150", "billing_period": "week",
             "sort_order": "4", "daily_cv_limit": "10", "daily_cover_letter_limit": "10",
             "daily_ats_limit": "10", "features": "One\nTwo", "is_active": "1"}
        f.update(over)
        return f

    def test_valid_plan_created(self):
        from app.models import PricingPlan
        self.login(self.admin_id)
        r = self.client.post("/admin/pricing/new", data=self._form())
        self.assertEqual(r.status_code, 302)
        with self.app.app_context():
            p = PricingPlan.query.filter_by(slug="weekly").first()
            self.assertEqual((p.price_kes, p.features), (150, ["One", "Two"]))

    def test_bad_number_is_a_form_error_not_a_500(self):
        self.login(self.admin_id)
        r = self.client.post("/admin/pricing/new", data=self._form(price_kes="abc"))
        self.assertEqual(r.status_code, 400)
        self.assertIn(b"Price must be a whole number", r.data)
        self.assertIn(b'value="Weekly"', r.data)          # typed values kept

    def test_duplicate_and_invalid_slug_rejected(self):
        self.login(self.admin_id)
        self.assertEqual(self.client.post("/admin/pricing/new", data=self._form(slug="pro")).status_code, 400)
        self.assertEqual(self.client.post("/admin/pricing/new", data=self._form(slug="Bad Slug!")).status_code, 400)

    def test_paid_plan_cannot_be_forever(self):
        self.login(self.admin_id)
        r = self.client.post("/admin/pricing/new", data=self._form(billing_period="forever"))
        self.assertEqual(r.status_code, 400)

    def test_rename_blocked_when_in_use(self):
        from app.models import PricingPlan, Subscription
        with self.app.app_context():
            self.db.session.add(Subscription(user_id=self.user_id, plan="pro", amount=800,
                                             status="active", payment_reference="R"))
            self.db.session.commit()
            pid = PricingPlan.query.filter_by(slug="pro").first().id
        self.login(self.admin_id)
        r = self.client.post(f"/admin/pricing/{pid}/edit",
                             data=self._form(name="Pro", slug="pro2", price_kes="800", billing_period="month"))
        self.assertEqual(r.status_code, 400)
        with self.app.app_context():
            self.assertEqual(self.db.session.get(PricingPlan, pid).slug, "pro")

    def test_edit_updates_unused_plan_and_keeps_own_slug(self):
        from app.models import PricingPlan
        with self.app.app_context():
            pid = PricingPlan.query.filter_by(slug="basic").first().id
        self.login(self.admin_id)
        r = self.client.post(f"/admin/pricing/{pid}/edit",
                             data=self._form(name="Basic+", slug="basic", price_kes="350", billing_period="month"))
        self.assertEqual(r.status_code, 302)
        with self.app.app_context():
            self.assertEqual(self.db.session.get(PricingPlan, pid).price_kes, 350)

    def test_delete_in_use_deactivates_unused_deletes_free_protected(self):
        from app.models import PricingPlan, Subscription
        with self.app.app_context():
            self.db.session.add(Subscription(user_id=self.user_id, plan="pro", amount=800,
                                             status="active", payment_reference="R"))
            self.db.session.commit()
            ids = {p.slug: p.id for p in PricingPlan.query.all()}
        self.login(self.admin_id)
        self.client.post(f"/admin/pricing/{ids['pro']}/delete")
        self.client.post(f"/admin/pricing/{ids['basic']}/delete")
        self.client.post(f"/admin/pricing/{ids['free']}/delete")
        with self.app.app_context():
            self.assertFalse(self.db.session.get(PricingPlan, ids["pro"]).is_active)
            self.assertIsNone(self.db.session.get(PricingPlan, ids["basic"]))
            self.assertIsNotNone(self.db.session.get(PricingPlan, ids["free"]))


if __name__ == "__main__":
    unittest.main()


class BroadcastRealMailPathTests(Base):
    def test_uses_mail_connection_when_configured(self):
        """With mail configured, one flask-mail connection is opened and used per user."""
        import flask_mail
        from app.models import BroadcastEmail
        calls = {"connect": 0, "send": 0}
        orig_connect = flask_mail.Mail.connect

        class Conn:
            def __enter__(s):
                calls["connect"] += 1
                return s
            def __exit__(s, *a):
                return False
            def send(s, msg):
                calls["send"] += 1

        flask_mail.Mail.connect = lambda self: Conn()
        self.addCleanup(setattr, flask_mail.Mail, "connect", orig_connect)
        self.app.config.update(MAIL_USERNAME="u", MAIL_DEFAULT_SENDER="n@x.com")
        self.login(self.admin_id)
        self.client.post("/admin/broadcast", data={"subject": "Hi", "body": "Text", "audience": "all"})
        self.assertEqual(calls, {"connect": 1, "send": 2})
        with self.app.app_context():
            row = BroadcastEmail.query.first()
            self.assertEqual((row.recipient_count, row.failed_count), (2, 0))
