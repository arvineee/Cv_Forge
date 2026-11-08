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
import io
import os
import secrets
from datetime import datetime, timezone
from app.services.section_intelligence import (
    apply_section, build_revamp_payload, audit_resume, next_questions,
    QUESTIONS, SECTIONS,
)
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, jsonify, current_app, send_file, abort, after_this_request)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.services.upload_validation import validate_upload, UploadRejected
from app.services.cv_diff import diff_snapshots
from app.services.storage import resolve_upload_folder

from app.models import db, Resume, ResumeVersion, Template, ActivityLog, AIUsage, PricingPlan
from app.ai_service import get_ai_service, RevampError

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


def _has_active_paid_plan() -> bool:
    """True only for a real, unexpired paid subscription (basic/pro/premium).

    Unlike User.is_premium (which only ever recognizes 'pro'/'premium' and
    ignores 'basic' entirely), this treats any paid tier as "paid" — this
    is the actual download gate now, so a Basic subscriber who's paid
    should not be treated the same as someone who never paid at all.
    """
    if not current_user.plan or current_user.plan == "free":
        return False
    if not current_user.plan_expires_at:
        return False
    expires = current_user.plan_expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires > datetime.now(timezone.utc)


def _can_download() -> bool:
    """The actual paywall moment now — everyone gets full dashboard/wizard
    access regardless of payment status, and only hits a paywall here,
    at download time, with the watermarked preview shown instead."""
    return _has_active_paid_plan()


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


def _plan_allows_public_link() -> bool:
    """Public CV sharing requires an active paid plan at minimum — anyone
    without a paid, unexpired subscription (i.e. still effectively on the
    free tier) can never share their CV publicly, full stop. Admins can
    further restrict it per paid tier via each plan's allow_public_link
    flag, but paid status is now a hard prerequisite either way."""
    if not _has_active_paid_plan():
        return False
    plan = _current_plan()
    return bool(plan and plan.allow_public_link)


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
    return render_template("cv/list.html", resumes=resumes,
                           allow_public_link=_plan_allows_public_link())


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
    template_id = request.args.get("template_id", type=int)
    return render_template("cv/new.html", templates=templates, template_id=template_id)


def _usable_template(template_id):
    """Return the active Template the current user may use, or None.
    Premium templates are limited to paid users, same as the gallery."""
    if not template_id:
        return None
    t = db.session.get(Template, template_id)
    if not t or not t.is_active:
        return None
    if t.is_premium and not current_user.is_premium:
        return None
    return t


def _active_templates():
    return Template.query.filter_by(is_active=True).order_by(Template.sort_order).all()


@cv_bp.route("/<int:resume_id>/template", methods=["POST"])
@login_required
def choose_template(resume_id):
    """Switch an existing CV (built, uploaded or revamped) to another template."""
    resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first_or_404()
    back = request.form.get("next")
    if back == "revamp":
        dest = url_for("cv.revamp", resume_id=resume.id)
    else:
        dest = url_for("cv.wizard_step", resume_id=resume.id, step="review")
    tid = request.form.get("template_id", type=int)
    t = _usable_template(tid)
    if not t:
        flash("That template isn't available on your plan.", "warning")
        return redirect(dest)
    resume.template_id = t.id
    t.use_count = (t.use_count or 0) + 1
    _log("cv_template_change", resume.id, {"template": t.slug})
    db.session.commit()
    flash(f"Template changed to {t.name}.", "success")
    return redirect(dest)


@cv_bp.route("/builder/<int:resume_id>", methods=["GET"])
@cv_bp.route("/builder", methods=["GET"])
@login_required
def builder(resume_id=None):
    resume = None
    if resume_id:
        resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first_or_404()
    templates = Template.query.filter_by(is_active=True).order_by(Template.sort_order).all()
    step = request.args.get("step", 1, type=int) or 1
    return render_template("cv/builder.html", resume=resume, templates=templates, step=step)


@cv_bp.route("/builder/create", methods=["POST"])
@login_required
def create_cv():
    title = (request.form.get("title", "My Resume").strip() or "My Resume")[:255]
    template_id = request.form.get("template_id", type=int)
    resume = Resume(user_id=current_user.id, title=title,
                    template_id=template_id, status="draft", source="builder")
    db.session.add(resume)
    db.session.flush()
    _log("cv_create", resume.id, {"title": title})
    db.session.commit()
    # NOTE: builder.html's Alpine init() calls this via fetch() and regexes
    # the response URL for /cv/builder/(\d+) to pick up resumeId — keep
    # this redirect target as-is or that JS breaks. The wizard has its own
    # entry point (wizard_new below) instead of taking over this route.
    return redirect(url_for("cv.builder", resume_id=resume.id, step=1))


@cv_bp.route("/wizard/new")
@login_required
def wizard_new():
    """Entry point for the guided wizard — creates a blank resume and drops
    the user straight into step 1, no theme picker required first."""
    title = (request.args.get("title", "My Resume").strip() or "My Resume")[:255]
    chosen = _usable_template(request.args.get("template_id", type=int))
    template_id = chosen.id if chosen else None
    resume = Resume(user_id=current_user.id, title=title,
                    template_id=template_id, status="draft", source="wizard")
    db.session.add(resume)
    db.session.flush()
    _log("cv_create", resume.id, {"title": title, "via": "wizard"})
    db.session.commit()
    return redirect(url_for("cv.wizard_step", resume_id=resume.id, step="personal_info"))


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
    context = str(data.get("context", ""))[:6000]  # cap prompt size

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


# ---------------------------------------------------------------------------
# Guided CV wizard — step-by-step Q&A alternative to the free-form builder.
# "Create a CV" now lands here: one section per page, with an optional
# "Enhance with AI" pass on the sections that benefit from it, ending in a
# Review step that generates the documents the user's plan allows, and
# either an AI Coach critique (Pro+) or a rule-based gaps teaser + upgrade
# nudge (free).
# ---------------------------------------------------------------------------

WIZARD_STEPS = [
    "personal_info", "professional_summary", "work_experience",
    "education", "skills", "certifications", "projects", "languages",
    "awards", "references", "review",
]

# Sections the AI can enhance inline, mapped onto assist_section()'s prompts.
WIZARD_AI_SECTIONS = {"professional_summary", "work_experience", "skills", "certifications"}


def _parse_projects_text(raw: str) -> list:
    """Turn 'Name | Role | Description | URL' lines into project dicts."""
    projects = []
    for line in raw.splitlines():
        parts = [x.strip() for x in line.split("|")]
        if not parts or not parts[0]:
            continue
        projects.append({
            "name": parts[0],
            "role": parts[1] if len(parts) > 1 else "",
            "description": parts[2] if len(parts) > 2 else "",
            "url": parts[3] if len(parts) > 3 else "",
        })
    return projects[:10]


def _parse_jobs_from_form(form) -> list:
    """One job per submitted block; achievements as one bullet per line."""
    titles = form.getlist("job_title")
    companies = form.getlist("company")
    locations = form.getlist("location")
    starts = form.getlist("start_date")
    ends = form.getlist("end_date")
    achievements_raw = form.getlist("achievements")
    jobs = []
    for i, title in enumerate(titles):
        if not title.strip():
            continue
        jobs.append({
            "job_title": title.strip(),
            "company": companies[i].strip() if i < len(companies) else "",
            "location": locations[i].strip() if i < len(locations) else "",
            "start_date": starts[i].strip() if i < len(starts) else "",
            "end_date": ends[i].strip() if i < len(ends) else "",
            "achievements": [l.strip() for l in achievements_raw[i].splitlines() if l.strip()]
                            if i < len(achievements_raw) else [],
        })
    return jobs


def _wizard_next_step(step: str) -> "str | None":
    i = WIZARD_STEPS.index(step)
    return WIZARD_STEPS[i + 1] if i + 1 < len(WIZARD_STEPS) else None


def _wizard_prev_step(step: str) -> "str | None":
    i = WIZARD_STEPS.index(step)
    return WIZARD_STEPS[i - 1] if i > 0 else None


def _detect_gaps(resume) -> list:
    """Cheap, non-AI heuristic pass over the resume. Used to give free-tier
    users something concrete ("here's what's weak") without burning an AI
    call — and to entice them toward the real AI Coach on Pro+."""
    gaps = []
    summary = (resume.professional_summary or "").strip()
    if not summary:
        gaps.append("You don't have a professional summary yet — it's the first thing recruiters read.")
    elif len(summary) < 60:
        gaps.append("Your professional summary is very short. A few more sentences of impact would help.")

    work = resume.work_experience or []
    if not work:
        gaps.append("No work experience added yet.")
    else:
        has_numbers = any(
            any(ch.isdigit() for ch in " ".join(job.get("achievements", []) or []))
            for job in work
        )
        if not has_numbers:
            gaps.append("None of your work experience bullets have numbers. Quantified results "
                        "(%, $, team size, time saved) rank higher with recruiters and ATS software.")

    if not resume.skills:
        gaps.append("No skills listed — many ATS systems filter out resumes with no skills section.")
    if not resume.certifications and not resume.projects:
        gaps.append("No certifications or projects listed — these help you stand out for less experience.")
    if resume.ats_score is None:
        gaps.append("You haven't run an ATS check on this resume yet.")
    elif resume.ats_score < 70:
        gaps.append(f"Your last ATS score was {resume.ats_score}/100 — there's real room to improve it.")
    return gaps


@cv_bp.route("/wizard/<int:resume_id>")
@login_required
def wizard_start(resume_id):
    """Resolves to whichever step still needs the user's attention, so
    returning to an in-progress CV picks up where they left off instead of
    always restarting at personal info."""
    resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first_or_404()
    order = {
        "personal_info": resume.personal_info,
        "professional_summary": resume.professional_summary,
        "work_experience": resume.work_experience,
        "education": resume.education,
        "skills": resume.skills,
    }
    for step, value in order.items():
        if not value:
            return redirect(url_for("cv.wizard_step", resume_id=resume_id, step=step))
    return redirect(url_for("cv.wizard_step", resume_id=resume_id, step="review"))


@cv_bp.route("/wizard/<int:resume_id>/<step>", methods=["GET"])
@login_required
def wizard_step(resume_id, step):
    if step not in WIZARD_STEPS:
        abort(404)
    resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first_or_404()

    context = dict(
        resume=resume, step=step,
        steps=WIZARD_STEPS, step_index=WIZARD_STEPS.index(step) + 1,
        total_steps=len(WIZARD_STEPS),
        prev_step=_wizard_prev_step(step), next_step=_wizard_next_step(step),
        ai_enabled=step in WIZARD_AI_SECTIONS,
    )

    if step == "review":
        plan = _current_plan()
        allow_docx = _plan_allows_docx()
        allow_coach = bool(current_user.is_premium and plan and plan.allow_career_coach)
        allow_public_link = _plan_allows_public_link()
        can_download = _can_download()
        coach_feedback, coach_error = None, None
        gaps = _detect_gaps(resume)

        if allow_coach:
            can_use, err = _check_ai_limit("career_coach")
            if can_use:
                try:
                    coach_feedback = get_ai_service().coach_review(resume, user_id=current_user.id)
                    db.session.commit()
                except Exception as e:
                    current_app.logger.error(f"Coach review error: {e}")
                    coach_error = "AI Coach is temporarily unavailable. Please try again."
            else:
                coach_error = err

        # Cheapest paid plan, so the unpaid preview can show a real
        # "from KES X" price instead of a vague "choose a plan".
        lowest_plan = None
        if not can_download:
            from app.services.pricing import annotate_plans
            lowest_plan = (PricingPlan.query
                           .filter(PricingPlan.is_active.is_(True), PricingPlan.price_kes > 0)
                           .order_by(PricingPlan.price_kes).first())
            if lowest_plan:
                annotate_plans([lowest_plan])

        context.update(
            allow_docx=allow_docx, allow_coach=allow_coach,
            allow_public_link=allow_public_link, can_download=can_download,
            coach_feedback=coach_feedback, coach_error=coach_error,
            gaps=gaps, lowest_plan=lowest_plan,
            templates=_active_templates(),
        )

    return render_template(f"cv/wizard_{step}.html", **context)


@cv_bp.route("/wizard/<int:resume_id>/<step>", methods=["POST"])
@login_required
def wizard_step_save(resume_id, step):
    if step not in WIZARD_STEPS or step == "review":
        abort(404)
    resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first_or_404()
    action = request.form.get("action", "next")
    enhance_index = None
    if action.startswith("enhance:"):
        try:
            enhance_index = int(action.split(":", 1)[1])
        except ValueError:
            enhance_index = 0
        action = "enhance"

    # -- Enhance with AI: run assist_section(), show the suggestion back on
    # the same step for the user to accept/edit before saving. Nothing is
    # written to the resume until they hit "Continue".
    if action == "enhance" and step in WIZARD_AI_SECTIONS:
        can_use, err = _check_ai_limit("cv_generate")
        if not can_use:
            flash(err, "warning")
            return redirect(url_for("cv.wizard_step", resume_id=resume_id, step=step))
        raw_input = request.form.get("draft", "")
        ai_role = None
        if step == "work_experience":
            # Enhance the specific role whose button was clicked, using what is
            # currently typed in the form. Save the form first so unsaved
            # edits (and newly added roles) are not lost on re-render.
            form_jobs = _parse_jobs_from_form(request.form)
            if form_jobs:
                resume.work_experience = form_jobs
                db.session.commit()
            idx = enhance_index if enhance_index is not None else 0
            # Indexes refer to form blocks; blank-title blocks are skipped when
            # saving, so map the block index onto the saved job list.
            titles = request.form.getlist("job_title")
            saved_idx = sum(1 for t in titles[:idx] if t.strip())
            jobs_now = resume.work_experience or []
            if idx < len(titles) and titles[idx].strip() and saved_idx < len(jobs_now):
                job = jobs_now[saved_idx]
                raw_input = "\n".join(job.get("achievements") or [])
                ai_role = job.get("job_title") or None
                if ai_role and job.get("company"):
                    ai_role = f"{ai_role} at {job['company']}"
                if job.get("job_title"):
                    raw_input = (f"Role: {job.get('job_title')}"
                                 f"{' at ' + job['company'] if job.get('company') else ''}\n{raw_input}")
            else:
                flash("Add a job title for this role before enhancing it with AI.", "warning")
                return redirect(url_for("cv.wizard_step", resume_id=resume_id, step=step))
        try:
            ai = get_ai_service()
            suggestion = ai.assist_section(section=step, context=raw_input,
                                           resume=resume, user_id=current_user.id)
            db.session.commit()
            # skills/certifications come back as a JSON array per the
            # assist_section() prompt — render as a comma/line list instead
            # of raw JSON text.
            if step in ("skills", "certifications"):
                import json as _json
                try:
                    items = _json.loads(suggestion)
                    if isinstance(items, list):
                        suggestion = ", ".join(items) if step == "skills" else "\n".join(items)
                except (ValueError, TypeError):
                    pass
        except Exception as e:
            current_app.logger.error(f"Wizard AI enhance error: {e}")
            flash("AI enhancement failed. You can keep editing manually.", "warning")
            suggestion = None
        return render_template(
            f"cv/wizard_{step}.html", resume=resume, step=step,
            steps=WIZARD_STEPS, step_index=WIZARD_STEPS.index(step) + 1,
            total_steps=len(WIZARD_STEPS),
            prev_step=_wizard_prev_step(step), next_step=_wizard_next_step(step),
            ai_enabled=True, ai_suggestion=suggestion, draft=raw_input, ai_role=ai_role,
        )

    # -- Save this step's answer (skip is allowed everywhere except
    # personal_info, so the wizard never blocks a user who just wants to
    # get to the end and download something).
    if step == "personal_info":
        resume.personal_info = {
            "full_name": request.form.get("full_name", "").strip(),
            "job_title": request.form.get("job_title", "").strip(),
            "email": request.form.get("email", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "location": request.form.get("location", "").strip(),
            "linkedin": request.form.get("linkedin", "").strip(),
        }
    elif step == "professional_summary":
        resume.professional_summary = request.form.get("content", "").strip() or None
    elif step == "work_experience":
        jobs = _parse_jobs_from_form(request.form)
        if jobs:
            resume.work_experience = jobs
    elif step == "education":
        # Field names match what builder.html / docx_service / pdf_service
        # already expect: degree, institution, year, grade.
        degrees = request.form.getlist("degree")
        institutions = request.form.getlist("institution")
        years = request.form.getlist("year")
        grades = request.form.getlist("grade")
        entries = []
        for i, degree in enumerate(degrees):
            if not degree.strip():
                continue
            entries.append({
                "degree": degree.strip(),
                "institution": institutions[i].strip() if i < len(institutions) else "",
                "year": years[i].strip() if i < len(years) else "",
                "grade": grades[i].strip() if i < len(grades) else "",
            })
        if entries:
            resume.education = entries
    elif step == "skills":
        raw = request.form.get("content", "")
        resume.skills = [s.strip() for s in raw.split(",") if s.strip()]
    elif step == "certifications":
        raw = request.form.get("content", "")
        resume.certifications = [l.strip() for l in raw.splitlines() if l.strip()]

    elif step == "projects":
        # One project per line: Name | Your role | What it does | link
        resume.projects = _parse_projects_text(request.form.get("content", ""))
    elif step == "languages":
        raw = request.form.get("content", "")
        apply_section(resume, "languages", [s for s in raw.replace("\n", ",").split(",")])
    elif step == "awards":
        raw = request.form.get("content", "")
        apply_section(resume, "awards", raw.splitlines())
    elif step == "references":
        raw = request.form.get("content", "").strip()
        # Either "Available on request" (plain text) or one referee per line:
        # Name | Job title | Company | Phone | Email
        if raw and "|" in raw:
            refs = []
            for line in raw.splitlines():
                parts = [x.strip() for x in line.split("|")]
                if parts and parts[0]:
                    refs.append({
                        "name": parts[0],
                        "title": parts[1] if len(parts) > 1 else "",
                        "company": parts[2] if len(parts) > 2 else "",
                        "phone": parts[3] if len(parts) > 3 else "",
                        "email": parts[4] if len(parts) > 4 else "",
                    })
            apply_section(resume, "references", refs)
        else:
            apply_section(resume, "references", raw)

    _log("cv_wizard_step", resume.id, {"step": step})
    db.session.commit()

    nxt = _wizard_next_step(step)
    return redirect(url_for("cv.wizard_step", resume_id=resume_id, step=nxt or "review"))


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
        try:
            validate_upload(file, ext)
        except UploadRejected as e:
            flash(str(e), "error")
            return redirect(request.url)
        safe_name = f"{secrets.token_hex(8)}_{filename}"

        # Resolve upload folder to absolute path so it works on PythonAnywhere
        upload_folder = resolve_upload_folder()

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
            template_id=getattr(_usable_template(request.args.get("template_id", type=int)), "id", None),
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
        # If anything essential is missing, ask for it before the AI revamp runs.
        if any(g.priority == "high" for g in audit_resume(resume.to_dict())):
            return redirect(url_for("cv.fill_gaps", resume_id=resume.id))
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

            # Projects and awards are now polished too. apply_section() only
            # writes validated, non-empty results, so a bad model reply
            # leaves the user's originals in place.
            if revamped.get("projects"):
                apply_section(resume, "projects", revamped["projects"])
            if revamped.get("awards"):
                apply_section(resume, "awards", revamped["awards"])

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
        except RevampError as e:
            db.session.rollback()
            current_app.logger.warning(f"Revamp rejected: {e}")
            flash("The AI could not produce a reliable revamp for this CV. "
                  "Your CV has not been changed. Please try again in a moment.", "error")
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Revamp error: {e}")
            flash("AI revamp failed. Please try again.", "error")

    return render_template("cv/revamp.html", resume=resume, templates=_active_templates())


# ---------------------------------------------------------------------------
# Fill the gaps: after an upload, ask only for what is missing. Simple answers
# are saved as typed. Work and education answers go through the AI, which
# drafts only from the facts given or returns follow-up questions (max 2 rounds).
# ---------------------------------------------------------------------------
FILL_TEXT_KEYS = {"professional_summary", "skills", "projects", "languages",
                  "awards", "certifications", "references"}
FILL_DRAFT_KEYS = {"work_experience", "education"}
FILL_MAX_ROUNDS = 2
FILL_WIZARD_KEYS = {"projects", "languages", "awards", "certifications", "references"}


def _parse_references_text(raw: str):
    """'Available on request' stays text; 'Name | Title | Company | Phone | Email' lines become dicts."""
    raw = (raw or "").strip()
    if not raw:
        return None
    if "|" not in raw:
        return raw[:300]
    refs = []
    for line in raw.splitlines():
        parts = [x.strip() for x in line.split("|")] + ["", "", "", "", ""]
        if parts[0]:
            refs.append({"name": parts[0], "title": parts[1], "company": parts[2],
                         "phone": parts[3], "email": parts[4]})
    return refs[:4] or None


def _apply_text_answer(resume, key: str, text: str) -> None:
    if key == "skills":
        resume.skills = [s.strip() for s in text.replace("\n", ",").split(",") if s.strip()][:60]
    elif key == "professional_summary":
        resume.professional_summary = text[:1200]
    elif key == "projects":
        apply_section(resume, "projects", _parse_projects_text(text))
    elif key == "languages":
        apply_section(resume, "languages", text.replace("\n", ",").split(","))
    elif key == "references":
        apply_section(resume, "references", _parse_references_text(text))
    else:  # awards, certifications
        apply_section(resume, key, text.splitlines())


def _merge_drafted(resume, key: str, items) -> None:
    """Add drafted jobs or education. Matching entries are updated, never duplicated."""
    if not isinstance(items, list):
        return
    if key == "work_experience":
        current = list(resume.work_experience or [])
        for it in items:
            if not isinstance(it, dict):
                continue
            title = str(it.get("job_title") or it.get("title") or "").strip()[:150]
            company = str(it.get("company") or "").strip()[:150]
            if not (title or company):
                continue
            bullets = [str(b).strip()[:300] for b in (it.get("achievements") or []) if str(b).strip()][:8]
            match = next((j for j in current
                          if str(j.get("job_title", "")).lower() == title.lower()
                          and str(j.get("company", "")).lower() == company.lower()), None)
            if match:
                if bullets:
                    match["achievements"] = bullets
            else:
                current.append({
                    "job_title": title, "company": company,
                    "location": str(it.get("location") or "").strip()[:120],
                    "start_date": str(it.get("start_date") or "").strip()[:30],
                    "end_date": str(it.get("end_date") or "").strip()[:30] or "Present",
                    "description": "", "achievements": bullets,
                })
        resume.work_experience = current
    elif key == "education":
        current = list(resume.education or [])
        for it in items:
            if not isinstance(it, dict):
                continue
            degree = str(it.get("degree") or "").strip()[:200]
            institution = str(it.get("institution") or "").strip()[:200]
            if not degree:
                continue
            year = str(it.get("year") or "").strip()[:30]
            grade = str(it.get("grade") or "").strip()[:60]
            match = next((e for e in current
                          if str(e.get("degree", "")).lower() == degree.lower()
                          and str(e.get("institution", "")).lower() == institution.lower()), None)
            if match:
                match["year"] = year or match.get("year", "")
                match["grade"] = grade or match.get("grade", "")
            else:
                current.append({"degree": degree, "institution": institution,
                                "year": year, "grade": grade})
        resume.education = current


def _page_questions(resume, extra_keys=()) -> list:
    """Current high and medium gaps, plus any keys the AI asked follow-ups for."""
    data = resume.to_dict()
    qs = next_questions(audit_resume(data), limit=5)
    have = {q["key"] for q in qs}
    for key in extra_keys:
        if key not in have and key in QUESTIONS:
            qs.append({"key": key, "label": SECTIONS[key]["label"],
                       "question": QUESTIONS[key], "why": ""})
    return qs


@cv_bp.route("/<int:resume_id>/fill-gaps", methods=["GET", "POST"])
@login_required
def fill_gaps(resume_id):
    resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first_or_404()

    if request.method == "GET":
        return render_template(
            "cv/fill_gaps.html", resume=resume,
            questions=_page_questions(resume), followups={}, answers={}, round=1,
            optional=[g for g in audit_resume(resume.to_dict())
                      if g.priority == "low" and g.key in FILL_WIZARD_KEYS],
        )

    rnd = request.form.get("round", type=int, default=1)
    answers, followups = {}, {}

    # 1. Save every simple answer straight away.
    for key in SECTIONS:
        text = request.form.get(f"answer_{key}", "").strip()
        if not text:
            continue
        answers[key] = text
        if key in FILL_TEXT_KEYS:
            _apply_text_answer(resume, key, text)

    # 2. Work and education go through the AI, which may ask follow-ups.
    draft_keys = [k for k in answers if k in FILL_DRAFT_KEYS]
    if draft_keys:
        can_use, err = _check_ai_limit("cv_revamp")
        if not can_use:
            flash(err, "warning")
        else:
            try:
                ai = get_ai_service()
                for key in draft_keys:
                    result = ai.draft_section(key, resume.to_dict(), answers[key], user_id=current_user.id)
                    if result["status"] == "needs_input":
                        followups[key] = result["questions"]
                    else:
                        _merge_drafted(resume, key, result.get("items"))
                _log("cv_fill_gaps", resume.id, {"round": rnd})
            except RevampError as e:
                current_app.logger.warning(f"Fill-gaps draft rejected: {e}")
                flash("We couldn't draft one of those sections. Try adding a little more detail.", "warning")
            except Exception as e:
                current_app.logger.error(f"Fill-gaps error: {e}")
                flash("The AI is unavailable right now. Your other answers were saved.", "error")

    db.session.commit()

    # 3. Ask again if the AI needs more, up to the round limit.
    if followups and rnd < FILL_MAX_ROUNDS:
        flash("A few more details would help. Answer below, or skip to continue.", "info")
        return render_template(
            "cv/fill_gaps.html", resume=resume,
            questions=_page_questions(resume, extra_keys=followups.keys()),
            followups=followups, answers=answers, round=rnd + 1,
            optional=[],
        )

    if followups:
        flash("We'll leave the parts we couldn't draft for you to add in the wizard.", "info")
    else:
        flash("Thanks. Your CV now has the details it needed.", "success")
    return redirect(url_for("cv.revamp", resume_id=resume.id))


@cv_bp.route("/<int:resume_id>/versions")
@login_required
def compare_versions(resume_id):
    resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first_or_404()
    versions = resume.versions.order_by(ResumeVersion.version_number.desc()).all()

    # Each version is compared with the one immediately before it, so the page
    # can show exactly what a revamp (or a restore) changed.
    by_number = {v.version_number: v for v in versions}
    diffs = {}
    for v in versions:
        prev = by_number.get(v.version_number - 1)
        if prev is not None:
            diffs[v.id] = diff_snapshots(prev.snapshot or {}, v.snapshot or {})
    return render_template("cv/versions.html", resume=resume, versions=versions, diffs=diffs)


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
        "languages", "awards", "custom_sections",
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


@cv_bp.route("/<int:resume_id>/preview.jpg")
@login_required
def preview_image(resume_id):
    """Pay-to-download teaser: the user's real CV with contact details masked,
    everything below the header blurred, and a watermark — all baked into the
    pixels (see app/services/cv_preview.py). Owner-only."""
    resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first_or_404()
    try:
        from app.services.cv_preview import build_preview
        data = build_preview(resume)
    except Exception as e:
        current_app.logger.error(f"Preview render error (resume {resume_id}): {e}")
        abort(503)
    resp = send_file(io.BytesIO(data), mimetype="image/jpeg")
    # The template adds ?v=<updated_at>, so a short private cache is safe.
    resp.headers["Cache-Control"] = "private, max-age=300"
    return resp


@cv_bp.route("/<int:resume_id>/download/<fmt>")
@login_required
def download(resume_id, fmt):
    resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first_or_404()
    fmt = fmt.lower()
    if fmt not in ("pdf", "docx"):
        abort(400)

    # The paywall now lives here, not at login/dashboard access. Everyone
    # can build a full CV for free; paying is only required to get the
    # actual file out.
    if not _can_download():
        flash("Subscribe to a plan to download your CV. You can preview it first below.", "warning")
        return redirect(url_for("cv.wizard_step", resume_id=resume_id, step="review"))

    if fmt == "docx" and not _plan_allows_docx():
        flash("DOCX download is a Pro feature. Upgrade your plan to download as Word.", "warning")
        return redirect(url_for("billing.plans"))

    try:
        if fmt == "pdf":
            from app.services.pdf_service import PDFService
            file_path = PDFService().generate(resume, photo_dir=_photo_dir())
            mimetype = "application/pdf"
            dl_name = f"{resume.title.replace(' ', '_')}.pdf"
        else:
            from app.services.docx_service import DOCXService
            file_path = DOCXService().generate(resume, photo_dir=_photo_dir())
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
        return redirect(url_for("cv.wizard_step", resume_id=resume_id, step="review"))


def _photo_dir() -> str:
    import os
    from app.services.storage import resolve_upload_folder
    return os.path.join(resolve_upload_folder(), "photos")


@cv_bp.route("/<int:resume_id>/photo", methods=["POST"])
@login_required
def upload_photo(resume_id):
    """Add or replace the profile photo. Requires an explicit consent tick."""
    from app.services.photo_service import process_photo, delete_photo, PhotoRejected
    resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first_or_404()
    back = url_for("cv.builder", resume_id=resume.id)

    if not request.form.get("consent"):
        flash("Please tick the consent box before uploading a photo.", "error")
        return redirect(back)

    upload = request.files.get("photo")
    if not upload or not upload.filename:
        flash("Choose a photo to upload.", "error")
        return redirect(back)

    try:
        filename = process_photo(upload.stream, _photo_dir())
    except PhotoRejected as e:
        flash(str(e), "error")
        return redirect(back)

    info = dict(resume.personal_info or {})
    old = info.get("photo")
    info["photo"] = filename
    info["photo_consent"] = True
    resume.personal_info = info
    if old:
        delete_photo(_photo_dir(), old)
    db.session.commit()
    flash("Photo added. It will appear on the sidebar templates.", "success")
    return redirect(back)


@cv_bp.route("/<int:resume_id>/photo.jpg")
@login_required
def photo_image(resume_id):
    """Serve the owner's own photo to their builder page. Never public."""
    import os
    from flask import send_file, abort
    resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first_or_404()
    filename = (resume.personal_info or {}).get("photo")
    if not filename:
        abort(404)
    path = os.path.join(_photo_dir(), os.path.basename(filename))
    if not os.path.isfile(path):
        abort(404)
    resp = send_file(path, mimetype="image/jpeg")
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


@cv_bp.route("/<int:resume_id>/photo/remove", methods=["POST"])
@login_required
def remove_photo(resume_id):
    from app.services.photo_service import delete_photo
    resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first_or_404()
    info = dict(resume.personal_info or {})
    if info.get("photo"):
        delete_photo(_photo_dir(), info["photo"])
    info.pop("photo", None)
    info.pop("photo_consent", None)
    resume.personal_info = info
    db.session.commit()
    flash("Photo removed.", "info")
    return redirect(url_for("cv.builder", resume_id=resume.id))


@cv_bp.route("/<int:resume_id>/delete", methods=["POST"])
@login_required
def delete(resume_id):
    resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first_or_404()
    title = resume.title
    from app.services.photo_service import delete_photo
    photo = (resume.personal_info or {}).get("photo")
    if photo:
        delete_photo(_photo_dir(), photo)
    # Uploaded originals hold the person's full CV; don't leave them on disk.
    if resume.original_file_path:
        try:
            from app.services.storage import resolve_upload_folder
            orig = os.path.join(resolve_upload_folder(), os.path.basename(resume.original_file_path))
            if os.path.isfile(orig):
                os.remove(orig)
        except Exception as e:
            current_app.logger.warning(f"Could not remove uploaded original: {e}")
    db.session.delete(resume)
    _log("cv_delete", resume_id, {"title": title})
    db.session.commit()
    flash(f'"{title}" deleted.', "info")
    return redirect(url_for("cv.list_cvs"))


@cv_bp.route("/<int:resume_id>/toggle-public", methods=["POST"])
@login_required
def toggle_public(resume_id):
    resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first_or_404()
    if not resume.is_public and not _plan_allows_public_link():
        return jsonify({"error": "Public CV links aren't available on your plan.",
                        "is_public": False, "public_url": None}), 403
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




