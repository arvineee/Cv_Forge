"""Rule-based free ATS checker: scoring, validation and keyword matching (no Flask needed)."""
import os
import re
import unittest

from tests._load import load

al = load("app/services/ats_lite.py", "ats_lite_under_test")

GOOD = """Daniel Kim
Nairobi | daniel.kim@example.com | +254 700 123 456 | linkedin.com/in/danielkim

Professional Summary
Software developer with 4 years of experience building web applications and APIs in Python and JavaScript. Ships small, tested changes often and works closely with designers and product managers.

Work Experience
Software Developer, Brightpath Tech
Mar 2022 - Present
- Built and maintain 12 REST API endpoints used by a web app with about 20,000 monthly users.
- Reduced page load time by 35% by adding caching and fixing slow database queries.
- Wrote automated tests that raised coverage on the payments module from 40% to 85%.
- Led a team of 3 developers during the migration of 8 services to Docker containers.

Junior Developer, Northwind Digital
Jun 2020 - Feb 2022
- Developed customer-facing features in React and Node.js as part of a team of 5.
- Fixed more than 60 reported bugs and wrote clear release notes for each deployment.
- Moved deployments to a CI pipeline, cutting release time from 2 hours to 20 minutes.
- Mentored 2 interns and reviewed about 15 pull requests every week.

Education
BSc Computer Science, Riverside University, 2016 - 2020

Skills
Python, JavaScript, React, Node.js, SQL, REST APIs, Git, Docker, Automated testing, PostgreSQL, Django, AWS
"""
POOR = ("I am a hard worker and team player. I am responsible for many things and my duties included helping "
        "customers. I worked on lots of projects at my last job and I am looking for a new opportunity where I "
        "can grow my career in a good company with nice people who work together every day.")
JD = ("We are hiring a Python developer to build APIs with Django and PostgreSQL. You will deploy services with "
      "Docker on AWS, write automated tests and work with Kubernetes. Experience with Terraform and GraphQL is a "
      "plus. Strong Python and Django skills are required.")


class ScoringTests(unittest.TestCase):
    def test_strong_cv_scores_high_and_weak_cv_scores_low(self):
        good, poor = al.analyse(GOOD), al.analyse(POOR)
        self.assertGreaterEqual(good["score"], 90)
        self.assertEqual(good["band"], "Strong")
        self.assertLessEqual(poor["score"], 15)
        self.assertEqual(poor["band"], "Early draft")
        self.assertGreaterEqual(len(good["strengths"]), 2)
        self.assertEqual(poor["strengths"], [])

    def test_category_scores_add_up_and_stay_in_range(self):
        for text in (GOOD, POOR, GOOD.replace("Mar 2022", "03/2022")):
            r = al.analyse(text)
            self.assertEqual(sum(c["score"] for c in r["categories"]), r["score"])
            self.assertEqual(sum(c["max"] for c in r["categories"]), 100)
            for c in r["categories"]:
                self.assertTrue(0 <= c["score"] <= c["max"], c)
            self.assertTrue(0 <= r["score"] <= 100)

    def test_issues_are_sorted_actionable_and_free_of_promises(self):
        r = al.analyse(POOR)
        lost = [i["lost"] for i in r["issues"]]
        self.assertEqual(lost, sorted(lost, reverse=True))
        self.assertGreaterEqual(len(r["issues"]), 8)
        for i in r["issues"]:
            self.assertIn(i["severity"], ("high", "medium", "low"))
            self.assertTrue(len(i["title"]) > 8 and len(i["fix"]) > 30)
            self.assertIsNone(re.search(r"(?i)guarantee|will get you|100%", i["title"] + i["fix"]))
        self.assertEqual(sum(i["lost"] for i in r["issues"]) + r["score"], 100)

    def test_section_headings_detected_in_common_styles(self):
        text = "WORK EXPERIENCE:\nstuff\n\nEducation & Training\nstuff\n\n--- Key Skills ---\nstuff\n\nPROFILE\nstuff"
        found = al._find_sections(text.split("\n"))
        self.assertEqual(set(found), {"experience", "education", "skills", "summary"})
        long_line = "Experience " + "x" * 60
        self.assertEqual(al._find_sections([long_line]), {})

    def test_years_are_not_phone_numbers_or_results(self):
        r = al.analyse("Name\nname@example.com\n2019 2020 2021 2022\n" + "word " * 60)
        self.assertEqual(next(c for c in r["categories"] if c["key"] == "contact")["score"], 7)
        self.assertEqual(r["stats"]["numbers"], 0)
        r2 = al.analyse(GOOD)
        self.assertGreaterEqual(r2["stats"]["numbers"], 10)

    def test_mixed_date_formats_are_flagged(self):
        mixed = GOOD.replace("Mar 2022 - Present", "03/2022 - Present")
        keys = {i["key"] for i in al.analyse(mixed)["issues"]}
        self.assertIn("date_format", keys)
        self.assertNotIn("date_format", {i["key"] for i in al.analyse(GOOD)["issues"]})

    def test_length_bands(self):
        def words(n): return GOOD + "\n" + " ".join(["filler"] * n)
        self.assertEqual(next(c for c in al.analyse(words(400))["categories"] if c["key"] == "length")["score"], 10)
        self.assertEqual(next(c for c in al.analyse(words(1500))["categories"] if c["key"] == "length")["score"], 3)

    def test_no_ai_or_network_dependencies(self):
        """The free checker must stay free to run: it may only import re and collections."""
        import ast
        with open(os.path.join(os.path.dirname(al.__file__), "ats_lite.py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        self.assertEqual(imported, {"re", "collections"})
        calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertNotIn("open", calls)


class KeywordTests(unittest.TestCase):
    def test_matches_and_missing_terms(self):
        kw = al.analyse(GOOD, JD)["keywords"]
        for term in ("python", "django", "postgresql", "docker"):
            self.assertIn(term, kw["matched"])
        for term in ("kubernetes", "terraform", "graphql"):
            self.assertIn(term, kw["missing"])
        for noise in ("hiring", "write", "strong", "required", "with", "the"):
            self.assertNotIn(noise, kw["matched"] + kw["missing"])
        self.assertEqual(kw["percent"], round(100 * len(kw["matched"]) / kw["total"]))

    def test_none_when_no_or_tiny_job_description(self):
        self.assertIsNone(al.analyse(GOOD)["keywords"])
        self.assertIsNone(al.analyse(GOOD, "   ")["keywords"])
        self.assertIsNone(al.keyword_match(GOOD, "Python developer"))

    def test_light_stemming(self):
        cv = "Managed marketing teams and ran campaigns " * 10
        kw = al.keyword_match(cv, "Manager needed for marketer roles running campaign management and strategy work for brands")
        self.assertIn("manager", kw["matched"])
        self.assertIn("marketer", kw["matched"])
        self.assertIn("strategy", kw["missing"])


class ValidationTests(unittest.TestCase):
    def test_validate_inputs(self):
        self.assertIsNotNone(al.validate_inputs("too short"))
        self.assertIsNotNone(al.validate_inputs("x" * (al.MAX_CV_CHARS + 1)))
        self.assertIsNotNone(al.validate_inputs(GOOD, "y" * (al.MAX_JD_CHARS + 1)))
        self.assertIsNone(al.validate_inputs(GOOD, JD))
        self.assertIsNone(al.validate_inputs(GOOD))

    def test_clean_text_removes_control_characters(self):
        dirty = "Line one\r\nLine\x00 two\x07\n\n\n\n\n\nLine three\tend"
        out = al.clean_text(dirty)
        self.assertNotIn("\x00", out)
        self.assertNotIn("\x07", out)
        self.assertNotIn("\r", out)
        self.assertNotIn("\n\n\n\n", out)
        self.assertIn("Line three\tend", out)
        self.assertEqual(al.clean_text(None), "")


if __name__ == "__main__":
    unittest.main()
