"""
PDF Generation Service — Enhanced Edition

Improvements over v1:
- Two selectable themes: 'modern' (sidebar accent column) and 'classic' (single-column).
- Accent color theming — one variable drives headers, rules, links, and skill chips.
- Skills rendered as styled chip cells (Table-based) not a flat comma string.
- LinkedIn / portfolio rendered as live clickable hyperlinks.
- KeepTogether blocks on job entries — no orphaned headers at page breaks.
- Page number footer injected via canvas onFirstPage / onLaterPages callbacks.
- generate_from_dict() convenience method works without an ORM model instance.
- All fields fail gracefully — missing values are skipped cleanly.
"""

import os
import re
import tempfile
import logging
from typing import Optional, Dict, Any, List

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch, mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, Flowable
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Theme Definitions
# ─────────────────────────────────────────────────────────────

THEMES: Dict[str, Dict[str, Any]] = {
    "modern": {
        "accent":       colors.HexColor("#2563eb"),   # Blue-600
        "accent_dark":  colors.HexColor("#1d4ed8"),   # Blue-700
        "text_primary": colors.HexColor("#0f172a"),   # Slate-900
        "text_muted":   colors.HexColor("#475569"),   # Slate-600
        "text_light":   colors.HexColor("#94a3b8"),   # Slate-400
        "bg_sidebar":   colors.HexColor("#f1f5f9"),   # Slate-100
        "rule_color":   colors.HexColor("#cbd5e1"),   # Slate-300
        "chip_bg":      colors.HexColor("#dbeafe"),   # Blue-100
        "chip_text":    colors.HexColor("#1e40af"),   # Blue-800
    },
    "classic": {
        "accent":       colors.HexColor("#1a1a2e"),
        "accent_dark":  colors.HexColor("#16213e"),
        "text_primary": colors.HexColor("#1a1a2e"),
        "text_muted":   colors.HexColor("#4a4a6a"),
        "text_light":   colors.HexColor("#9a9ab0"),
        "bg_sidebar":   colors.HexColor("#f5f5f5"),
        "rule_color":   colors.HexColor("#c8c8d8"),
        "chip_bg":      colors.HexColor("#e8e8f0"),
        "chip_text":    colors.HexColor("#1a1a2e"),
    },
}


# ─────────────────────────────────────────────────────────────
# Utility: Escape XML entities for ReportLab Paragraph markup
# ─────────────────────────────────────────────────────────────

def _esc(value: Any) -> str:
    """Escape a value for safe use inside ReportLab Paragraph XML markup."""
    if value is None:
        return ""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ─────────────────────────────────────────────────────────────
# Resume Data Normalizer
# ─────────────────────────────────────────────────────────────

def _normalize_resume(resume: Any) -> Dict[str, Any]:
    """
    Accept either an ORM model instance or a plain dict and return a clean dict.
    All keys are guaranteed to exist; values are either the real data or safe defaults.
    """
    if isinstance(resume, dict):
        data = resume
    else:
        # ORM model — convert attribute access to dict
        data = {
            "personal_info":         getattr(resume, "personal_info", {}) or {},
            "professional_summary":  getattr(resume, "professional_summary", None),
            "work_experience":       getattr(resume, "work_experience", []) or [],
            "education":             getattr(resume, "education", []) or [],
            "skills":                getattr(resume, "skills", []) or [],
            "title":                 getattr(resume, "title", None),
        }

    personal = data.get("personal_info") or {}

    # Build display name
    name = (
        personal.get("full_name")
        or f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip()
        or data.get("title")
        or "Resume"
    )

    return {
        "name":          name,
        "job_title":     personal.get("job_title") or "",
        "email":         personal.get("email") or "",
        "phone":         personal.get("phone") or "",
        "location":      personal.get("location") or "",
        "linkedin":      personal.get("linkedin") or "",
        "portfolio":     personal.get("portfolio") or "",
        "summary":       data.get("professional_summary") or "",
        "work":          data.get("work_experience") or [],
        "education":     data.get("education") or [],
        "skills":        data.get("skills") or [],
    }


# ─────────────────────────────────────────────────────────────
# Page Footer Canvas Callback
# ─────────────────────────────────────────────────────────────

def _make_footer_callback(name: str, accent_color: colors.Color):
    """Returns a canvas callback that draws a page number footer."""
    def _draw_footer(canvas_obj, doc):
        canvas_obj.saveState()
        canvas_obj.setFont("Helvetica", 8)
        canvas_obj.setFillColor(colors.HexColor("#94a3b8"))
        page_num = canvas_obj.getPageNumber()
        footer_text = f"{name} · Page {page_num}"
        canvas_obj.drawCentredString(doc.pagesize[0] / 2, 0.4 * inch, footer_text)
        canvas_obj.restoreState()
    return _draw_footer


# ─────────────────────────────────────────────────────────────
# Skills Chip Renderer
# ─────────────────────────────────────────────────────────────

def _build_skills_table(skills: List[str], theme: Dict, style: ParagraphStyle) -> Table:
    """
    Renders skills as a flowing grid of styled chip cells.
    Chips are grouped into rows of ~4 per row.
    """
    CHIPS_PER_ROW = 4
    chip_style = ParagraphStyle(
        "Chip",
        parent=style,
        fontSize=8.5,
        leading=11,
        textColor=theme["chip_text"],
        alignment=TA_CENTER,
    )

    cells = []
    for skill in skills:
        p = Paragraph(_esc(skill), chip_style)
        cells.append(p)

    # Pad to fill last row
    while len(cells) % CHIPS_PER_ROW != 0:
        cells.append(Paragraph("", chip_style))

    rows = [cells[i:i + CHIPS_PER_ROW] for i in range(0, len(cells), CHIPS_PER_ROW)]

    col_width = (6.5 * inch) / CHIPS_PER_ROW
    tbl = Table(rows, colWidths=[col_width] * CHIPS_PER_ROW, hAlign="LEFT")
    tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), theme["chip_bg"]),
        ("ROUNDEDCORNERS", [4]),
        ("TOPPADDING",  (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [theme["chip_bg"]]),
        ("GRID",         (0, 0), (-1, -1), 0.5, colors.white),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tbl


# ─────────────────────────────────────────────────────────────
# Main PDF Service
# ─────────────────────────────────────────────────────────────

class PDFService:
    """
    Generate a polished, themed PDF resume.

    Usage:
        # From ORM model
        path = PDFService(theme="modern").generate(resume_obj)

        # From plain dict
        path = PDFService(theme="classic").generate_from_dict(data_dict)
    """

    def __init__(self, page_size=letter, theme: str = "modern"):
        self.page_size = page_size
        self.theme = THEMES.get(theme, THEMES["modern"])
        self.styles = self._build_styles()

    # ─────────────────────────────────────────────────────────
    # Style Registry
    # ─────────────────────────────────────────────────────────

    def _build_styles(self) -> Dict[str, ParagraphStyle]:
        base = getSampleStyleSheet()
        t = self.theme
        s: Dict[str, ParagraphStyle] = {}

        s["name"] = ParagraphStyle(
            "Name", parent=base["Title"],
            fontSize=26, leading=30, alignment=TA_CENTER,
            textColor=t["text_primary"], spaceAfter=4,
        )
        s["job_title_header"] = ParagraphStyle(
            "JobTitleHeader", parent=base["Normal"],
            fontSize=12, leading=15, alignment=TA_CENTER,
            textColor=t["accent"], spaceAfter=8,
        )
        s["contact"] = ParagraphStyle(
            "Contact", parent=base["Normal"],
            fontSize=9, leading=12, alignment=TA_CENTER,
            textColor=t["text_muted"], spaceAfter=4,
        )
        s["contact_link"] = ParagraphStyle(
            "ContactLink", parent=base["Normal"],
            fontSize=9, leading=12, alignment=TA_CENTER,
            textColor=t["accent"], spaceAfter=12,
        )
        s["section_heading"] = ParagraphStyle(
            "SectionHeading", parent=base["Heading2"],
            fontSize=11, leading=14,
            textColor=t["accent"],
            fontName="Helvetica-Bold",
            spaceBefore=14, spaceAfter=3,
            borderPadding=(0, 0, 2, 0),
        )
        s["exp_title"] = ParagraphStyle(
            "ExpTitle", parent=base["Normal"],
            fontSize=11, leading=14,
            fontName="Helvetica-Bold",
            textColor=t["text_primary"],
        )
        s["exp_meta"] = ParagraphStyle(
            "ExpMeta", parent=base["Normal"],
            fontSize=9.5, leading=12,
            textColor=t["text_muted"], spaceAfter=3,
        )
        s["body"] = ParagraphStyle(
            "Body", parent=base["Normal"],
            fontSize=10, leading=14,
            textColor=t["text_primary"],
            alignment=TA_JUSTIFY,
        )
        s["bullet"] = ParagraphStyle(
            "Bullet", parent=base["Normal"],
            fontSize=10, leading=14,
            leftIndent=14, firstLineIndent=0,
            textColor=t["text_primary"],
        )
        s["edu_line"] = ParagraphStyle(
            "EduLine", parent=base["Normal"],
            fontSize=10, leading=14,
            textColor=t["text_primary"],
        )
        s["chip"] = ParagraphStyle(
            "Chip", parent=base["Normal"],
            fontSize=8.5, leading=11, alignment=TA_CENTER,
            textColor=t["chip_text"],
        )
        return s

    # ─────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────

    def generate(self, resume) -> str:
        """Generate PDF from an ORM model instance. Returns temp file path."""
        return self._build_pdf(_normalize_resume(resume))

    def generate_from_dict(self, data: Dict[str, Any]) -> str:
        """Generate PDF from a plain dict (e.g. from CVParser output). Returns temp file path."""
        return self._build_pdf(_normalize_resume(data))

    # ─────────────────────────────────────────────────────────
    # PDF Assembly
    # ─────────────────────────────────────────────────────────

    def _build_pdf(self, d: Dict[str, Any]) -> str:
        fd, path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)

        footer_cb = _make_footer_callback(d["name"], self.theme["accent"])

        doc = SimpleDocTemplate(
            path,
            pagesize=self.page_size,
            leftMargin=0.75 * inch,
            rightMargin=0.75 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.65 * inch,
            title=d["name"],
            author=d["name"],
            subject="Resume",
        )

        story = []

        # ── Header Block ──────────────────────────────────────
        story.append(Paragraph(_esc(d["name"]), self.styles["name"]))

        if d["job_title"]:
            story.append(Paragraph(_esc(d["job_title"]), self.styles["job_title_header"]))

        # Contact line: email | phone | location
        contact_parts = [_esc(v) for v in [d["email"], d["phone"], d["location"]] if v]
        if contact_parts:
            story.append(Paragraph(" &nbsp;·&nbsp; ".join(contact_parts), self.styles["contact"]))

        # Hyperlinks: LinkedIn | Portfolio
        # Build hex string from RGB components — hexval() returns '#x...' which is invalid
        _a = self.theme["accent"]
        accent_hex = "#{:02X}{:02X}{:02X}".format(
            int(_a.red * 255), int(_a.green * 255), int(_a.blue * 255)
        )
        link_parts = []
        if d["linkedin"]:
            url = d["linkedin"] if d["linkedin"].startswith("http") else f"https://{d['linkedin']}"
            link_parts.append(f'<link href="{url}" color="{accent_hex}">LinkedIn</link>')
        if d["portfolio"]:
            url = d["portfolio"] if d["portfolio"].startswith("http") else f"https://{d['portfolio']}"
            label = "GitHub" if "github.com" in url else "Portfolio"
            link_parts.append(f'<link href="{url}" color="{accent_hex}">{label}</link>')
        if link_parts:
            story.append(Paragraph(" &nbsp;·&nbsp; ".join(link_parts), self.styles["contact_link"]))

        story.append(HRFlowable(
            width="100%", thickness=1.5,
            color=self.theme["accent"], spaceAfter=10,
        ))

        # ── Professional Summary ──────────────────────────────
        if d["summary"]:
            story += self._section("PROFESSIONAL SUMMARY")
            story.append(Paragraph(_esc(d["summary"]), self.styles["body"]))
            story.append(Spacer(1, 6))

        # ── Work Experience ───────────────────────────────────
        if d["work"]:
            story += self._section("WORK EXPERIENCE")
            for job in d["work"]:
                story.append(self._build_job_block(job))

        # ── Education ─────────────────────────────────────────
        if d["education"]:
            story += self._section("EDUCATION")
            for edu in d["education"]:
                story.append(self._build_edu_block(edu))

        # ── Skills ────────────────────────────────────────────
        if d["skills"]:
            story += self._section("SKILLS")
            story.append(_build_skills_table(d["skills"], self.theme, self.styles["chip"]))
            story.append(Spacer(1, 6))

        doc.build(story, onFirstPage=footer_cb, onLaterPages=footer_cb)
        logger.info(f"PDF generated at: {path}")
        return path

    # ─────────────────────────────────────────────────────────
    # Section Heading Builder
    # ─────────────────────────────────────────────────────────

    def _section(self, title: str) -> list:
        """Returns [Heading Paragraph, thin rule] for a section."""
        return [
            Paragraph(title, self.styles["section_heading"]),
            HRFlowable(
                width="100%", thickness=0.75,
                color=self.theme["rule_color"], spaceAfter=6,
            ),
        ]

    # ─────────────────────────────────────────────────────────
    # Job Block Builder
    # ─────────────────────────────────────────────────────────

    def _build_job_block(self, job: Dict[str, Any]) -> KeepTogether:
        """
        Builds a single work experience block wrapped in KeepTogether
        to prevent orphaned headers at page breaks.
        """
        block = []

        title = _esc(job.get("title") or "")
        company = _esc(job.get("company") or "")
        start = _esc(job.get("start_date") or "")
        end = _esc(job.get("end_date") or "Present")

        # Title row: bold title on left, date range on right — via two-column table
        date_range = f"{start} – {end}" if start else end
        title_style = self.styles["exp_title"]
        date_style = ParagraphStyle(
            "DateRight", parent=self.styles["exp_meta"],
            alignment=TA_RIGHT, textColor=self.theme["text_muted"],
        )

        if title or date_range:
            header_row = Table(
                [[Paragraph(title, title_style), Paragraph(date_range, date_style)]],
                colWidths=["70%", "30%"],
                hAlign="LEFT",
            )
            header_row.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                ("LEFTPADDING",  (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING",   (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING",(0, 0), (-1, -1), 2),
            ]))
            block.append(header_row)

        if company:
            block.append(Paragraph(company, self.styles["exp_meta"]))

        description = job.get("description") or ""
        if description:
            block += self._render_description(description)

        block.append(Spacer(1, 8))
        return KeepTogether(block)

    # ─────────────────────────────────────────────────────────
    # Education Block Builder
    # ─────────────────────────────────────────────────────────

    def _build_edu_block(self, edu: Dict[str, Any]) -> KeepTogether:
        block = []
        degree = _esc(edu.get("degree") or "")
        institution = _esc(edu.get("institution") or "")
        year = _esc(edu.get("year") or "")
        grade = _esc(edu.get("grade") or "")

        # Build hex from RGB components — hexval() returns '#x475569' (invalid in ReportLab XML)
        _m = self.theme["text_muted"]
        muted_hex = "#{:02X}{:02X}{:02X}".format(
            int(_m.red * 255), int(_m.green * 255), int(_m.blue * 255)
        )

        # Degree + year on same line
        degree_line = f"<b>{degree}</b>" if degree else ""
        if year:
            degree_line += f" <font color='{muted_hex}'>({year})</font>"
        if degree_line:
            block.append(Paragraph(degree_line, self.styles["edu_line"]))

        meta_parts = [institution, grade]
        meta = "  ·  ".join(p for p in meta_parts if p)
        if meta:
            block.append(Paragraph(
                f'<font color="{muted_hex}">{meta}</font>',
                self.styles["edu_line"],
            ))

        block.append(Spacer(1, 6))
        return KeepTogether(block)

    # ─────────────────────────────────────────────────────────
    # Description Renderer (paragraphs + bullet lists)
    # ─────────────────────────────────────────────────────────

    def _render_description(self, text: str) -> list:
        """
        Renders job description text:
        - Lines starting with •, -, *, or digits followed by . are rendered as bullet points.
        - Other lines are rendered as body paragraphs.
        """
        items = []
        BULLET_RE = r"^[\•\-\*\–\u2022]\s*|^\d+\.\s+"

        for line in text.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            if re.match(BULLET_RE, stripped):
                clean = re.sub(BULLET_RE, "", stripped)
                items.append(Paragraph(f"• {_esc(clean)}", self.styles["bullet"]))
            else:
                items.append(Paragraph(_esc(stripped), self.styles["body"]))
        return items




