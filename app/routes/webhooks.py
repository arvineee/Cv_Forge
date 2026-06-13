"""
CVForge AI - Webhooks Blueprint
Fixed: HMAC signature verification, db.session.get() instead of User.query.get()
"""
import hashlib
import hmac
import json
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

    subscription = Subscription.query.filter_by(payment_reference=reference).first()
    if not subscription:
        current_app.logger.warning(f"No subscription found for reference={reference}")
        return

    if subscription.status == "active":
        current_app.logger.info(f"Subscription {subscription.id} already active, skipping")
        return

    subscription.activate(transaction_id=transaction_id)

    # Use db.session.get() — not User.query.get() which is deprecated in SQLAlchemy 2.x
    user = db.session.get(User, subscription.user_id)
    if user:
        user.plan = subscription.plan
        from app.models import utcnow
        from datetime import timedelta
        user.plan_expires_at = utcnow() + timedelta(days=30)

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
