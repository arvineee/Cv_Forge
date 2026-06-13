"""
CVForge AI - Billing Blueprint
Fixed: billing/index.html template added, uses PricingPlan from DB
"""
import secrets
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from app.models import db, PricingPlan, Subscription, Payment

billing_bp = Blueprint("billing", __name__)


@billing_bp.route("/")
@login_required
def index():
    subscriptions = (current_user.subscriptions
                     .order_by(Subscription.created_at.desc()).all())
    payments = (current_user.payments
                .order_by(Payment.created_at.desc()).all())
    active_sub = current_user.get_active_subscription()
    plans = PricingPlan.query.filter_by(is_active=True).order_by(PricingPlan.sort_order).all()
    return render_template("billing/index.html",
                           subscriptions=subscriptions,
                           payments=payments,
                           active_sub=active_sub,
                           plans=plans)


@billing_bp.route("/plans")
def plans():
    plans = PricingPlan.query.filter_by(is_active=True).order_by(PricingPlan.sort_order).all()
    return render_template("billing/plans.html", plans=plans)


@billing_bp.route("/subscribe/<plan_slug>", methods=["POST"])
@login_required
def subscribe(plan_slug):
    plan = PricingPlan.query.filter_by(slug=plan_slug, is_active=True).first_or_404()

    if plan.price_kes == 0:
        flash("You're already on the free plan.", "info")
        return redirect(url_for("billing.index"))

    phone = request.form.get("phone", "").strip()
    if not phone:
        flash("Phone number is required for M-Pesa payment.", "error")
        return redirect(url_for("billing.plans"))

    reference = f"CVF-{secrets.token_hex(6).upper()}"
    subscription = Subscription(
        user_id=current_user.id,
        plan=plan.slug,
        amount=plan.price_kes,
        currency="KES",
        status="pending",
        payment_reference=reference,
    )
    db.session.add(subscription)
    db.session.flush()

    payment = Payment(
        user_id=current_user.id,
        subscription_id=subscription.id,
        amount=plan.price_kes,
        currency="KES",
        status="pending",
        payment_method="mpesa",
        lipana_checkout_request_id=reference,
        phone=phone,
    )
    db.session.add(payment)
    db.session.commit()

    try:
        from app.services.lipana_service import LipanaService
        lipana = LipanaService()
        resp = lipana.initiate_payment(
            phone=phone,
            amount=plan.price_kes,
            reference=reference,
            description=f"CVForge {plan.name} Plan",
        )
        if resp.get("success"):
            flash("M-Pesa payment request sent! Check your phone.", "success")
            return redirect(url_for("billing.payment_pending", reference=reference))
        else:
            flash(f"Payment initiation failed: {resp.get('message', 'Unknown error')}", "error")
    except Exception as e:
        current_app.logger.error(f"Lipana error: {e}")
        flash("Payment service unavailable. Please try again.", "error")

    return redirect(url_for("billing.plans"))


@billing_bp.route("/pending/<reference>")
@login_required
def payment_pending(reference):
    subscription = Subscription.query.filter_by(
        payment_reference=reference, user_id=current_user.id
    ).first_or_404()
    return render_template("billing/payments.html", subscription=subscription)


@billing_bp.route("/success")
@login_required
def success():
    return render_template("billing/success.html")


@billing_bp.route("/status/<reference>")
@login_required
def payment_status(reference):
    subscription = Subscription.query.filter_by(
        payment_reference=reference, user_id=current_user.id
    ).first()
    if not subscription:
        return jsonify({"status": "not_found"})
    return jsonify({
        "status": subscription.status,
        "plan": subscription.plan,
        "redirect": url_for("billing.success") if subscription.status == "active" else None,
    })
