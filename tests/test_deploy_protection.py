"""Deployment safety: migration history must never be uploaded by auto-deploy."""
import unittest

from scripts.pa_deploy import should_upload


class DeploymentMigrationProtectionTests(unittest.TestCase):
    def test_root_migrations_are_never_uploaded(self):
        self.assertFalse(should_upload("migrations/env.py"))
        self.assertFalse(should_upload("migrations/versions/0001_initial.py"))

    def test_nested_migrations_are_never_uploaded(self):
        self.assertFalse(should_upload("app/migrations/env.py"))
        self.assertFalse(should_upload("app/migrations/versions/0001_initial.py"))

    def test_normal_application_code_is_still_uploaded(self):
        self.assertTrue(should_upload("app/routes/billing.py"))
        self.assertTrue(should_upload("app/services/intasend_service.py"))


if __name__ == "__main__":
    unittest.main()
