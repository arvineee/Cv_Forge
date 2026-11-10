"""CVForge AI - public free ATS checker (no sign-up, no AI calls, nothing stored)."""
import threading
import time
from collections import defaultdict, deque

from flask import Blueprint, make_response, render_template, request, url_for

from app.routes.seo import site_base_url
from app.services import ats_lite
from app.services.site_content import faq_jsonld

free_ats_bp = Blueprint("free_ats", __name__)

PAGE_TITLE = "Free ATS Resume Checker: Score Your CV Online | CVForge"
PAGE_DESCRIPTION = (
    "Paste your CV for a free ATS resume check. Get a score, see the fixes and match "
    "keywords to a job post in seconds. No sign-up, and nothing is saved."
)
PAGE_KEYWORDS = ("ATS resume checker, free ATS checker, ATS CV checker, resume checker, ATS score, "
                 "CV checker online, ATS friendly resume check, resume keyword checker")

FAQS = [
    ("What is an ATS?",
     "An applicant tracking system (ATS) is software many employers use to collect, sort and search job "
     "applications. It reads your CV into fields, so clear headings, a simple layout and the right keywords "
     "help it read yours correctly."),
    ("Is this the same system employers use?",
     "No. Every employer uses its own software and settings, and nobody outside those companies can see how "
     "they rank a CV. This tool checks common formatting and content signals, so treat the score as a guide to "
     "improve your CV, not a prediction."),
    ("Do you save my CV?",
     "No. We use the text you paste only to work out your result and we do not store it. Please leave out "
     "anything you do not want to share, such as ID numbers."),
    ("How is the score worked out?",
     "It is out of 100: contact details 15, section headings 20, length 10, numbers and results 20, writing "
     "style 20 and dates 15. The job keyword match is shown separately when you add a job description."),
    ("Can I check my CV against a job description?",
     "Yes. Paste the job post in the second box and we show which important words from it appear in your CV "
     "and which are missing. Only add a missing word if it is true for you."),
    ("Is the ATS checker really free?",
     "Yes. The score, every fix and the keyword check are free with no sign-up. If you want help rewriting "
     "your CV, a free CVForge account lets you build and preview a CV with AI, and a plan is needed to download it."),
]

# Soft per-IP limit. ProxyFix (see create_app) makes remote_addr the visitor's real address.
# It is per process and in memory only, and nothing is persisted.
CHECKS_PER_HOUR = 30
_WINDOW = 3600
_hits = defaultdict(deque)
_lock = threading.Lock()


def _rate_limited(ip):
    now = time.time()
    with _lock:
        q = _hits[ip]
        while q and now - q[0] > _WINDOW:
            q.popleft()
        if len(q) >= CHECKS_PER_HOUR:
            return True
        q.append(now)
        if len(_hits) > 5000:
            for key in [k for k, v in _hits.items() if not v or now - v[-1] > _WINDOW]:
                _hits.pop(key, None)
        return False


def _jsonld():
    base = site_base_url()
    here = base + url_for("free_ats.checker")
    return {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "WebApplication", "name": "CVForge Free ATS Resume Checker", "url": here,
             "applicationCategory": "BusinessApplication", "operatingSystem": "Any",
             "description": PAGE_DESCRIPTION,
             "offers": {"@type": "Offer", "price": "0", "priceCurrency": "KES"}},
            {"@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": base + "/"},
                {"@type": "ListItem", "position": 2, "name": "Free ATS resume checker", "item": here}]},
            faq_jsonld(FAQS),
        ],
    }


@free_ats_bp.route("/free-ats-checker", methods=["GET", "POST"])
def checker():
    ctx = dict(page_title=PAGE_TITLE, page_description=PAGE_DESCRIPTION, page_keywords=PAGE_KEYWORDS,
               faqs=FAQS, jsonld=_jsonld(), result=None, error=None, cv_text="", jd_text="",
               max_cv=ats_lite.MAX_CV_CHARS, max_jd=ats_lite.MAX_JD_CHARS)
    if request.method == "GET":
        return render_template("free_ats/page.html", **ctx)

    cv_text = ats_lite.clean_text(request.form.get("cv_text", ""))
    jd_text = ats_lite.clean_text(request.form.get("job_description", ""))
    ctx.update(cv_text=cv_text, jd_text=jd_text)
    status = 200
    if _rate_limited(request.remote_addr or "unknown"):
        ctx["error"] = ("You have run a lot of checks in the last hour. Please try again later, "
                        "or create a free account to keep improving your CV.")
        status = 429
    else:
        error = ats_lite.validate_inputs(cv_text, jd_text)
        if error:
            ctx["error"] = error
            status = 400
        else:
            ctx["result"] = ats_lite.analyse(cv_text, jd_text)
    resp = make_response(render_template("free_ats/page.html", **ctx), status)
    resp.headers["Cache-Control"] = "no-store"   # the page echoes the visitor's CV text
    return resp
