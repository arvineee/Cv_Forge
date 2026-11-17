"""CVForge AI - Dashboard Blueprint"""
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app.models import (db, Resume, CoverLetter, ATSReport, AIUsage, Profile,
                        PricingPlan, UserSettings, ActivityLog, PageVisit)

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard")
@login_required
def index():
    resumes = (Resume.query.filter_by(user_id=current_user.id)
               .order_by(Resume.updated_at.desc()).limit(5).all())
    unfinished_resumes = (Resume.query.filter_by(user_id=current_user.id, status="draft")
                          .order_by(Resume.updated_at.desc()).limit(10).all())
    cover_letters = (CoverLetter.query.filter_by(user_id=current_user.id, is_archived=False)
                     .order_by(CoverLetter.updated_at.desc()).limit(5).all())
    recent_report = (ATSReport.query.filter_by(user_id=current_user.id)
                     .order_by(ATSReport.created_at.desc()).first())
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
    return render_template("dashboard/index.html",
                           now_utc=datetime.now(timezone.utc),
                           resumes=resumes,
                           unfinished_resumes=unfinished_resumes,
                           cover_letters=cover_letters,
                           recent_report=recent_report,
                           daily_ai_used=daily_ai_used,
                           lowest_plan=lowest_plan,
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
