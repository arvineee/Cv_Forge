"""
CVForge AI - branded PDF version of the user manual.

build_manual_pdf(site_url) returns the PDF as bytes. Content comes from
manual_content.py. The cover page carries the site logo and name; every
other page has a header with the name and a footer with the site address
and page number.
"""
import io
import os
import re
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer,
                                PageBreak, Table, TableStyle, Image, ListFlowable, ListItem,
                                NextPageTemplate, KeepTogether)

from app.services.manual_content import MANUAL_TITLE, MANUAL_TAGLINE, SECTIONS

BRAND_NAME = "CVForge AI"
BRAND_GREEN = colors.HexColor("#0B8F5B")
INK = colors.HexColor("#0E1A2B")
MUTED = colors.HexColor("#5B6B7F")
LIGHT = colors.HexColor("#EAF6F0")
RULE = colors.HexColor("#D5DEE8")

LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "favicon.ico")


def _small_logo():
    """Logo scaled down for the PDF so the file stays small."""
    try:
        from PIL import Image as PILImage
        im = PILImage.open(LOGO_PATH).convert("RGB")
        im.thumbnail((512, 512))
        out = io.BytesIO()
        im.save(out, "JPEG", quality=88)
        out.seek(0)
        return out
    except Exception:
        return LOGO_PATH


def _inline(text: str) -> str:
    """Escape XML and turn **bold** into <b>."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


def _styles():
    base = dict(fontName="Helvetica", textColor=INK, leading=15, fontSize=10.5)
    return {
        "body": ParagraphStyle("body", spaceAfter=7, **base),
        "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=20, leading=24,
                             textColor=INK, spaceBefore=4, spaceAfter=4),
        "h3": ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=12, leading=15,
                             textColor=BRAND_GREEN, spaceBefore=9, spaceAfter=4),
        "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=9.5, leading=12.5, textColor=INK),
        "cellh": ParagraphStyle("cellh", fontName="Helvetica-Bold", fontSize=9.5, leading=12.5,
                                textColor=colors.white),
        "cover_title": ParagraphStyle("ct", fontName="Helvetica-Bold", fontSize=32, leading=38,
                                      textColor=INK, alignment=1),
        "cover_tag": ParagraphStyle("ctag", fontName="Helvetica", fontSize=15, leading=20,
                                    textColor=MUTED, alignment=1, spaceBefore=8),
        "cover_small": ParagraphStyle("cs", fontName="Helvetica", fontSize=10.5, leading=15,
                                      textColor=MUTED, alignment=1),
        "toc": ParagraphStyle("toc", fontName="Helvetica", fontSize=11, leading=18, textColor=INK),
    }


def _list(items, st, ordered):
    flow = ListFlowable(
        [ListItem(Paragraph(_inline(i), st["body"]), leftIndent=16) for i in items],
        bulletType="1" if ordered else "bullet",
        start=1 if ordered else "•",
        leftIndent=16, bulletFontName="Helvetica-Bold" if ordered else "Helvetica",
        bulletColor=BRAND_GREEN, bulletFontSize=10,
    )
    return flow


def _table(header, rows, st, width):
    n = len(header)
    first = 0.28 if n == 2 else 0.24
    rest = (1 - first) / (n - 1)
    col_w = [width * first] + [width * rest] * (n - 1)
    data = [[Paragraph(_inline(h), st["cellh"]) for h in header]]
    for r in rows:
        data.append([Paragraph(_inline(c), st["cell"]) for c in r])
    t = Table(data, colWidths=col_w, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_GREEN),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F9F7")]),
        ("GRID", (0, 0), (-1, -1), 0.5, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


def _blocks(blocks, st, width):
    out = []
    for b in blocks:
        kind = b[0]
        if kind == "p":
            out.append(Paragraph(_inline(b[1]), st["body"]))
        elif kind == "h3":
            out.append(Paragraph(_inline(b[1]), st["h3"]))
        elif kind == "ul":
            out += [_list(b[1], st, False), Spacer(1, 5)]
        elif kind == "ol":
            out += [_list(b[1], st, True), Spacer(1, 5)]
        elif kind == "table":
            out += [_table(b[1], b[2], st, width), Spacer(1, 8)]
    return out


def build_manual_pdf(site_url: str = "") -> bytes:
    site_url = (site_url or "").rstrip("/")
    site_label = re.sub(r"^https?://", "", site_url) or BRAND_NAME
    st = _styles()
    buf = io.BytesIO()
    page_w, page_h = A4
    margin = 0.85 * inch
    width = page_w - 2 * margin

    def cover_page(canvas, _doc):
        canvas.saveState()
        canvas.setFillColor(BRAND_GREEN)
        canvas.rect(0, page_h - 14 * mm, page_w, 14 * mm, stroke=0, fill=1)
        canvas.rect(0, 0, page_w, 10 * mm, stroke=0, fill=1)
        canvas.restoreState()

    def inner_page(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(BRAND_GREEN)
        canvas.rect(0, page_h - 9 * mm, page_w, 9 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(margin, page_h - 6 * mm, BRAND_NAME)
        canvas.setFont("Helvetica", 9)
        canvas.drawRightString(page_w - margin, page_h - 6 * mm, MANUAL_TITLE)
        canvas.setStrokeColor(RULE)
        canvas.line(margin, 0.6 * inch, page_w - margin, 0.6 * inch)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 8.5)
        canvas.drawString(margin, 0.4 * inch, site_label)
        canvas.drawRightString(page_w - margin, 0.4 * inch, f"Page {doc.page - 1}")
        canvas.restoreState()

    cover_frame = Frame(margin, 0.9 * inch, width, page_h - 1.8 * inch, id="cover")
    body_frame = Frame(margin, 0.8 * inch, width, page_h - 1.7 * inch, id="body")
    doc = BaseDocTemplate(
        buf, pagesize=A4, title=MANUAL_TITLE, author=BRAND_NAME, subject=MANUAL_TAGLINE,
        pageTemplates=[
            PageTemplate(id="cover", frames=[cover_frame], onPage=cover_page),
            PageTemplate(id="inner", frames=[body_frame], onPage=inner_page),
        ],
    )

    story = [Spacer(1, 0.9 * inch)]
    if os.path.isfile(LOGO_PATH):
        logo_w = 2.2 * inch
        story.append(Image(_small_logo(), width=logo_w, height=logo_w, hAlign="CENTER"))
    story += [
        Spacer(1, 0.5 * inch),
        Paragraph(_inline(BRAND_NAME), st["cover_title"]),
        Paragraph("User Manual", ParagraphStyle("cm", parent=st["cover_title"], fontSize=26,
                                                leading=32, textColor=BRAND_GREEN)),
        Paragraph(_inline(MANUAL_TAGLINE), st["cover_tag"]),
        Spacer(1, 1.2 * inch),
        Paragraph(f"Edition {date.today().strftime('%B %Y')}", st["cover_small"]),
    ]
    if site_url:
        story.append(Paragraph(_inline(site_url), st["cover_small"]))
    story += [NextPageTemplate("inner"), PageBreak()]

    story.append(Paragraph("Contents", st["h1"]))
    for i, sec in enumerate(SECTIONS, 1):
        story.append(Paragraph(f"{i}.&nbsp;&nbsp;{_inline(sec['title'])}", st["toc"]))
    story.append(Spacer(1, 14))

    for i, sec in enumerate(SECTIONS, 1):
        if i > 1:
            story.append(Spacer(1, 10))
        head = [Paragraph(f"{i}. {_inline(sec['title'])}", st["h1"]),
                Table([[""]], colWidths=[width], rowHeights=[2],
                      style=[("BACKGROUND", (0, 0), (-1, -1), BRAND_GREEN)]),
                Spacer(1, 8)]
        body = _blocks(sec["blocks"], st, width)
        # keep the heading with the first block so it is never stranded at a page bottom
        story += [KeepTogether(head + body[:1])] + body[1:]

    doc.build(story)
    return buf.getvalue()
