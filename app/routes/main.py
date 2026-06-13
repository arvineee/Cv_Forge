"""CVForge AI - Main / Public Blueprint"""
from flask import Blueprint, render_template, abort
from app.models import Resume, PricingPlan

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    plans = PricingPlan.query.filter_by(is_active=True).order_by(PricingPlan.sort_order).all()
    return render_template("landing.html", plans=plans)


@main_bp.route("/about")
def about():
    return render_template("about.html")


@main_bp.route("/pricing")
def pricing():
    plans = PricingPlan.query.filter_by(is_active=True).order_by(PricingPlan.sort_order).all()
    return render_template("pricing.html", plans=plans)


@main_bp.route("/resume/<token>")
def public_resume(token):
    resume = Resume.query.filter_by(public_token=token, is_public=True).first_or_404()
    # Safe access — never crash on missing fields
    personal = resume.personal_info or {}
    return render_template("cv/public.html", resume=resume, personal=personal)
