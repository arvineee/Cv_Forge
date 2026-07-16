"""
CVForge AI - Visitor Tracking

Lightweight before_request hook that logs page visits for the admin
dashboard. Deliberately minimal — writes one row per real page view, skips
static assets/webhooks/API polling, and truncates IPs rather than storing
them in full. This is NOT meant to replace a real analytics tool if you
need funnels/retention/etc — it's just "who's visiting the site" for an
admin glance.

Performance note: this adds one DB write per page view. On SQLite +
PythonAnywhere that's fine at low-to-moderate traffic, but if CVForge
gets real volume, watch your DB file size (see KEEP_DAYS below for
pruning) and consider batching writes or moving to a real analytics
service instead.
"""
import hashlib
from flask import request, session, current_app
from app.models import db, PageVisit

# Paths/prefixes never worth logging — static assets, the tracker's own
# noise, webhooks (external services, not visitors), and API polling.
SKIP_PREFIXES = ("/static/", "/webhooks/", "/api/", "/favicon.ico")

# How long to keep visit rows before pruning (see prune_old_visits below).
KEEP_DAYS = 90


def _truncate_ip(ip: str) -> str:
    """Zero the last octet of an IPv4 address, or truncate the last
    hextet of IPv6 — keeps enough for rough geographic/traffic-pattern
    insight without storing a precise, individually-identifying address."""
    if not ip:
        return ""
    if "." in ip:  # IPv4
        parts = ip.split(".")
        if len(parts) == 4:
            parts[-1] = "0"
            return ".".join(parts)
        return ip
    if ":" in ip:  # IPv6
        parts = ip.split(":")
        return ":".join(parts[:-1] + ["0"]) if len(parts) > 1 else ip
    return ip


def _get_session_id() -> str:
    """Stable-per-browser-session id for rough unique-visitor counting,
    without needing to store anything more identifying than a hash of
    Flask's own session cookie value."""
    sid = session.get("_visit_sid")
    if not sid:
        import secrets
        sid = secrets.token_hex(16)
        session["_visit_sid"] = sid
    return hashlib.sha256(sid.encode()).hexdigest()[:32]


def register_visitor_tracking(app):
    @app.before_request
    def _track_visit():
        try:
            if request.method not in ("GET", "POST"):
                return
            path = request.path
            if any(path.startswith(p) for p in SKIP_PREFIXES):
                return

            from flask_login import current_user
            user_id = None
            if current_user.is_authenticated:
                # Respect the existing allow_analytics opt-out for
                # logged-in users — don't attribute a visit to their
                # account if they've turned tracking off, though the
                # anonymous page-view row is still recorded for
                # aggregate traffic counts.
                settings = getattr(current_user, "settings", None)
                if not settings or settings.allow_analytics:
                    user_id = current_user.id

            visit = PageVisit(
                user_id=user_id,
                path=path[:255],
                method=request.method,
                ip_truncated=_truncate_ip(request.remote_addr or ""),
                user_agent=(request.user_agent.string or "")[:300] if request.user_agent else None,
                referrer=(request.referrer or "")[:500] if request.referrer else None,
                session_id=_get_session_id(),
            )
            db.session.add(visit)
            db.session.commit()
        except Exception as e:
            # Tracking must never break the actual request.
            db.session.rollback()
            current_app.logger.warning(f"Visit tracking failed (non-fatal): {e}")


def prune_old_visits():
    """
    Delete visit rows older than KEEP_DAYS. Not scheduled automatically —
    run this periodically (e.g. via a PythonAnywhere Scheduled Task calling
    `flask prune-visits`, registered in cli.py) so the visits table doesn't
    grow unbounded on a disk-constrained PythonAnywhere plan.
    """
    from datetime import timedelta
    from app.models import utcnow
    cutoff = utcnow() - timedelta(days=KEEP_DAYS)
    deleted = PageVisit.query.filter(PageVisit.created_at < cutoff).delete()
    db.session.commit()
    return deleted

