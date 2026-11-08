"""
Paystack hosted-checkout client for CVForge.

All requests are server-to-server. Never expose PAYSTACK_SECRET_KEY to the
browser. Amounts are supplied in KES and converted to the smallest currency
unit (KES cents) before initialization.
"""
import logging
from urllib.parse import quote
from decimal import Decimal, InvalidOperation

import requests
from flask import current_app

logger = logging.getLogger(__name__)


class PaystackError(Exception):
    """Raised when Paystack cannot initialize or verify a transaction."""


class PaystackService:
    TIMEOUT = (5, 20)

    def __init__(self):
        self.secret_key = (current_app.config.get("PAYSTACK_SECRET_KEY") or "").strip()
        self.base_url = (current_app.config.get("PAYSTACK_BASE_URL")
                         or "https://api.paystack.co").rstrip("/")
        if not self.secret_key:
            raise PaystackError("Paystack is not configured. Add PAYSTACK_SECRET_KEY.")

    def _request(self, method, path, **kwargs):
        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        try:
            response = requests.request(
                method, f"{self.base_url}{path}", headers=headers,
                timeout=self.TIMEOUT, **kwargs
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            logger.exception("Paystack API request failed")
            raise PaystackError("Paystack is temporarily unavailable. Please try again.") from exc
        except ValueError as exc:
            raise PaystackError("Paystack returned an invalid response.") from exc

        if not isinstance(payload, dict) or not payload.get("status"):
            message = payload.get("message", "Paystack request was unsuccessful.") if isinstance(payload, dict) else "Invalid Paystack response."
            raise PaystackError(str(message))
        return payload.get("data") or {}

    @staticmethod
    def to_minor_units(amount_kes):
        try:
            amount = Decimal(str(amount_kes))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise PaystackError("Invalid payment amount.") from exc
        if not amount.is_finite() or amount <= 0:
            raise PaystackError("Payment amount must be greater than zero.")
        minor = amount * 100
        if minor != minor.to_integral_value():
            raise PaystackError("Payment amount has unsupported decimal precision.")
        return int(minor)

    def initialize(self, *, email, amount_kes, reference, callback_url, metadata):
        amount = self.to_minor_units(amount_kes)
        data = self._request("POST", "/transaction/initialize", json={
            "email": email,
            "amount": amount,
            "currency": "KES",
            "reference": reference,
            "callback_url": callback_url,
            "metadata": metadata,
        })
        authorization_url = data.get("authorization_url")
        returned_reference = data.get("reference")
        if not authorization_url or returned_reference != reference:
            logger.error("Unexpected Paystack initialization response for ref=%s", reference)
            raise PaystackError("Could not start Paystack checkout. Please try again.")
        return data

    def verify(self, reference):
        if not reference or len(reference) > 100:
            raise PaystackError("Invalid payment reference.")
        path = "/transaction/verify/" + quote(reference, safe="")
        return self._request("GET", path)
