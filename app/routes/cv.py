"""
CVForge AI - CV Blueprint

Fixes applied in this pass:
- upload() now runs _check_ai_limit() before calling CVParser().parse().
  Parsing calls Gemini internally, so previously a free user could upload
  unlimited CVs and burn unlimited AI calls with zero rate limiting.
- download("docx") now checks the user's plan (PricingPlan.allow_docx)
  before generating a DOCX. Previously any user, free or paid, could
  download DOCX regardless of plan.
- download() now deletes the generated temp file after send_file() via
  after_this_request, instead of leaking a new PDF/DOCX into /tmp on every
  single download forever.
- revamp()'s merge step no longer does a blind
  `for key, val in revamped.items(): setattr(resume, key, val)`. That
  would happily overwrite ANY attribute the AI's JSON happened to name
  (including ones that were never meant to be touched) as long as
  hasattr() was true. It's now a fixed whitelist of fields the AI is
  actually allowed to change, and skill_groups (if returned) are merged
  into custom_sections rather than dropped.
- ai_assist() and revamp() now pass user_id=current_user.id into the AI
  service calls so the AIUsage cache (previously always-dead) actually
  activates for repeat requests.
"""
import os
import secrets
from datetime import datetime, timezone
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, jsonify, current_app, send_file, abort, after_this_request)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.models import db, Resume, ResumeVersion, Template, ActivityLog, AIUsage, PricingPlan
from app.ai_service import get_ai_service

cv_bp = Blueprint("cv", __name__)

# Fields the AI Revamp response is allowed to write back onto a Resume.
# Anything else in the AI's JSON is ignored, even if it happens to match
# an existing model attribute name (id, user_id, is_public, etc. must
# never be settable from AI output).
REVAMP_ALLOWED_FIELDS = {"professional_summary", "work_experience", "skills"}


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


def _current_plan() -> "PricingPlan | None":
    """Look up the PricingPlan row matching the user's current plan slug."""
    return PricingPlan.query.filter_by(slug=current_user.plan, is_active=True).first()


def _plan_allows_docx() -> bool:
    if current_user.is_premium:
        plan = _current_plan()
        if plan:
            return bool(plan.allow_docx)
        # Premium but no matching plan row configured — default to allowing it
        return True
    # Free-tier: only allow if explicitly configured on the "free" plan row
    plan = _current_plan()
    return bool(plan and plan.allow_docx)


def _cleanup_after_send(file_path: str):
    """Register a cleanup callback so generated PDF/DOCX temp files don't
    pile up in /tmp — pdf_service/docx_service both create files with
    delete=False / mkstemp and never remove them themselves."""
    @after_this_request
    def _remove(response):
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            current_app.logger.warning(f"Temp file cleanup failed: {e}")
        return response


@cv_bp.route("/")
@login_required
def list_cvs():
    resumes = (Resume.query.filter_by(user_id=current_user.id)
               .order_by(Resume.updated_at.desc()).all())
    return render_template("cv/list.html", resumes=resumes)


@cv_bp.route("/start")
@login_required
def start():
    """Action hub — the single entry point for the CV flow.

    Users land here first and pick an intent (create from scratch,
    upload an existing CV, or write a cover letter / run an ATS check)
    instead of being dropped straight into the builder or the theme
    picker with no context. Point every "Create / New CV" link in the
    app (navbar, dashboard, landing page) at this route now, instead
    of directly at cv.new or cv.builder.
    """
    resumes = (Resume.query.filter_by(user_id=current_user.id)
               .order_by(Resume.updated_at.desc()).limit(3).all())
    return render_template("cv/start.html", resumes=resumes)


@cv_bp.route("/new")
@login_required
def new_cv():
    """Step 2 of the create flow: pick a theme. Reached only after the
    user chooses 'Create a new CV' on the /cv/start hub — create_cv()
    below then uses the chosen template_id to start the builder."""
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
        result = ai.assist_section(section=section, context=context, resume=resume,
                                    user_id=current_user.id)
        # NOTE: do NOT also call AIUsage.log_usage() here — passing
        # user_id into assist_section() already makes ai._call() insert
        # an AIUsage row internally (that's what makes the 24h response
        # cache work at all). Logging it again here double-counted every
        # single AI call, which silently halved everyone's real daily
        # limit (GEMINI_FREE_USER_DAILY_LIMIT) and doubled the platform-
        # wide daily count used for GEMINI_DAILY_LIMIT and the admin
        # "AI Usage Today" stat. db.session.commit() below is still
        # needed to persist the row _call() already added to the session.
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

        # Parsing calls Gemini internally (AI-assisted extraction), so it
        # needs to be rate-limited the same as any other AI feature —
        # previously this was uncapped for every plan.
        can_use, err = _check_ai_limit("cv_parse")
        if not can_use:
            flash(err, "warning")
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
            AIUsage.log_usage(user_id=current_user.id, feature="cv_parse", prompt=filename)
        except Exception as e:
            current_app.logger.error(f"CV parse error: {e}")
            parsed = {}

        personal = parsed.get("personal_info") or {}
        parsed_name = (
            personal.get("full_name")
            or f"{personal.get('first_name','')} {personal.get('last_name','')}".strip()
        )
        resume_title = f"{parsed_name}'s CV" if parsed_name else f"Uploaded: {filename[:100]}"

        # Normalize work experience — support both 'title' and 'job_title' keys
        raw_work = parsed.get("work_experience") or []
        normalized_work = []
        for job in raw_work:
            if isinstance(job, dict):
                normalized_work.append({
                    "job_title":   job.get("job_title") or job.get("title") or "",
                    "company":     job.get("company") or "",
                    "location":    job.get("location") or "",
                    "start_date":  job.get("start_date") or "",
                    "end_date":    job.get("end_date") or "Present",
                    "description": job.get("description") or "",
                    "achievements":job.get("achievements") or [],
                })

        # Build custom_sections to store all new fields the parser captured
        # that don't have dedicated Resume model columns
        custom_sections = {
            "skill_groups":  parsed.get("skill_groups") or [],
            "achievements":  parsed.get("achievements") or [],
            "interests":     parsed.get("interests") or [],
            "publications":  parsed.get("publications") or [],
            "volunteer":     parsed.get("volunteer") or "",
            "extra_sections":parsed.get("extra_sections") or {},
        }

        resume = Resume(
            user_id=current_user.id,
            title=resume_title[:255],
            status="draft", source="upload",
            original_filename=filename,
            original_file_path=safe_name,
            personal_info=personal,
            professional_summary=parsed.get("professional_summary") or parsed.get("objective"),
            work_experience=normalized_work,
            education=parsed.get("education") or [],
            skills=parsed.get("skills") or [],
            certifications=parsed.get("certifications") or [],
            languages=parsed.get("languages") or [],
            awards=parsed.get("awards") or [],
            projects=[
                {
                    "name": p.get("name",""),
                    "description": p.get("description",""),
                    "url": p.get("url",""),
                }
                for p in (parsed.get("projects") or [])
                if isinstance(p, dict)
            ],
            custom_sections=custom_sections,
        )
        db.session.add(resume)
        db.session.flush()
        _log("cv_upload", resume.id, {"filename": filename})
        db.session.commit()

        if not parsed_name and not normalized_work and not parsed.get("education"):
            flash("CV uploaded, but we couldn't automatically extract its content. "
                  "You may need to fill in details manually before revamping.", "warning")
        else:
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

            revamped = ai.revamp_resume(resume, user_id=current_user.id)

            # Whitelisted merge — only fields the AI is actually allowed to
            # touch get written back. Never blindly setattr() on arbitrary
            # keys the model's JSON happened to include.
            if revamped.get("professional_summary"):
                resume.professional_summary = revamped["professional_summary"]

            if revamped.get("work_experience"):
                normalized = []
                for job in revamped["work_experience"]:
                    if not isinstance(job, dict):
                        continue
                    normalized.append({
                        "job_title":    job.get("job_title") or job.get("title") or "",
                        "company":      job.get("company") or "",
                        "location":     job.get("location") or "",
                        "start_date":   job.get("start_date") or "",
                        "end_date":     job.get("end_date") or "Present",
                        "description":  job.get("description") or "",
                        "achievements": job.get("achievements") or [],
                    })
                if normalized:
                    resume.work_experience = normalized

            if revamped.get("skill_groups"):
                custom = dict(resume.custom_sections or {})
                custom["skill_groups"] = revamped["skill_groups"]
                resume.custom_sections = custom
            elif revamped.get("skills"):
                resume.skills = revamped["skills"]

            resume.source = "revamp"

            after_version = ResumeVersion(
                resume_id=resume.id,
                version_number=version_count + 2,
                label="After AI Revamp",
                snapshot=resume.to_dict(),
                created_by="ai_revamp",
            )
            db.session.add(after_version)
            # AIUsage.log_usage() removed here — ai.revamp_resume(..., user_id=...)
            # already logs the call inside ai_service._call(). See ai_assist()
            # above for the full explanation of the double-counting bug.
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

    if fmt == "docx" and not _plan_allows_docx():
        flash("DOCX download is a Pro feature. Upgrade your plan to download as Word.", "warning")
        return redirect(url_for("billing.plans"))

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

        resume.download_count = (resume.download_count or 0) + 1
        resume.last_downloaded_at = datetime.now(timezone.utc)
        _log("cv_download", resume.id, {"format": fmt})
        db.session.commit()

        _cleanup_after_send(file_path)
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



