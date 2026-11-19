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
    app.cli.add_command(sync_job_feeds_cmd)
    app.cli.add_command(process_job_alerts_cmd)
    app.cli.add_command(setup_cmd)
    app.cli.add_command(doctor_cmd)
    app.cli.add_command(ensure_schema_cmd)


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


@click.command("sync-job-feeds")
@with_appcontext
def sync_job_feeds_cmd():
    """Import vacancies from explicitly configured, allow-listed RSS/Atom feeds."""
    from app.services.job_discovery import sync_job_feeds
    result = sync_job_feeds()
    click.echo("Job feeds: " + ", ".join(f"{key}={value}" for key, value in result.items()))


@click.command("process-job-alerts")
@click.option("--dry-run", is_flag=True, help="Show matches without creating notifications.")
@click.option("--limit", default=500, show_default=True, help="Maximum listings evaluated per saved alert.")
@with_appcontext
def process_job_alerts_cmd(dry_run, limit):
    """Create idempotent in-app notifications for newly matching vacancies."""
    from app.services.job_alerts import process_job_alerts
    result = process_job_alerts(dry_run=dry_run, limit=limit)
    click.echo("Job alerts: " + ", ".join(f"{key}={value}" for key, value in result.items()))


@click.command("ensure-schema")
@with_appcontext
def ensure_schema_cmd():
    """Create any tables that are missing. Never alters or drops existing tables."""
    from app.models import db
    db.create_all()
    click.secho("Schema is up to date (missing tables created, existing ones untouched).", fg="green")


@click.command("setup")
@click.option("--skip-seed", is_flag=True, help="Only create tables; do not seed plans/templates.")
@with_appcontext
def setup_cmd(skip_seed):
    """One-command, re-runnable bootstrap for a fresh or existing install.

    Creates missing tables, seeds default plans and templates (only what is
    missing), links template thumbnails, and creates an admin account when
    ADMIN_EMAIL and ADMIN_PASSWORD are set in the environment/.env. Safe to run
    again after every deploy.
    """
    import os
    from flask import current_app
    from app.models import db, User, Profile, UserSettings, PricingPlan, Template
    db.create_all()
    click.secho("OK tables", fg="green")
    if not skip_seed:
        runner = current_app.test_cli_runner()
        if PricingPlan.query.count() == 0:
            runner.invoke(args=["seed-plans"])
            click.secho("OK pricing plans seeded", fg="green")
        runner.invoke(args=["seed-templates"])
        runner.invoke(args=["set-thumbnails"])
        click.secho(f"OK templates ({Template.query.count()}) ready", fg="green")
    email = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD") or ""
    if email and password:
        user = User.query.filter_by(email=email).first()
        if user:
            if not user.is_admin:
                user.is_admin = True
                db.session.commit()
                click.secho(f"OK {email} promoted to admin", fg="green")
            else:
                click.echo(f"-- admin {email} already exists")
        else:
            from datetime import datetime, timezone, timedelta
            user = User(email=email, first_name="Admin", last_name="User", is_admin=True, is_verified=True,
                        plan="premium", plan_expires_at=datetime.now(timezone.utc) + timedelta(days=36500))
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            db.session.add(Profile(user_id=user.id))
            db.session.add(UserSettings(user_id=user.id))
            db.session.commit()
            click.secho(f"OK admin {email} created", fg="green")
    else:
        click.echo("-- set ADMIN_EMAIL and ADMIN_PASSWORD in .env to auto-create an admin (or run flask create-admin)")
    click.echo("Next: open /admin/job-sources to add your job feeds.")


@click.command("doctor")
@with_appcontext
def doctor_cmd():
    """Check configuration and tell you exactly what to fix."""
    from flask import current_app
    from app.models import db, User, PricingPlan, Template, JobFeedSource, JobOpportunity
    cfg = current_app.config
    problems = 0

    def check(ok, good, bad, hint=""):
        nonlocal problems
        if ok:
            click.secho(f"  OK  {good}", fg="green")
        else:
            problems += 1
            click.secho(f"  !!  {bad}", fg="red")
            if hint:
                click.echo(f"        -> {hint}")

    click.echo("Configuration")
    check(bool(cfg.get("SECRET_KEY")), "SECRET_KEY is set", "SECRET_KEY is missing", "Add SECRET_KEY=<long random string> to .env")
    site = (cfg.get("SITE_URL") or "")
    check(site.startswith("https://"), f"SITE_URL = {site}", "SITE_URL is not set to your https address",
          "Set SITE_URL=https://cvforge.site so canonical URLs and the sitemap are correct")
    check(bool(cfg.get("GEMINI_API_KEY")), "GEMINI_API_KEY is set", "GEMINI_API_KEY is missing (AI features will fail)", "Add it to .env")
    check(bool(cfg.get("PAYSTACK_SECRET_KEY") or cfg.get("INTASEND_SECRET_KEY")), "A payment provider key is set",
          "No payment provider keys found", "Set PAYSTACK_* and/or INTASEND_* keys in .env")
    check(bool(cfg.get("MAIL_USERNAME") and cfg.get("MAIL_PASSWORD")), "SMTP credentials are set",
          "SMTP credentials missing (verification and reset emails will not send)", "Set MAIL_USERNAME / MAIL_PASSWORD")

    click.echo("Database")
    try:
        users = User.query.count()
        check(True, f"Connected ({users} users, {PricingPlan.query.count()} plans, {Template.query.count()} templates)", "")
        check(User.query.filter_by(is_admin=True).count() > 0, "At least one admin exists", "No admin account yet",
              "Run flask create-admin (or set ADMIN_EMAIL/ADMIN_PASSWORD and run flask setup)")
    except Exception as exc:
        check(False, "", f"Database not ready: {exc}", "Run flask setup")
        db.session.rollback()

    click.echo("Job discovery")
    try:
        from app.services.job_discovery import ensure_schema, _load_feed_config
        ensure_schema()
        feeds, allowed = _load_feed_config()
        check(bool(feeds), f"{len(feeds)} approved feed(s), {len(allowed)} approved host(s)", "No job feeds configured",
              "Add feeds at /admin/job-sources")
        check(JobOpportunity.query.filter_by(is_active=True).count() > 0, "Vacancies imported",
              "No vacancies imported yet", "Run flask sync-job-feeds or press 'Sync all now' in Admin -> Job sources")
    except Exception as exc:
        check(False, "", f"Job discovery check failed: {exc}")
        db.session.rollback()

    click.echo()
    if problems:
        click.secho(f"{problems} item(s) need attention.", fg="yellow")
        raise SystemExit(1)
    click.secho("Everything looks good.", fg="green")
