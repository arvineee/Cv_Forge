"""Conservative, opt-in Pro upgrade reminders for free-tier users."""
from datetime import datetime, timedelta, timezone

from app.models import db, User, UserSettings, Notification, utcnow, _make_aware

# A user receives no more than four marketing nudges in total.
MAX_NUDGES = 4
# Safety cap per scheduled/admin-triggered run; not a per-user limit.
MAX_NUDGES_PER_RUN = 200
NUDGE_INTERVAL_DAYS = 7
REGISTERED_GRACE_DAYS = 3

NUDGE_TITLE = "Get more from CVForge with Pro"
NUDGE_MESSAGE = (
    "Pro gives you more room to improve your CV, unlock DOCX downloads and use "
    "version history. Pay by card or M-Pesa. Each subscription lasts for its "
    "plan period and does not renew automatically."
)


def get_nudge_candidates(limit=MAX_NUDGES_PER_RUN):
    """Return opted-in, verified free users below the lifetime nudge cap."""
    now = utcnow()
    nudge_cutoff = now - timedelta(days=NUDGE_INTERVAL_DAYS)
    registered_cutoff = now - timedelta(days=REGISTERED_GRACE_DAYS)
    safe_limit = max(0, min(int(limit or MAX_NUDGES_PER_RUN), MAX_NUDGES_PER_RUN))
    return (
        User.query
        .join(UserSettings, UserSettings.user_id == User.id)
        .filter(User.plan == "free")
        .filter(User.is_active.is_(True))
        .filter(User.is_verified.is_(True))
        .filter(UserSettings.email_newsletter.is_(True))
        .filter(UserSettings.nudge_count < MAX_NUDGES)
        .filter(User.created_at < registered_cutoff)
        .filter(db.or_(
            UserSettings.last_nudge_sent_at.is_(None),
            UserSettings.last_nudge_sent_at < nudge_cutoff,
        ))
        .order_by(User.created_at.desc())
        .limit(safe_limit)
        .all()
    )


def send_pro_upgrade_nudges() -> dict:
    """Send due nudges and stamp cadence only when the mailer accepts a send.

    ``sent`` means handed successfully to Flask-Mail/SMTP, not confirmed
    inbox delivery. A missing mail configuration is counted as failed and
    does not consume one of the user's four allowed reminders.
    """
    from app.services.email_service import send_pro_nudge_email

    candidates = get_nudge_candidates()
    result = {"total": len(candidates), "sent": 0, "failed": 0, "skipped": 0}
    for user in candidates:
        # Re-check under a row lock so overlapping scheduler/admin runs do
        # not both send to the same user on databases with row-lock support.
        settings = (UserSettings.query.filter_by(user_id=user.id)
                    .with_for_update().first())
        now = utcnow()
        cooldown_cutoff = datetime.now(timezone.utc) - timedelta(days=NUDGE_INTERVAL_DAYS)
        last_nudge = _make_aware(settings.last_nudge_sent_at) if settings else None
        if (not settings or not user.is_active or not user.is_verified
                or user.plan != "free" or not settings.email_newsletter
                or (settings.nudge_count or 0) >= MAX_NUDGES
                or (last_nudge and last_nudge >= cooldown_cutoff)):
            db.session.rollback()
            result["skipped"] += 1
            continue

        try:
            delivered = bool(send_pro_nudge_email(user))
        except Exception:
            db.session.rollback()
            result["failed"] += 1
            continue
        if not delivered:
            db.session.rollback()
            result["failed"] += 1
            continue

        db.session.add(Notification(
            user_id=user.id,
            title=NUDGE_TITLE,
            message=NUDGE_MESSAGE,
            type="upgrade",
            action_url="/billing/plans",
        ))
        settings.last_nudge_sent_at = now
        settings.nudge_count = (settings.nudge_count or 0) + 1
        try:
            db.session.commit()
            result["sent"] += 1
        except Exception:
            db.session.rollback()
            result["failed"] += 1

    return result
