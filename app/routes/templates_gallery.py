"""CVForge AI - Templates Gallery Blueprint"""
from flask import Blueprint, render_template, request
from flask_login import current_user
from app.models import db, Template

templates_gallery_bp = Blueprint("templates_gallery", __name__)


@templates_gallery_bp.route("/")
def index():
    category = request.args.get("category", "all")
    q = Template.query.filter_by(is_active=True)
    if category != "all":
        q = q.filter_by(category=category)
    templates = q.order_by(Template.sort_order).all()
    categories = db.session.query(Template.category).distinct().all()
    categories = [c[0] for c in categories]
    return render_template("templates_gallery/index.html",
                           templates=templates,
                           categories=categories,
                           active_category=category)
