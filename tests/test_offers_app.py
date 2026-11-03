"""
App-level tests for offers and feedback: real pages, real database.

Same pattern as test_app_smoke.py: skipped when the full Flask dependencies
aren't installed, and run in CI, which installs requirements.txt.

NOTE: written in a sandbox that lacked Flask and SQLAlchemy, so these have
NOT been executed yet. Run them once in CI or your own environment, and fix
any failures before relying on them.
"""
import datetime as dt
import unittest

try:
    from app import create_app
    from app.models import db, Offer, OfferRedemption, Feedback, PricingPlan, Subscription
    from app.services.pricing import checkout_price, reserve_redemption, confirm_redemption
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
class OffersOnPages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app(_TestConfig)
        cls.app.config["TESTING"] = True
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        db.create_all()
        runner = cls.app.test_cli_runner()
        runner.invoke(args=["seed-plans"])
        runner.invoke(args=["seed-templates"])
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.drop_all()
        cls.ctx.pop()

    def setUp(self):
        Offer.query.delete()
        OfferRedemption.query.delete()
        db.session.commit()

    def _pro(self):
        return PricingPlan.query.filter_by(slug="pro").first()

    def _pricing_html(self):
        return self.client.get("/pricing").get_data(as_text=True)

    def test_base_price_shown_without_offers(self):
        pro = self._pro()
        self.assertIsNotNone(pro)
        self.assertIn(f"KES {pro.price_kes}", self._pricing_html())

    def test_live_offer_shows_discounted_price_and_label(self):
        pro = self._pro()
        db.session.add(Offer(name="t", public_label="Test 30 off", discount_type="percent",
                             discount_value=30, is_active=True))
        db.session.commit()
        expected = pro.price_kes - pro.price_kes * 30 // 100
        html = self._pricing_html()
        self.assertIn(f"KES {expected}", html)
        self.assertIn("Test 30 off", html)

    def test_voided_offer_reverts_pricing_page(self):
        pro = self._pro()
        db.session.add(Offer(name="t", public_label="Gone soon", discount_type="percent",
                             discount_value=30, is_active=False))
        db.session.commit()
        html = self._pricing_html()
        self.assertIn(f"KES {pro.price_kes}", html)
        self.assertNotIn("Gone soon", html)

    def test_expired_offer_reverts(self):
        pro = self._pro()
        past = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)
        db.session.add(Offer(name="t", public_label="Old", discount_type="percent",
                             discount_value=30, is_active=True, ends_at=past))
        db.session.commit()
        self.assertIn(f"KES {pro.price_kes}", self._pricing_html())

    def test_checkout_price_is_server_side_and_reverts(self):
        pro = self._pro()
        o = Offer(name="t", public_label="x", discount_type="fixed", discount_value=100, is_active=True)
        db.session.add(o)
        db.session.commit()
        charged, offer, saving = checkout_price(pro)
        self.assertEqual((charged, saving), (pro.price_kes - 100, 100))
        o.is_active = False
        db.session.commit()
        self.assertEqual(checkout_price(pro)[0], pro.price_kes)

    def test_sold_out_offer_reverts(self):
        pro = self._pro()
        o = Offer(name="t", public_label="x", discount_type="percent", discount_value=20,
                  is_active=True, max_redemptions=1)
        db.session.add(o)
        db.session.commit()
        from app.models import Subscription as S, User
        user = User(email="offer-test@example.com", password_hash="x")
        db.session.add(user)
        db.session.flush()
        sub = S(user_id=user.id, plan=pro.slug, amount=1, currency="KES", status="active",
                payment_reference="OFFER-TEST-1")
        db.session.add(sub)
        db.session.flush()
        reserve_redemption(o, sub, user.id, pro.price_kes, 1)
        confirm_redemption(sub.id)
        db.session.commit()
        self.assertEqual(checkout_price(pro)[0], pro.price_kes)


@unittest.skipUnless(APP_AVAILABLE, "full app dependencies not installed")
class FeedbackForm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app(_TestConfig)
        cls.app.config["TESTING"] = True
        cls.ctx = cls.app.app_context()
        cls.ctx.push()
        db.create_all()
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.drop_all()
        cls.ctx.pop()

    def setUp(self):
        Feedback.query.delete()
        db.session.commit()

    def test_feedback_page_loads_for_visitors(self):
        self.assertEqual(self.client.get("/feedback").status_code, 200)

    def test_valid_feedback_is_stored(self):
        resp = self.client.post("/feedback", data={
            "category": "bug", "rating": "4", "message": "The pricing page loads slowly on my phone.",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Feedback.query.count(), 1)
        item = Feedback.query.first()
        self.assertEqual(item.category, "bug")
        self.assertEqual(item.rating, 4)

    def test_honeypot_discards_bot_submissions(self):
        self.client.post("/feedback", data={
            "category": "general", "message": "Buy cheap links now please", "website": "spam",
        })
        self.assertEqual(Feedback.query.count(), 0)

    def test_short_message_is_rejected(self):
        self.client.post("/feedback", data={"category": "general", "message": "hi"})
        self.assertEqual(Feedback.query.count(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
