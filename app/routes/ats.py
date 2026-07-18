"""
CVForge AI - ATS Blueprint

Fixes / features added in this pass:
- Fixed a real bug: resume_id was computed with
    request.form.get(...) or request.json.get(...) if request.is_json else None
  Python's ternary binds looser than "or", so this evaluated as
    (A or B) if C else D
  meaning any normal (non-JSON) form submission always threw the form's
  resume_id away and used None instead, regardless of what was submitted.
- job_description is now fully optional everywhere. If it's blank, ats_check
  runs a general ATS/formatting audit of the resume instead of a
  job-match analysis (see ai_service.ats_check).
- New: upload-and-check flow. You can now upload a CV file directly on the
  ATS page and get a score with NO saved Resume and NO job description
  required. Text is pulled straight from the file via
  CVParser.extract_text() (fast text-only extraction — no second AI parse
  call), and fed into ats_check(resume_text=...).
- Uploaded files for ad-hoc checks are temp files, deleted after the check
  runs — they were never meant to become permanent CVs.
"""
import os
import secrets
from flask import (Blueprint, render_template, request, jsonify, current_app,
                   flash, redirect, url_for, after_this_request)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.models import db, Resume, ATSReport, JobMatch, AIUsage, ActivityLog
from app.ai_service import get_ai_service

ats_bp = Blueprint("ats", __name__)

ALLOWED_EXTENSIONS = {"pdf", "docx"}


def _check_limit():
    if current_user.is_premium:
        return True, ""
    daily = AIUsage.get_daily_count(current_user.id, "ats_check")
    limit = current_app.config.get("GEMINI_FREE_USER_DAILY_LIMIT", 3)
    if daily >= limit:
        return False, f"Daily ATS limit reached ({limit}/day). Upgrade to Pro for unlimited checks."
    return True, ""


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _get_resume_id_from_request() -> int:
    """
    Safely pull resume_id from either a form POST or a JSON POST.
    Previously this used a ternary expression that discarded form values
    entirely on non-JSON requests due to Python operator precedence.
    """
    form_val = request.form.get("resume_id", type=int)
    if form_val:
        return form_val
    if request.is_json:
        body = request.get_json(silent=True) or {}
        try:
            return int(body.get("resume_id")) if body.get("resume_id") else None
        except (TypeError, ValueError):
            return None
    return None


def _get_job_description_from_request() -> str:
    return (request.form.get("job_description") or
            (request.get_json(silent=True) or {}).get("job_description", "") or "")


def _save_report(report_data: dict, resume_id: int = None, source_label: str = None):
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
    return report


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
    """Check ATS score for an existing saved resume. Job description is optional —
    if omitted, this runs a general ATS/formatting audit instead of a job match."""
    can, err = _check_limit()
    if not can:
        if request.is_json:
            return jsonify({"error": err}), 429
        flash(err, "warning")
        return redirect(url_for("ats.index"))

    resume_id = _get_resume_id_from_request()
    job_description = _get_job_description_from_request()

    resume = None
    if resume_id:
        resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first()

    try:
        ai = get_ai_service()
        report_data = ai.ats_check(resume=resume, job_description=job_description,
                                    user_id=current_user.id)
    except Exception as e:
        current_app.logger.error(f"ATS check error: {e}")
        msg = "ATS analysis failed. Please try again."
        if request.is_json:
            return jsonify({"error": msg}), 503
        flash(msg, "error")
        return redirect(url_for("ats.index"))

    report = _save_report(report_data, resume_id=resume_id)

    if resume:
        resume.ats_score = report.score
        resume.ats_report = report_data

    # AIUsage.log_usage() removed — ai.ats_check(..., user_id=...) already
    # logs the call inside ai_service._call(). Logging it again here
    # double-counted every ATS check against the daily limit.
    db.session.add(ActivityLog(
        user_id=current_user.id, action="ats_check",
        resource_type="resume", resource_id=resume_id,
        ip_address=request.remote_addr,
    ))
    db.session.commit()

    if request.is_json:
        return jsonify({"success": True, "report": report_data, "report_id": report.id})

    return render_template("ats/report.html", report=report, report_data=report_data, resume=resume)


@ats_bp.route("/check-upload", methods=["POST"])
@login_required
def check_upload():
    """
    Upload a CV file and get an ATS check immediately — no saved Resume
    required, no job description required. Job description is still
    accepted as an OPTIONAL extra field: if provided, the check becomes a
    job-match analysis; if not, it's a general ATS/formatting audit of the
    uploaded CV on its own.
    """
    can, err = _check_limit()
    if not can:
        if request.is_json:
            return jsonify({"error": err}), 429
        flash(err, "warning")
        return redirect(url_for("ats.index"))

    if "cv_file" not in request.files or not request.files["cv_file"].filename:
        msg = "Please choose a CV file to upload."
        if request.is_json:
            return jsonify({"error": msg}), 400
        flash(msg, "error")
        return redirect(url_for("ats.index"))

    file = request.files["cv_file"]
    if not _allowed_file(file.filename):
        msg = "Only PDF and DOCX files are supported."
        if request.is_json:
            return jsonify({"error": msg}), 400
        flash(msg, "error")
        return redirect(url_for("ats.index"))

    job_description = _get_job_description_from_request()  # optional, may be ""

    filename = secure_filename(file.filename)
    ext = filename.rsplit(".", 1)[1].lower()
    safe_name = f"ats_{secrets.token_hex(8)}_{filename}"

    upload_folder = current_app.config["UPLOAD_FOLDER"]
    if not os.path.isabs(upload_folder):
        upload_folder = os.path.join(current_app.root_path, "..", upload_folder)
    upload_folder = os.path.abspath(upload_folder)
    os.makedirs(upload_folder, exist_ok=True)

    upload_path = os.path.join(upload_folder, safe_name)
    file.save(upload_path)

    @after_this_request
    def _cleanup(response):
        try:
            if os.path.exists(upload_path):
                os.remove(upload_path)
        except Exception as e:
            current_app.logger.warning(f"ATS upload cleanup failed: {e}")
        return response

    try:
        from app.services.cv_parser import CVParser
        raw_text = CVParser().extract_text(upload_path, ext)
    except Exception as e:
        current_app.logger.error(f"ATS upload text extraction error: {e}")
        raw_text = ""

    if not raw_text or len(raw_text.strip()) < 40:
        msg = "Couldn't read enough text from that file. Try a different PDF/DOCX export of your CV."
        if request.is_json:
            return jsonify({"error": msg}), 422
        flash(msg, "error")
        return redirect(url_for("ats.index"))

    try:
        ai = get_ai_service()
        report_data = ai.ats_check(resume=None, job_description=job_description,
                                    resume_text=raw_text, user_id=current_user.id)
    except Exception as e:
        current_app.logger.error(f"ATS upload check error: {e}")
        msg = "ATS analysis failed. Please try again."
        if request.is_json:
            return jsonify({"error": msg}), 503
        flash(msg, "error")
        return redirect(url_for("ats.index"))

    report = _save_report(report_data, resume_id=None)

    # AIUsage.log_usage() removed — same double-counting fix as check() above.
    db.session.add(ActivityLog(
        user_id=current_user.id, action="ats_check_upload",
        resource_type="resume", resource_id=None,
        ip_address=request.remote_addr, details={"filename": filename},
    ))
    db.session.commit()

    if request.is_json:
        return jsonify({"success": True, "report": report_data, "report_id": report.id})

    return render_template("ats/report.html", report=report, report_data=report_data, resume=None)


@ats_bp.route("/report/<int:report_id>")
@login_required
def report(report_id):
    report = ATSReport.query.filter_by(id=report_id, user_id=current_user.id).first_or_404()
    resume = db.session.get(Resume, report.resume_id) if report.resume_id else None
    report_data = {
        "ats_score": report.score,
        "grade": report.grade,
        "strengths": report.strengths or [],
        "suggestions": report.suggestions or [],
        "keyword_analysis": report.keyword_analysis or {},
        "format_issues": report.issues or [],
    }
    return render_template("ats/report.html", report=report, report_data=report_data, resume=resume)


