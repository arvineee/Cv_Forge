"""
Browser tests for the progress overlay (static/js/progress.js).

Needs Playwright with Chromium (pip install playwright && playwright install chromium).
Skipped when Playwright isn't installed. Runs the real script and overlay markup.
"""
import os
import tempfile
import time
import shutil
import unittest

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT = True
except ImportError:
    PLAYWRIGHT = False

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

HARNESS = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<form id="f1" method="POST" action="about:blank" data-progress="Revamping your CV with AI" data-estimate="3">
  <input name="x" value="1"><button type="submit" id="b1">Go</button></form>
<form id="f2" method="POST" action="about:blank" data-progress="Form message" data-estimate="3">
  <button type="submit" id="b2" name="action" value="enhance" data-progress="Improving with AI" data-estimate="2">Enhance</button></form>
<a id="dl" href="#" data-progress="Preparing your file" data-estimate="2" data-autohide="1">Download</a>
{partial}
<script src="progress.js"></script>
<script>
  document.querySelectorAll("form").forEach(f => f.addEventListener("submit", e => e.preventDefault()));
  window.slowWork = (ms, fail) => new Promise((res, rej) =>
      setTimeout(() => fail ? rej(new Error("boom")) : res({ok: true}), ms));
</script></body></html>"""


@unittest.skipUnless(PLAYWRIGHT, "Playwright not installed")
class ProgressOverlay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        shutil.copy(os.path.join(ROOT, "app", "static", "js", "progress.js"), cls.dir)
        with open(os.path.join(ROOT, "app", "templates", "_progress.html")) as f:
            partial = f.read().replace("{{ url_for('static', filename='js/progress.js') }}", "progress.js")
        with open(os.path.join(cls.dir, "harness.html"), "w") as f:
            f.write(HARNESS.replace("{partial}", partial))
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def setUp(self):
        self.page = self.browser.new_page()
        self.errors = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.goto("file://" + os.path.join(self.dir, "harness.html"))

    def tearDown(self):
        self.page.close()

    def _visible(self):
        return self.page.evaluate("!document.getElementById('cv-progress').classList.contains('hidden')")

    def _label(self):
        return self.page.inner_text("#cv-progress-label")

    def _width(self):
        return float(self.page.evaluate("parseFloat(document.getElementById('cv-progress-bar').style.width)"))

    def test_form_submit_shows_overlay_with_form_message(self):
        self.page.click("#b1")
        time.sleep(0.3)
        self.assertTrue(self._visible())
        self.assertEqual(self._label(), "Revamping your CV with AI")

    def test_bar_rises_but_stays_under_92_until_done(self):
        self.page.click("#b1")
        time.sleep(0.4)
        first = self._width()
        time.sleep(1.0)
        second = self._width()
        self.assertGreater(second, first)
        self.assertLessEqual(second, 92.0)

    def test_submit_button_message_overrides_form_message(self):
        self.page.click("#b2")
        time.sleep(0.2)
        self.assertEqual(self._label(), "Improving with AI")

    def test_track_hides_overlay_after_success(self):
        self.page.evaluate("void CVProgress.track(slowWork(400, false), {label: 'Saving', estimate: 2})")
        time.sleep(0.2)
        self.assertTrue(self._visible())
        time.sleep(1.0)
        self.assertFalse(self._visible())

    def test_track_hides_overlay_after_failure(self):
        self.page.evaluate("void CVProgress.track(slowWork(300, true), {label: 'Saving', estimate: 2}).catch(() => {})")
        time.sleep(1.0)
        self.assertFalse(self._visible())

    def test_download_link_autohides(self):
        self.page.click("#dl")
        time.sleep(0.3)
        self.assertTrue(self._visible())
        time.sleep(1.6)
        self.assertFalse(self._visible())

    def test_back_navigation_hides_overlay(self):
        self.page.evaluate("CVProgress.show('Working', {estimate: 10})")
        self.page.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}))")
        time.sleep(0.5)
        self.assertFalse(self._visible())

    def test_no_javascript_errors(self):
        self.page.click("#b1")
        time.sleep(0.3)
        self.assertEqual(self.errors, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
