"""
CVForge AI - Webhooks Blueprint
Fixed: HMAC signature verification, db.session.get() instead of User.query.get()
"""
import hashlib
import hmac
import json
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from app.models import db, User, Payment, Subscription, PricingPlan

webhooks_bp = Blueprint("webhooks", __name__)


def _verify_paystack_signature(payload: bytes, headers) -> bool:
    """Verify modern timestamped Paystack-Signature or legacy x-paystack-signature."""
    signing_secret = (current_app.config.get("PAYSTACK_WEBHOOK_SECRET") or "").strip()
    signature_header = headers.get("Paystack-Signature", "")

    # Current Paystack signing secrets use a timestamped header. Verify the
    # raw bytes exactly as received; parsing and re-serializing JSON is unsafe.
    if signature_header and signing_secret:
        parts = [part.strip() for part in signature_header.split(",")]
        timestamp = next((part[2:] for part in parts if part.startswith("t=")), None)
        signatures = [part[3:] for part in parts if part.startswith("v1=")]
        try:
            signed_at = int(timestamp) if timestamp else 0
        except (TypeError, ValueError):
            signed_at = 0
        if signed_at and abs(int(datetime.utcnow().timestamp()) - signed_at) <= 300:
            expected = hmac.new(
                signing_secret.encode(), str(signed_at).encode() + b"." + payload, hashlib.sha512
            ).hexdigest()
            for item in signatures:
                # v1 values are key-id:hex-signature; tolerate plain hex as well.
                candidate = item.split(":", 1)[-1]
                if hmac.compare_digest(expected, candidate):
                    return True

    # Legacy Paystack integrations sign the raw body with the API secret key.
    legacy_secret = (current_app.config.get("PAYSTACK_SECRET_KEY") or "").strip()
    legacy_signature = headers.get("x-paystack-signature", "")
    if legacy_secret and legacy_signature:
        expected = hmac.new(legacy_secret.encode(), payload, hashlib.sha512).hexdigest()
        return hmac.compare_digest(expected, legacy_signature)
    return False


def confirm_paystack_payment(reference: str) -> bool:
    """Verify a Paystack reference and safely activate its matching CVForge order."""
    if not reference or len(reference) > 100:
        return False
    payment = Payment.query.filter_by(
        lipana_checkout_request_id=reference, payment_method="paystack"
    ).first()
    subscription = Subscription.query.filter_by(payment_reference=reference).first()
    if (not payment or not subscription
            or payment.subscription_id != subscription.id
            or payment.user_id != subscription.user_id
            or int(payment.amount) != int(subscription.amount)):
        current_app.logger.warning("Paystack reference/order mismatch in CVForge: %s", reference)
        return False
    if subscription.status == "active" and payment.status == "success":
        return True

    from app.services.paystack_service import PaystackService
    from app.services.paystack_service import PaystackError
    try:
        transaction = PaystackService().verify(reference)
    except PaystackError:
        current_app.logger.exception("Could not verify Paystack reference %s", reference)
        return False

    # Verify every material property against the order stored before checkout.
    try:
        expected_amount = int(payment.amount) * 100
        received_amount = int(transaction.get("amount", -1))
    except (TypeError, ValueError):
        return False
    if (transaction.get("status") != "success"
            or transaction.get("reference") != reference
            or received_amount != expected_amount
            or (transaction.get("currency") or "").upper() != "KES"):
        current_app.logger.error("Paystack verification mismatch for reference=%s", reference)
        return False

    user = db.session.get(User, payment.user_id)
    customer = transaction.get("customer") or {}
    if not user or (customer.get("email") and customer.get("email", "").lower() != user.email.lower()):
        current_app.logger.error("Paystack customer mismatch for reference=%s", reference)
        return False

    transaction_id = transaction.get("id")
    if transaction_id is None:
        current_app.logger.error("Paystack response has no transaction id for %s", reference)
        return False
    return _handle_payment_success({
        "reference": reference,
        "transaction_id": str(transaction_id),
        "provider": "paystack",
        "paystack_transaction": transaction,
    })


@webhooks_bp.route("/paystack", methods=["POST"])
def paystack_webhook():
    payload = request.get_data(cache=True)
    if not _verify_paystack_signature(payload, request.headers):
        current_app.logger.warning("Paystack webhook rejected: invalid or missing signature")
        return jsonify({"error": "Invalid signature"}), 401
    try:
        event = json.loads(payload)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid JSON"}), 400

    if event.get("event") != "charge.success":
        return jsonify({"received": True, "ignored": True}), 200
    data = event.get("data") or {}
    reference = data.get("reference")
    if not reference:
        return jsonify({"error": "Missing transaction reference"}), 400
    if not confirm_paystack_payment(reference):
        # Ask Paystack to retry rather than acknowledging an unverified/missing order.
        return jsonify({"error": "Payment not verified; retry later"}), 503
    return jsonify({"received": True}), 200


def _verify_lipana_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


@webhooks_bp.route("/lipana", methods=["POST"])
def lipana_webhook():
    payload = request.get_data()
    sig = request.headers.get("X-Lipana-Signature", "")
    secret = current_app.config.get("LIPANA_WEBHOOK_SECRET", "")

    # Fail closed: with no secret configured this endpoint would accept anyone's
    # "payment.success" and hand out paid plans for free.
    if not secret:
        current_app.logger.error("Lipana webhook rejected: LIPANA_WEBHOOK_SECRET is not set")
        return jsonify({"error": "Webhook not configured"}), 503
    if not _verify_lipana_signature(payload, sig, secret):
        current_app.logger.warning("Lipana webhook: invalid signature")
        return jsonify({"error": "Invalid signature"}), 401

    try:
        data = json.loads(payload)
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 400

    event = data.get("event")
    transaction_data = data.get("data", {})
    reference = transaction_data.get("reference") or transaction_data.get("checkout_request_id")

    current_app.logger.info(f"Lipana webhook event={event} ref={reference}")

    if event == "payment.success":
        _handle_payment_success(transaction_data)
    elif event == "payment.failed":
        _handle_payment_failed(transaction_data)
    else:
        current_app.logger.info(f"Unhandled webhook event: {event}")

    return jsonify({"received": True}), 200


def _handle_payment_success(data: dict):
    reference = data.get("reference") or data.get("checkout_request_id")
    transaction_id = data.get("transaction_id") or data.get("mpesa_receipt_number")
    if not reference:
        # filter_by(payment_reference=None) would match rows with a NULL reference.
        current_app.logger.error("Payment success webhook without a reference")
        return False

    # FIX: Lipana (like most webhook providers) delivers "at least once" —
    # the same event can arrive twice (retry after a slow 200, network
    # blip, etc). The old code did read-then-write
    # (`if status == "active": skip`), which has a race: two near-
    # simultaneous deliveries can both read "pending" before either
    # commits, and both proceed to activate/charge logic. with_for_update()
    # takes a row lock so the second delivery blocks until the first
    # commits, then re-reads the now-"active" status and skips cleanly.
    subscription = (Subscription.query
                     .filter_by(payment_reference=reference)
                     .with_for_update()
                     .first())
    if not subscription:
        current_app.logger.error(f"No subscription found for reference={reference}")
        return False  # caller decides: IntaSend should retry, not silently drop

    if subscription.status == "active":
        current_app.logger.info(f"Subscription {subscription.id} already active, skipping duplicate webhook")
        db.session.rollback()  # release the row lock, nothing to write
        return True

    # Duration comes from the plan (weekly / monthly / yearly), not a hardcoded 30.
    from datetime import timedelta, timezone as _tz
    from app.services.pricing import period_days, confirm_redemption
    plan_row = PricingPlan.query.filter_by(slug=subscription.plan).first()
    days = period_days(plan_row.billing_period if plan_row else "month")

    subscription.activate(transaction_id=transaction_id, days=days)
    confirm_redemption(subscription.id)

    # Use db.session.get() — not User.query.get() which is deprecated in SQLAlchemy 2.x
    user = db.session.get(User, subscription.user_id)
    if user:
        from app.services.pricing import resolve_plan_change
        new_plan, expires_at, kind = resolve_plan_change(user, subscription.plan, days)
        user.plan = new_plan
        # plan_expires_at is DateTime(timezone=True); keep it aware here.
        user.plan_expires_at = expires_at
        subscription.end_date = expires_at  # so the receipt matches what the user got
        current_app.logger.info(f"Plan change user={user.id} kind={kind} plan={new_plan}")

    payment = Payment.query.filter_by(
        lipana_checkout_request_id=reference
    ).first()
    if payment:
        payment.status = "success"
        payment.lipana_transaction_id = transaction_id
        payment.raw_webhook = data

    db.session.commit()
    current_app.logger.info(f"Payment success: user={subscription.user_id} plan={subscription.plan}")
    return True


def _handle_payment_failed(data: dict):
    reference = data.get("reference") or data.get("checkout_request_id")
    if not reference:
        return
    subscription = Subscription.query.filter_by(payment_reference=reference).first()
    if subscription and subscription.status == "active":
        # A late/duplicate FAILED must never undo a payment that already succeeded.
        current_app.logger.warning(f"Ignoring FAILED for already-active subscription ref={reference}")
        return
    if subscription:
        subscription.status = "failed"
        from app.services.pricing import release_redemption
        release_redemption(subscription.id)  # return the offer seat
    payment = Payment.query.filter_by(lipana_checkout_request_id=reference).first()
    if payment:
        payment.status = "failed"
        payment.raw_webhook = data
    db.session.commit()
    current_app.logger.info(f"Payment failed: ref={reference}")


# ─────────────────────────────────────────────────────────────
# IntaSend webhook — separate route because IntaSend's payload shape and
# auth mechanism are both different from Lipana's:
# - Auth: a static "challenge" string configured in the IntaSend
#   dashboard, echoed back in every payload (not HMAC).
# - Payload: invoice_id, state (PENDING/PROCESSING/COMPLETE/FAILED),
#   api_ref (your reference), net_amount, failed_reason.
# ─────────────────────────────────────────────────────────────

@webhooks_bp.route("/intasend", methods=["POST"])
def intasend_webhook():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    from app.services.intasend_service import IntaSendService
    try:
        service = IntaSendService()
    except ImportError:
        current_app.logger.error("intasend-python not installed — cannot verify webhook")
        return jsonify({"error": "Service unavailable"}), 503

    if not service.verify_webhook_challenge(data.get("challenge", "")):
        current_app.logger.warning("IntaSend webhook: invalid challenge")
        return jsonify({"error": "Invalid challenge"}), 401

    reference = data.get("api_ref")
    invoice_id = data.get("invoice_id")
    state = data.get("state")

    current_app.logger.info(f"IntaSend webhook state={state} ref={reference} invoice={invoice_id}")

    if state == "COMPLETE":
        handled = _handle_payment_success({
            "reference": reference,
            "checkout_request_id": reference,
            "transaction_id": invoice_id,
        })
        if handled is False:
            # Usually means the checkout row isn't committed yet, or the
            # reference doesn't match. A 503 makes IntaSend redeliver, so the
            # payment isn't lost. Raw payload is logged for manual recovery.
            current_app.logger.error(
                f"IntaSend COMPLETE could not be matched: ref={reference} invoice={invoice_id} payload={data}"
            )
            return jsonify({"error": "Subscription not found, retry later"}), 503
    elif state == "FAILED":
        _handle_payment_failed({
            "reference": reference,
            "checkout_request_id": reference,
            "failed_reason": data.get("failed_reason"),
        })
    else:
        # PENDING / PROCESSING — no action, just log. The final COMPLETE
        # or FAILED delivery is what matters.
        current_app.logger.info(f"IntaSend webhook state={state} for ref={reference} — no action taken")

    return jsonify({"received": True}), 200

