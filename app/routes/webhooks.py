"""
CVForge AI - Webhooks Blueprint
Fixed: HMAC signature verification, db.session.get() instead of User.query.get()
"""
import hashlib
import hmac
import json
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from app.models import db, User, Payment, Subscription

webhooks_bp = Blueprint("webhooks", __name__)


def _verify_lipana_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


@webhooks_bp.route("/lipana", methods=["POST"])
def lipana_webhook():
    payload = request.get_data()
    sig = request.headers.get("X-Lipana-Signature", "")
    secret = current_app.config.get("LIPANA_WEBHOOK_SECRET", "")

    if secret and not _verify_lipana_signature(payload, sig, secret):
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
        current_app.logger.warning(f"No subscription found for reference={reference}")
        return

    if subscription.status == "active":
        current_app.logger.info(f"Subscription {subscription.id} already active, skipping duplicate webhook")
        db.session.rollback()  # release the row lock, nothing to write
        return

    subscription.activate(transaction_id=transaction_id)

    # Use db.session.get() — not User.query.get() which is deprecated in SQLAlchemy 2.x
    user = db.session.get(User, subscription.user_id)
    if user:
        user.plan = subscription.plan
        # FIX: plan_expires_at is DateTime(timezone=True); the old code wrote
        # utcnow() (a naive datetime, by design for other columns) into it,
        # which is inconsistent with how reset_token_expires etc. are set
        # elsewhere with datetime.now(timezone.utc). Standardize on aware here.
        from datetime import timedelta, timezone as _tz
        user.plan_expires_at = datetime.now(_tz.utc) + timedelta(days=30)

    payment = Payment.query.filter_by(
        lipana_checkout_request_id=reference
    ).first()
    if payment:
        payment.status = "success"
        payment.lipana_transaction_id = transaction_id
        payment.raw_webhook = data

    db.session.commit()
    current_app.logger.info(f"Payment success: user={subscription.user_id} plan={subscription.plan}")


def _handle_payment_failed(data: dict):
    reference = data.get("reference") or data.get("checkout_request_id")
    subscription = Subscription.query.filter_by(payment_reference=reference).first()
    if subscription:
        subscription.status = "failed"
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
        _handle_payment_success({
            "reference": reference,
            "checkout_request_id": reference,
            "transaction_id": invoice_id,
        })
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

