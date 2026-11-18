"""Deterministic, low-cost matching for opt-in in-app job alerts."""
import re
from urllib.parse import urlencode
from app.models import db, JobAlertPreference, JobOpportunity, JobAlertDelivery, Notification

def _tokens(value):
    return {word.lower() for word in re.findall(r"[a-zA-Z0-9+#.]{2,}", value or "")}

def _matches(preference, job):
    wanted = _tokens(preference.keywords)
    haystack = _tokens(" ".join([job.title or "", job.description or "", job.company_name or ""]))
    if not wanted.intersection(haystack):
        return False
    if preference.country and preference.country.casefold() not in (job.country or "").casefold():
        return False
    if preference.location:
        place = " ".join([job.location or "", job.country or "", job.description or ""]).casefold()
        if preference.location.casefold() not in place:
            return False
    return True

def process_job_alerts(dry_run=False, limit=500):
    result = {"preferences": 0, "evaluated": 0, "matches": 0, "notifications_created": 0}
    preferences = JobAlertPreference.query.filter_by(is_active=True).order_by(JobAlertPreference.id.asc()).all()
    for preference in preferences:
        result["preferences"] += 1
        jobs = (JobOpportunity.query.filter_by(is_active=True)
                .order_by(JobOpportunity.published_at.desc().nullslast(), JobOpportunity.id.desc())
                .limit(max(1, min(int(limit), 2000))).all())
        for job in jobs:
            result["evaluated"] += 1
            if not _matches(preference, job):
                continue
            result["matches"] += 1
            exists = JobAlertDelivery.query.filter_by(preference_id=preference.id, job_opportunity_id=job.id).first()
            if exists or dry_run:
                continue
            notification = Notification(user_id=preference.user_id, title="Job match: " + (job.title or "Job opportunity")[:210], message=f"A vacancy matches your saved alert ‘{preference.name}’. Source: {job.source_name}. Review the original listing before applying.", type="info", action_url="/career/jobs?" + urlencode({"q": job.title[:80]}))
            db.session.add(notification)
            db.session.flush()
            db.session.add(JobAlertDelivery(preference_id=preference.id, job_opportunity_id=job.id, notification_id=notification.id))
            result["notifications_created"] += 1
    if not dry_run:
        db.session.commit()
    else:
        db.session.rollback()
    return result
