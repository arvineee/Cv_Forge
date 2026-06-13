"""
CVForge AI - Admin Blueprint
Fixed: impersonate uses POST+CSRF, uses db.session.get(),
added pricing plan management, template management
"""
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, abort
from flask_login import login_required, current_user
from functools import wraps
from app.models import db, User, Payment, Subscription, ActivityLog, AIUsage, Template, PricingPlan

admin_bp = Blueprint("admin", __name__)


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ── Dashboard ─────────────────────────────────────────────────────

@admin_bp.route("/")
@login_required
@admin_required
def index():
    total_users = User.query.count()
    pro_users = User.query.filter_by(plan="pro").count()
    premium_users = User.query.filter_by(plan="premium").count()
    total_revenue = db.session.query(
        db.func.sum(Payment.amount)
    ).filter_by(status="success").scalar() or 0
    daily_ai_usage = AIUsage.get_total_daily_count()

    return render_template("admin/index.html",
                           total_users=total_users,
                           pro_users=pro_users,
                           premium_users=premium_users,
                           total_revenue=total_revenue,
                           daily_ai_usage=daily_ai_usage)


# ── Users ─────────────────────────────────────────────────────────

@admin_bp.route("/users")
@login_required
@admin_required
def users():
    page = request.args.get("page", 1, type=int)
    q = request.args.get("q", "").strip()
    query = User.query
    if q:
        query = query.filter(
            db.or_(User.email.ilike(f"%{q}%"),
                   User.first_name.ilike(f"%{q}%"),
                   User.last_name.ilike(f"%{q}%"))
        )
    pagination = query.order_by(User.created_at.desc()).paginate(page=page, per_page=50)
    return render_template("admin/users.html", pagination=pagination, q=q)


@admin_bp.route("/users/<int:user_id>/impersonate", methods=["POST"])
@login_required
@admin_required
def impersonate(user_id):
    from flask_login import login_user
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    login_user(user)
    flash(f"Impersonating {user.email}.", "warning")
    return redirect(url_for("dashboard.index"))


@admin_bp.route("/users/<int:user_id>/toggle-active", methods=["POST"])
@login_required
@admin_required
def toggle_user_active(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    user.is_active = not user.is_active
    db.session.commit()
    flash(f"User {'activated' if user.is_active else 'deactivated'}.", "success")
    return redirect(url_for("admin.users"))


# ── Payments ──────────────────────────────────────────────────────

@admin_bp.route("/payments")
@login_required
@admin_required
def payments():
    payments = Payment.query.order_by(Payment.created_at.desc()).limit(200).all()
    return render_template("admin/payments.html", payments=payments)


# ── Pricing Plans ─────────────────────────────────────────────────

@admin_bp.route("/pricing")
@login_required
@admin_required
def pricing():
    plans = PricingPlan.query.order_by(PricingPlan.sort_order).all()
    return render_template("admin/pricing.html", plans=plans)


@admin_bp.route("/pricing/new", methods=["GET", "POST"])
@login_required
@admin_required
def pricing_new():
    if request.method == "POST":
        features_raw = request.form.get("features", "")
        features_list = [f.strip() for f in features_raw.splitlines() if f.strip()]
        plan = PricingPlan(
            slug=request.form.get("slug", "").lower().strip(),
            name=request.form.get("name", "").strip(),
            price_kes=int(request.form.get("price_kes", 0)),
            billing_period=request.form.get("billing_period", "month"),
            is_active=bool(request.form.get("is_active")),
            is_popular=bool(request.form.get("is_popular")),
            sort_order=int(request.form.get("sort_order", 0)),
            features=features_list,
            daily_cv_limit=int(request.form.get("daily_cv_limit", 3)),
            daily_cover_letter_limit=int(request.form.get("daily_cover_letter_limit", 3)),
            daily_ats_limit=int(request.form.get("daily_ats_limit", 5)),
            allow_docx=bool(request.form.get("allow_docx")),
            allow_version_history=bool(request.form.get("allow_version_history")),
            allow_career_coach=bool(request.form.get("allow_career_coach")),
        )
        db.session.add(plan)
        db.session.commit()
        flash(f"Plan '{plan.name}' created.", "success")
        return redirect(url_for("admin.pricing"))
    return render_template("admin/pricing_form.html", plan=None)


@admin_bp.route("/pricing/<int:plan_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def pricing_edit(plan_id):
    plan = db.session.get(PricingPlan, plan_id)
    if not plan:
        abort(404)

    if request.method == "POST":
        features_raw = request.form.get("features", "")
        features_list = [f.strip() for f in features_raw.splitlines() if f.strip()]
        plan.slug = request.form.get("slug", plan.slug).lower().strip()
        plan.name = request.form.get("name", plan.name).strip()
        plan.price_kes = int(request.form.get("price_kes", plan.price_kes))
        plan.billing_period = request.form.get("billing_period", plan.billing_period)
        plan.is_active = bool(request.form.get("is_active"))
        plan.is_popular = bool(request.form.get("is_popular"))
        plan.sort_order = int(request.form.get("sort_order", plan.sort_order))
        plan.features = features_list
        plan.daily_cv_limit = int(request.form.get("daily_cv_limit", plan.daily_cv_limit))
        plan.daily_cover_letter_limit = int(request.form.get("daily_cover_letter_limit", plan.daily_cover_letter_limit))
        plan.daily_ats_limit = int(request.form.get("daily_ats_limit", plan.daily_ats_limit))
        plan.allow_docx = bool(request.form.get("allow_docx"))
        plan.allow_version_history = bool(request.form.get("allow_version_history"))
        plan.allow_career_coach = bool(request.form.get("allow_career_coach"))
        db.session.commit()
        flash(f"Plan '{plan.name}' updated.", "success")
        return redirect(url_for("admin.pricing"))

    return render_template("admin/pricing_form.html", plan=plan)


@admin_bp.route("/pricing/<int:plan_id>/delete", methods=["POST"])
@login_required
@admin_required
def pricing_delete(plan_id):
    plan = db.session.get(PricingPlan, plan_id)
    if not plan:
        abort(404)
    db.session.delete(plan)
    db.session.commit()
    flash("Plan deleted.", "info")
    return redirect(url_for("admin.pricing"))


# ── Templates ─────────────────────────────────────────────────────

@admin_bp.route("/templates")
@login_required
@admin_required
def templates():
    templates = Template.query.order_by(Template.sort_order).all()
    return render_template("admin/templates.html", templates=templates)


@admin_bp.route("/templates/new", methods=["GET", "POST"])
@login_required
@admin_required
def template_new():
    if request.method == "POST":
        t = Template(
            name=request.form.get("name", "").strip(),
            slug=request.form.get("slug", "").lower().strip().replace(" ", "-"),
            description=request.form.get("description", "").strip(),
            category=request.form.get("category", "professional"),
            is_premium=bool(request.form.get("is_premium")),
            is_active=bool(request.form.get("is_active", True)),
            sort_order=int(request.form.get("sort_order", 0)),
            accent_color=request.form.get("accent_color", "#2563eb"),
            font_style=request.form.get("font_style", "modern"),
        )
        db.session.add(t)
        db.session.commit()
        flash(f"Template '{t.name}' created.", "success")
        return redirect(url_for("admin.templates"))
    return render_template("admin/template_form.html", template=None)


@admin_bp.route("/templates/<int:template_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def template_edit(template_id):
    t = db.session.get(Template, template_id)
    if not t:
        abort(404)

    if request.method == "POST":
        t.name = request.form.get("name", t.name).strip()
        t.slug = request.form.get("slug", t.slug).lower().strip().replace(" ", "-")
        t.description = request.form.get("description", t.description).strip()
        t.category = request.form.get("category", t.category)
        t.is_premium = bool(request.form.get("is_premium"))
        t.is_active = bool(request.form.get("is_active"))
        t.sort_order = int(request.form.get("sort_order", t.sort_order))
        t.accent_color = request.form.get("accent_color", t.accent_color)
        t.font_style = request.form.get("font_style", t.font_style)
        db.session.commit()
        flash(f"Template '{t.name}' updated.", "success")
        return redirect(url_for("admin.templates"))

    return render_template("admin/template_form.html", template=t)


@admin_bp.route("/templates/<int:template_id>/toggle", methods=["POST"])
@login_required
@admin_required
def template_toggle(template_id):
    t = db.session.get(Template, template_id)
    if not t:
        abort(404)
    t.is_active = not t.is_active
    db.session.commit()
    flash(f"Template {'activated' if t.is_active else 'deactivated'}.", "success")
    return redirect(url_for("admin.templates"))
