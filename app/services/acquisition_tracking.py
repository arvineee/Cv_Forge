"""First-touch acquisition attribution using the existing signed Flask session.

No database schema changes are required: the compact attribution snapshot is
copied into the existing ActivityLog.details JSON when an account registers.
Only campaign labels and a referrer hostname are retained; query strings and
full referrer URLs are deliberately not stored.
"""
import re
from urllib.parse import urlparse

from flask import request, session

SESSION_KEY = "_cvforge_first_touch"
UTM_FIELDS = {
    "utm_source": "utm_source",
    "utm_medium": "utm_medium",
    "utm_campaign": "utm_campaign",
    "utm_content": "utm_content",
    "utm_term": "utm_term",
}
MAX_VALUE_LENGTH = 120


def _clean_value(value, max_length=MAX_VALUE_LENGTH):
    """Normalize a campaign label without accepting control characters."""
    if value is None:
        return ""
    value = re.sub(r"[\x00-\x1f\x7f]", "", str(value)).strip()
    return value[:max_length]


def _external_referrer_host(referrer):
    if not referrer:
        return ""
    try:
        parsed = urlparse(referrer)
        host = (parsed.hostname or "").lower().strip(".")
        request_host = (request.host or "").split(":", 1)[0].lower().strip(".")
        if request_host.startswith("www."):
            request_host = request_host[4:]
        if not host or host == request_host:
            return ""
        return host[4:] if host.startswith("www.") else host
    except (TypeError, ValueError):
        return ""


def capture_first_touch():
    """Capture first-touch attribution once per browser session.

    Called by visitor tracking on the first eligible GET. Safe to call again
    from registration/OAuth handlers as a fallback when tracking is disabled.
    """
    existing = session.get(SESSION_KEY)
    if isinstance(existing, dict) and existing.get("source"):
        return existing

    values = {
        key: _clean_value(request.args.get(query_key))
        for query_key, key in UTM_FIELDS.items()
    }
    referrer_host = _external_referrer_host(request.referrer)
    source = values["utm_source"] or referrer_host or "direct"
    medium = values["utm_medium"] or ("referral" if referrer_host else "direct")

    attribution = {
        "source": _clean_value(source),
        "medium": _clean_value(medium),
        "campaign": values["utm_campaign"],
        "content": values["utm_content"],
        "term": values["utm_term"],
        "referrer_host": referrer_host,
        "landing_path": _clean_value(request.path, 180) or "/",
        "model": "first_touch",
    }
    session[SESSION_KEY] = attribution
    return attribution


def get_signup_attribution():
    """Return the compact first-touch snapshot plus the shared session ID."""
    from app.services.visitor_tracking import get_analytics_session_id

    attribution = session.get(SESSION_KEY)
    if not isinstance(attribution, dict) or not attribution.get("source"):
        attribution = capture_first_touch()
    # Rebuild the allow-listed structure; never copy arbitrary session data.
    result = {
        "acquisition_source": _clean_value(attribution.get("source")) or "direct",
        "acquisition_medium": _clean_value(attribution.get("medium")) or "direct",
        "acquisition_campaign": _clean_value(attribution.get("campaign")),
        "acquisition_content": _clean_value(attribution.get("content")),
        "acquisition_term": _clean_value(attribution.get("term")),
        "referrer_host": _clean_value(attribution.get("referrer_host")),
        "landing_path": _clean_value(attribution.get("landing_path"), 180) or "/",
        "attribution_model": "first_touch",
        "session_id": get_analytics_session_id(),
    }
    return result
