"""CVForge AI - Dashboard Blueprint"""
from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app.models import Resume, CoverLetter, ATSReport, AIUsage

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard")
@login_required
def index():
    resumes = (Resume.query.filter_by(user_id=current_user.id)
               .order_by(Resume.updated_at.desc()).limit(5).all())
    cover_letters = (CoverLetter.query.filter_by(user_id=current_user.id, is_archived=False)
                     .order_by(CoverLetter.updated_at.desc()).limit(5).all())
    recent_report = (ATSReport.query.filter_by(user_id=current_user.id)
                     .order_by(ATSReport.created_at.desc()).first())
    daily_ai_used = AIUsage.get_daily_count(current_user.id)
    return render_template("dashboard/index.html",
                           resumes=resumes,
                           cover_letters=cover_letters,
                           recent_report=recent_report,
                           daily_ai_used=daily_ai_used)


from flask import request, flash, redirect, url_for
from flask_login import current_user
from app.models import db, Profile


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
    else:
        prof = Profile(user_id=current_user.id)
        for field in ("phone", "location", "job_title", "linkedin_url", "portfolio_url", "github_url", "bio"):
            val = request.form.get(field, "").strip()
            setattr(prof, field, val or None)
        db.session.add(prof)

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
