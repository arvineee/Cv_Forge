"""
CVForge AI - Pricing & Offers

Single source of truth for what a customer pays.

Design rules:
- PricingPlan.price_kes is the base price and is never modified by offers.
- An Offer is an overlay. Its effective price is computed on every read,
  so an expired, sold-out, or voided offer reverts to base automatically.
- The browser never sends a price. Checkout calls checkout_price() on the
  server, so a voided offer can't be charged even if the page was stale.
- Redemption seats: a pending checkout holds a seat for PENDING_HOLD. After
  that it stops counting, so abandoned checkouts don't block an offer forever.
  (Known limit: the cap check is not row-locked, so a burst of simultaneous
  checkouts can overshoot max_redemptions by a few. Acceptable at this scale.)
"""
from datetime import datetime, timedelta, timezone

from app.models import db, Offer, OfferRedemption, PricingPlan, utcnow, EAT

MIN_CHARGE_KES = 10              # never discount a plan below this
PENDING_HOLD = timedelta(minutes=30)
PERIOD_DAYS = {"week": 7, "month": 30, "year": 365}


def period_days(billing_period: str) -> int:
    """How long a plan lasts once paid. 'forever' (free) and unknowns get 30."""
    return PERIOD_DAYS.get(billing_period, 30)


def _now():
    return datetime.now(timezone.utc)


# ── Offer status and discount math ───────────────────────────────

def redemption_count(offer: Offer) -> int:
    cutoff = utcnow() - PENDING_HOLD  # naive UTC, matches how created_at is stored
    return (OfferRedemption.query
            .filter(OfferRedemption.offer_id == offer.id)
            .filter(db.or_(
                OfferRedemption.status == "redeemed",
                db.and_(OfferRedemption.status == "pending",
                        OfferRedemption.created_at >= cutoff),
            )).count())


def offer_status(offer: Offer, now=None) -> str:
    """voided | scheduled | expired | sold_out | live"""
    now = now or _now()
    if not offer.is_active:
        return "voided"
    starts, ends = offer.starts_at_aware, offer.ends_at_aware
    if starts and now < starts:
        return "scheduled"
    if ends and now >= ends:
        return "expired"
    if offer.max_redemptions and redemption_count(offer) >= offer.max_redemptions:
        return "sold_out"
    return "live"


def discount_amount(offer: Offer, base_price: int) -> int:
    """KES taken off base_price. Never drops the price below MIN_CHARGE_KES."""
    if base_price <= MIN_CHARGE_KES:
        return 0
    if offer.discount_type == "percent":
        # Floor the discount, so the price rounds up to a whole shilling in the business's favour.
        raw = base_price * offer.discount_value // 100
    else:
        raw = offer.discount_value
    return max(0, min(raw, base_price - MIN_CHARGE_KES))


def _best_live_offer(plan: PricingPlan, offers, now):
    """Live offer that saves the customer the most on this plan, or None."""
    best, best_saving = None, 0
    if plan.price_kes <= 0:
        return None
    for offer in offers:
        if not offer.applies_to(plan.slug):
            continue
        if offer_status(offer, now) != "live":
            continue
        saving = discount_amount(offer, plan.price_kes)
        if saving > best_saving:
            best, best_saving = offer, saving
    return best


# ── Public API used by routes and templates ──────────────────────

def annotate_plans(plans, now=None):
    """
    Attach display attributes to plan objects for templates. These are
    transient and never written to the database:
      base_price     - the real price
      display_price  - what the customer pays right now
      live_offer     - the Offer in effect, or None
      saving         - KES off
      period_days    - how long one payment lasts
    """
    now = now or _now()
    offers = Offer.query.filter_by(is_active=True).all()
    for plan in plans:
        plan.base_price = plan.price_kes
        plan.period_days = period_days(plan.billing_period)
        plan.live_offer = None
        plan.saving = 0
        plan.display_price = plan.price_kes
        offer = _best_live_offer(plan, offers, now)
        if offer:
            saving = discount_amount(offer, plan.price_kes)
            plan.live_offer = offer
            plan.saving = saving
            plan.display_price = plan.price_kes - saving
    return plans


def checkout_price(plan: PricingPlan, now=None):
    """
    Authoritative price for a checkout starting right now.
    Returns (charged_kes, offer_or_None, saving_kes).
    """
    now = now or _now()
    offers = Offer.query.filter_by(is_active=True).all()
    offer = _best_live_offer(plan, offers, now)
    if not offer:
        return plan.price_kes, None, 0
    saving = discount_amount(offer, plan.price_kes)
    return plan.price_kes - saving, offer, saving


def banner_offer(now=None):
    """The live offer with the biggest saving on any paid plan, for the pricing banner."""
    now = now or _now()
    offers = Offer.query.filter_by(is_active=True).all()
    best, best_saving = None, 0
    for offer in offers:
        if offer_status(offer, now) != "live":
            continue
        for plan in PricingPlan.query.filter_by(is_active=True).all():
            if plan.price_kes > 0 and offer.applies_to(plan.slug):
                saving = discount_amount(offer, plan.price_kes)
                if saving > best_saving:
                    best, best_saving = offer, saving
    return best


# ── Plan changes: renew, upgrade, downgrade ───────────────────────
#
# One place decides what a successful payment does to a user's plan, so the
# webhook, the status-poll reconcile and admin claim approval all agree.
#
#   same plan, still active   -> RENEW: new days are added after the current
#                                expiry, so paying early never loses time.
#   higher-priced plan        -> UPGRADE: switches now, full new period from today.
#                                (Unused days on the old plan are not credited.)
#   lower-priced plan         -> blocked at checkout (see purchase_blocker). If one
#                                still gets paid, e.g. two checkouts in flight, the
#                                user keeps the higher plan and the paid days are
#                                added to it, so nobody loses money.

def _plan_price(slug: str) -> int:
    row = PricingPlan.query.filter_by(slug=slug).first()
    return row.price_kes if row else 0


def _active_paid_expiry(user):
    """Aware expiry of the user's current paid plan, or None if free/expired."""
    from app.models import _make_aware
    if not user.plan or user.plan == "free" or not user.plan_expires_at:
        return None
    expiry = _make_aware(user.plan_expires_at)
    return expiry if expiry > _now() else None


def resolve_plan_change(user, new_slug: str, days: int, now=None):
    """Return (plan_slug, expires_at, kind) for a paid purchase. kind is
    'new', 'renewal', 'upgrade' or 'kept_higher'. Does not modify the user."""
    now = now or _now()
    expiry = _active_paid_expiry(user)
    if expiry is None:
        return new_slug, now + timedelta(days=days), "new"
    if user.plan == new_slug:
        return new_slug, expiry + timedelta(days=days), "renewal"
    if _plan_price(new_slug) > _plan_price(user.plan):
        return new_slug, now + timedelta(days=days), "upgrade"
    return user.plan, expiry + timedelta(days=days), "kept_higher"


def purchase_blocker(user, plan: PricingPlan):
    """Message explaining why this purchase should not go ahead, or None."""
    expiry = _active_paid_expiry(user)
    if expiry is None or user.plan == plan.slug:
        return None
    if plan.price_kes < _plan_price(user.plan):
        until = expiry.astimezone(EAT).strftime("%d %b %Y")
        return (f"Your {user.plan.title()} plan is active until {until}, so you can't buy a "
                f"cheaper plan now. Renew {user.plan.title()} or upgrade instead.")
    return None


# ── Redemption bookkeeping (called from billing and webhooks) ────

def reserve_redemption(offer: Offer, subscription, user_id: int, base: int, charged: int):
    """Call after subscription has been flushed (so it has an id)."""
    db.session.add(OfferRedemption(
        offer_id=offer.id, subscription_id=subscription.id, user_id=user_id,
        base_amount=base, charged_amount=charged, status="pending",
    ))


def confirm_redemption(subscription_id: int):
    r = OfferRedemption.query.filter_by(subscription_id=subscription_id).first()
    if r and r.status != "redeemed":
        r.status = "redeemed"


def release_redemption(subscription_id: int):
    r = OfferRedemption.query.filter_by(subscription_id=subscription_id).first()
    if r and r.status == "pending":
        r.status = "released"


# ── Parsing admin form input ─────────────────────────────────────


def parse_local_datetime(raw: str):
    """'2026-11-30T23:59' (Nairobi local, from datetime-local input) -> aware UTC. None if blank."""
    raw = (raw or "").strip()
    if not raw:
        return None
    local = datetime.strptime(raw, "%Y-%m-%dT%H:%M").replace(tzinfo=EAT)
    return local.astimezone(timezone.utc)
