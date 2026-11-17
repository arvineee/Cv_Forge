"""Provider-neutral payment/order checks shared by Paystack and IntaSend.

No database schema changes are required. Legacy payment column names are
exposed through generic model aliases so historical production rows remain
readable without a migration.
"""
from decimal import Decimal, InvalidOperation

INTASEND_PAYMENT_METHODS = frozenset({"mpesa", "card"})


def decimal_amount(value):
    """Return a finite Decimal, or None for missing/invalid amounts."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return amount if amount.is_finite() else None


def validate_payment_order(payment, subscription, reference, *, methods=None):
    """Ensure the local payment and subscription describe the same order."""
    if not payment or not subscription or not reference:
        return False, "missing_order"
    if payment.provider_reference != reference or subscription.payment_reference != reference:
        return False, "reference_mismatch"
    if payment.subscription_id != subscription.id:
        return False, "subscription_mismatch"
    if payment.user_id != subscription.user_id:
        return False, "customer_mismatch"
    if methods is not None and payment.payment_method not in methods:
        return False, "provider_mismatch"

    payment_amount = decimal_amount(payment.amount)
    subscription_amount = decimal_amount(subscription.amount)
    if payment_amount is None or subscription_amount is None or payment_amount != subscription_amount:
        return False, "amount_mismatch"

    payment_currency = (payment.currency or "KES").strip().upper()
    subscription_currency = (subscription.currency or "KES").strip().upper()
    if not payment_currency or payment_currency != subscription_currency:
        return False, "currency_mismatch"

    metadata = payment.raw_webhook if isinstance(payment.raw_webhook, dict) else {}
    snapshot = metadata.get("order_snapshot")
    if isinstance(snapshot, dict):
        if snapshot.get("plan") and snapshot["plan"] != subscription.plan:
            return False, "plan_mismatch"
        if snapshot.get("user_id") is not None and str(snapshot["user_id"]) != str(subscription.user_id):
            return False, "snapshot_customer_mismatch"
        snap_amount = decimal_amount(snapshot.get("amount"))
        if snap_amount is not None and snap_amount != payment_amount:
            return False, "snapshot_amount_mismatch"
        snap_currency = (snapshot.get("currency") or payment_currency).strip().upper()
        if snap_currency != payment_currency:
            return False, "snapshot_currency_mismatch"

    return True, None


def extract_intasend_invoice(response):
    """Normalize the IntaSend SDK status response to its invoice object."""
    if not isinstance(response, dict):
        return None
    invoice = response.get("invoice")
    if isinstance(invoice, dict):
        return invoice
    raw = response.get("raw")
    if isinstance(raw, dict):
        nested = raw.get("invoice")
        if isinstance(nested, dict):
            return nested
        if raw.get("invoice_id"):
            return raw
    if response.get("invoice_id"):
        return response
    return None


def validate_intasend_invoice(invoice, payment, subscription, reference, *, expected_invoice_id=None,
                              allowed_states=("COMPLETE",)):
    """Validate the provider's authoritative invoice before fulfilling an order."""
    if not isinstance(invoice, dict):
        return False, "invalid_invoice"
    valid, reason = validate_payment_order(
        payment, subscription, reference, methods=INTASEND_PAYMENT_METHODS
    )
    if not valid:
        return False, reason

    invoice_id = str(invoice.get("invoice_id") or "").strip()
    if not invoice_id:
        return False, "missing_invoice_id"
    if expected_invoice_id and invoice_id != str(expected_invoice_id):
        return False, "invoice_id_mismatch"
    if str(invoice.get("api_ref") or "") != reference:
        return False, "reference_mismatch"
    if str(invoice.get("state") or "").upper() not in {s.upper() for s in allowed_states}:
        return False, "state_mismatch"

    received_amount = decimal_amount(invoice.get("value"))
    expected_amount = decimal_amount(payment.amount)
    if received_amount is None or expected_amount is None or received_amount != expected_amount:
        return False, "amount_mismatch"

    received_currency = (invoice.get("currency") or "").strip().upper()
    expected_currency = (payment.currency or subscription.currency or "KES").strip().upper()
    if not received_currency or received_currency != expected_currency:
        return False, "currency_mismatch"

    return True, None
