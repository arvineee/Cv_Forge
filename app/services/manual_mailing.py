"""
CVForge AI - one-time "user manual" email to existing users.

Safe to re-run: a user who already has the manual Notification is skipped,
so nobody is emailed twice. Respects the newsletter opt-out. No schema change.
"""
import os
from flask import current_app
from app.models import db, User, UserSettings, Notification

MANUAL_NOTIFICATION_TITLE = "Your CVForge AI user manual"
MANUAL_NOTIFICATION_MESSAGE = "Read or download the CVForge AI user manual: how to build, revamp and download your CV."
DEFAULT_LIMIT = 200


def get_manual_candidates(limit=DEFAULT_LIMIT, only_email=None):
    already = db.session.query(Notification.user_id).filter(
        Notification.title == MANUAL_NOTIFICATION_TITLE)
    q = (User.query
         .outerjoin(UserSettings, UserSettings.user_id == User.id)
         .filter(User.is_active.is_(True), User.is_verified.is_(True))
         .filter(db.or_(UserSettings.id.is_(None), UserSettings.email_newsletter.is_(True)))
         .filter(~User.id.in_(already)))
    if only_email:
        q = q.filter(User.email == only_email.strip().lower())
    return q.order_by(User.created_at.asc()).limit(limit).all()


def send_manual_emails(limit=DEFAULT_LIMIT, only_email=None, dry_run=False):
    """Returns {"total", "sent", "failed", "skipped"}. dry_run only counts."""
    from app.services.email_service import send_manual_email

    users = get_manual_candidates(limit=limit, only_email=only_email)
    result = {"total": len(users), "sent": 0, "failed": 0, "skipped": 0}
    if dry_run:
        return result

    base = (current_app.config.get("SITE_URL") or os.environ.get("SITE_URL")
            or "https://cvforgeai.com")
    # url_for(_external=True) needs a request context when run from the CLI.
    with current_app.test_request_context("/", base_url=base):
        for user in users:
            try:
                ok = send_manual_email(user)
            except Exception as e:
                current_app.logger.warning(f"Manual email failed for user {user.id}: {e}")
                result["failed"] += 1
                continue
            if not ok:
                result["skipped"] += 1
                continue
            db.session.add(Notification(
                user_id=user.id, title=MANUAL_NOTIFICATION_TITLE,
                message=MANUAL_NOTIFICATION_MESSAGE, type="info", action_url="/guide"))
            db.session.commit()
            result["sent"] += 1
    return result
