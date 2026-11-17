"""Effective plan and usage entitlements for CVForge.

Plan limits are read from the existing PricingPlan rows. No schema changes or
new migrations are required. An expired paid plan falls back to the free plan.
"""

LIMIT_FIELD_BY_FEATURE = {
    "cv_generate": "daily_cv_limit",
    "cv_parse": "daily_cv_limit",
    "cv_revamp": "daily_cv_limit",
    "career_coach": "daily_cv_limit",
    "cover_letter": "daily_cover_letter_limit",
    "ats_check": "daily_ats_limit",
}


def get_effective_plan(user):
    """Return the current valid plan row, falling back to the configured free row."""
    from app.models import PricingPlan

    paid = bool(getattr(user, "has_paid_plan", False))
    slug = getattr(user, "plan", None) if paid else "free"
    plan = PricingPlan.query.filter_by(slug=slug).first() if slug else None
    if plan:
        return plan
    if slug != "free":
        return PricingPlan.query.filter_by(slug="free").first()
    return None


def get_daily_limit(user, feature, fallback_limit=3):
    """Resolve the per-feature daily limit from the user's effective plan."""
    field = LIMIT_FIELD_BY_FEATURE.get(feature)
    plan = get_effective_plan(user)
    raw_limit = getattr(plan, field, None) if plan and field else None
    if raw_limit is None:
        raw_limit = fallback_limit
    try:
        return max(0, int(raw_limit))
    except (TypeError, ValueError):
        return max(0, int(fallback_limit or 0))


def check_daily_limit(user, feature, fallback_limit=3, *, label=None):
    """Return (allowed, message, used, limit) for a user's daily AI allowance."""
    from app.models import AIUsage

    used = AIUsage.get_daily_count(user.id, feature)
    limit = get_daily_limit(user, feature, fallback_limit)
    if used < limit:
        return True, "", used, limit
    feature_label = label or {
        "cv_generate": "CV AI assistance",
        "cv_parse": "CV parsing",
        "cv_revamp": "CV revamp",
        "career_coach": "Career Coach",
        "cover_letter": "cover letter generation",
        "ats_check": "ATS checks",
    }.get(feature, feature.replace("_", " "))
    return False, f"Daily {feature_label} limit reached ({limit}/day). Upgrade your plan for more access.", used, limit
