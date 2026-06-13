"""CVForge AI - API Blueprint (v1)"""
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from app.models import db, Resume, CoverLetter

api_bp = Blueprint("api", __name__)


@api_bp.route("/resumes")
@login_required
def list_resumes():
    resumes = Resume.query.filter_by(user_id=current_user.id).order_by(Resume.updated_at.desc()).all()
    return jsonify([r.to_dict() for r in resumes])


@api_bp.route("/resumes/<int:resume_id>")
@login_required
def get_resume(resume_id):
    resume = Resume.query.filter_by(id=resume_id, user_id=current_user.id).first_or_404()
    return jsonify(resume.to_dict())


@api_bp.route("/me")
@login_required
def me():
    return jsonify({
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "plan": current_user.plan,
        "is_premium": current_user.is_premium,
    })
