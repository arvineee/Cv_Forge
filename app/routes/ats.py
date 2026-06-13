"""
CVForge AI - ATS Blueprint
Fixed: unified import path (app.ai_service), consistent error handling
"""
from flask import Blueprint, render_template, request, jsonify, current_app, flash, redirect, url_for
from flask_login import login_required, current_user
from app.models import db, Resume, ATSReport, JobMatch, AIUsage, ActivityLog
from app.ai_service import get_ai_service

ats_bp = Blueprint("ats", __name__)


def _check_limit():
    if current_user.is_premium:
        return True, ""
    daily = AIUsage.get_daily_count(current_user.id, "ats_check")
    limit = current_app.config.get("GEMINI_FREE_USER_DAILY_LIMIT", 5)
    if daily >= limit:
        return False, f"Daily ATS limit reached ({limit}/day). Upgrade to Pro for unlimited checks."
    return True, ""


@ats_bp.route("/")
@login_required
def index():
    resumes = Resume.query.filter_by(user_id=current_user.id).order_by(Resume.updated_at.desc()).all()
    recent_reports = (ATSReport.query.filter_by(user_id=current_user.id)
                      .order_by(ATSReport.created_at.desc()).limit(5).all())
    return render_template("ats/index.html", resumes=resumes, recent_reports=recent_reports)


@ats_bp.route("/check", methods=["POST"])
@login_required
def check():
    can, err = _check_limit()
    if not can:
        if request.is_json:
            return jsonify({"error": err}), 429
        flash(err, "warning")
        return redirect(url_for("ats.index"))

    resume_id = request.form.get("resume_id", type=int) or request.json.get("resume_id") if request.is_json else None
    job_description = (request.form.get("job_description") or
                       (request.get_json(silent=True) or {}).get("job_description", ""))

    resume = None
    if resume_id:
        resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first()

    try:
        ai = get_ai_service()
        report_data = ai.ats_check(resume=resume, job_description=job_description)
    except Exception as e:
        current_app.logger.error(f"ATS check error: {e}")
        msg = "ATS analysis failed. Please try again."
        if request.is_json:
            return jsonify({"error": msg}), 503
        flash(msg, "error")
        return redirect(url_for("ats.index"))

    report = ATSReport(
        user_id=current_user.id,
        resume_id=resume_id,
        score=report_data.get("ats_score", 0),
        grade=report_data.get("grade"),
        issues=report_data.get("format_issues"),
        strengths=report_data.get("strengths"),
        suggestions=report_data.get("suggestions"),
        keyword_analysis={
            "matched": report_data.get("matched_keywords"),
            "missing": report_data.get("missing_keywords"),
        },
    )
    db.session.add(report)

    if resume:
        resume.ats_score = report.score
        resume.ats_report = report_data

    AIUsage.log_usage(current_user.id, "ats_check", job_description[:200])
    db.session.add(ActivityLog(
        user_id=current_user.id, action="ats_check",
        resource_type="resume", resource_id=resume_id,
        ip_address=request.remote_addr,
    ))
    db.session.commit()

    if request.is_json:
        return jsonify({"success": True, "report": report_data, "report_id": report.id})

    return render_template("ats/report.html", report=report, report_data=report_data, resume=resume)


@ats_bp.route("/report/<int:report_id>")
@login_required
def report(report_id):
    report = ATSReport.query.filter_by(id=report_id, user_id=current_user.id).first_or_404()
    resume = Resume.query.get(report.resume_id) if report.resume_id else None
    report_data = {
        "ats_score": report.score,
        "grade": report.grade,
        "strengths": report.strengths or [],
        "suggestions": report.suggestions or [],
        "keyword_analysis": report.keyword_analysis or {},
        "format_issues": report.issues or [],
    }
    return render_template("ats/report.html", report=report, report_data=report_data, resume=resume)
