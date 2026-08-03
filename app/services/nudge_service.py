"""
CVForge AI - Pro-upgrade nudge service

Single source of truth for "who gets a Pro-upgrade reminder email and
when." Used by:
  - the existing `flask send-nudges` CLI command in app/cli.py (wire it
    to call send_pro_upgrade_nudges() below instead of whatever inline
    query it currently has, so the CLI and the admin panel can never
    disagree on who's eligible)
  - the new manual "Send reminders now" button on /admin/nudges

Save this as app/services/nudge_service.py.
"""
from datetime import timedelta
from app.models import db, User, UserSettings, Notification, utcnow

# Don't nudge the same free user more than once a week.
NUDGE_INTERVAL_DAYS = 7


def get_nudge_candidates():
    """Free-tier users eligible for a Pro-upgrade reminder right now:
    active, verified, opted in to email_newsletter, and either never
    nudged or not nudged within NUDGE_INTERVAL_DAYS."""
    cutoff = utcnow() - timedelta(days=NUDGE_INTERVAL_DAYS)
    return (
        User.query
        .join(UserSettings, UserSettings.user_id == User.id)
        .filter(User.plan == "free")
        .filter(User.is_active.is_(True))
        .filter(User.is_verified.is_(True))
        .filter(UserSettings.email_newsletter.is_(True))
        .filter(db.or_(
            UserSettings.last_nudge_sent_at.is_(None),
            UserSettings.last_nudge_sent_at < cutoff,
        ))
        .order_by(User.created_at.desc())
        .all()
    )


def send_pro_upgrade_nudges() -> int:
    """Email every eligible free-tier user a Pro-upgrade reminder, log an
    in-app Notification, and stamp last_nudge_sent_at so they aren't
    nudged again for NUDGE_INTERVAL_DAYS. Returns the number sent.

    NOTE: assumes an existing app/services/email_service.send_email()
    helper (matching the pdf_service/docx_service pattern already in
    this codebase). Adjust the import/call below to match your actual
    email service's signature.
    """
    from app.services.email_service import send_email

    sent = 0
    for user in get_nudge_candidates():
        try:
            send_email(
                to=user.email,
                subject="Get more out of CVForge AI \u2014 upgrade to Pro",
                template="emails/pro_nudge.html",
                first_name=user.first_name or "there",
            )
        except Exception:
            # One bad address / SMTP hiccup shouldn't stop the rest of
            # the batch — skip and keep going.
            continue

        db.session.add(Notification(
            user_id=user.id,
            title="Unlock unlimited CVs with Pro",
            message=("Upgrade to Pro for unlimited AI generations, DOCX "
                      "downloads, and version history."),
            type="upgrade",
            action_url="/billing/plans",
        ))
        user.settings.last_nudge_sent_at = utcnow()
        sent += 1

    db.session.commit()
    return sent

