"""
CVForge AI - CV Blueprint
Fixed: unified import path, added restore_version route,
certifications/projects/references save as lists, BytesIO cover letter download
"""
import os
import secrets
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, jsonify, current_app, send_file, abort)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.models import db, Resume, ResumeVersion, Template, ActivityLog, AIUsage
from app.ai_service import get_ai_service

cv_bp = Blueprint("cv", __name__)


def _allowed_file(filename: str) -> bool:
    allowed = current_app.config.get("ALLOWED_EXTENSIONS", {"pdf", "docx"})
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed


def _log(action, resource_id=None, details=None):
    db.session.add(ActivityLog(
        user_id=current_user.id, action=action,
        resource_type="resume", resource_id=resource_id,
        ip_address=request.remote_addr, details=details,
    ))


def _check_ai_limit(feature: str) -> tuple:
    if current_user.is_premium:
        return True, ""
    daily = AIUsage.get_daily_count(current_user.id, feature)
    limit = current_app.config["GEMINI_FREE_USER_DAILY_LIMIT"]
    if daily >= limit:
        return False, f"Daily limit reached ({limit}/day). Upgrade to Pro for unlimited access."
    if AIUsage.get_total_daily_count() >= current_app.config["GEMINI_DAILY_LIMIT"]:
        return False, "AI service is temporarily busy. Please try again later."
    return True, ""


@cv_bp.route("/")
@login_required
def list_cvs():
    resumes = (Resume.query.filter_by(user_id=current_user.id)
               .order_by(Resume.updated_at.desc()).all())
    return render_template("cv/list.html", resumes=resumes)


@cv_bp.route("/new")
@login_required
def new_cv():
    templates = Template.query.filter_by(is_active=True).order_by(Template.sort_order).all()
    return render_template("cv/new.html", templates=templates)


@cv_bp.route("/builder/<int:resume_id>", methods=["GET"])
@cv_bp.route("/builder", methods=["GET"])
@login_required
def builder(resume_id=None):
    resume = None
    if resume_id:
        resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first_or_404()
    templates = Template.query.filter_by(is_active=True).order_by(Template.sort_order).all()
    step = int(request.args.get("step", 1))
    return render_template("cv/builder.html", resume=resume, templates=templates, step=step)


@cv_bp.route("/builder/create", methods=["POST"])
@login_required
def create_cv():
    title = request.form.get("title", "My Resume").strip() or "My Resume"
    template_id = request.form.get("template_id", type=int)
    resume = Resume(user_id=current_user.id, title=title,
                    template_id=template_id, status="draft", source="builder")
    db.session.add(resume)
    db.session.flush()
    _log("cv_create", resume.id, {"title": title})
    db.session.commit()
    return redirect(url_for("cv.builder", resume_id=resume.id, step=1))


@cv_bp.route("/builder/<int:resume_id>/save", methods=["POST"])
@login_required
def autosave(resume_id):
    resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first_or_404()
    data = request.get_json(silent=True) or {}
    section = data.get("section")
    content = data.get("content")

    json_sections = {
        "personal_info", "work_experience", "education", "skills",
        "certifications", "projects", "references", "languages", "awards",
    }
    text_sections = {"professional_summary"}

    if section in json_sections:
        # Certifications/projects/references: if sent as string, wrap in list
        if section in ("certifications", "projects", "references") and isinstance(content, str):
            content = [line.strip() for line in content.splitlines() if line.strip()]
        setattr(resume, section, content)
    elif section in text_sections:
        setattr(resume, section, content)

    if "title" in data:
        resume.title = (data["title"] or resume.title)[:255]

    db.session.commit()
    return jsonify({"success": True, "updated_at": resume.updated_at.isoformat()})


@cv_bp.route("/builder/<int:resume_id>/ai-assist", methods=["POST"])
@login_required
def ai_assist(resume_id):
    resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first_or_404()
    can_use, err = _check_ai_limit("cv_generate")
    if not can_use:
        return jsonify({"error": err}), 429

    data = request.get_json(silent=True) or {}
    section = data.get("section", "")
    context = data.get("context", "")

    try:
        ai = get_ai_service()
        result = ai.assist_section(section=section, context=context, resume=resume)
        AIUsage.log_usage(user_id=current_user.id, feature="cv_generate", prompt=context)
        db.session.commit()
        return jsonify({"success": True, "result": result})
    except Exception as e:
        current_app.logger.error(f"AI assist error: {e}")
        return jsonify({"error": "AI service unavailable. Please try again."}), 503


@cv_bp.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "POST":
        if "cv_file" not in request.files:
            flash("No file selected.", "error")
            return redirect(request.url)
        file = request.files["cv_file"]
        if not file.filename:
            flash("No file selected.", "error")
            return redirect(request.url)
        if not _allowed_file(file.filename):
            flash("Only PDF and DOCX files are supported.", "error")
            return redirect(request.url)

        filename = secure_filename(file.filename)
        ext = filename.rsplit(".", 1)[1].lower()
        safe_name = f"{secrets.token_hex(8)}_{filename}"

        # Resolve upload folder to absolute path so it works on PythonAnywhere
        upload_folder = current_app.config["UPLOAD_FOLDER"]
        if not os.path.isabs(upload_folder):
            upload_folder = os.path.join(current_app.root_path, "..", upload_folder)
        upload_folder = os.path.abspath(upload_folder)
        os.makedirs(upload_folder, exist_ok=True)

        upload_path = os.path.join(upload_folder, safe_name)
        file.save(upload_path)

        try:
            from app.services.cv_parser import CVParser
            parsed = CVParser().parse(upload_path, ext)
        except Exception as e:
            current_app.logger.error(f"CV parse error: {e}")
            parsed = {}

        personal = parsed.get("personal_info") or {}
        # Use name from parsed personal_info as resume title if available
        parsed_name = (
            personal.get("full_name")
            or f"{personal.get('first_name','')} {personal.get('last_name','')}".strip()
        )
        resume_title = f"{parsed_name}'s CV" if parsed_name else f"Uploaded: {filename[:100]}"

        # Normalize work experience: ensure each entry has 'job_title' key
        # so both the builder UI and PDF service can read it
        raw_work = parsed.get("work_experience") or []
        normalized_work = []
        for job in raw_work:
            if isinstance(job, dict):
                normalized_work.append({
                    "job_title":  job.get("title") or job.get("job_title") or "",
                    "company":    job.get("company") or "",
                    "start_date": job.get("start_date") or "",
                    "end_date":   job.get("end_date") or "Present",
                    "description":job.get("description") or "",
                    "achievements": [],
                })

        resume = Resume(
            user_id=current_user.id,
            title=resume_title[:255],
            status="draft", source="upload",
            original_filename=filename,
            original_file_path=safe_name,
            personal_info=personal,
            professional_summary=parsed.get("professional_summary"),
            work_experience=normalized_work,
            education=parsed.get("education") or [],
            skills=parsed.get("skills") or [],
            certifications=parsed.get("extra_sections", {}).get("certifications", []),
            custom_sections=parsed.get("extra_sections") or {},
        )
        db.session.add(resume)
        db.session.flush()
        _log("cv_upload", resume.id, {"filename": filename})
        db.session.commit()
        flash("CV uploaded successfully! You can now revamp it with AI.", "success")
        return redirect(url_for("cv.revamp", resume_id=resume.id))

    return render_template("cv/upload.html")


@cv_bp.route("/revamp/<int:resume_id>", methods=["GET", "POST"])
@login_required
def revamp(resume_id):
    resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first_or_404()

    if request.method == "POST":
        can_use, err = _check_ai_limit("cv_revamp")
        if not can_use:
            flash(err, "warning")
            return redirect(url_for("cv.revamp", resume_id=resume_id))

        try:
            ai = get_ai_service()
            version_count = resume.versions.count()
            version = ResumeVersion(
                resume_id=resume.id,
                version_number=version_count + 1,
                label="Before AI Revamp",
                snapshot=resume.to_dict(),
                ats_score=resume.ats_score,
                created_by="user",
            )
            db.session.add(version)

            revamped = ai.revamp_resume(resume)
            for key, val in revamped.items():
                if hasattr(resume, key) and val:
                    setattr(resume, key, val)
            resume.source = "revamp"

            after_version = ResumeVersion(
                resume_id=resume.id,
                version_number=version_count + 2,
                label="After AI Revamp",
                snapshot=resume.to_dict(),
                created_by="ai_revamp",
            )
            db.session.add(after_version)
            AIUsage.log_usage(current_user.id, "cv_revamp", str(resume_id))
            _log("cv_revamp", resume.id)
            db.session.commit()
            flash("Resume revamped successfully! Compare versions below.", "success")
            return redirect(url_for("cv.compare_versions", resume_id=resume_id))
        except Exception as e:
            current_app.logger.error(f"Revamp error: {e}")
            flash("AI revamp failed. Please try again.", "error")

    return render_template("cv/revamp.html", resume=resume)


@cv_bp.route("/<int:resume_id>/versions")
@login_required
def compare_versions(resume_id):
    resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first_or_404()
    versions = resume.versions.order_by(ResumeVersion.version_number.desc()).all()
    return render_template("cv/versions.html", resume=resume, versions=versions)


@cv_bp.route("/<int:resume_id>/versions/<int:version_id>/restore", methods=["POST"])
@login_required
def restore_version(resume_id, version_id):
    """Restore a previous version's snapshot onto the current resume."""
    resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first_or_404()
    version = ResumeVersion.query.filter_by(id=version_id, resume_id=resume_id).first_or_404()

    snap = version.snapshot or {}
    restorable = [
        "personal_info", "professional_summary", "work_experience",
        "education", "skills", "certifications", "projects", "references",
        "languages", "awards",
    ]
    for field in restorable:
        if field in snap:
            setattr(resume, field, snap[field])

    # Save restore as a new version for auditability
    version_count = resume.versions.count()
    db.session.add(ResumeVersion(
        resume_id=resume.id,
        version_number=version_count + 1,
        label=f"Restored from v{version.version_number}",
        snapshot=resume.to_dict(),
        created_by="user",
    ))
    _log("cv_restore", resume.id, {"from_version": version.version_number})
    db.session.commit()
    flash(f"Restored to version {version.version_number}.", "success")
    return redirect(url_for("cv.compare_versions", resume_id=resume_id))


@cv_bp.route("/<int:resume_id>/download/<fmt>")
@login_required
def download(resume_id, fmt):
    resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first_or_404()
    fmt = fmt.lower()
    if fmt not in ("pdf", "docx"):
        abort(400)

    try:
        if fmt == "pdf":
            from app.services.pdf_service import PDFService
            file_path = PDFService().generate(resume)
            mimetype = "application/pdf"
            dl_name = f"{resume.title.replace(' ', '_')}.pdf"
        else:
            from app.services.docx_service import DOCXService
            file_path = DOCXService().generate(resume)
            mimetype = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            dl_name = f"{resume.title.replace(' ', '_')}.docx"

        from datetime import datetime, timezone
        resume.download_count = (resume.download_count or 0) + 1
        resume.last_downloaded_at = datetime.now(timezone.utc)
        _log("cv_download", resume.id, {"format": fmt})
        db.session.commit()
        return send_file(file_path, as_attachment=True, download_name=dl_name, mimetype=mimetype)
    except Exception as e:
        current_app.logger.error(f"Download error: {e}")
        flash("Download failed. Please try again.", "error")
        return redirect(url_for("cv.builder", resume_id=resume_id))


@cv_bp.route("/<int:resume_id>/delete", methods=["POST"])
@login_required
def delete(resume_id):
    resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first_or_404()
    title = resume.title
    db.session.delete(resume)
    _log("cv_delete", resume_id, {"title": title})
    db.session.commit()
    flash(f'"{title}" deleted.', "info")
    return redirect(url_for("cv.list_cvs"))


@cv_bp.route("/<int:resume_id>/toggle-public", methods=["POST"])
@login_required
def toggle_public(resume_id):
    resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first_or_404()
    if not resume.is_public:
        resume.is_public = True
        resume.public_token = secrets.token_urlsafe(32)
    else:
        resume.is_public = False
        resume.public_token = None
    db.session.commit()
    return jsonify({
        "is_public": resume.is_public,
        "public_url": url_for("main.public_resume", token=resume.public_token, _external=True)
        if resume.is_public else None,
    })

