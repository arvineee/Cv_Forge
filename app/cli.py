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
from flask.cli import with_appcontext


@click.command("send-nudges")
@with_appcontext
def send_nudges():
    """
    Email free-tier users an occasional reminder of what Pro unlocks.
    Cadence rules (deliberately conservative — this should never feel
    like spam) now live in app/services/nudge_service.py, shared with
    the "Send reminders now" button in the admin panel:
      - Only users on the free plan
      - Only users registered more than 3 days ago (give them a chance
        to actually use the free tier first)
      - Only users who haven't been nudged in the last 7 days
      - Capped at 4 nudges total, ever, per user — after that, silence
      - Respects UserSettings.email_newsletter opt-out
    """
    from app.services.nudge_service import send_pro_upgrade_nudges

    result = send_pro_upgrade_nudges()
    click.echo(
        f"Nudges: sent={result['sent']} failed={result['failed']} "
        f"skipped={result.get('skipped', 0)} (of {result['total']} candidates)"
    )


@click.command("prune-visits")
@with_appcontext
def prune_visits():
    """Delete page-visit rows older than the retention window (default 90 days)."""
    from app.services.visitor_tracking import prune_old_visits
    deleted = prune_old_visits()
    click.echo(f"Pruned {deleted} old page-visit rows.")


@click.command("send-manual-email")
@click.option("--limit", default=200, show_default=True, help="Max emails in this run.")
@click.option("--only", "only_email", default=None, help="Send to this one user only (for a test).")
@click.option("--dry-run", is_flag=True, help="Count who would be emailed; send nothing.")
@with_appcontext
def send_manual_email_cmd(limit, only_email, dry_run):
    """Email existing users a link to the user manual (once per user)."""
    from app.services.manual_mailing import send_manual_emails
    r = send_manual_emails(limit=limit, only_email=only_email, dry_run=dry_run)
    label = "Would send" if dry_run else "Manual emails"
    click.echo(f"{label}: total={r['total']} sent={r['sent']} failed={r['failed']} skipped={r['skipped']}")


def register_cli(app):
    app.cli.add_command(send_manual_email_cmd)
    app.cli.add_command(send_nudges)
    app.cli.add_command(prune_visits)
    app.cli.add_command(send_cv_reminders_cmd)
    app.cli.add_command(cv_conversion_report_cmd)




@click.command("send-cv-reminders")
@click.option("--limit", default=200, show_default=True, help="Maximum reminder emails in this run.")
@click.option("--dry-run", is_flag=True, help="Count eligible reminders without sending.")
@with_appcontext
def send_cv_reminders_cmd(limit, dry_run):
    """Send scheduled 24h/72h reminders for unfinished CV drafts."""
    from app.services.conversion_tracking import send_abandoned_cv_reminders
    result = send_abandoned_cv_reminders(limit=limit, dry_run=dry_run)
    click.echo(f"CV reminders: sent={result['sent']} failed={result['failed']} "
               f"would_send={result['would_send']} skipped={result['skipped']}")


@click.command("cv-conversion-report")
@click.option("--days", default=30, show_default=True, help="Reporting window in days.")
@with_appcontext
def cv_conversion_report_cmd(days):
    """Print first-CV funnel events for the selected reporting window."""
    from datetime import datetime, timedelta, timezone
    from app.models import ActivityLog, db
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, days))
    cohort = db.session.query(ActivityLog.user_id).filter(
        ActivityLog.action == "register", ActivityLog.created_at >= cutoff,
        ActivityLog.user_id.isnot(None)).distinct().subquery()
    actions = ("register", "first_cv_started", "first_cv_completed", "first_cv_downloaded")
    for action in actions:
        query = db.session.query(db.func.count(db.distinct(ActivityLog.user_id))).filter(
            ActivityLog.action == action, ActivityLog.user_id.in_(cohort))
        if action == "register":
            query = query.filter(ActivityLog.created_at >= cutoff)
        count = query.scalar() or 0
        click.echo(f"{action}: {count}")

