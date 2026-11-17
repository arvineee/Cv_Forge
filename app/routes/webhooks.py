"""Payment webhooks for CVForge's supported providers: Paystack and IntaSend.

Provider notifications are never treated as proof of payment on their own.
Paystack is verified through its transaction API; IntaSend is verified by
retrieving the invoice from its API and matching the stored order.
"""
import hashlib
import hmac
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, request, jsonify, current_app

from app.models import db, User, Payment, Subscription, PricingPlan
from app.services.payment_integrity import (
    INTASEND_PAYMENT_METHODS,
    extract_intasend_invoice,
    validate_intasend_invoice,
    validate_payment_order,
)

webhooks_bp = Blueprint("webhooks", __name__)


def _verify_paystack_signature(payload: bytes, headers) -> bool:
    """Verify Paystack's timestamped signature or legacy raw-body signature."""
    signing_secret = (current_app.config.get("PAYSTACK_WEBHOOK_SECRET") or "").strip()
    signature_header = headers.get("Paystack-Signature", "")

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
                candidate = item.split(":", 1)[-1]
                if hmac.compare_digest(expected, candidate):
                    return True

    legacy_secret = (current_app.config.get("PAYSTACK_SECRET_KEY") or "").strip()
    legacy_signature = headers.get("x-paystack-signature", "")
    if legacy_secret and legacy_signature:
        expected = hmac.new(legacy_secret.encode(), payload, hashlib.sha512).hexdigest()
        return hmac.compare_digest(expected, legacy_signature)
    return False


def _payment_metadata(payment):
    return dict(payment.raw_webhook) if isinstance(payment.raw_webhook, dict) else {}


def _safe_provider_event(data, provider):
    """Keep useful reconciliation fields, never raw secrets or full provider payloads."""
    keys = (
        "reference", "currency", "amount", "value", "status", "state", "paid_at",
        "channel", "invoice_id", "provider_ref", "mpesa_reference", "failed_code",
        "failed_reason", "provider_transaction_id", "transaction_id",
    )
    safe = {key: data[key] for key in keys if data.get(key) is not None}
    safe["provider"] = provider
    return safe


def _verify_paystack_order(reference):
    if not isinstance(reference, str) or not reference or len(reference) > 100:
        return None, None
    payment = Payment.query.filter_by(
        provider_reference=reference, payment_method="paystack"
    ).first()
    subscription = Subscription.query.filter_by(payment_reference=reference).first()
    valid, reason = validate_payment_order(
        payment, subscription, reference, methods={"paystack"}
    )
    if not valid:
        current_app.logger.warning("Paystack local order validation failed: ref=%s reason=%s", reference, reason)
        return None, None
    return payment, subscription


def confirm_paystack_payment(reference: str) -> bool:
    """Verify a Paystack transaction and safely activate its matching order."""
    payment, subscription = _verify_paystack_order(reference)
    if not payment or not subscription:
        return False
    if subscription.status == "active" and payment.status == "success":
        return True

    from app.services.paystack_service import PaystackService, PaystackError
    try:
        transaction = PaystackService().verify(reference)
    except PaystackError:
        current_app.logger.exception("Could not verify Paystack reference %s", reference)
        return False
    if not isinstance(transaction, dict):
        current_app.logger.error("Paystack verification returned an invalid transaction: ref=%s", reference)
        return False

    try:
        expected_amount = Decimal(str(payment.amount)) * Decimal("100")
        received_amount = Decimal(str(transaction.get("amount", "-1")))
    except (InvalidOperation, TypeError, ValueError):
        return False

    expected_currency = (payment.currency or subscription.currency or "KES").upper()
    if (transaction.get("status") != "success"
            or transaction.get("reference") != reference
            or not received_amount.is_finite()
            or received_amount != expected_amount
            or (transaction.get("currency") or "").upper() != expected_currency):
        current_app.logger.error("Paystack verification mismatch for reference=%s", reference)
        return False

    user = db.session.get(User, payment.user_id)
    customer = transaction.get("customer") or {}
    if not isinstance(customer, dict):
        customer = {}
    provider_email = (customer.get("email") or "").strip().lower()
    if not user or (provider_email and provider_email != user.email.lower()):
        current_app.logger.error("Paystack customer mismatch for reference=%s", reference)
        return False

    transaction_id = transaction.get("id")
    if transaction_id is None:
        current_app.logger.error("Paystack response has no transaction id for %s", reference)
        return False

    provider_transaction_id = f"paystack:{transaction_id}"
    safe_event = {
        "reference": reference,
        "provider_transaction_id": provider_transaction_id,
        "currency": expected_currency,
        "amount": str(payment.amount),
        "status": "success",
        "paid_at": transaction.get("paid_at"),
        "channel": transaction.get("channel"),
    }
    return _handle_payment_success({
        "reference": reference,
        "transaction_id": provider_transaction_id,
        "provider": "paystack",
        "provider_event": safe_event,
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
    if not isinstance(event, dict):
        return jsonify({"error": "Invalid event payload"}), 400

    if event.get("event") != "charge.success":
        return jsonify({"received": True, "ignored": True}), 200
    data = event.get("data") or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid transaction payload"}), 400
    reference = data.get("reference")
    if not reference:
        return jsonify({"error": "Missing transaction reference"}), 400
    if not confirm_paystack_payment(reference):
        # Ask Paystack to retry rather than acknowledging an unverified order.
        return jsonify({"error": "Payment not verified; retry later"}), 503
    return jsonify({"received": True}), 200


def _verified_intasend_invoice(reference, invoice_id, allowed_states):
    """Fetch and validate the authoritative IntaSend invoice for a CVForge order."""
    if (not isinstance(reference, str) or not reference or len(reference) > 100
            or not isinstance(invoice_id, (str, int)) or not str(invoice_id).strip()):
        return None
    payment = Payment.query.filter_by(provider_reference=reference).first()
    subscription = Subscription.query.filter_by(payment_reference=reference).first()
    if not payment or payment.payment_method not in INTASEND_PAYMENT_METHODS:
        current_app.logger.warning("IntaSend order has no matching payment: ref=%s", reference)
        return None

    metadata = _payment_metadata(payment)
    stored_invoice_id = metadata.get("invoice_id")
    requested_invoice_id = str(invoice_id).strip()
    if not requested_invoice_id or (stored_invoice_id and requested_invoice_id != str(stored_invoice_id)):
        current_app.logger.error("IntaSend invoice ID does not match checkout record: ref=%s", reference)
        return None

    try:
        from app.services.intasend_service import IntaSendService
        result = IntaSendService().check_status(invoice_id=str(invoice_id))
    except Exception:
        current_app.logger.exception("IntaSend invoice verification request failed: ref=%s", reference)
        return None
    if not isinstance(result, dict) or not result.get("success"):
        current_app.logger.warning("IntaSend invoice status unavailable: ref=%s", reference)
        return None

    invoice = extract_intasend_invoice(result)
    valid, reason = validate_intasend_invoice(
        invoice, payment, subscription, reference,
        expected_invoice_id=requested_invoice_id,
        allowed_states=allowed_states,
    )
    if not valid:
        current_app.logger.error("IntaSend invoice validation failed: ref=%s reason=%s", reference, reason)
        return None
    return payment, subscription, invoice


def confirm_intasend_payment(reference: str, invoice_id: str) -> bool:
    """Confirm an IntaSend COMPLETE invoice only after API-side order matching."""
    verified = _verified_intasend_invoice(reference, invoice_id, {"COMPLETE"})
    if not verified:
        return False
    payment, subscription, invoice = verified
    if subscription.status == "active" and payment.status == "success":
        return True

    provider_reference = (invoice.get("provider_ref") or invoice.get("mpesa_reference")
                          or invoice.get("invoice_id"))
    transaction_id = f"intasend:{provider_reference}"
    safe_event = {
        "reference": reference,
        "invoice_id": str(invoice.get("invoice_id")),
        "provider_ref": invoice.get("provider_ref"),
        "mpesa_reference": invoice.get("mpesa_reference"),
        "currency": invoice.get("currency"),
        "value": str(invoice.get("value")),
        "state": invoice.get("state"),
        "provider_transaction_id": transaction_id,
    }
    return _handle_payment_success({
        "reference": reference,
        "transaction_id": transaction_id,
        "provider": "intasend",
        "provider_event": safe_event,
    })


def confirm_intasend_failure(reference: str, invoice_id: str) -> bool:
    """Only mark an IntaSend order failed after the provider API confirms it."""
    verified = _verified_intasend_invoice(reference, invoice_id, {"FAILED", "CANCELED"})
    if not verified:
        return False
    _handle_payment_failed({
        "reference": reference,
        "provider": "intasend",
        "failed_reason": verified[2].get("failed_reason"),
        "invoice_id": str(verified[2].get("invoice_id")),
    })
    return True


def reconcile_intasend_payment(reference: str, invoice_id: str) -> bool:
    """One-call status reconciliation for the user's pending-payment poll."""
    verified = _verified_intasend_invoice(
        reference, invoice_id, {"COMPLETE", "FAILED", "CANCELED"}
    )
    if not verified:
        return False
    _payment, _subscription, invoice = verified
    state = str(invoice.get("state") or "").upper()
    if state == "COMPLETE":
        provider_reference = (invoice.get("provider_ref") or invoice.get("mpesa_reference")
                              or invoice.get("invoice_id"))
        transaction_id = f"intasend:{provider_reference}"
        safe_event = {
            "reference": reference,
            "invoice_id": str(invoice.get("invoice_id")),
            "provider_ref": invoice.get("provider_ref"),
            "mpesa_reference": invoice.get("mpesa_reference"),
            "currency": invoice.get("currency"),
            "value": str(invoice.get("value")),
            "state": state,
            "provider_transaction_id": transaction_id,
        }
        return _handle_payment_success({
            "reference": reference, "transaction_id": transaction_id,
            "provider": "intasend", "provider_event": safe_event,
        })
    return _handle_payment_failed({
        "reference": reference, "provider": "intasend",
        "failed_reason": invoice.get("failed_reason"),
        "invoice_id": str(invoice.get("invoice_id")),
    })


def _handle_payment_success(data: dict):
    """Idempotent activation path shared by verified payments and admin claims."""
    reference = data.get("reference") or data.get("checkout_request_id")
    transaction_id = data.get("transaction_id") or data.get("provider_transaction_id")
    provider = data.get("provider") or "manual"
    if not reference:
        current_app.logger.error("Payment success without a reference")
        return False

    subscription = (Subscription.query
                    .filter_by(payment_reference=reference)
                    .with_for_update()
                    .first())
    if not subscription:
        current_app.logger.error("No subscription found for reference=%s", reference)
        return False

    payment = (Payment.query.filter_by(provider_reference=reference)
               .with_for_update().first())
    if payment:
        valid, reason = validate_payment_order(payment, subscription, reference)
        if not valid:
            current_app.logger.error("Payment activation order mismatch: ref=%s reason=%s", reference, reason)
            db.session.rollback()
            return False
        expected_methods = {
            "paystack": {"paystack"},
            "intasend": INTASEND_PAYMENT_METHODS,
        }.get(provider)
        if expected_methods is not None and payment.payment_method not in expected_methods:
            current_app.logger.error("Provider/payment-method mismatch: ref=%s provider=%s", reference, provider)
            db.session.rollback()
            return False
    elif provider in {"paystack", "intasend"}:
        current_app.logger.error("Verified provider payment has no local payment row: ref=%s", reference)
        db.session.rollback()
        return False

    if transaction_id:
        existing = Payment.query.filter(
            Payment.provider_transaction_id == str(transaction_id)
        ).first()
        if existing and (not payment or existing.id != payment.id):
            current_app.logger.error("Duplicate provider transaction ID rejected: ref=%s", reference)
            db.session.rollback()
            return False

    if subscription.status == "active":
        if payment and payment.status != "success":
            payment.status = "success"
            if transaction_id:
                payment.provider_transaction_id = str(transaction_id)
                subscription.provider_transaction_id = str(transaction_id)
            db.session.commit()
        else:
            db.session.rollback()
        return True

    from app.services.pricing import period_days, confirm_redemption, resolve_plan_change
    metadata = _payment_metadata(payment) if payment else {}
    snapshot = metadata.get("order_snapshot") if isinstance(metadata, dict) else None
    snapshot_period = snapshot.get("billing_period") if isinstance(snapshot, dict) else None
    plan_row = PricingPlan.query.filter_by(slug=subscription.plan).first()
    billing_period = snapshot_period or (plan_row.billing_period if plan_row else "month")
    days = period_days(billing_period)

    user = db.session.get(User, subscription.user_id)
    if not user:
        db.session.rollback()
        return False

    subscription.activate(transaction_id=transaction_id, days=days)
    confirm_redemption(subscription.id)
    new_plan, expires_at, kind = resolve_plan_change(user, subscription.plan, days)
    user.plan = new_plan
    user.plan_expires_at = expires_at
    subscription.end_date = expires_at
    current_app.logger.info("Plan change user=%s kind=%s plan=%s", user.id, kind, new_plan)

    if payment:
        payment.status = "success"
        if transaction_id:
            payment.provider_transaction_id = str(transaction_id)
        event = data.get("provider_event")
        if not isinstance(event, dict):
            event = _safe_provider_event(data, provider)
        metadata.update({"provider": provider, "last_verified_event": event})
        payment.raw_webhook = metadata

    db.session.commit()
    current_app.logger.info("Payment success: user=%s plan=%s provider=%s",
                            subscription.user_id, subscription.plan, provider)
    return True


def _handle_payment_failed(data: dict):
    reference = data.get("reference") or data.get("checkout_request_id")
    if not reference:
        return False
    payment = Payment.query.filter_by(provider_reference=reference).first()
    provider = data.get("provider") or "intasend"
    if payment and provider == "intasend" and payment.payment_method not in INTASEND_PAYMENT_METHODS:
        current_app.logger.warning("Ignoring IntaSend failure for non-IntaSend payment: ref=%s", reference)
        return False

    subscription = (Subscription.query.filter_by(payment_reference=reference)
                    .with_for_update().first())
    if (subscription and subscription.status == "active") or (payment and payment.status == "success"):
        current_app.logger.warning("Ignoring FAILED for already-successful payment ref=%s", reference)
        db.session.rollback()
        return False
    if subscription:
        subscription.status = "failed"
        from app.services.pricing import release_redemption
        release_redemption(subscription.id)
    if payment and payment.status != "success":
        payment.status = "failed"
        metadata = _payment_metadata(payment)
        metadata["last_failure"] = {
            "provider": provider,
            "invoice_id": data.get("invoice_id"),
            "failed_reason": (str(data.get("failed_reason") or "")[:300] or None),
        }
        payment.raw_webhook = metadata
    db.session.commit()
    current_app.logger.info("Payment failed: ref=%s provider=%s", reference, provider)
    return True


@webhooks_bp.route("/intasend", methods=["POST"])
def intasend_webhook():
    """IntaSend collection_event; challenge plus server-side invoice verification."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON"}), 400

    topic = data.get("topic")
    if topic and topic != "collection_event":
        return jsonify({"received": True, "ignored": True}), 200

    from app.services.intasend_service import IntaSendService
    try:
        service = IntaSendService()
    except ImportError:
        current_app.logger.error("intasend-python not installed; cannot verify webhook")
        return jsonify({"error": "Service unavailable"}), 503

    challenge = data.get("challenge")
    if not isinstance(challenge, str):
        challenge = ""
    if not service.verify_webhook_challenge(challenge):
        current_app.logger.warning("IntaSend webhook rejected: invalid challenge")
        return jsonify({"error": "Invalid challenge"}), 401

    reference = data.get("api_ref")
    invoice_id = data.get("invoice_id")
    state = str(data.get("state") or "").upper()
    if state in {"COMPLETE", "FAILED", "CANCELED"} and (
            not isinstance(reference, str) or not reference
            or not isinstance(invoice_id, (str, int)) or not str(invoice_id).strip()):
        return jsonify({"error": "Missing invoice reference"}), 400

    if state == "COMPLETE":
        if not confirm_intasend_payment(reference, invoice_id):
            # Provider API confirmation failed or order fields did not match.
            # A 503 allows a transient provider/API issue to be retried.
            return jsonify({"error": "Payment not verified; retry later"}), 503
    elif state in {"FAILED", "CANCELED"}:
        if not confirm_intasend_failure(reference, invoice_id):
            return jsonify({"error": "Failure not verified; retry later"}), 503
    else:
        # PENDING / PROCESSING / RETRY / PARTIAL do not activate a plan.
        current_app.logger.info("IntaSend non-final invoice state=%s ref=%s", state, reference)

    return jsonify({"received": True}), 200
