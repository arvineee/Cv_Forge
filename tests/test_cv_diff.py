import unittest

from tests._load import load

diff = load("app/services/cv_diff.py", "cv_diff")


class CvDiffTests(unittest.TestCase):
    def setUp(self):
        self.old = {
            "professional_summary": "Clerk with cash handling experience.",
            "work_experience": [
                {"job_title": "Clerk", "company": "Acme",
                 "achievements": ["Handled cash", "Served customers"]},
            ],
            "skills": ["Excel"],
        }
        self.new = {
            "professional_summary": "Experienced clerk with strong cash handling.",
            "work_experience": [
                {"job_title": "Clerk", "company": "Acme",
                 "achievements": ["Managed cash for [N] transactions", "Served customers"]},
            ],
            "skills": ["Excel", "SQL"],
        }

    def test_identical_snapshots_report_no_change(self):
        result = diff.diff_snapshots(self.old, self.old)
        self.assertFalse(result["changed"])
        self.assertIsNone(result["summary"])
        self.assertEqual(result["jobs"], [])

    def test_summary_diff_marks_changed_words(self):
        result = diff.diff_snapshots(self.old, self.new)
        ops = [s["op"] for s in result["summary"]]
        self.assertIn("insert", ops)
        self.assertIn("delete", ops)
        self.assertIn("equal", ops)

    def test_only_changed_jobs_are_listed(self):
        result = diff.diff_snapshots(self.old, self.new)
        self.assertEqual(len(result["jobs"]), 1)
        bullets = result["jobs"][0]["bullets"]
        self.assertEqual(
            [b for b in bullets if b["op"] == "insert"],
            [{"op": "insert", "text": "Managed cash for [N] transactions"}],
        )

    def test_added_skill_is_reported(self):
        result = diff.diff_snapshots(self.old, self.new)
        self.assertEqual(result["skills"]["added"], ["SQL"])
        self.assertEqual(result["skills"]["removed"], [])

    def test_skill_groups_are_flattened_and_deduplicated(self):
        snap = {"custom_sections": {"skill_groups": [
            {"group": "Tech", "skills": ["Python", "SQL"]},
            {"group": "Other", "skills": ["python"]},
        ]}, "skills": ["SQL"]}
        self.assertEqual(diff._flat_skills(snap), ["Python", "SQL"])

    def test_handles_missing_snapshots(self):
        result = diff.diff_snapshots(None, None)
        self.assertFalse(result["changed"])


if __name__ == "__main__":
    unittest.main()
