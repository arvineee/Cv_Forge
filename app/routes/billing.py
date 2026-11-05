"""
CVForge AI - Billing Blueprint
Prices come from PricingPlan plus any live Offer, resolved on the server
by app/services/pricing.py. The client never sends an amount.
"""
import secrets
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from app.models import db, PricingPlan, Subscription, Payment
from app.services.pricing import (
    annotate_plans, checkout_price, reserve_redemption, banner_offer,
)

billing_bp = Blueprint("billing", __name__)


def _active_plans():
    return (PricingPlan.query.filter_by(is_active=True)
            .order_by(PricingPlan.sort_order).all())


def _create_pending(plan, method, phone=None):
    """Create a pending Subscription + Payment at the server-computed price."""
    charged, offer, _saving = checkout_price(plan)
    reference = f"CVF-{secrets.token_hex(6).upper()}"

    subscription = Subscription(
        user_id=current_user.id,
        plan=plan.slug,
        amount=charged,
        currency="KES",
        status="pending",
        payment_reference=reference,
    )
    db.session.add(subscription)
    db.session.flush()

    payment = Payment(
        user_id=current_user.id,
        subscription_id=subscription.id,
        amount=charged,
        currency="KES",
        status="pending",
        payment_method=method,
        lipana_checkout_request_id=reference,
        phone=phone,
    )
    db.session.add(payment)

    if offer:
        reserve_redemption(offer, subscription, current_user.id, plan.price_kes, charged)

    db.session.commit()
    return reference, charged, plan.price_kes


@billing_bp.route("/")
@login_required
def index():
    subscriptions = (current_user.subscriptions
                     .order_by(Subscription.created_at.desc()).all())
    payments = (current_user.payments
                .order_by(Payment.created_at.desc()).all())
    active_sub = current_user.get_active_subscription()
    plans = annotate_plans(_active_plans())
    return render_template("billing/index.html",
                           subscriptions=subscriptions,
                           payments=payments,
                           active_sub=active_sub,
                           plans=plans)


@billing_bp.route("/plans")
def plans():
    plans = annotate_plans(_active_plans())
    requested_plan = request.args.get("plan")
    selected_plan_slug = next(
        (plan.slug for plan in plans if plan.slug == requested_plan and plan.price_kes > 0),
        None,
    )
    return render_template("billing/plans.html", plans=plans,
                           offer_banner=banner_offer(),
                           selected_plan_slug=selected_plan_slug)


@billing_bp.route("/continue/<plan_slug>")
@login_required
def continue_to_plan(plan_slug):
    plan = PricingPlan.query.filter_by(slug=plan_slug, is_active=True).first_or_404()
    if plan.price_kes <= 0:
        return redirect(url_for("cv.start"))
    return redirect(url_for("billing.plans", plan=plan.slug))


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

    reference, charged, _base = _create_pending(plan, "mpesa", phone=phone)

    try:
        from app.services.intasend_service import IntaSendService
        intasend = IntaSendService()
        resp = intasend.initiate_payment(
            phone=phone,
            amount=charged,
            reference=reference,
            description=f"CVForge {plan.name} Plan",
            email=current_user.email,
        )
        if resp.get("success"):
            flash("M-Pesa payment request sent! Check your phone.", "success")
            return redirect(url_for("billing.payment_pending", reference=reference))
        else:
            flash(f"Payment initiation failed: {resp.get('message', 'Unknown error')}", "error")
    except Exception as e:
        current_app.logger.error(f"IntaSend error: {e}")
        flash("Payment service unavailable. Please try again.", "error")

    return redirect(url_for("billing.plans"))


@billing_bp.route("/subscribe-card/<plan_slug>", methods=["POST"])
@login_required
def subscribe_card(plan_slug):
    """
    Card payment via IntaSend's hosted Checkout page. The redirect is UX
    only. The COMPLETE/FAILED result arrives via /webhooks/intasend, which is
    the source of truth for activation.
    """
    plan = PricingPlan.query.filter_by(slug=plan_slug, is_active=True).first_or_404()

    if plan.price_kes == 0:
        flash("You're already on the free plan.", "info")
        return redirect(url_for("billing.index"))

    reference, charged, _base = _create_pending(plan, "card")

    try:
        from app.services.intasend_service import IntaSendService
        intasend = IntaSendService()
        resp = intasend.initiate_card_payment(
            email=current_user.email,
            first_name=current_user.first_name or "",
            last_name=current_user.last_name or "",
            amount=charged,
            reference=reference,
            currency="KES",
            redirect_url=url_for("billing.payment_pending", reference=reference, _external=True),
            comment=f"CVForge {plan.name} Plan",
        )
        if resp.get("success"):
            return redirect(resp["checkout_url"])
        else:
            flash(f"Card payment could not be started: {resp.get('message', 'Unknown error')}", "error")
    except Exception as e:
        current_app.logger.error(f"IntaSend card checkout error: {e}")
        flash("Card payment service unavailable. Please try again.", "error")

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
