"""CVForge AI - Dashboard Blueprint"""
from flask import Blueprint, render_template, request, flash, redirect, url_for, abort
from flask_login import login_required, current_user
from datetime import date, datetime
from urllib.parse import urlparse
from sqlalchemy import or_
from app.models import (db, Resume, CoverLetter, ATSReport, AIUsage, Profile,
                        PricingPlan, UserSettings, ActivityLog, PageVisit,
                        JobApplication, JobMatch, JobOpportunity, JobAlertPreference,
                        JobAlertDelivery, Notification)

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.app_context_processor
def _shell_helpers():
    """Lazy counters for the app shell (sidebar badge, bell). The query only
    runs when a template actually calls nav_counts(), and a failure never
    breaks a page."""
    def nav_counts():
        counts = {"unread": 0}
        try:
            if current_user.is_authenticated:
                counts["unread"] = Notification.query.filter_by(
                    user_id=current_user.id, is_read=False).filter(
                    Notification.action_url.like("/career/jobs%")).count()
        except Exception:
            db.session.rollback()
        return counts
    return {"nav_counts": nav_counts}


@dashboard_bp.route("/dashboard")
@login_required
def index():
    resumes = (Resume.query.filter_by(user_id=current_user.id)
               .order_by(Resume.updated_at.desc()).limit(5).all())
    unfinished_resumes = (Resume.query.filter_by(user_id=current_user.id, status="draft")
                          .order_by(Resume.updated_at.desc()).limit(10).all())
    cover_letters = (CoverLetter.query.filter_by(user_id=current_user.id, is_archived=False)
                     .order_by(CoverLetter.updated_at.desc()).limit(5).all())
    recent_reports = (ATSReport.query.filter_by(user_id=current_user.id)
                      .order_by(ATSReport.created_at.desc()).limit(6).all())
    recent_report = recent_reports[0] if recent_reports else None
    previous_report = recent_reports[1] if len(recent_reports) > 1 else None
    score_change = (recent_report.score - previous_report.score
                    if recent_report and previous_report else None)

    # Build career insights only from the user's own saved ATS reports.
    # Missing keywords are suggestions to review, not skills the user should
    # claim unless they genuinely have the experience.
    keyword_gaps = []
    if recent_report and isinstance(recent_report.keyword_analysis, dict):
        raw_gaps = recent_report.keyword_analysis.get("missing") or []
        if isinstance(raw_gaps, list):
            keyword_gaps = [str(item).strip() for item in raw_gaps
                            if isinstance(item, (str, int, float)) and str(item).strip()][:8]
    insight_suggestions = recent_report.suggestions if recent_report else []
    if not isinstance(insight_suggestions, list):
        insight_suggestions = []
    insight_suggestions = insight_suggestions[:3]
    daily_ai_used = AIUsage.get_daily_count(current_user.id)
    from app.services.pricing import annotate_plans
    cheapest_paid_plan = (PricingPlan.query
                          .filter_by(is_active=True)
                          .filter(PricingPlan.price_kes > 0)
                          .order_by(PricingPlan.price_kes)
                          .first())
    lowest_plan = annotate_plans([cheapest_paid_plan])[0] if cheapest_paid_plan else None
    from app.routes.cv import _plan_allows_public_link
    from datetime import datetime, timezone
    from app.models import utcnow
    completed_cv_ids = {
        row.resource_id for row in ActivityLog.query.filter_by(
            user_id=current_user.id, action="cv_completed", resource_type="resume"
        ).all()
    }
    first_downloaded_cv_ids = {
        row.resource_id for row in ActivityLog.query.filter_by(
            user_id=current_user.id, action="cv_first_download", resource_type="resume"
        ).all()
    }
    # Job-search snapshot for the dashboard home (read-only aggregates).
    from datetime import date as _date
    pipeline = {status: 0 for status in JobApplication.STATUSES}
    for status, total in (db.session.query(JobApplication.status, db.func.count(JobApplication.id))
                          .filter_by(user_id=current_user.id).group_by(JobApplication.status).all()):
        pipeline[status] = total
    upcoming = (JobApplication.query.filter_by(user_id=current_user.id)
                .filter(JobApplication.deadline.isnot(None), JobApplication.deadline >= _date.today(),
                        JobApplication.status.in_(("saved", "applied", "interview")))
                .order_by(JobApplication.deadline).limit(3).all())
    latest_jobs = (JobOpportunity.query.filter_by(is_active=True)
                   .order_by(JobOpportunity.published_at.desc().nullslast(), JobOpportunity.created_at.desc())
                   .limit(3).all())
    active_jobs_total = JobOpportunity.query.filter_by(is_active=True).count()
    return render_template("dashboard/index.html",
                           pipeline=pipeline, pipeline_total=sum(pipeline.values()),
                           upcoming_deadlines=upcoming, latest_jobs=latest_jobs,
                           active_jobs_total=active_jobs_total,
                           now_utc=utcnow(),
                           resumes=resumes,
                           unfinished_resumes=unfinished_resumes,
                           cover_letters=cover_letters,
                           recent_report=recent_report,
                           recent_reports=recent_reports,
                           score_change=score_change,
                           keyword_gaps=keyword_gaps,
                           insight_suggestions=insight_suggestions,
                           daily_ai_used=daily_ai_used,
                           lowest_plan=lowest_plan,
                           completed_cv_ids=completed_cv_ids,
                           first_downloaded_cv_ids=first_downloaded_cv_ids,
                           allow_public_link=_plan_allows_public_link())


@dashboard_bp.route("/dashboard/profile")
@login_required
def profile():
    return render_template("dashboard/profile.html")


@dashboard_bp.route("/dashboard/profile/update", methods=["POST"])
@login_required
def update_profile():
    current_user.first_name = request.form.get("first_name", "").strip() or current_user.first_name
    current_user.last_name = request.form.get("last_name", "").strip() or current_user.last_name

    if current_user.profile:
        prof = current_user.profile
        for field in ("phone", "location", "job_title", "linkedin_url", "portfolio_url", "github_url", "bio"):
            val = request.form.get(field, "").strip()
            setattr(prof, field, val or None)
        prof.email_notifications = request.form.get("email_notifications") == "on"
    else:
        prof = Profile(user_id=current_user.id)
        for field in ("phone", "location", "job_title", "linkedin_url", "portfolio_url", "github_url", "bio"):
            val = request.form.get(field, "").strip()
            setattr(prof, field, val or None)
        prof.email_notifications = request.form.get("email_notifications") == "on"
        db.session.add(prof)

    settings = current_user.settings
    if not settings:
        settings = UserSettings(user_id=current_user.id)
        db.session.add(settings)
    settings.email_newsletter = request.form.get("email_newsletter") == "on"
    settings.allow_analytics = request.form.get("allow_analytics") == "on"

    if not settings.allow_analytics:
        # Remove account-level attribution and linkage while preserving the
        # anonymous aggregate visit rows for traffic totals.
        registration = ActivityLog.query.filter_by(
            user_id=current_user.id, action="register"
        ).order_by(ActivityLog.created_at.asc()).first()
        if registration and isinstance(registration.details, dict):
            details = dict(registration.details)
            for key in (
                "session_id", "acquisition_source", "acquisition_medium",
                "acquisition_campaign", "acquisition_content", "acquisition_term",
                "referrer_host", "landing_path", "attribution_model",
            ):
                details.pop(key, None)
            registration.details = details
        PageVisit.query.filter_by(user_id=current_user.id).update(
            {PageVisit.user_id: None}, synchronize_session=False
        )

    db.session.commit()
    flash("Profile updated.", "success")
    return redirect(url_for("dashboard.profile"))


@dashboard_bp.route("/dashboard/profile/password", methods=["POST"])
@login_required
def change_password():
    current_pw = request.form.get("current_password", "")
    new_pw = request.form.get("new_password", "")
    confirm_pw = request.form.get("confirm_password", "")

    if not current_user.check_password(current_pw):
        flash("Current password is incorrect.", "error")
    elif len(new_pw) < 8:
        flash("New password must be at least 8 characters.", "error")
    elif new_pw != confirm_pw:
        flash("New passwords do not match.", "error")
    else:
        current_user.set_password(new_pw)
        db.session.commit()
        flash("Password updated successfully.", "success")

    return redirect(url_for("dashboard.profile"))




@dashboard_bp.route("/onboarding")
@login_required
def onboarding():
    """First-session guide that explains the guided CV path without blocking access."""
    from app.models import ActivityLog
    has_started = ActivityLog.query.filter_by(user_id=current_user.id, action="first_cv_started").first() is not None
    return render_template("dashboard/onboarding.html", has_started=has_started)


# ── Job description matching ──────────────────────────────────────
@dashboard_bp.route("/career/match", methods=["GET", "POST"])
@login_required
def career_match():
    """Compare one of the user's saved CVs with a pasted vacancy description."""
    from flask import current_app
    from app.ai_service import get_ai_service

    resumes = Resume.query.filter_by(user_id=current_user.id).order_by(Resume.updated_at.desc()).all()
    if request.method == "POST":
        resume_id = request.form.get("resume_id", type=int)
        resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first() if resume_id else None
        description = (request.form.get("job_description") or "").strip()
        title = (request.form.get("job_title") or "").strip()[:255] or None
        company = (request.form.get("company_name") or "").strip()[:255] or None
        if not resume:
            flash("Choose one of your saved CVs.", "error")
            return redirect(url_for("dashboard.career_match"))
        if len(description) < 100:
            flash("Paste a job description with at least 100 characters for a useful comparison.", "warning")
            return redirect(url_for("dashboard.career_match"))
        if len(description) > 8000:
            description = description[:8000]
        limit = current_app.config.get("GEMINI_FREE_USER_DAILY_LIMIT", 3)
        if not current_user.is_premium and AIUsage.get_daily_count(current_user.id, "ats_check") >= limit:
            flash(f"Daily analysis limit reached ({limit}/day). Upgrade your plan or try again tomorrow.", "warning")
            return redirect(url_for("dashboard.career_match"))
        try:
            report = get_ai_service().ats_check(resume=resume, job_description=description, user_id=current_user.id)
            match_score = report.get("match_score")
            if not isinstance(match_score, (int, float)):
                match_score = report.get("ats_score", 0)
            match_score = max(0, min(100, int(match_score or 0)))
            item = JobMatch(
                user_id=current_user.id, resume_id=resume.id, job_title=title,
                company_name=company, job_description=description,
                match_score=match_score, ats_score=max(0, min(100, int(report.get("ats_score") or 0))),
                missing_keywords=report.get("missing_keywords") or [],
                matched_keywords=report.get("matched_keywords") or [],
                skills_gap=report.get("skills_gap") or [],
                suggestions=report.get("suggestions") or [], full_report=report,
            )
            db.session.add(item)
            db.session.flush()
            db.session.add(ActivityLog(user_id=current_user.id, action="job_match_analyzed",
                resource_type="job_match", resource_id=item.id,
                details={"match_score": match_score, "resume_id": resume.id}))
            db.session.commit()
            flash("Your job match analysis is ready.", "success")
            return redirect(url_for("dashboard.career_match", result=item.id))
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Career job-match analysis failed")
            flash("We couldn't complete the comparison. Please try again.", "error")
            return redirect(url_for("dashboard.career_match"))

    result_id = request.args.get("result", type=int)
    result = JobMatch.query.filter_by(id=result_id, user_id=current_user.id).first() if result_id else None
    listing_id = request.args.get("job_id", type=int)
    job_listing = JobOpportunity.query.filter_by(id=listing_id, is_active=True).first() if listing_id else None
    history = JobMatch.query.filter_by(user_id=current_user.id).order_by(JobMatch.created_at.desc()).limit(10).all()
    return render_template("career/match.html", resumes=resumes, result=result, history=history, job_listing=job_listing)


@dashboard_bp.route("/career/match/<int:match_id>/save", methods=["POST"])
@login_required
def save_match_as_application(match_id):
    match = JobMatch.query.filter_by(id=match_id, user_id=current_user.id).first_or_404()
    existing = JobApplication.query.filter_by(user_id=current_user.id, job_title=(match.job_title or "Untitled role"),
                                               company_name=(match.company_name or "Company not specified")).first()
    if existing:
        flash("This opportunity is already in your Career Workspace.", "info")
        return redirect(url_for("dashboard.applications"))
    item = JobApplication(
        user_id=current_user.id, resume_id=match.resume_id,
        job_title=match.job_title or "Untitled role",
        company_name=match.company_name or "Company not specified",
        status="saved", notes=f"Added from CVForge Job Match. Match score: {match.match_score or 0}%.\n\nJob description:\n{match.job_description[:7000]}",
    )
    db.session.add(item)
    db.session.add(ActivityLog(user_id=current_user.id, action="job_match_saved_to_workspace",
        resource_type="job_application"))
    db.session.commit()
    flash("Opportunity saved to your Career Workspace.", "success")
    return redirect(url_for("dashboard.applications"))


# ── Job discovery ─────────────────────────────────────────────────
PUBLIC_JOB_PREVIEW = 6  # listings shown to visitors who are not signed in


@dashboard_bp.route("/career/jobs")
def job_discovery():
    term = (request.args.get("q") or "").strip()[:100]
    country = (request.args.get("country") or "").strip()[:80]
    location = (request.args.get("location") or "").strip()[:100]
    query = JobOpportunity.query.filter_by(is_active=True)
    if term:
        pattern = f"%{term}%"
        query = query.filter(or_(JobOpportunity.title.ilike(pattern), JobOpportunity.company_name.ilike(pattern), JobOpportunity.description.ilike(pattern)))
    if country:
        query = query.filter(JobOpportunity.country.ilike(f"%{country}%"))
    if location:
        query = query.filter(JobOpportunity.location.ilike(f"%{location}%"))
    is_member = current_user.is_authenticated
    ordered = query.order_by(JobOpportunity.published_at.desc().nullslast(), JobOpportunity.created_at.desc())
    countries = [row[0] for row in db.session.query(JobOpportunity.country).filter_by(is_active=True).distinct().order_by(JobOpportunity.country).limit(80).all()]
    if not is_member:
        total = query.count()
        jobs = ordered.limit(PUBLIC_JOB_PREVIEW).all()
        next_url = request.full_path.rstrip("?")
        return render_template("career/jobs_public.html", jobs=jobs, total=total, hidden=max(total - len(jobs), 0),
                               term=term, country=country, location=location, countries=countries, next_url=next_url)
    jobs = ordered.limit(60).all()
    return render_template("career/jobs.html", jobs=jobs, term=term, country=country, location=location, countries=countries)


@dashboard_bp.route("/career/jobs/<int:job_id>/save", methods=["POST"])
@login_required
def save_discovered_job(job_id):
    job = JobOpportunity.query.filter_by(id=job_id, is_active=True).first_or_404()
    existing = JobApplication.query.filter_by(user_id=current_user.id, job_url=job.url).first()
    if existing:
        flash("You have already saved this vacancy to your Career Workspace.", "info")
        return redirect(url_for("dashboard.applications"))
    item = JobApplication(user_id=current_user.id, company_name=(job.company_name or "See original listing")[:180],
        job_title=job.title[:180], job_url=job.url, location=(job.location or job.country)[:180],
        employment_type=job.employment_type[:60] if job.employment_type else None, status="saved",
        notes=f"Found via CVForge Job Discovery. Source: {job.source_name}\n\n{job.description[:7000]}")
    db.session.add(item)
    db.session.flush()
    db.session.add(ActivityLog(user_id=current_user.id, action="job_discovery_saved", resource_type="job_application", resource_id=item.id, details={"job_opportunity_id": job.id, "source": job.source_name}))
    db.session.commit()
    flash("Vacancy saved to your Career Workspace.", "success")
    return redirect(url_for("dashboard.applications"))


# ── Career workspace: job application tracker ─────────────────────
@dashboard_bp.route("/career/applications")
@login_required
def applications():
    status = request.args.get("status", "").strip().lower()
    query = JobApplication.query.filter_by(user_id=current_user.id)
    if status in JobApplication.STATUSES:
        query = query.filter_by(status=status)
    items = query.order_by(JobApplication.updated_at.desc()).all()
    counts = {key: JobApplication.query.filter_by(user_id=current_user.id, status=key).count()
              for key in JobApplication.STATUSES}
    resumes = Resume.query.filter_by(user_id=current_user.id).order_by(Resume.updated_at.desc()).all()
    return render_template("career/applications.html", applications=items, counts=counts,
                           statuses=JobApplication.STATUSES, active_status=status, resumes=resumes)


def _parse_date(value):
    value = (value or "").strip()
    return date.fromisoformat(value) if value else None


@dashboard_bp.route("/career/applications/new", methods=["POST"])
@login_required
def create_application():
    company = request.form.get("company_name", "").strip()
    title = request.form.get("job_title", "").strip()
    if not company or not title:
        flash("Company and job title are required.", "error")
        return redirect(url_for("dashboard.applications"))
    status = request.form.get("status", "saved").strip().lower()
    if status not in JobApplication.STATUSES:
        status = "saved"
    resume_id = request.form.get("resume_id", type=int)
    resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first() if resume_id else None
    raw_url = request.form.get("job_url", "").strip()
    if raw_url:
        parsed = urlparse(raw_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            flash("Enter a valid job link starting with https:// or http://.", "error")
            return redirect(url_for("dashboard.applications"))
    try:
        item = JobApplication(user_id=current_user.id, resume_id=resume.id if resume else None,
            company_name=company[:180], job_title=title[:180], job_url=raw_url or None,
            location=request.form.get("location", "").strip()[:180] or None,
            employment_type=request.form.get("employment_type", "").strip()[:60] or None,
            salary_range=request.form.get("salary_range", "").strip()[:120] or None,
            status=status, date_applied=_parse_date(request.form.get("date_applied")),
            deadline=_parse_date(request.form.get("deadline")),
            notes=request.form.get("notes", "").strip()[:10000] or None)
        db.session.add(item)
        db.session.flush()
        db.session.add(ActivityLog(user_id=current_user.id, action="job_application_created", resource_type="job_application", resource_id=item.id, details={"status": status}))
        db.session.commit()
        flash("Job opportunity added to your career workspace.", "success")
    except ValueError:
        db.session.rollback()
        flash("Please enter valid dates.", "error")
    return redirect(url_for("dashboard.applications"))


@dashboard_bp.route("/career/applications/<int:application_id>/update", methods=["POST"])
@login_required
def update_application(application_id):
    item = JobApplication.query.filter_by(id=application_id, user_id=current_user.id).first_or_404()
    status = request.form.get("status", "").strip().lower()
    if status not in JobApplication.STATUSES:
        abort(400)
    item.status = status
    try:
        if "date_applied" in request.form:
            item.date_applied = _parse_date(request.form.get("date_applied")) or item.date_applied
        if "deadline" in request.form:
            item.deadline = _parse_date(request.form.get("deadline"))
        if "interview_at" in request.form:
            item.interview_at = datetime.fromisoformat(request.form["interview_at"]) if request.form.get("interview_at") else None
        if "notes" in request.form:
            item.notes = request.form.get("notes", "").strip()[:10000] or None
        if "resume_id" in request.form:
            resume_id = request.form.get("resume_id", type=int)
            if resume_id:
                resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first()
                if not resume:
                    abort(400)
                item.resume_id = resume.id
            else:
                item.resume_id = None
        db.session.add(ActivityLog(user_id=current_user.id, action="job_application_status_updated", resource_type="job_application", resource_id=item.id, details={"status": status}))
        db.session.commit()
        flash("Application updated.", "success")
    except ValueError:
        db.session.rollback()
        flash("Please enter valid dates and times.", "error")
    return redirect(url_for("dashboard.applications"))


@dashboard_bp.route("/career/applications/<int:application_id>/delete", methods=["POST"])
@login_required
def delete_application(application_id):
    item = JobApplication.query.filter_by(id=application_id, user_id=current_user.id).first_or_404()
    db.session.add(ActivityLog(user_id=current_user.id, action="job_application_deleted", resource_type="job_application", resource_id=item.id))
    db.session.delete(item)
    db.session.commit()
    flash("Application removed.", "success")
    return redirect(url_for("dashboard.applications"))


# ── Personalised job alerts (in-app only; no unsolicited email) ─────────────
@dashboard_bp.route("/career/job-alerts", methods=["GET", "POST"])
@login_required
def job_alerts():
    if request.method == "POST":
        keywords = " ".join((request.form.get("keywords") or "").split())[:500]
        country = (request.form.get("country") or "").strip()[:80] or None
        location = (request.form.get("location") or "").strip()[:180] or None
        name = (request.form.get("name") or "My job alert").strip()[:100] or "My job alert"
        if not keywords:
            flash("Enter at least one job title or skill keyword.", "error")
        elif JobAlertPreference.query.filter_by(user_id=current_user.id).count() >= 10:
            flash("You can save up to 10 job alerts.", "error")
        else:
            db.session.add(JobAlertPreference(user_id=current_user.id, name=name, keywords=keywords, country=country, location=location, is_active=True))
            db.session.commit()
            flash("Job alert saved. New matching vacancies will appear in your notifications after the next alert run.", "success")
        return redirect(url_for("dashboard.job_alerts"))
    preferences = JobAlertPreference.query.filter_by(user_id=current_user.id).order_by(JobAlertPreference.created_at.desc()).all()
    notifications = Notification.query.filter_by(user_id=current_user.id).filter(Notification.action_url.like("/career/jobs%" )).order_by(Notification.created_at.desc()).limit(30).all()
    return render_template("career/job_alerts.html", preferences=preferences, notifications=notifications)


@dashboard_bp.route("/career/job-alerts/<int:preference_id>/toggle", methods=["POST"])
@login_required
def toggle_job_alert(preference_id):
    preference = JobAlertPreference.query.filter_by(id=preference_id, user_id=current_user.id).first_or_404()
    preference.is_active = not preference.is_active
    db.session.commit()
    flash("Job alert " + ("activated." if preference.is_active else "paused."), "success")
    return redirect(url_for("dashboard.job_alerts"))


@dashboard_bp.route("/career/job-alerts/<int:preference_id>/delete", methods=["POST"])
@login_required
def delete_job_alert(preference_id):
    preference = JobAlertPreference.query.filter_by(id=preference_id, user_id=current_user.id).first_or_404()
    db.session.delete(preference)
    db.session.commit()
    flash("Job alert deleted.", "success")
    return redirect(url_for("dashboard.job_alerts"))
