"""
Every Jinja template must at least parse. This catches broken tags, unclosed
blocks and typos before they reach production, and needs only Jinja2.
"""
import glob
import os
import unittest

import jinja2

from tests._load import ROOT

TEMPLATE_DIR = os.path.join(ROOT, "app", "templates")


class TemplateSyntaxTests(unittest.TestCase):
    def test_all_templates_parse(self):
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(TEMPLATE_DIR))
        paths = glob.glob(os.path.join(TEMPLATE_DIR, "**", "*.html"), recursive=True)
        self.assertGreater(len(paths), 20, "template discovery looks wrong")
        failures = []
        for path in paths:
            rel = os.path.relpath(path, TEMPLATE_DIR)
            try:
                with open(path, encoding="utf-8") as fh:
                    env.parse(fh.read())
            except jinja2.TemplateSyntaxError as e:
                failures.append(f"{rel}:{e.lineno}: {e.message}")
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
