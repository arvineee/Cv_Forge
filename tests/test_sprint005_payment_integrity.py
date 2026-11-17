"""Pure tests for Sprint 005 provider/order verification rules."""
import unittest
from types import SimpleNamespace

from tests._load import load

integrity = load("app/services/payment_integrity.py", "payment_integrity_sprint005")


class PaymentIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.reference = "CVF-ABC123"
        self.payment = SimpleNamespace(
            id=10, user_id=7, subscription_id=20, amount=799,
            currency="KES", payment_method="mpesa", provider_reference=self.reference,
            raw_webhook={
                "invoice_id": "INV-123",
                "order_snapshot": {
                    "plan": "pro", "billing_period": "month",
                    "amount": "799", "currency": "KES", "user_id": 7,
                },
            },
        )
        self.subscription = SimpleNamespace(
            id=20, user_id=7, amount=799, currency="KES",
            plan="pro", payment_reference=self.reference,
        )

    def invoice(self, **changes):
        data = {
            "invoice_id": "INV-123", "api_ref": self.reference,
            "state": "COMPLETE", "value": "799.00", "currency": "KES",
            "provider_ref": "QWE123",
        }
        data.update(changes)
        return data

    def test_valid_intasend_invoice_matches_order(self):
        ok, reason = integrity.validate_intasend_invoice(
            self.invoice(), self.payment, self.subscription, self.reference,
            expected_invoice_id="INV-123",
        )
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_rejects_amount_mismatch(self):
        ok, reason = integrity.validate_intasend_invoice(
            self.invoice(value="798.99"), self.payment, self.subscription, self.reference
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "amount_mismatch")

    def test_rejects_currency_mismatch(self):
        ok, reason = integrity.validate_intasend_invoice(
            self.invoice(currency="USD"), self.payment, self.subscription, self.reference
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "currency_mismatch")

    def test_rejects_reference_mismatch(self):
        ok, reason = integrity.validate_intasend_invoice(
            self.invoice(api_ref="OTHER"), self.payment, self.subscription, self.reference
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "reference_mismatch")

    def test_rejects_invoice_id_mismatch(self):
        ok, reason = integrity.validate_intasend_invoice(
            self.invoice(invoice_id="OTHER"), self.payment, self.subscription,
            self.reference, expected_invoice_id="INV-123",
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "invoice_id_mismatch")

    def test_rejects_wrong_provider_method(self):
        self.payment.payment_method = "paystack"
        ok, reason = integrity.validate_intasend_invoice(
            self.invoice(), self.payment, self.subscription, self.reference
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "provider_mismatch")

    def test_rejects_non_complete_state(self):
        ok, reason = integrity.validate_intasend_invoice(
            self.invoice(state="PROCESSING"), self.payment, self.subscription, self.reference
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "state_mismatch")

    def test_rejects_subscription_customer_mismatch(self):
        self.subscription.user_id = 99
        ok, reason = integrity.validate_intasend_invoice(
            self.invoice(), self.payment, self.subscription, self.reference
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "customer_mismatch")

    def test_extracts_documented_invoice_response(self):
        invoice = self.invoice()
        self.assertEqual(integrity.extract_intasend_invoice({"invoice": invoice}), invoice)

    def test_decimal_amount_rejects_nan(self):
        self.assertIsNone(integrity.decimal_amount("NaN"))
        self.assertIsNone(integrity.decimal_amount("not-a-number"))


if __name__ == "__main__":
    unittest.main()
