"""CVForge AI - User guide (web page + branded PDF download).

Public on purpose: the link in the manual email must work for people who are
not logged in.
"""
from flask import Blueprint, render_template, Response, request
from app.services.manual_content import MANUAL_TITLE, MANUAL_TAGLINE, SECTIONS

guide_bp = Blueprint("guide", __name__)


@guide_bp.app_template_filter("manual_inline")
def manual_inline(text):
    """Escape text, then turn **bold** into <b>."""
    import re
    from markupsafe import Markup, escape
    return Markup(re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", str(escape(text))))


@guide_bp.route("/guide")
def index():
    return render_template("guide/index.html", title=MANUAL_TITLE, tagline=MANUAL_TAGLINE,
                           sections=SECTIONS)


@guide_bp.route("/guide/download")
def download():
    from app.services.manual_pdf import build_manual_pdf
    data = build_manual_pdf(request.url_root)
    resp = Response(data, mimetype="application/pdf")
    resp.headers["Content-Disposition"] = 'attachment; filename="CVForge-AI-User-Manual.pdf"'
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp
