"""Cohort-based acquisition, activation and retention reporting.

Uses existing User, ActivityLog, PageVisit and Payment tables only. The
report intentionally distinguishes signup-cohort conversion from payments
received during the reporting window and keeps gross revenue separated by
currency.
"""
from datetime import timedelta

from sqlalchemy import func

from app.models import ActivityLog, PageVisit, Payment, User, db, utcnow

ACTIVE_ACTIONS = (
    "login", "cv_create", "cv_started", "first_cv_started",
    "cv_completed", "first_cv_completed", "cv_download",
    "first_cv_downloaded", "ats_check", "ats_check_upload",
    "cover_letter_create",
)
def _distinct_event_users(action, cohort):
    return (db.session.query(func.count(func.distinct(ActivityLog.user_id)))
            .filter(ActivityLog.action == action,
                    ActivityLog.user_id.in_(cohort)).scalar()) or 0


def build_growth_report(days=30):
    """Build a founder growth report for a 7, 30 or 90 day signup cohort."""
    days = days if days in (7, 30, 90) else 30
    cutoff = utcnow() - timedelta(days=days)
    cohort = db.session.query(User.id).filter(User.created_at >= cutoff).subquery()

    signups = User.query.filter(User.created_at >= cutoff).count()
    started_users = _distinct_event_users("first_cv_started", cohort)
    activated_users = _distinct_event_users("first_cv_completed", cohort)
    downloaded_users = _distinct_event_users("first_cv_downloaded", cohort)

    # Cohort conversion is lifetime-to-date after registration, not merely
    # customers whose payment happened to land inside the signup window.
    paid_customers = (db.session.query(func.count(func.distinct(Payment.user_id)))
        .join(User, User.id == Payment.user_id)
        .filter(User.created_at >= cutoff,
                Payment.status == "success",
                Payment.created_at >= User.created_at)
        .scalar()) or 0

    revenue_rows = (db.session.query(Payment.currency, func.sum(Payment.amount))
        .filter(Payment.status == "success", Payment.created_at >= cutoff)
        .group_by(Payment.currency).all())
    revenue_by_currency = [
        {"currency": currency or "KES", "amount": int(amount or 0)}
        for currency, amount in revenue_rows
    ]
    provider_rows = (db.session.query(
            Payment.payment_method, Payment.currency,
            func.sum(Payment.amount), func.count(Payment.id))
        .filter(Payment.status == "success", Payment.created_at >= cutoff)
        .group_by(Payment.payment_method, Payment.currency).all())
    revenue_by_provider = [
        {"provider": method or "unknown", "currency": currency or "KES",
         "amount": int(amount or 0), "payments": int(count or 0)}
        for method, currency, amount, count in provider_rows
    ]

    signup_daily = (db.session.query(func.date(User.created_at).label("day"),
                                     func.count(User.id).label("count"))
        .filter(User.created_at >= cutoff)
        .group_by("day").order_by("day").all())

    active_users = (db.session.query(func.count(func.distinct(ActivityLog.user_id)))
        .filter(ActivityLog.user_id.isnot(None),
                ActivityLog.action.in_(ACTIVE_ACTIONS),
                ActivityLog.created_at >= cutoff)
        .scalar()) or 0
    repeat_user_ids = (db.session.query(ActivityLog.user_id.label("user_id"))
        .filter(ActivityLog.user_id.isnot(None),
                ActivityLog.action.in_(ACTIVE_ACTIONS),
                ActivityLog.created_at >= cutoff)
        .group_by(ActivityLog.user_id)
        .having(func.count(func.distinct(func.date(ActivityLog.created_at))) >= 2)
        .subquery())
    repeat_active_users = (db.session.query(func.count()).select_from(repeat_user_ids).scalar()) or 0
    returning_users = (db.session.query(func.count(func.distinct(ActivityLog.user_id)))
        .join(User, User.id == ActivityLog.user_id)
        .filter(User.created_at < cutoff,
                ActivityLog.action.in_(ACTIVE_ACTIONS),
                ActivityLog.created_at >= cutoff)
        .scalar()) or 0

    registration_events = (ActivityLog.query
        .filter(ActivityLog.action == "register",
                ActivityLog.created_at >= cutoff,
                ActivityLog.user_id.isnot(None))
        .order_by(ActivityLog.created_at.desc()).all())
    source_counts = {}
    campaign_counts = {}
    for event in registration_events:
        details = event.details if isinstance(event.details, dict) else {}
        source = (details.get("acquisition_source") or "Direct / untagged")
        medium = (details.get("acquisition_medium") or "unknown")
        key = (str(source)[:120], str(medium)[:120])
        source_counts[key] = source_counts.get(key, 0) + 1
        campaign = str(details.get("acquisition_campaign") or "").strip()
        if campaign:
            campaign_counts[campaign[:120]] = campaign_counts.get(campaign[:120], 0) + 1
    acquisition_sources = [
        {"source": source, "medium": medium, "signups": count}
        for (source, medium), count in sorted(
            source_counts.items(), key=lambda item: (-item[1], item[0][0], item[0][1])
        )[:12]
    ]
    acquisition_campaigns = [
        {"campaign": campaign, "signups": count}
        for campaign, count in sorted(
            campaign_counts.items(), key=lambda item: (-item[1], item[0])
        )[:10]
    ]

    landing_sessions = (db.session.query(func.count(func.distinct(PageVisit.session_id)))
        .filter(PageVisit.path == "/", PageVisit.created_at >= cutoff,
                PageVisit.session_id.isnot(None)).scalar()) or 0
    signup_session_ids = {
        (event.details or {}).get("session_id")
        for event in registration_events
        if isinstance(event.details, dict) and (event.details or {}).get("session_id")
    }
    # Intersect in SQL instead of loading every visitor session into memory.
    landing_signups = 0
    if signup_session_ids:
        landing_signups = (db.session.query(func.count(func.distinct(PageVisit.session_id)))
            .filter(PageVisit.path == "/", PageVisit.created_at >= cutoff,
                    PageVisit.session_id.in_(signup_session_ids))
            .scalar()) or 0

    activation_rate = round(activated_users * 100 / signups, 1) if signups else 0
    paid_conversion = round(paid_customers * 100 / signups, 1) if signups else 0
    repeat_usage_rate = round(repeat_active_users * 100 / active_users, 1) if active_users else 0
    landing_signup_rate = round(landing_signups * 100 / landing_sessions, 1) if landing_sessions else 0

    funnel = [
        {"label": "Unique homepage sessions", "count": landing_sessions},
        {"label": "New registrations", "count": signups},
        {"label": "Started first CV", "count": started_users},
        {"label": "Completed first CV", "count": activated_users},
        {"label": "Downloaded first CV", "count": downloaded_users},
    ]
    funnel_rates = [
        {"label": "Homepage session → registration", "rate": landing_signup_rate},
        {"label": "Registration → first CV start",
         "rate": round(started_users * 100 / signups, 1) if signups else 0},
        {"label": "Registration → first CV completion",
         "rate": activation_rate},
        {"label": "Registration → first CV download",
         "rate": round(downloaded_users * 100 / signups, 1) if signups else 0},
    ]

    return {
        "days": days,
        "signups": signups,
        "started_users": started_users,
        "activated_users": activated_users,
        "downloaded_users": downloaded_users,
        "paid_customers": paid_customers,
        "activation_rate": activation_rate,
        "paid_conversion": paid_conversion,
        "revenue_by_currency": revenue_by_currency,
        "revenue_by_provider": revenue_by_provider,
        "signup_daily": signup_daily,
        "active_users": active_users,
        "repeat_active_users": repeat_active_users,
        "repeat_usage_rate": repeat_usage_rate,
        "returning_users": returning_users,
        "acquisition_sources": acquisition_sources,
        "acquisition_campaigns": acquisition_campaigns,
        "landing_sessions": landing_sessions,
        "landing_signups": landing_signups,
        "landing_signup_rate": landing_signup_rate,
        "funnel": funnel,
        "funnel_rates": funnel_rates,
    }
