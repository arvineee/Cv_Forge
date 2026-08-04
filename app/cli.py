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
        f"(of {result['total']} candidates)"
    )


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


