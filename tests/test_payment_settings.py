import os
import tempfile
import unittest

from tests._load import load

ps = load("app/services/payment_settings.py", "payment_settings_under_test")


class PaymentSettingsTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "instance", "payment_settings.json")
        for p in ps.PROVIDERS.values():
            os.environ.pop(p["env"], None)

    def test_defaults_on_when_no_file(self):
        self.assertTrue(ps.is_enabled("paystack", self.path))
        self.assertTrue(ps.is_enabled("intasend", self.path))

    def test_toggle_off_and_on_keeps_other_provider(self):
        ps.set_enabled("paystack", False, self.path)
        self.assertFalse(ps.is_enabled("paystack", self.path))
        self.assertTrue(ps.is_enabled("intasend", self.path))
        ps.set_enabled("intasend", False, self.path)
        self.assertEqual(ps.all_status(self.path), {"paystack": False, "intasend": False})
        ps.set_enabled("paystack", True, self.path)
        self.assertTrue(ps.is_enabled("paystack", self.path))
        self.assertFalse(ps.is_enabled("intasend", self.path))

    def test_env_default_off_until_switched(self):
        os.environ["INTASEND_ENABLED"] = "false"
        try:
            self.assertFalse(ps.is_enabled("intasend", self.path))
            ps.set_enabled("intasend", True, self.path)
            self.assertTrue(ps.is_enabled("intasend", self.path))
        finally:
            os.environ.pop("INTASEND_ENABLED", None)

    def test_corrupt_file_falls_back_to_default(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w") as fh:
            fh.write("{not json")
        self.assertTrue(ps.is_enabled("paystack", self.path))

    def test_unknown_provider_is_off_and_cannot_be_set(self):
        self.assertFalse(ps.is_enabled("lipana", self.path))
        with self.assertRaises(ValueError):
            ps.set_enabled("lipana", True, self.path)


if __name__ == "__main__":
    unittest.main()
