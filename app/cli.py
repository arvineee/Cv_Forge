"""
CVForge AI - CLI Commands

Registered as Flask CLI commands so they can be scheduled via
PythonAnywhere's "Scheduled Tasks" (Tasks tab), which runs arbitrary
shell commands on a cron-like schedule. Example scheduled task command:

    cd /home/CvForge/Cv_Forge && venv/bin/flask send-nudges

Run daily. It's intentionally NOT run automatically on every request or
on app startup — nudge emails should be deliberate and scheduled, not
triggered by page traffic.

DEPENDS ON EMAIL ACTUALLY WORKING. If you're still on PythonAnywhere's
free tier (SMTP blocked) this will fail silently per-user (logged, not
crashing) until that's resolved — see email_service.py.
"""
import click
from flask import current_app
from flask.cli import with_appcontext
from datetime import timedelta


@click.command("send-nudges")
@with_appcontext
def send_nudges():
    """
    Email free-tier users an occasional reminder of what Pro unlocks.
    Cadence rules (deliberately conservative — this should never feel
    like spam):
      - Only users on the free plan
      - Only users registered more than 3 days ago (give them a chance
        to actually use the free tier first)
      - Only users who haven't been nudged in the last 7 days
      - Capped at 4 nudges total, ever, per user — after that, silence
      - Respects UserSettings.email_newsletter opt-out
    """
    from app.models import db, User, UserSettings, utcnow
    from app.services.email_service import send_pro_nudge_email

    now = utcnow()
    registered_before = now - timedelta(days=3)
    not_nudged_since = now - timedelta(days=7)
    max_nudges = 4

    candidates = (
        db.session.query(User)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .filter(
            User.plan == "free",
            User.is_active.is_(True),
            User.is_verified.is_(True),
            User.created_at <= registered_before,
        )
        .all()
    )

    sent, skipped, failed = 0, 0, 0

    for user in candidates:
        settings = user.settings
        if settings and not settings.email_newsletter:
            skipped += 1
            continue

        nudge_count = settings.nudge_count if settings else 0
        last_sent = settings.last_nudge_sent_at if settings else None

        if nudge_count >= max_nudges:
            skipped += 1
            continue
        if last_sent and last_sent > not_nudged_since:
            skipped += 1
            continue

        try:
            send_pro_nudge_email(user)
        except Exception as e:
            current_app.logger.error(f"Nudge email failed for user_id={user.id}: {e}")
            failed += 1
            continue

        if not settings:
            settings = UserSettings(user_id=user.id)
            db.session.add(settings)
        settings.last_nudge_sent_at = now
        settings.nudge_count = (settings.nudge_count or 0) + 1
        sent += 1

    db.session.commit()
    click.echo(f"Nudges: sent={sent} skipped={skipped} failed={failed} (of {len(candidates)} candidates)")


@click.command("prune-visits")
@with_appcontext
def prune_visits():
    """Delete page-visit rows older than the retention window (default 90 days)."""
    from app.services.visitor_tracking import prune_old_visits
    deleted = prune_old_visits()
    click.echo(f"Pruned {deleted} old page-visit rows.")


def register_cli(app):
    app.cli.add_command(send_nudges)
    app.cli.add_command(prune_visits)

