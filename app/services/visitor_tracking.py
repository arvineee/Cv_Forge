"""
CVForge AI - Visitor Tracking

Lightweight visitor tracking for the admin dashboard.

Page-view capture is deliberately kept off the request's critical path:
requests enqueue a small, privacy-conscious payload and a per-process
background worker writes visits in batches. This avoids making every
homepage request wait for a database transaction. The queue is bounded;
if it fills, analytics events are dropped rather than slowing or failing
customer requests. As with any in-process queue, events still waiting at a
process restart/reload may be lost. Core application data is never queued.
"""
import hashlib
import queue
import threading
import time
from urllib.parse import urlparse
from flask import request, session, current_app
from app.models import db, PageVisit

_QUEUE_SIZE = 2048
_BATCH_SIZE = 50
_FLUSH_WAIT_SECONDS = 0.25

# Paths/prefixes never worth logging — static assets, the tracker's own
# noise, webhooks (external services, not visitors), and API polling.
SKIP_PREFIXES = ("/static/", "/webhooks/", "/api/", "/favicon.ico")

# Paths whose last segment is a secret (reset / verify tokens, public CV links).
# The token is stored as "<redacted>" so the visits table never holds a working
# account-takeover link.
TOKEN_PREFIXES = ("/auth/reset-password/", "/auth/verify/", "/resume/")


def _redact_path(path: str) -> str:
    for prefix in TOKEN_PREFIXES:
        if path.startswith(prefix):
            return prefix + "<redacted>"
    return path

# How long to keep visit rows before pruning (see prune_old_visits below).
KEEP_DAYS = 90


def _clean_referrer(ref):
    """Referrer with any secret token path swapped for a placeholder."""
    if not ref:
        return None
    parsed = urlparse(ref)
    if any(parsed.path.startswith(p) for p in TOKEN_PREFIXES):
        return f"{parsed.scheme}://{parsed.netloc}{_redact_path(parsed.path)}"[:500]
    return ref[:500]


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


def _start_writer(app):
    """Start one bounded, batched visit writer for this app process."""
    if app.extensions.get("cvforge_visit_writer"):
        return app.extensions["cvforge_visit_writer"]

    visits = queue.Queue(maxsize=int(app.config.get("VISITOR_TRACKING_QUEUE_SIZE", _QUEUE_SIZE)))
    app.extensions["cvforge_visit_writer"] = visits

    def _write_batches():
        while True:
            try:
                first = visits.get(timeout=1.0)
            except queue.Empty:
                continue

            batch = [first]
            deadline = time.monotonic() + _FLUSH_WAIT_SECONDS
            while len(batch) < _BATCH_SIZE:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    batch.append(visits.get(timeout=remaining))
                except queue.Empty:
                    break

            try:
                with app.app_context():
                    db.session.add_all(PageVisit(**item) for item in batch)
                    db.session.commit()
            except Exception as exc:
                with app.app_context():
                    db.session.rollback()
                    app.logger.warning("Visitor tracking batch failed (non-fatal): %s", exc)
            finally:
                for _ in batch:
                    visits.task_done()

    worker = threading.Thread(
        target=_write_batches,
        name="cvforge-visitor-writer",
        daemon=True,
    )
    worker.start()
    return visits


def register_visitor_tracking(app):
    # Set VISITOR_TRACKING_ASYNC=false only for a diagnostic fallback. The
    # default keeps analytics enabled while removing its DB commit from the
    # response path. The bounded queue prevents unbounded memory growth.
    visit_queue = _start_writer(app) if app.config.get("VISITOR_TRACKING_ASYNC", True) else None

    @app.before_request
    def _track_visit():
        try:
            # Analytics records page views, not form submissions. Skipping
            # POSTs avoids unnecessary writes for login, checkout and forms.
            if request.method != "GET":
                return
            path = request.path
            if any(path.startswith(p) for p in SKIP_PREFIXES):
                return

            from flask_login import current_user
            user_id = None
            if current_user.is_authenticated:
                # Respect the existing allow_analytics opt-out for logged-in
                # users while retaining anonymous aggregate page views.
                settings = getattr(current_user, "settings", None)
                if not settings or settings.allow_analytics:
                    user_id = current_user.id

            visit_data = {
                "user_id": user_id,
                "path": _redact_path(path)[:255],
                "method": "GET",
                "ip_truncated": _truncate_ip(request.remote_addr or ""),
                "user_agent": (request.user_agent.string or "")[:300] if request.user_agent else None,
                "referrer": _clean_referrer(request.referrer),
                "session_id": _get_session_id(),
            }

            if visit_queue is None:
                db.session.add(PageVisit(**visit_data))
                db.session.commit()
                return

            try:
                visit_queue.put_nowait(visit_data)
            except queue.Full:
                # Never make a visitor wait because the optional analytics
                # queue is full. Record a rate-limited diagnostic counter.
                dropped = app.extensions.get("cvforge_visit_dropped", 0) + 1
                app.extensions["cvforge_visit_dropped"] = dropped
                if dropped == 1 or dropped % 100 == 0:
                    app.logger.warning("Visitor tracking queue full; dropped %s event(s).", dropped)
        except Exception as exc:
            # Tracking must never break the actual request.
            if visit_queue is None:
                db.session.rollback()
            current_app.logger.warning("Visit tracking failed (non-fatal): %s", exc)


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

