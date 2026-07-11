"""
CVForge AI - IntaSend Payment Service

Drop-in alternative to LipanaService — same public interface
(`initiate_payment(phone, amount, reference, description)` returning
`{"success": bool, "message": str}`), so billing.py needs almost no
changes to switch: just
    from app.services.intasend_service import IntaSendService as PaymentService
instead of
    from app.services.lipana_service import LipanaService as PaymentService

Built against IntaSend's actual documented contract
(developers.intasend.com), not guessed:
- pip install intasend-python
- APIService(token=SECRET_KEY, publishable_key=PUBLISHABLE_KEY, test=bool)
- service.collect.mpesa_stk_push(phone_number, email, amount, narrative)
- service.collect.status(invoice_id=...)
- Webhooks are authenticated with a static "challenge" string (set in the
  IntaSend dashboard, echoed back in every webhook payload) — NOT HMAC.

Same retry/rate-limit/dedup patterns as lipana_service.py, adapted: since
the intasend-python SDK's underlying HTTP client isn't ours to configure
with a urllib3 Retry adapter, retry is implemented as an explicit manual
loop around the SDK call instead.
"""
import time
import threading
import logging
from typing import Dict, Any

from flask import current_app

logger = logging.getLogger(__name__)


class _RateLimiter:
    """Same in-process token bucket as lipana_service.py."""
    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps = []
        self._lock = threading.Lock()

    def allow(self) -> bool:
        now = time.monotonic()
        with self._lock:
            cutoff = now - self.window_seconds
            self._timestamps = [t for t in self._timestamps if t > cutoff]
            if len(self._timestamps) >= self.max_requests:
                return False
            self._timestamps.append(now)
            return True

    def wait_time(self) -> float:
        with self._lock:
            if not self._timestamps:
                return 0.0
            oldest = min(self._timestamps)
            return max(0.0, self.window_seconds - (time.monotonic() - oldest))


class _InFlightGuard:
    """Same duplicate-click guard as lipana_service.py."""
    def __init__(self, ttl_seconds: float = 30.0):
        self.ttl_seconds = ttl_seconds
        self._pending: Dict[str, float] = {}
        self._lock = threading.Lock()

    def try_acquire(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            expiry = self._pending.get(key)
            if expiry and expiry > now:
                return False
            self._pending[key] = now + self.ttl_seconds
            return True

    def release(self, key: str):
        with self._lock:
            self._pending.pop(key, None)


class IntaSendService:
    _rate_limiter = _RateLimiter(max_requests=20, window_seconds=60)
    _inflight = _InFlightGuard(ttl_seconds=30)

    # Retry only on things that are actually retryable — network blips /
    # 5xx. IntaSend validation errors (bad phone number, insufficient
    # config) will raise from the SDK immediately and should NOT be
    # retried, since retrying a bad request just wastes rate limit budget.
    MAX_RETRIES = 3
    BACKOFF_BASE_SECONDS = 1.0

    def __init__(self):
        self.secret_key = current_app.config.get("INTASEND_SECRET_KEY", "")
        self.publishable_key = current_app.config.get("INTASEND_PUBLISHABLE_KEY", "")
        self.test_mode = current_app.config.get("INTASEND_ENV", "sandbox") != "production"
        self.webhook_challenge = current_app.config.get("INTASEND_WEBHOOK_CHALLENGE", "")

        try:
            from intasend import APIService
        except ImportError:
            raise ImportError(
                "intasend-python is not installed. Run: pip install intasend-python"
            )

        self._service = APIService(
            token=self.secret_key,
            publishable_key=self.publishable_key,
            test=self.test_mode,
        )

        # Sandbox and live are separate IntaSend accounts/domains
        # (sandbox.intasend.com vs payment.intasend.com), not a toggle —
        # mismatched keys here produce a confusing "Invalid token for
        # sandbox environment" error rather than a clear "wrong account"
        # message. Logging the resolved mode on every init makes that
        # mismatch obvious immediately instead of after a failed payment.
        logger.info(f"IntaSendService initialized: mode={'SANDBOX' if self.test_mode else 'LIVE'} "
                    f"(INTASEND_ENV={current_app.config.get('INTASEND_ENV', 'sandbox')})")
        if not self.secret_key or not self.publishable_key:
            logger.warning("IntaSendService initialized with missing key(s) — payments will fail")

    def initiate_payment(self, phone: str, amount: float, reference: str,
                          description: str = "", email: str = "") -> Dict[str, Any]:
        """
        Trigger an M-Pesa STK push via IntaSend.

        email is required by IntaSend's API (it's part of their customer
        record). billing.py passes current_user.email since you collect it
        at registration. The placeholder fallback below only exists as a
        safety net for callers that don't have a user's email handy — if
        you see it in logs during normal checkout, that's worth
        investigating (a user with a blank email shouldn't be possible if
        registration requires one).
        """
        if not self._rate_limiter.allow():
            wait = self._rate_limiter.wait_time()
            logger.warning(f"IntaSend rate limit hit, retry in {wait:.1f}s")
            return {"success": False, "message": "Too many payment requests right now. Please wait a moment and try again."}

        if not self._inflight.try_acquire(reference):
            logger.warning(f"Duplicate initiate_payment call for reference={reference} suppressed")
            return {"success": False, "message": "A payment request for this order is already in progress. Check your phone."}

        phone_normalized = self._normalize_phone(phone)
        if not email:
            logger.warning(f"initiate_payment called without an email for reference={reference} — using placeholder. This shouldn't happen from billing.py's normal checkout flow.")
        placeholder_email = email or f"{phone_normalized}@noemail.cvforge.app"

        last_error = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                resp = self._service.collect.mpesa_stk_push(
                    phone_number=phone_normalized,
                    email=placeholder_email,
                    amount=amount,
                    narrative=description or f"CVForge payment {reference}",
                    api_ref=reference,
                )
                invoice = resp.get("invoice", resp) if isinstance(resp, dict) else {}
                invoice_id = invoice.get("invoice_id") if isinstance(invoice, dict) else None

                return {
                    "success": True,
                    "message": "Payment request sent! Check your phone.",
                    "invoice_id": invoice_id,
                    "raw": resp,
                }

            except Exception as e:
                last_error = e
                # Only retry on things that look transient (timeouts,
                # connection errors, 5xx). If the SDK raises a clean
                # validation-style error, bail immediately instead of
                # retrying a request that will fail identically 3 times.
                transient_markers = ("timeout", "connection", "502", "503", "504")
                if not any(m in str(e).lower() for m in transient_markers) or attempt == self.MAX_RETRIES:
                    break
                sleep_for = self.BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                logger.warning(f"IntaSend STK push attempt {attempt} failed ({e}), retrying in {sleep_for}s")
                time.sleep(sleep_for)

        logger.error(f"IntaSend STK push failed for reference={reference}: {last_error}")
        return {"success": False, "message": "Payment service is temporarily unavailable. Please try again shortly."}

    def check_status(self, invoice_id: str) -> Dict[str, Any]:
        try:
            resp = self._service.collect.status(invoice_id=invoice_id)
            return {"success": True, **resp} if isinstance(resp, dict) else {"success": True, "raw": resp}
        except Exception as e:
            logger.error(f"IntaSend status check error for invoice_id={invoice_id}: {e}")
            return {"success": False, "message": "Could not fetch payment status."}

    def verify_webhook_challenge(self, payload_challenge: str) -> bool:
        """
        IntaSend authenticates webhooks with a static challenge string
        (set in the IntaSend dashboard, echoed back in every payload) —
        not HMAC. Still use constant-time comparison to avoid timing
        side-channels on the comparison itself.
        """
        import hmac
        if not self.webhook_challenge:
            logger.warning("INTASEND_WEBHOOK_CHALLENGE is not configured — webhook cannot be verified")
            return False
        return hmac.compare_digest(self.webhook_challenge, payload_challenge or "")

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        phone = phone.strip().replace(" ", "").replace("-", "")
        if phone.startswith("+"):
            phone = phone[1:]
        if phone.startswith("0"):
            phone = "254" + phone[1:]
        elif phone.startswith("7") or phone.startswith("1"):
            phone = "254" + phone
        return phone

