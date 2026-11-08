"""
CVForge AI - Billing Blueprint
Prices come from PricingPlan plus any live Offer, resolved on the server
by app/services/pricing.py. The client never sends an amount.

Adds: /claim-payment/<reference> so a user whose webhook was missed can
paste their M-Pesa confirmation message and have an admin verify it.
"""
import secrets
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from app.models import (db, PricingPlan, Subscription, Payment,
                        ManualPaymentClaim, Notification)
from app.services.pricing import (
    annotate_plans, checkout_price, reserve_redemption, banner_offer, purchase_blocker,
)

billing_bp = Blueprint("billing", __name__)


def _active_plans():
    return (PricingPlan.query.filter_by(is_active=True)
            .order_by(PricingPlan.sort_order).all())


# How long before the status poll asks IntaSend directly, and when we give up.
RECONCILE_AFTER_SECONDS = 45
PENDING_TIMEOUT_SECONDS = 600


def _remember_invoice(reference: str, invoice_id) -> None:
    """Store the IntaSend invoice id so the status poll can check it later."""
    if not invoice_id:
        return
    payment = Payment.query.filter_by(lipana_checkout_request_id=reference).first()
    if payment:
        payment.raw_webhook = {"invoice_id": str(invoice_id)}
        db.session.commit()


def _invoice_id_from(resp: dict):
    """IntaSend nests the invoice differently for STK push and checkout."""
    if not isinstance(resp, dict):
        return None
    if resp.get("invoice_id"):
        return resp["invoice_id"]
    raw = resp.get("raw") or {}
    invoice = raw.get("invoice") if isinstance(raw, dict) else None
    if isinstance(invoice, dict) and invoice.get("invoice_id"):
        return invoice["invoice_id"]
    return raw.get("invoice_id") if isinstance(raw, dict) else None


def _reconcile_with_intasend(subscription, reference: str) -> None:
    """If a payment has been pending a while, ask IntaSend directly.

    Covers missed or failed webhook deliveries. Reuses the webhook handlers,
    which are idempotent, so calling this repeatedly is safe.
    """
    from app.routes.webhooks import _handle_payment_success, _handle_payment_failed

    created = subscription.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    if (datetime.now(timezone.utc) - created).total_seconds() < RECONCILE_AFTER_SECONDS:
        return

    payment = Payment.query.filter_by(lipana_checkout_request_id=reference).first()
    invoice_id = (payment.raw_webhook or {}).get("invoice_id") if payment and isinstance(payment.raw_webhook, dict) else None
    if not invoice_id:
        return  # nothing to check against; the webhook is the only route

    try:
        from app.services.intasend_service import IntaSendService
        result = IntaSendService().check_status(invoice_id=invoice_id)
    except Exception as e:
        current_app.logger.warning(f"Reconcile skipped for ref={reference}: {e}")
        return
    if not result.get("success"):
        return

    invoice = result.get("invoice") if isinstance(result.get("invoice"), dict) else result
    state = invoice.get("state")
    current_app.logger.info(f"Reconcile ref={reference} invoice={invoice_id} state={state}")

    if state == "COMPLETE":
        _handle_payment_success({"reference": reference, "checkout_request_id": reference,
                                 "transaction_id": invoice_id})
    elif state == "FAILED":
        _handle_payment_failed({"reference": reference, "checkout_request_id": reference,
                                "failed_reason": invoice.get("failed_reason")})


def _abandon_pending(reference: str) -> None:
    """The provider never accepted this checkout: close it and free any offer seat."""
    from app.services.pricing import release_redemption
    sub = Subscription.query.filter_by(payment_reference=reference, status="pending").first()
    if not sub:
        return
    sub.status = "failed"
    release_redemption(sub.id)
    payment = Payment.query.filter_by(lipana_checkout_request_id=reference).first()
    if payment and payment.status == "pending":
        payment.status = "failed"
    db.session.commit()


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

    blocker = purchase_blocker(current_user, plan)
    if blocker:
        flash(blocker, "warning")
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
            _remember_invoice(reference, resp.get("invoice_id"))
            flash("M-Pesa payment request sent! Check your phone.", "success")
            return redirect(url_for("billing.payment_pending", reference=reference))
        else:
            _abandon_pending(reference)
            flash(f"Payment initiation failed: {resp.get('message', 'Unknown error')}", "error")
    except Exception as e:
        current_app.logger.error(f"IntaSend error: {e}")
        db.session.rollback()
        _abandon_pending(reference)
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

    blocker = purchase_blocker(current_user, plan)
    if blocker:
        flash(blocker, "warning")
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
            _remember_invoice(reference, _invoice_id_from(resp))
            return redirect(resp["checkout_url"])
        else:
            _abandon_pending(reference)
            flash(f"Card payment could not be started: {resp.get('message', 'Unknown error')}", "error")
    except Exception as e:
        current_app.logger.error(f"IntaSend card checkout error: {e}")
        db.session.rollback()
        _abandon_pending(reference)
        flash("Card payment service unavailable. Please try again.", "error")

    return redirect(url_for("billing.plans"))


@billing_bp.route("/subscribe-paystack/<plan_slug>", methods=["POST"])
@login_required
def subscribe_paystack(plan_slug):
    """Start a Paystack hosted checkout using the server-resolved plan price."""
    plan = PricingPlan.query.filter_by(slug=plan_slug, is_active=True).first_or_404()

    if plan.price_kes <= 0:
        flash("The free plan does not require payment.", "info")
        return redirect(url_for("billing.index"))

    blocker = purchase_blocker(current_user, plan)
    if blocker:
        flash(blocker, "warning")
        return redirect(url_for("billing.index"))

    reference, charged, _base = _create_pending(plan, "paystack")
    try:
        from app.services.paystack_service import PaystackService
        service = PaystackService()
        result = service.initialize(
            email=current_user.email,
            amount_kes=charged,
            reference=reference,
            callback_url=url_for("billing.paystack_callback", _external=True),
            metadata={
                "user_id": current_user.id,
                "subscription_reference": reference,
                "plan": plan.slug,
                "custom_fields": [
                    {"display_name": "Plan", "variable_name": "plan", "value": plan.name},
                    {"display_name": "CVForge Reference", "variable_name": "cvforge_reference", "value": reference},
                ],
            },
        )
        # Keep the checkout URL and Paystack reference for support/audit.
        payment = Payment.query.filter_by(lipana_checkout_request_id=reference).first()
        if payment:
            payment.raw_webhook = {
                "provider": "paystack",
                "checkout_url": result.get("authorization_url"),
                "access_code": result.get("access_code"),
            }
            db.session.commit()
        return redirect(result["authorization_url"])
    except Exception as exc:
        current_app.logger.exception("Paystack checkout initialization failed for %s", reference)
        db.session.rollback()
        _abandon_pending(reference)
        flash("Paystack checkout could not be started. Please try again or use M-Pesa.", "error")
        return redirect(url_for("billing.plans"))


@billing_bp.route("/paystack/callback")
@login_required
def paystack_callback():
    """Verify the return from Paystack; the redirect itself is never proof of payment."""
    reference = (request.args.get("reference") or "").strip()
    if not reference:
        flash("We could not identify that payment. Please check your payment history.", "error")
        return redirect(url_for("billing.index"))

    subscription = Subscription.query.filter_by(
        payment_reference=reference, user_id=current_user.id
    ).first()
    if not subscription:
        flash("That payment reference does not belong to your account.", "error")
        return redirect(url_for("billing.index"))

    from app.routes.webhooks import confirm_paystack_payment
    try:
        confirmed = confirm_paystack_payment(reference)
    except Exception:
        current_app.logger.exception("Paystack callback verification failed for %s", reference)
        confirmed = False

    if confirmed:
        flash("Payment confirmed. Your CVForge plan is now active.", "success")
        return redirect(url_for("billing.success"))

    flash("Payment is not confirmed yet. If you completed checkout, allow a moment for confirmation.", "info")
    return redirect(url_for("billing.payment_pending", reference=reference))


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

    status = subscription.status
    if status == "pending":
        payment = Payment.query.filter_by(lipana_checkout_request_id=reference).first()
        if payment and payment.payment_method == "paystack":
            created = subscription.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            raw = payment.raw_webhook if isinstance(payment.raw_webhook, dict) else {}
            last_checked = raw.get("paystack_last_checked_at")
            try:
                last_checked_at = datetime.fromisoformat(last_checked) if last_checked else None
                if last_checked_at and last_checked_at.tzinfo is None:
                    last_checked_at = last_checked_at.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                last_checked_at = None
            now = datetime.now(timezone.utc)
            due = (now - created).total_seconds() >= RECONCILE_AFTER_SECONDS
            due = due and (not last_checked_at or (now - last_checked_at).total_seconds() >= 60)
            if due:
                try:
                    from app.routes.webhooks import confirm_paystack_payment
                    confirm_paystack_payment(reference)
                except Exception:
                    current_app.logger.exception("Paystack status reconciliation failed for %s", reference)
                # Throttle verification polling if the provider still reports pending.
                db.session.refresh(payment)
                latest_raw = payment.raw_webhook if isinstance(payment.raw_webhook, dict) else {}
                if payment.status == "pending":
                    latest_raw["paystack_last_checked_at"] = now.isoformat()
                    payment.raw_webhook = latest_raw
                    db.session.commit()
        else:
            _reconcile_with_intasend(subscription, reference)
        db.session.refresh(subscription)
        status = subscription.status
    if status == "pending":
        created = subscription.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - created).total_seconds() > PENDING_TIMEOUT_SECONDS:
            status = "timeout"

    return jsonify({
        "status": status,
        "plan": subscription.plan,
        "reference": reference,
        "redirect": url_for("billing.success") if status == "active" else None,
    })


@billing_bp.route("/claim-payment/<reference>", methods=["POST"])
@login_required
def claim_payment(reference):
    """User pastes their M-Pesa / bank confirmation message so an admin
    can manually verify and activate the plan when a webhook is missed."""
    subscription = Subscription.query.filter_by(
        payment_reference=reference, user_id=current_user.id
    ).first_or_404()

    if subscription.status == "active":
        flash("This payment is already active — no claim needed.", "info")
        return redirect(url_for("billing.payment_pending", reference=reference))

    message = (request.form.get("pasted_message") or "").strip()
    phone = (request.form.get("contact_phone") or "").strip()

    if len(message) < 20:
        flash("Please paste the full confirmation message you received from M-Pesa or your bank.", "error")
        return redirect(url_for("billing.payment_pending", reference=reference))

    existing = ManualPaymentClaim.query.filter_by(
        subscription_id=subscription.id, status="pending"
    ).first()
    if existing:
        flash("You already submitted a claim for this payment. Our team is reviewing it.", "info")
        return redirect(url_for("billing.payment_pending", reference=reference))

    claim = ManualPaymentClaim(
        user_id=current_user.id,
        subscription_id=subscription.id,
        reference=reference,
        pasted_message=message[:2000],
        contact_phone=phone or None,
    )
    db.session.add(claim)
    db.session.add(Notification(
        user_id=current_user.id,
        title="Payment claim received",
        message="We received your payment confirmation. Our team will verify it and activate your plan shortly.",
        type="info",
        action_url="/billing/",
    ))
    db.session.commit()

    current_app.logger.info(
        f"Manual payment claim submitted: user={current_user.id} ref={reference}"
    )
    flash("Thanks — your claim is in. We'll activate your plan once we verify the payment.", "success")
    return redirect(url_for("billing.payment_pending", reference=reference))
