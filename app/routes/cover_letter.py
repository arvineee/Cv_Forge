"""
CVForge AI - Cover Letter Blueprint
Fixed: BytesIO download (works under all WSGI servers), XSS-safe rendering,
PDF download option added
"""
import io
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, jsonify, current_app, send_file, abort)
from flask_login import login_required, current_user

from app.models import db, CoverLetter, Resume, AIUsage, ActivityLog
from app.ai_service import get_ai_service

cover_letter_bp = Blueprint("cover_letter", __name__)


def _log(action, resource_id=None, details=None):
    db.session.add(ActivityLog(
        user_id=current_user.id, action=action,
        resource_type="cover_letter", resource_id=resource_id,
        ip_address=request.remote_addr, details=details,
    ))


def _check_limit():
    if current_user.is_premium:
        return True, ""
    daily = AIUsage.get_daily_count(current_user.id, "cover_letter")
    limit = current_app.config["GEMINI_FREE_USER_DAILY_LIMIT"]
    if daily >= limit:
        return False, f"Daily limit reached ({limit}/day). Upgrade to Pro for unlimited access."
    return True, ""


@cover_letter_bp.route("/")
@login_required
def list_letters():
    letters = (CoverLetter.query
               .filter_by(user_id=current_user.id, is_archived=False)
               .order_by(CoverLetter.updated_at.desc()).all())
    return render_template("cover_letter/list.html", letters=letters)


@cover_letter_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_letter():
    resumes = (Resume.query.filter_by(user_id=current_user.id)
               .order_by(Resume.updated_at.desc()).all())

    if request.method == "POST":
        can, err = _check_limit()
        if not can:
            flash(err, "warning")
            return redirect(url_for("cover_letter.new_letter"))

        job_title = request.form.get("job_title", "").strip()
        company_name = request.form.get("company_name", "").strip()
        job_description = request.form.get("job_description", "").strip()
        tone = request.form.get("tone", "professional")
        resume_id = request.form.get("resume_id", type=int)

        resume = None
        if resume_id:
            resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first()

        try:
            ai = get_ai_service()
            content = ai.generate_cover_letter(
                job_title=job_title,
                company_name=company_name,
                job_description=job_description,
                tone=tone,
                resume=resume,
            )
        except Exception as e:
            current_app.logger.error(f"Cover letter generation failed: {e}")
            flash("AI service unavailable. Please try again.", "error")
            return redirect(url_for("cover_letter.new_letter"))

        title = f"Cover Letter – {job_title or 'New Role'}"
        if company_name:
            title += f" at {company_name}"

        letter = CoverLetter(
            user_id=current_user.id,
            resume_id=resume_id,
            title=title[:255],
            job_title=job_title,
            company_name=company_name,
            job_description=job_description,
            tone=tone,
            content=content,
        )
        db.session.add(letter)
        db.session.flush()
        AIUsage.log_usage(current_user.id, "cover_letter", job_description[:200])
        _log("cover_letter_create", letter.id)
        db.session.commit()
        flash("Cover letter generated!", "success")
        return redirect(url_for("cover_letter.view_letter", letter_id=letter.id))

    return render_template("cover_letter/new.html", resumes=resumes)


@cover_letter_bp.route("/<int:letter_id>")
@login_required
def view_letter(letter_id):
    letter = CoverLetter.query.filter_by(
        id=letter_id, user_id=current_user.id
    ).first_or_404()
    return render_template("cover_letter/view.html", letter=letter)


@cover_letter_bp.route("/<int:letter_id>/edit", methods=["POST"])
@login_required
def edit_letter(letter_id):
    letter = CoverLetter.query.filter_by(
        id=letter_id, user_id=current_user.id
    ).first_or_404()
    data = request.get_json(silent=True) or {}
    if "content" in data:
        letter.content = data["content"]
    if "title" in data:
        letter.title = data["title"][:255]
    db.session.commit()
    return jsonify({"success": True})


@cover_letter_bp.route("/<int:letter_id>/download/<fmt>")
@login_required
def download(letter_id, fmt):
    letter = CoverLetter.query.filter_by(
        id=letter_id, user_id=current_user.id
    ).first_or_404()
    fmt = fmt.lower()

    if fmt == "txt":
        # Use BytesIO — works correctly under all WSGI servers
        buf = io.BytesIO(letter.content.encode("utf-8"))
        buf.seek(0)
        filename = f"cover_letter_{letter_id}.txt"
        letter.download_count = (letter.download_count or 0) + 1
        db.session.commit()
        return send_file(
            buf,
            as_attachment=True,
            download_name=filename,
            mimetype="text/plain; charset=utf-8",
        )

    if fmt == "pdf":
        try:
            from app.services.pdf_service import PDFService
            file_path = PDFService().generate_cover_letter(letter)
            filename = f"cover_letter_{letter_id}.pdf"
            letter.download_count = (letter.download_count or 0) + 1
            db.session.commit()
            return send_file(
                file_path,
                as_attachment=True,
                download_name=filename,
                mimetype="application/pdf",
            )
        except Exception as e:
            current_app.logger.error(f"Cover letter PDF error: {e}")
            flash("PDF generation failed. Please download as text.", "error")
            return redirect(url_for("cover_letter.view_letter", letter_id=letter_id))

    abort(400)


@cover_letter_bp.route("/<int:letter_id>/delete", methods=["POST"])
@login_required
def delete_letter(letter_id):
    letter = CoverLetter.query.filter_by(
        id=letter_id, user_id=current_user.id
    ).first_or_404()
    db.session.delete(letter)
    _log("cover_letter_delete", letter_id)
    db.session.commit()
    flash("Cover letter deleted.", "info")
    return redirect(url_for("cover_letter.list_letters"))
