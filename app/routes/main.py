"""CVForge AI - Main / Public Blueprint"""
from flask import Blueprint, render_template, abort, url_for
from app.models import Resume, PricingPlan
from app.routes.seo import site_base_url
from app.services.pricing import annotate_plans, banner_offer
from app.services import site_content

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    plans = annotate_plans(PricingPlan.query.filter_by(is_active=True).order_by(PricingPlan.sort_order).all())
    base = site_base_url()
    jsonld = site_content.landing_jsonld(
        base_url=base,
        plans=plans,
        pricing_url=base + url_for("main.pricing"),
        logo_url=base + url_for("static", filename="logo.png"),
    )
    return render_template("landing.html", plans=plans, faqs=site_content.LANDING_FAQS,
                           jsonld=jsonld)


@main_bp.route("/about")
def about():
    return render_template("about.html")


@main_bp.route("/pricing")
def pricing():
    plans = annotate_plans(PricingPlan.query.filter_by(is_active=True).order_by(PricingPlan.sort_order).all())
    return render_template("pricing.html", plans=plans, offer_banner=banner_offer(),
                           faqs=site_content.PRICING_FAQS)


@main_bp.route("/resume/<token>")
def public_resume(token):
    resume = Resume.query.filter_by(public_token=token, is_public=True).first_or_404()
    # Safe access — never crash on missing fields
    personal = resume.personal_info or {}
    return render_template("cv/public.html", resume=resume, personal=personal)
@main_bp.route("/privacy")
def privacy():
    return render_template("privacy.html")

@main_bp.route("/terms")
def terms():
    return render_template("terms.html")
