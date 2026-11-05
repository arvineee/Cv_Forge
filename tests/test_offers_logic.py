"""
Logic tests for app/services/pricing.py with the database layer stubbed.
DB-backed behaviour (queries, webhooks, routes) is NOT covered here.
"""
import sys, types, importlib.util, unittest
from datetime import datetime, timedelta, timezone

import os
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EAT = timezone(timedelta(hours=3))
_module_names = ("app", "app.models", "app.services", "app.services.pricing")
_original_modules = {name: sys.modules.get(name) for name in _module_names}

# ── stub the models layer ───────────────────────────────────────
store = {"offers": [], "plans": [], "redemptions": []}

class _Q:
    def __init__(self, rows): self.rows = rows
    def filter_by(self, **kw):
        return _Q([r for r in self.rows if all(getattr(r, k, None) == v for k, v in kw.items())])
    def filter(self, *a, **k): return self
    def all(self): return list(self.rows)
    def first(self): return self.rows[0] if self.rows else None
    def order_by(self, *a): return self
    def count(self): return len(self.rows)

def _make_aware(dt):
    if dt is None: return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

class Offer:
    def __init__(self, **kw):
        self.id = len(store["offers"]) + 1
        self.is_active = True
        self.plan_slugs = None
        self.starts_at = None; self.ends_at = None; self.max_redemptions = None
        self.public_label = "x"; self.name = "x"
        self.__dict__.update(kw)
        store["offers"].append(self)
    @property
    def starts_at_aware(self): return _make_aware(self.starts_at)
    @property
    def ends_at_aware(self): return _make_aware(self.ends_at)
    def applies_to(self, slug): return not self.plan_slugs or slug in self.plan_slugs
    class _query:
        pass
Offer.query = type("Q", (), {})()
Offer.query = None

class PricingPlan:
    def __init__(self, **kw):
        self.is_active = True; self.sort_order = 0
        self.__dict__.update(kw)

class OfferRedemption:
    pass

class _Db:
    class session:
        @staticmethod
        def add(x): pass
    @staticmethod
    def or_(*a): return None
    @staticmethod
    def and_(*a): return None

def utcnow(): return datetime.utcnow()

models = types.ModuleType("app.models")
models.db = _Db; models.Offer = Offer; models.OfferRedemption = OfferRedemption
models.PricingPlan = PricingPlan; models.utcnow = utcnow; models.EAT = EAT
models._make_aware = _make_aware
app_pkg = types.ModuleType("app"); app_pkg.__path__ = []
sys.modules["app"] = app_pkg
sys.modules["app.models"] = models

# Fake query objects so pricing.py's Offer.query / PricingPlan.query work
def _install_queries():
    Offer.query = _Q(store["offers"])
    PricingPlan.query = _Q(store["plans"])
    OfferRedemption.query = _Q(store["redemptions"])

spec = importlib.util.spec_from_file_location("app.services.pricing", f"{ROOT}/app/services/pricing.py")
pricing = importlib.util.module_from_spec(spec)
sys.modules["app.services"] = types.ModuleType("app.services")
sys.modules["app.services.pricing"] = pricing
spec.loader.exec_module(pricing)
for _name, _module in _original_modules.items():
    if _module is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _module

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
BEFORE = NOW - timedelta(days=1)
AFTER = NOW + timedelta(days=1)

def reset():
    store["offers"].clear(); store["plans"].clear(); store["redemptions"].clear()
    _install_queries()
    pricing.redemption_count = lambda o: 0  # no seats used unless a test says so

def plan(slug="pro", price=499, period="month"):
    p = PricingPlan(slug=slug, price_kes=price, billing_period=period, name=slug.title())
    store["plans"].append(p)
    return p


class DiscountMath(unittest.TestCase):
    def setUp(self): reset()
    def test_percent(self):
        o = Offer(discount_type="percent", discount_value=30)
        self.assertEqual(pricing.discount_amount(o, 499), 149)   # 499*30//100
    def test_fixed(self):
        o = Offer(discount_type="fixed", discount_value=100)
        self.assertEqual(pricing.discount_amount(o, 499), 100)
    def test_floor_never_below_minimum(self):
        o = Offer(discount_type="fixed", discount_value=600)
        self.assertEqual(pricing.discount_amount(o, 499), 499 - pricing.MIN_CHARGE_KES)
    def test_tiny_base_not_discounted(self):
        o = Offer(discount_type="percent", discount_value=50)
        self.assertEqual(pricing.discount_amount(o, 10), 0)
    def test_period_days(self):
        self.assertEqual([pricing.period_days(x) for x in ["week","month","year","forever","??"]],
                         [7,30,365,30,30])


class OfferLifecycle(unittest.TestCase):
    """The core requirement: offer applies, then the price reverts when it stops being live."""
    def setUp(self): reset()

    def test_live_offer_changes_displayed_and_charged_price(self):
        p = plan(price=499)
        Offer(discount_type="percent", discount_value=30, starts_at=BEFORE, ends_at=AFTER, public_label="Sale")
        pricing.annotate_plans([p], now=NOW)
        self.assertEqual(p.display_price, 350)
        self.assertEqual(p.base_price, 499)
        charged, offer, saving = pricing.checkout_price(p, now=NOW)
        self.assertEqual((charged, saving), (350, 149))
        self.assertIsNotNone(offer)

    def test_expired_offer_reverts_to_base(self):
        p = plan(price=499)
        Offer(discount_type="percent", discount_value=30, starts_at=BEFORE - timedelta(days=5), ends_at=BEFORE)
        later = NOW
        pricing.annotate_plans([p], now=later)
        self.assertEqual(p.display_price, 499)
        self.assertIsNone(p.live_offer)
        self.assertEqual(pricing.checkout_price(p, now=later)[0], 499)

    def test_scheduled_offer_not_yet_applied(self):
        p = plan()
        Offer(discount_type="fixed", discount_value=100, starts_at=AFTER, ends_at=AFTER + timedelta(days=3))
        pricing.annotate_plans([p], now=NOW)
        self.assertEqual(p.display_price, 499)

    def test_voided_offer_reverts_even_within_dates(self):
        p = plan()
        Offer(discount_type="percent", discount_value=30, is_active=False)
        pricing.annotate_plans([p], now=NOW)
        self.assertEqual(p.display_price, 499)
        self.assertEqual(pricing.checkout_price(p, now=NOW)[0], 499)

    def test_sold_out_offer_reverts(self):
        p = plan()
        o = Offer(discount_type="percent", discount_value=30, max_redemptions=5)
        pricing.redemption_count = lambda offer: 5  # all seats used
        pricing.annotate_plans([p], now=NOW)
        self.assertEqual(p.display_price, 499)
        self.assertEqual(pricing.offer_status(o, NOW), "sold_out")

    def test_restored_offer_applies_again(self):
        p = plan()
        o = Offer(discount_type="percent", discount_value=30, is_active=False)
        pricing.annotate_plans([p], now=NOW); self.assertEqual(p.display_price, 499)
        o.is_active = True
        pricing.annotate_plans([p], now=NOW); self.assertEqual(p.display_price, 350)

    def test_offer_scoped_to_one_plan(self):
        pro = plan("pro", 499); prem = plan("premium", 1499)
        Offer(discount_type="percent", discount_value=20, plan_slugs=["premium"])
        pricing.annotate_plans([pro, prem], now=NOW)
        self.assertEqual(pro.display_price, 499)
        self.assertEqual(prem.display_price, 1200)  # 299.8 discount floors to 299

    def test_best_offer_wins_when_several_live(self):
        p = plan(price=1000)
        Offer(name="small", discount_type="percent", discount_value=10)
        Offer(name="big", discount_type="fixed", discount_value=400)
        pricing.annotate_plans([p], now=NOW)
        self.assertEqual(p.live_offer.name, "big")
        self.assertEqual(p.display_price, 600)

    def test_free_plan_never_discounted(self):
        free = plan("free", 0, "forever")
        Offer(discount_type="percent", discount_value=90)
        pricing.annotate_plans([free], now=NOW)
        self.assertEqual(free.display_price, 0)
        self.assertIsNone(free.live_offer)

    def test_banner_only_for_live_offers(self):
        plan(price=499)
        Offer(name="gone", discount_type="percent", discount_value=50, ends_at=BEFORE, public_label="Old")
        self.assertIsNone(pricing.banner_offer(now=NOW))
        Offer(name="now", discount_type="percent", discount_value=20, ends_at=AFTER, public_label="New")
        self.assertEqual(pricing.banner_offer(now=NOW).public_label, "New")


class Datetimes(unittest.TestCase):
    def test_nairobi_local_input_becomes_utc(self):
        dt = pricing.parse_local_datetime("2026-11-30T23:59")
        self.assertEqual(dt, datetime(2026, 11, 30, 20, 59, tzinfo=timezone.utc))
    def test_blank_is_none(self):
        self.assertIsNone(pricing.parse_local_datetime("  "))


if __name__ == "__main__":
    unittest.main(verbosity=2)
