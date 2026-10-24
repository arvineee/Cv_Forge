import unittest

from tests._load import load

ai = load("app/ai_service.py", "ai_service")

SOURCE = {
    "professional_summary": "Old summary",
    "work_experience": [
        {"job_title": "Clerk", "company": "Acme", "location": "Nairobi",
         "start_date": "2019", "end_date": "2021",
         "achievements": ["Handled cash", "Served customers"]},
        {"job_title": "Analyst", "company": "Bank", "location": "Nairobi",
         "start_date": "2021", "end_date": "Present",
         "achievements": ["Built reports"]},
    ],
    "skills": ["Excel"],
}


class RevampValidationTests(unittest.TestCase):
    def test_valid_output_is_merged(self):
        out = {
            "professional_summary": "Experienced clerk.",
            "work_experience": [
                {"job_title": "Clerk", "achievements": ["Managed cash for [N] transactions", "Delivered service"]},
                {"job_title": "Analyst", "achievements": ["Produced [X] reports monthly"]},
            ],
            "skills": ["Excel", "SQL"],
        }
        result = ai._validate_revamp(out, SOURCE)
        self.assertEqual(result["professional_summary"], "Experienced clerk.")
        self.assertEqual(result["work_experience"][0]["achievements"][0],
                         "Managed cash for [N] transactions")
        self.assertEqual(result["skills"], ["Excel", "SQL"])

    def test_bullet_count_change_keeps_original_bullets_for_that_job(self):
        out = {
            "professional_summary": "Summary.",
            "work_experience": [
                {"job_title": "Clerk", "achievements": ["A", "B"]},
                {"job_title": "Analyst", "achievements": ["Built reports", "Invented extra bullet"]},
            ],
        }
        result = ai._validate_revamp(out, SOURCE)
        self.assertEqual(result["work_experience"][1]["achievements"], ["Built reports"])

    def test_company_and_dates_are_taken_from_source_not_model(self):
        out = {
            "professional_summary": "Summary.",
            "work_experience": [
                {"job_title": "Clerk", "company": "Invented Ltd", "start_date": "1999",
                 "achievements": ["A", "B"]},
                {"job_title": "Analyst", "achievements": ["X"]},
            ],
        }
        result = ai._validate_revamp(out, SOURCE)
        self.assertEqual(result["work_experience"][0]["company"], "Acme")
        self.assertEqual(result["work_experience"][0]["start_date"], "2019")

    def test_non_object_output_is_rejected(self):
        with self.assertRaises(ai.RevampError):
            ai._validate_revamp(["not", "an", "object"], SOURCE)

    def test_empty_summary_is_rejected(self):
        with self.assertRaises(ai.RevampError):
            ai._validate_revamp({"professional_summary": "   "}, SOURCE)

    def test_oversized_summary_is_rejected(self):
        with self.assertRaises(ai.RevampError):
            ai._validate_revamp({"professional_summary": "x" * 2000}, SOURCE)

    def test_clean_json_fence_strips_markdown(self):
        self.assertEqual(ai._clean_json_fence('```json\n{"a": 1}\n```'), '{"a": 1}')
        self.assertEqual(ai._clean_json_fence('{"a": 1}'), '{"a": 1}')


if __name__ == "__main__":
    unittest.main()
