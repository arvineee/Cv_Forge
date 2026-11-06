"""
CVForge AI - Admin Blueprint

Includes:
- Impersonate (POST+CSRF, audit logged)
- Pricing plan & template management
- Manual plan activation for approved payment claims or goodwill extensions
- Manual payment claims review (approve runs the same _handle_payment_success
  path as a real webhook, so state never drifts)
- Broadcast email to filtered users with a two-step preview/confirm
"""
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, abort
from flask_login import login_required, current_user
from functools import wraps
from app.models import (db, User, Payment, Subscription, ActivityLog, AIUsage, Template,
                        PricingPlan, Offer, OfferRedemption, Feedback,
                        ManualPaymentClaim, BroadcastEmail, Notification, utcnow)

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

    from app.services.nudge_service import get_nudge_candidates
    nudge_due_count = len(get_nudge_candidates())
    pending_claims = ManualPaymentClaim.query.filter_by(status="pending").count()

    return render_template("admin/index.html",
                           total_users=total_users,
                           pro_users=pro_users,
                           premium_users=premium_users,
                           total_revenue=total_revenue,
                           daily_ai_usage=daily_ai_usage,
                           nudge_due_count=nudge_due_count,
                           pending_claims=pending_claims)


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
    # FIX: impersonation previously left no audit trail at all — no record
    # of which admin did it, or who they became. Log it before switching
    # sessions, while current_user is still the admin.
    db.session.add(ActivityLog(
        user_id=current_user.id, action="admin_impersonate_start",
        resource_type="user", resource_id=user.id,
        ip_address=request.remote_addr,
        details={"admin_email": current_user.email, "target_email": user.email},
    ))
    db.session.commit()
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
            billing_period=request.form.get("billing_period", "month") if request.form.get("billing_period") in ("week", "month", "year", "forever") else "month",
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
            allow_public_link=bool(request.form.get("allow_public_link")),
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
        plan.allow_public_link = bool(request.form.get("allow_public_link"))
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


# ── Pro-upgrade nudges ───────────────────────────────────────────

@admin_bp.route("/nudges", methods=["GET", "POST"])
@login_required
@admin_required
def nudges():
    from app.services.nudge_service import (
        get_nudge_candidates, send_pro_upgrade_nudges,
        NUDGE_INTERVAL_DAYS, REGISTERED_GRACE_DAYS, MAX_NUDGES,
    )

    if request.method == "POST":
        result = send_pro_upgrade_nudges()
        db.session.add(ActivityLog(
            user_id=current_user.id, action="admin_send_nudges",
            resource_type="user", resource_id=None,
            ip_address=request.remote_addr, details=result,
        ))
        db.session.commit()
        msg = f"Sent {result['sent']} upgrade reminder email{'s' if result['sent'] != 1 else ''}."
        if result["failed"]:
            msg += f" {result['failed']} failed — check logs."
        flash(msg, "success" if not result["failed"] else "warning")
        return redirect(url_for("admin.nudges"))

    candidates = get_nudge_candidates()
    return render_template("admin/nudges.html",
                           candidates=candidates,
                           interval_days=NUDGE_INTERVAL_DAYS,
                           grace_days=REGISTERED_GRACE_DAYS,
                           max_nudges=MAX_NUDGES)


# ── Visitors ──────────────────────────────────────────────────────

@admin_bp.route("/visitors")
@login_required
@admin_required
def visitors():
    from datetime import timedelta
    from app.models import PageVisit
    from sqlalchemy import func

    days = request.args.get("days", 7, type=int)
    cutoff = utcnow() - timedelta(days=days)

    recent = (PageVisit.query.filter(PageVisit.created_at >= cutoff)
              .order_by(PageVisit.created_at.desc()).limit(200).all())

    total_views = PageVisit.query.filter(PageVisit.created_at >= cutoff).count()
    unique_visitors = (db.session.query(func.count(func.distinct(PageVisit.session_id)))
                        .filter(PageVisit.created_at >= cutoff).scalar()) or 0
    logged_in_visits = (PageVisit.query.filter(PageVisit.created_at >= cutoff,
                                                PageVisit.user_id.isnot(None)).count())

    top_pages = (db.session.query(PageVisit.path, func.count(PageVisit.id).label("views"))
                 .filter(PageVisit.created_at >= cutoff)
                 .group_by(PageVisit.path)
                 .order_by(func.count(PageVisit.id).desc())
                 .limit(15).all())

    daily = (db.session.query(func.date(PageVisit.created_at).label("day"),
                               func.count(PageVisit.id).label("views"))
             .filter(PageVisit.created_at >= cutoff)
             .group_by("day")
             .order_by("day")
             .all())

    return render_template("admin/visitors.html",
                           recent=recent, total_views=total_views,
                           unique_visitors=unique_visitors,
                           logged_in_visits=logged_in_visits,
                           top_pages=top_pages, daily=daily, days=days)


# ── Offers (time-limited discounts) ───────────────────────────────

def _offer_form_values(form):
    """
    Validate admin input. Returns (data, errors). Prices are never touched
    here; an offer only describes a discount that applies while it's live.
    """
    from app.services.pricing import parse_local_datetime
    errors = []
    name = form.get("name", "").strip()
    public_label = form.get("public_label", "").strip()
    if not name:
        errors.append("Internal name is required.")
    if not public_label:
        errors.append("Public label is required (e.g. 'Launch week: 30% off').")
    if len(public_label) > 120:
        errors.append("Public label must be 120 characters or fewer.")

    discount_type = form.get("discount_type", "percent")
    if discount_type not in ("percent", "fixed"):
        errors.append("Discount type must be percent or fixed.")
    try:
        discount_value = int(form.get("discount_value", "0"))
    except ValueError:
        discount_value = 0
        errors.append("Discount value must be a whole number.")
    if discount_type == "percent" and not (1 <= discount_value <= 90):
        errors.append("Percent discount must be between 1 and 90.")
    if discount_type == "fixed" and discount_value < 1:
        errors.append("Fixed discount must be at least KES 1.")

    slugs = [s for s in form.getlist("plan_slugs") if s]
    plan_slugs = slugs or None  # none ticked = every paid plan

    try:
        starts_at = parse_local_datetime(form.get("starts_at"))
        ends_at = parse_local_datetime(form.get("ends_at"))
    except ValueError:
        starts_at = ends_at = None
        errors.append("Start or end date is not a valid date and time.")
    if starts_at and ends_at and ends_at <= starts_at:
        errors.append("End must be after start.")

    max_raw = (form.get("max_redemptions") or "").strip()
    max_redemptions = None
    if max_raw:
        try:
            max_redemptions = int(max_raw)
            if max_redemptions < 1:
                errors.append("Maximum redemptions must be at least 1 (or leave blank).")
        except ValueError:
            errors.append("Maximum redemptions must be a whole number.")

    data = dict(
        name=name, public_label=public_label, discount_type=discount_type,
        discount_value=discount_value, plan_slugs=plan_slugs,
        starts_at=starts_at, ends_at=ends_at, max_redemptions=max_redemptions,
        is_active=bool(form.get("is_active")),
    )
    return data, errors


@admin_bp.route("/offers")
@login_required
@admin_required
def offers():
    from app.services.pricing import offer_status, redemption_count
    rows = []
    for o in Offer.query.order_by(Offer.created_at.desc()).all():
        redeemed = OfferRedemption.query.filter_by(offer_id=o.id, status="redeemed").all()
        rows.append({
            "offer": o,
            "status": offer_status(o),
            "seats_used": redemption_count(o),
            "paid_count": len(redeemed),
            "kes_given_away": sum(r.base_amount - r.charged_amount for r in redeemed),
        })
    return render_template("admin/offers.html", rows=rows)


@admin_bp.route("/offers/new", methods=["GET", "POST"])
@login_required
@admin_required
def offer_new():
    paid_plans = PricingPlan.query.filter(PricingPlan.price_kes > 0).order_by(PricingPlan.sort_order).all()
    if request.method == "POST":
        data, errors = _offer_form_values(request.form)
        if not errors:
            offer = Offer(**data)
            db.session.add(offer)
            db.session.commit()
            flash(f"Offer '{offer.name}' created.", "success")
            return redirect(url_for("admin.offers"))
        for e in errors:
            flash(e, "error")
        return render_template("admin/offer_form.html", offer=None, paid_plans=paid_plans, form=request.form)
    return render_template("admin/offer_form.html", offer=None, paid_plans=paid_plans, form=None)


@admin_bp.route("/offers/<int:offer_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def offer_edit(offer_id):
    offer = db.session.get(Offer, offer_id)
    if not offer:
        abort(404)
    paid_plans = PricingPlan.query.filter(PricingPlan.price_kes > 0).order_by(PricingPlan.sort_order).all()
    if request.method == "POST":
        data, errors = _offer_form_values(request.form)
        if not errors:
            for k, v in data.items():
                setattr(offer, k, v)
            db.session.commit()
            flash(f"Offer '{offer.name}' updated.", "success")
            return redirect(url_for("admin.offers"))
        for e in errors:
            flash(e, "error")
        return render_template("admin/offer_form.html", offer=offer, paid_plans=paid_plans, form=request.form)
    return render_template("admin/offer_form.html", offer=offer, paid_plans=paid_plans, form=None)


@admin_bp.route("/offers/<int:offer_id>/void", methods=["POST"])
@login_required
@admin_required
def offer_void(offer_id):
    """Void: the offer stops applying immediately and prices revert to base."""
    offer = db.session.get(Offer, offer_id)
    if not offer:
        abort(404)
    offer.is_active = False
    db.session.add(ActivityLog(
        user_id=current_user.id, action="admin_offer_void",
        resource_type="offer", resource_id=offer.id,
        ip_address=request.remote_addr, details={"name": offer.name},
    ))
    db.session.commit()
    flash(f"Offer '{offer.name}' voided. Prices have reverted to base.", "info")
    return redirect(url_for("admin.offers"))


@admin_bp.route("/offers/<int:offer_id>/restore", methods=["POST"])
@login_required
@admin_required
def offer_restore(offer_id):
    offer = db.session.get(Offer, offer_id)
    if not offer:
        abort(404)
    offer.is_active = True
    db.session.commit()
    flash(f"Offer '{offer.name}' is active again (dates and seat limit still apply).", "success")
    return redirect(url_for("admin.offers"))


# ── Feedback review ───────────────────────────────────────────────

@admin_bp.route("/feedback")
@login_required
@admin_required
def feedback():
    from app.routes.feedback import CATEGORIES
    status = request.args.get("status", "new")
    category = request.args.get("category", "")
    q = Feedback.query
    if status != "all":
        q = q.filter_by(status=status)
    if category:
        q = q.filter_by(category=category)
    items = q.order_by(Feedback.created_at.desc()).limit(200).all()
    counts = dict(db.session.query(Feedback.status, db.func.count(Feedback.id))
                  .group_by(Feedback.status).all())
    avg_rating = db.session.query(db.func.avg(Feedback.rating)).filter(Feedback.rating.isnot(None)).scalar()
    return render_template("admin/feedback.html", items=items, status=status,
                           category=category, categories=CATEGORIES, counts=counts,
                           avg_rating=round(avg_rating, 1) if avg_rating else None)


@admin_bp.route("/feedback/<int:item_id>", methods=["POST"])
@login_required
@admin_required
def feedback_update(item_id):
    item = db.session.get(Feedback, item_id)
    if not item:
        abort(404)
    new_status = request.form.get("status", item.status)
    if new_status in ("new", "reviewed", "resolved"):
        item.status = new_status
    item.admin_note = (request.form.get("admin_note", item.admin_note or "").strip() or None)
    db.session.commit()
    flash("Feedback updated.", "success")
    return redirect(request.referrer or url_for("admin.feedback"))


# ── Manual plan activation ───────────────────────────────────────

@admin_bp.route("/manual-plan", methods=["GET", "POST"])
@login_required
@admin_required
def manual_plan():
    """Give an admin a single place to find a user and set their plan
    directly, e.g. after approving a manual payment claim or granting
    a goodwill extension."""
    email = (request.args.get("email") or "").strip().lower()
    user = User.query.filter_by(email=email).first() if email else None
    plans = PricingPlan.query.order_by(PricingPlan.sort_order).all()

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        plan_slug = request.form.get("plan", "free")
        try:
            days = int(request.form.get("days", 30))
        except (TypeError, ValueError):
            days = 30
        # Server-side bounds: the form's min/max is client-only, and a zero or
        # negative value would set an already-expired plan while telling the
        # user it was activated.
        days = max(1, min(days, 3650))
        note = (request.form.get("note") or "").strip()

        user = User.query.filter_by(email=email).first()
        if not user:
            flash(f"No user found with email '{email}'.", "error")
            return redirect(url_for("admin.manual_plan"))

        allowed_plans = {"free", "basic", "pro", "premium"} | {p.slug for p in plans}
        if plan_slug not in allowed_plans:
            flash("Invalid plan.", "error")
            return redirect(url_for("admin.manual_plan", email=email))

        from datetime import datetime, timezone, timedelta
        user.plan = plan_slug
        if plan_slug == "free":
            user.plan_expires_at = None
        else:
            user.plan_expires_at = datetime.now(timezone.utc) + timedelta(days=days)

        db.session.add(ActivityLog(
            user_id=current_user.id, action="admin_manual_set_plan",
            resource_type="user", resource_id=user.id,
            ip_address=request.remote_addr,
            details={"plan": plan_slug, "days": days, "note": note},
        ))
        db.session.add(Notification(
            user_id=user.id,
            title="Your plan has been updated",
            message=f"An administrator set your plan to '{plan_slug}'."
                    + (f" Note: {note}" if note else ""),
            type="success", action_url="/billing/",
        ))
        db.session.commit()

        from app.services.email_service import send_plan_changed_email
        try:
            send_plan_changed_email(user, plan_slug, days, note)
        except Exception as e:
            current_app.logger.warning(f"Plan-changed email failed for user {user.id}: {e}")

        flash(f"{user.email} set to '{plan_slug}' for {days} day(s).", "success")
        return redirect(url_for("admin.manual_plan", email=user.email))

    return render_template("admin/manual_plan.html", user=user, plans=plans, email=email)


# ── Manual payment claims ────────────────────────────────────────

@admin_bp.route("/claims")
@login_required
@admin_required
def claims():
    status = request.args.get("status", "pending")
    q = ManualPaymentClaim.query
    if status != "all":
        q = q.filter_by(status=status)
    items = q.order_by(ManualPaymentClaim.created_at.desc()).limit(200).all()
    counts = dict(db.session.query(
        ManualPaymentClaim.status, db.func.count(ManualPaymentClaim.id)
    ).group_by(ManualPaymentClaim.status).all())
    return render_template("admin/claims.html", items=items, status=status, counts=counts)


@admin_bp.route("/claims/<int:claim_id>/approve", methods=["POST"])
@login_required
@admin_required
def claim_approve(claim_id):
    claim = db.session.get(ManualPaymentClaim, claim_id)
    if not claim:
        abort(404)
    if claim.status != "pending":
        flash(f"That claim was already {claim.status}.", "info")
        return redirect(url_for("admin.claims"))

    note = (request.form.get("admin_note") or "").strip()

    # Reuse the exact same activation path as a real webhook, so the
    # subscription, user plan, payment row and offer redemption are all
    # kept consistent — no risk of a manual approval drifting from the
    # normal payment flow.
    from app.routes.webhooks import _handle_payment_success

    # Fall back to the linked subscription's reference if the claim row's own
    # reference is empty, so a valid claim isn't left unactivated.
    reference = claim.reference or (
        claim.subscription.payment_reference if claim.subscription else None
    )
    activated = False
    if reference:
        activated = _handle_payment_success({
            "reference": reference,
            "checkout_request_id": reference,
            "transaction_id": f"MANUAL-{claim.id}",
        })

    claim.status = "approved"
    claim.admin_note = note or None
    claim.reviewed_by = current_user.id
    claim.reviewed_at = utcnow()
    db.session.add(ActivityLog(
        user_id=current_user.id, action="admin_claim_approve",
        resource_type="manual_payment_claim", resource_id=claim.id,
        ip_address=request.remote_addr,
        details={"reference": reference, "activated": bool(activated)},
    ))
    # Only tell the user their plan is active if it actually is. When nothing
    # matched, the admin finishes via Manual Plan, which notifies the user
    # itself — so we don't send a false "activated" message here.
    if activated:
        db.session.add(Notification(
            user_id=claim.user_id,
            title="Payment confirmed",
            message="We verified your payment and activated your plan."
                    + (f" {note}" if note else ""),
            type="success", action_url="/billing/",
        ))
    db.session.commit()

    if activated:
        try:
            from app.services.email_service import send_claim_approved_email
            user = db.session.get(User, claim.user_id)
            if user:
                send_claim_approved_email(user, claim, note)
        except Exception as e:
            current_app.logger.warning(f"Claim-approved email failed for claim {claim.id}: {e}")

    if activated:
        flash("Claim approved and plan activated.", "success")
    else:
        flash("Claim marked approved, but no pending subscription matched the reference. "
              "You may need to set the plan manually via Manual Plan.", "warning")
    return redirect(url_for("admin.claims"))


@admin_bp.route("/claims/<int:claim_id>/reject", methods=["POST"])
@login_required
@admin_required
def claim_reject(claim_id):
    claim = db.session.get(ManualPaymentClaim, claim_id)
    if not claim:
        abort(404)
    if claim.status != "pending":
        flash(f"That claim was already {claim.status}.", "info")
        return redirect(url_for("admin.claims"))

    note = (request.form.get("admin_note") or "").strip()

    claim.status = "rejected"
    claim.admin_note = note or None
    claim.reviewed_by = current_user.id
    claim.reviewed_at = utcnow()
    db.session.add(ActivityLog(
        user_id=current_user.id, action="admin_claim_reject",
        resource_type="manual_payment_claim", resource_id=claim.id,
        ip_address=request.remote_addr,
        details={"reference": claim.reference, "note": note},
    ))
    db.session.add(Notification(
        user_id=claim.user_id,
        title="We couldn't verify your payment",
        message=note or "Please contact support with your M-Pesa confirmation message.",
        type="warning", action_url="/support",
    ))
    db.session.commit()

    try:
        from app.services.email_service import send_claim_rejected_email
        user = db.session.get(User, claim.user_id)
        if user:
            send_claim_rejected_email(user, claim, note)
    except Exception as e:
        current_app.logger.warning(f"Claim-rejected email failed for claim {claim.id}: {e}")

    flash("Claim rejected. The user has been notified.", "info")
    return redirect(url_for("admin.claims"))


# ── Broadcast email to users ─────────────────────────────────────

@admin_bp.route("/broadcast", methods=["GET", "POST"])
@login_required
@admin_required
def broadcast():
    """Send a plain-text announcement to a filtered set of users.
    Two-step: POST with preview_only=1 renders a preview + recipient
    count; then confirm sends. Audience filter is stored so it's clear
    who received each message."""
    if request.method == "POST":
        subject = (request.form.get("subject") or "").strip()
        body = (request.form.get("body") or "").strip()
        audience = request.form.get("audience", "all")
        preview_only = bool(request.form.get("preview_only"))

        if not subject or not body:
            flash("Subject and message are required.", "error")
            return redirect(url_for("admin.broadcast"))

        if audience not in ("all", "free", "paid", "verified", "newsletter"):
            audience = "all"

        q = User.query.filter(User.is_active.is_(True))
        if audience == "free":
            q = q.filter(User.plan == "free")
        elif audience == "paid":
            q = q.filter(User.plan.in_(["basic", "pro", "premium"]))
        elif audience == "verified":
            q = q.filter(User.is_verified.is_(True))
        elif audience == "newsletter":
            from app.models import UserSettings
            q = q.join(UserSettings, UserSettings.user_id == User.id).filter(
                UserSettings.email_newsletter.is_(True)
            )

        recipients = q.order_by(User.created_at.asc()).all()

        if preview_only:
            return render_template("admin/broadcast.html",
                                   recent=BroadcastEmail.query
                                            .order_by(BroadcastEmail.created_at.desc())
                                            .limit(20).all(),
                                   preview_subject=subject,
                                   preview_body=body,
                                   preview_count=len(recipients),
                                   subject=subject, body=body, audience=audience)

        from app.services.email_service import send_broadcast_email

        row = BroadcastEmail(
            subject=subject, body=body, audience=audience,
            sent_by=current_user.id,
        )
        db.session.add(row)
        db.session.flush()

        sent = 0
        failed = 0
        for user in recipients:
            try:
                ok = send_broadcast_email(user, subject, body)
                if ok:
                    sent += 1
                else:
                    failed += 1
            except Exception as e:
                current_app.logger.warning(f"Broadcast failed for user {user.id}: {e}")
                failed += 1

        row.recipient_count = sent
        row.failed_count = failed
        db.session.add(ActivityLog(
            user_id=current_user.id, action="admin_broadcast",
            resource_type="broadcast_email", resource_id=row.id,
            ip_address=request.remote_addr,
            details={"audience": audience, "sent": sent, "failed": failed},
        ))
        db.session.commit()

        msg = f"Broadcast sent to {sent} user(s)."
        if failed:
            msg += f" {failed} failed — check logs."
        flash(msg, "success" if not failed else "warning")
        return redirect(url_for("admin.broadcast"))

    return render_template("admin/broadcast.html",
                           recent=BroadcastEmail.query
                                    .order_by(BroadcastEmail.created_at.desc())
                                    .limit(20).all(),
                           preview_subject=None, preview_body=None,
                           preview_count=None, subject="", body="", audience="all")
