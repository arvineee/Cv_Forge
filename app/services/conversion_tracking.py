"""Sprint 003 conversion events and abandoned-CV recovery.

Uses the existing ActivityLog table so this release needs no schema migration.
Events are idempotent at user/resume level where appropriate.
"""
from datetime import datetime, timedelta, timezone

from app.models import ActivityLog, User, Resume, db


def _event_exists(user_id, action, resource_id=None):
    q = ActivityLog.query.filter_by(user_id=user_id, action=action)
    if resource_id is not None:
        q = q.filter_by(resource_id=resource_id)
    return q.first() is not None


def record_event(user_id, action, resume_id=None, details=None):
    if _event_exists(user_id, action, resume_id):
        return False
    db.session.add(ActivityLog(
        user_id=user_id, action=action, resource_type="resume" if resume_id else None,
        resource_id=resume_id, details=details or {},
    ))
    return True


def mark_cv_started(user_id, resume_id, source="wizard"):
    """Record per-resume starts and the account's first start exactly once."""
    record_event(user_id, "cv_started", resume_id, {"source": source})
    if not _event_exists(user_id, "first_cv_started"):
        record_event(user_id, "first_cv_started", details={"resume_id": resume_id, "source": source})


def resume_is_complete(resume):
    """A useful first draft needs identity/contact plus at least one content section."""
    info = resume.personal_info or {}
    has_identity = bool((info.get("full_name") or "").strip())
    has_contact = bool((info.get("email") or "").strip())
    has_content = bool(
        (resume.professional_summary or "").strip()
        or resume.work_experience
        or resume.education
        or resume.skills
    )
    return has_identity and has_contact and has_content


def mark_cv_completed(user_id, resume):
    """Record completion per resume and first completion per account."""
    if not resume_is_complete(resume):
        return False
    resume.status = "complete"
    record_event(user_id, "cv_completed", resume.id, {"title": resume.title})
    if not _event_exists(user_id, "first_cv_completed"):
        record_event(user_id, "first_cv_completed", details={"resume_id": resume.id})
    return True


def send_abandoned_cv_reminders(stage_hours=(24, 72), limit=200, dry_run=False):
    """Send at most one 24h and one 72h reminder per incomplete resume.

    Call from a daily scheduled task. Completed resumes and users who disabled
    the dedicated CV progress reminder preference are excluded. The marketing
    newsletter opt-out does not suppress this product-service reminder.
    """
    now = datetime.now(timezone.utc)
    eligible_before = now - timedelta(hours=min(stage_hours))
    starts = (ActivityLog.query.filter_by(action="cv_started")
              .filter(ActivityLog.created_at <= eligible_before)
              .order_by(ActivityLog.created_at.desc()).limit(5000).all())
    result = {"sent": 0, "failed": 0, "skipped": 0, "would_send": 0}
    for start in starts:
        if result["sent"] + result["failed"] + result["would_send"] >= limit:
            break
        if not start.user_id or not start.resource_id:
            result["skipped"] += 1
            continue
        resume = db.session.get(Resume, start.resource_id)
        user = db.session.get(User, start.user_id)
        if not resume or not user or resume.user_id != user.id:
            result["skipped"] += 1
            continue
        if ActivityLog.query.filter_by(user_id=user.id, action="cv_completed", resource_id=resume.id).first():
            result["skipped"] += 1
            continue
        # This is a requested product-service reminder, not marketing.
        # Respect the dedicated CV progress reminder preference; the
        # separate newsletter opt-out controls Pro marketing nudges only.
        profile_opt_out = bool(user.profile and not user.profile.email_notifications)
        if not user.is_active or not user.is_verified or profile_opt_out:
            result["skipped"] += 1
            continue
        started = start.created_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        age_hours = (now - started).total_seconds() / 3600
        recent_reminder = ActivityLog.query.filter(
            ActivityLog.user_id == user.id,
            ActivityLog.action.in_(("cv_abandonment_email_24h", "cv_abandonment_email_72h")),
            ActivityLog.created_at >= now - timedelta(hours=24),
        ).first()
        if recent_reminder:
            result["skipped"] += 1
            continue
        # If the scheduler was delayed, choose only the most relevant
        # eligible stage. Never send a stale 24-hour email after a 72-hour
        # reminder has already been sent (or is due now).
        eligible_stages = [stage for stage in sorted(stage_hours, reverse=True)
                           if age_hours >= stage]
        if not eligible_stages:
            result["skipped"] += 1
            continue
        stage = eligible_stages[0]
        action = f"cv_abandonment_email_{stage}h"
        if _event_exists(user.id, action, resume.id):
            result["skipped"] += 1
            continue
        if dry_run:
            result["would_send"] += 1
            continue
        try:
            from app.services.email_service import send_cv_abandonment_email
            delivered = send_cv_abandonment_email(user, resume, stage)
            if not delivered:
                result["skipped"] += 1
                continue
            record_event(user.id, action, resume.id, {"stage_hours": stage})
            db.session.commit()
            result["sent"] += 1
        except Exception:
            db.session.rollback()
            result["failed"] += 1
    return result
