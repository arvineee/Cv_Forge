"""CVForge AI - User guide (web page + branded PDF download).

Public on purpose: the link in the manual email must work for people who are
not logged in.
"""
from flask import Blueprint, render_template, Response, request, url_for
from app.services.manual_content import MANUAL_TITLE, MANUAL_TAGLINE, MANUAL_UPDATED, SECTIONS

guide_bp = Blueprint("guide", __name__)


@guide_bp.app_template_filter("manual_inline")
def manual_inline(text):
    """Escape text, then turn **bold** into <b>."""
    import re
    from markupsafe import Markup, escape
    return Markup(re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", str(escape(text))))


def _faq():
    """Question/answer pairs for FAQ structured data, from the troubleshooting table."""
    for sec in SECTIONS:
        for b in sec["blocks"]:
            if b[0] == "table" and b[1][0] == "Problem":
                return [(f"{p[0].lower()}{p[1:]}: how do I fix it?", a) for p, a in b[2]]
    return []


def _jsonld():
    page = url_for("guide.index", _external=True)
    name = "CVForge AI"
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "TechArticle",
                "headline": "How to Use CVForge AI: User Manual and CV Guide",
                "description": "Step-by-step guide to building, revamping, checking and downloading a CV with CVForge AI.",
                "image": url_for("static", filename="og-default.jpg", _external=True),
                "inLanguage": "en",
                "dateModified": MANUAL_UPDATED,
                "mainEntityOfPage": page,
                "author": {"@type": "Organization", "name": name},
                "publisher": {"@type": "Organization", "name": name, "logo": {
                    "@type": "ImageObject",
                    "url": url_for("static", filename="icon-512.png", _external=True)}},
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home",
                     "item": url_for("main.index", _external=True)},
                    {"@type": "ListItem", "position": 2, "name": "User Guide", "item": page},
                ],
            },
            {
                "@type": "FAQPage",
                "mainEntity": [{"@type": "Question", "name": q,
                                "acceptedAnswer": {"@type": "Answer", "text": a}}
                               for q, a in _faq()],
            },
        ],
    }


@guide_bp.route("/guide")
def index():
    return render_template("guide/index.html", title=MANUAL_TITLE, tagline=MANUAL_TAGLINE,
                           sections=SECTIONS, jsonld=_jsonld())


@guide_bp.route("/guide/download")
def download():
    from app.services.manual_pdf import build_manual_pdf
    data = build_manual_pdf(request.url_root)
    resp = Response(data, mimetype="application/pdf")
    resp.headers["Content-Disposition"] = 'attachment; filename="CVForge-AI-User-Manual.pdf"'
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp
