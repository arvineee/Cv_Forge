"""App-level Sprint 005 payment and entitlement regression tests."""
import unittest
from datetime import datetime, timedelta, timezone

try:
    from app import create_app
    from app.models import db, User, PricingPlan, Subscription, Payment, AIUsage
    from app.services.entitlements import get_daily_limit, get_effective_plan, check_daily_limit
    APP_AVAILABLE = True
except ImportError:
    APP_AVAILABLE = False


class _Config:
    SECRET_KEY = "sprint005-test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False
    TESTING = True
    GEMINI_API_KEY = ""
    GEMINI_DAILY_LIMIT = 1000
    GEMINI_FREE_USER_DAILY_LIMIT = 3
    PAYSTACK_SECRET_KEY = "test-paystack-secret"
    PAYSTACK_WEBHOOK_SECRET = ""
    INTASEND_SECRET_KEY = "test-intasend-secret"
    INTASEND_PUBLISHABLE_KEY = "test-intasend-publishable"
    INTASEND_WEBHOOK_CHALLENGE = "test-challenge"
    INTASEND_ENV = "sandbox"
    UPLOAD_FOLDER = "/tmp/cvforge-sprint005-tests"
    SESSION_COOKIE_SECURE = False
    MAIL_USERNAME = None


@unittest.skipUnless(APP_AVAILABLE, "full Flask dependencies not installed")
class Sprint005PaymentAppTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(_Config)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.drop_all()
        db.create_all()
        self.user = User(email="buyer@example.com", is_verified=True)
        db.session.add(self.user)
        self.plan = PricingPlan(
            slug="pro", name="Pro", price_kes=799, billing_period="year",
            daily_cv_limit=12, daily_cover_letter_limit=8, daily_ats_limit=6,
            allow_docx=True, allow_version_history=True,
        )
        self.free = PricingPlan(
            slug="free", name="Free", price_kes=0, billing_period="forever",
            daily_cv_limit=2, daily_cover_letter_limit=1, daily_ats_limit=3,
        )
        db.session.add_all([self.plan, self.free])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _order(self, method="mpesa", *, raw=None):
        reference = "CVF-SPRINT005"
        self.user.plan = "free"
        sub = Subscription(
            user_id=self.user.id, plan="pro", amount=799, currency="KES",
            status="pending", payment_reference=reference,
        )
        db.session.add(sub)
        db.session.flush()
        payment = Payment(
            user_id=self.user.id, subscription_id=sub.id, amount=799,
            currency="KES", status="pending", payment_method=method,
            provider_reference=reference,
            raw_webhook=raw or {
                "provider": "intasend",
                "invoice_id": "INV-005",
                "order_snapshot": {
                    "plan": "pro", "billing_period": "month", "amount": "799",
                    "currency": "KES", "user_id": self.user.id,
                },
            },
        )
        db.session.add(payment)
        db.session.commit()
        return reference, sub, payment

    def test_provider_neutral_aliases_preserve_legacy_database_columns(self):
        reference, _sub, payment = self._order()
        payment.provider_transaction_id = "INTA-TRANSACTION"
        db.session.commit()
        self.assertEqual(payment.lipana_checkout_request_id, reference)
        self.assertEqual(payment.lipana_transaction_id, "INTA-TRANSACTION")

    def test_plan_limits_are_read_from_effective_plan(self):
        self.assertEqual(get_effective_plan(self.user).slug, "free")
        self.assertEqual(get_daily_limit(self.user, "cover_letter", 3), 1)
        self.user.plan = "pro"
        self.user.plan_expires_at = datetime.now(timezone.utc) + timedelta(days=30)
        db.session.commit()
        self.assertEqual(get_effective_plan(self.user).slug, "pro")
        self.assertEqual(get_daily_limit(self.user, "cv_generate", 3), 12)
        self.assertEqual(get_daily_limit(self.user, "ats_check", 3), 6)

    def test_plan_limit_blocks_after_configured_usage(self):
        AIUsage.log_usage(self.user.id, "cover_letter", "first")
        db.session.commit()
        allowed, _message, used, limit = check_daily_limit(self.user, "cover_letter", 3)
        self.assertFalse(allowed)
        self.assertEqual((used, limit), (1, 1))

    def test_intasend_payment_activates_only_after_invoice_api_match(self):
        reference, sub, payment = self._order()
        import app.services.intasend_service as service_module
        original = service_module.IntaSendService

        class FakeIntaSend:
            def __init__(self):
                pass
            def check_status(self, invoice_id):
                return {"success": True, "invoice": {
                    "invoice_id": invoice_id, "api_ref": reference,
                    "state": "COMPLETE", "value": "799.00", "currency": "KES",
                    "provider_ref": "QWE005",
                }}

        service_module.IntaSendService = FakeIntaSend
        try:
            from app.routes.webhooks import confirm_intasend_payment
            self.assertTrue(confirm_intasend_payment(reference, "INV-005"))
        finally:
            service_module.IntaSendService = original

        db.session.refresh(sub)
        db.session.refresh(payment)
        db.session.refresh(self.user)
        self.assertEqual(sub.status, "active")
        self.assertEqual(payment.status, "success")
        self.assertEqual(payment.provider_transaction_id, "intasend:QWE005")
        self.assertEqual(self.user.plan, "pro")
        # The user bought a month even though the live plan row currently says year.
        self.assertEqual((sub.end_date - sub.start_date).days, 30)

    def test_intasend_amount_mismatch_does_not_activate(self):
        reference, sub, payment = self._order()
        import app.services.intasend_service as service_module
        original = service_module.IntaSendService

        class FakeIntaSend:
            def __init__(self):
                pass
            def check_status(self, invoice_id):
                return {"success": True, "invoice": {
                    "invoice_id": invoice_id, "api_ref": reference,
                    "state": "COMPLETE", "value": "798.00", "currency": "KES",
                }}

        service_module.IntaSendService = FakeIntaSend
        try:
            from app.routes.webhooks import confirm_intasend_payment
            self.assertFalse(confirm_intasend_payment(reference, "INV-005"))
        finally:
            service_module.IntaSendService = original

        db.session.refresh(sub)
        db.session.refresh(payment)
        self.assertEqual(sub.status, "pending")
        self.assertEqual(payment.status, "pending")

    def test_paystack_transaction_is_verified_against_local_order(self):
        reference, sub, payment = self._order(method="paystack", raw={
            "provider": "paystack",
            "order_snapshot": {
                "plan": "pro", "billing_period": "month", "amount": "799",
                "currency": "KES", "user_id": self.user.id,
            },
        })
        import app.services.paystack_service as service_module
        original = service_module.PaystackService

        class FakePaystack:
            def __init__(self):
                pass
            def verify(self, ref):
                return {"status": "success", "reference": ref, "amount": 79900,
                        "currency": "KES", "id": 123456,
                        "customer": {"email": self_email}}

        self_email = self.user.email
        service_module.PaystackService = FakePaystack
        try:
            from app.routes.webhooks import confirm_paystack_payment
            self.assertTrue(confirm_paystack_payment(reference))
        finally:
            service_module.PaystackService = original

        db.session.refresh(sub)
        db.session.refresh(payment)
        self.assertEqual(sub.status, "active")
        self.assertEqual(payment.status, "success")
        self.assertEqual(payment.provider_transaction_id, "paystack:123456")


if __name__ == "__main__":
    unittest.main()
