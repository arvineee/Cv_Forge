"""
CVForge AI - PDF Service v3
Flexible renderer — renders every section the parser captures.
Handles: skill groups with subtitles, achievements, languages,
interests, references, awards, publications, volunteer, projects,
extra/unknown sections. Works for any CV structure.
"""

import os
import tempfile
import re
from typing import Dict, Any, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
    Table, TableStyle, KeepTogether,
)
from reportlab.platypus.flowables import Flowable


# ─────────────────────────────────────────────────────────────
# Theme Registry
# ─────────────────────────────────────────────────────────────

THEMES: Dict[str, Dict] = {
    "modern":     {"accent": "#2563eb", "header_bg": "#1e3a5f", "header_fg": "#ffffff"},
    "classic":    {"accent": "#1e3a5f", "header_bg": "#1e3a5f", "header_fg": "#ffffff"},
    "minimal":    {"accent": "#374151", "header_bg": "#374151", "header_fg": "#ffffff"},
    "teal":       {"accent": "#0d9488", "header_bg": "#0d9488", "header_fg": "#ffffff"},
    "executive":  {"accent": "#111827", "header_bg": "#111827", "header_fg": "#ffffff"},
    "emerald":    {"accent": "#059669", "header_bg": "#059669", "header_fg": "#ffffff"},
    "purple":     {"accent": "#7c3aed", "header_bg": "#7c3aed", "header_fg": "#ffffff"},
    "rose":       {"accent": "#e11d48", "header_bg": "#e11d48", "header_fg": "#ffffff"},
    "navy":       {"accent": "#1e40af", "header_bg": "#1e40af", "header_fg": "#ffffff"},
    "terracotta": {"accent": "#b45309", "header_bg": "#b45309", "header_fg": "#ffffff"},
}

# Map Template.slug → theme name
SLUG_TO_THEME = {
    "classic-navy": "navy",
    "modern-blue": "modern",
    "minimal-gray": "minimal",
    "creative-teal": "teal",
    "executive-black": "executive",
    "emerald-fresh": "emerald",
    "purple-bold": "purple",
    "warm-terracotta": "terracotta",
    "rose-modern": "rose",
    "clean-white": "minimal",
    "tech-dark": "executive",
    "two-column-pro": "modern",
}


def _hex_to_color(hex_str: str):
    hex_str = hex_str.lstrip("#")
    r, g, b = int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16)
    return colors.Color(r / 255, g / 255, b / 255)


# ─────────────────────────────────────────────────────────────
# Custom Flowable — Color Bar left of section heading
# ─────────────────────────────────────────────────────────────

class AccentBar(Flowable):
    def __init__(self, width, accent_color, height=2):
        super().__init__()
        self.width = width
        self.accent = accent_color
        self.height = height

    def draw(self):
        self.canv.setFillColor(self.accent)
        self.canv.rect(0, 0, self.width, self.height, fill=1, stroke=0)

    def wrap(self, *args):
        return self.width, self.height


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _esc(text: str) -> str:
    """Escape XML special chars for ReportLab paragraphs."""
    if not text:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


BULLET_RE = re.compile(
    r"^[·•\-\*–\u2022\u00b7]\s*|^-\s*\.\s*|^\d+\.\s+",
    re.UNICODE,
)


def _split_bullets(text: str) -> List[str]:
    """Split a description into individual bullet strings."""
    if not text:
        return []
    items = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        cleaned = BULLET_RE.sub("", line).strip()
        if cleaned:
            items.append(cleaned)
    return items


def _normalize_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize parsed data dict so all keys exist with safe defaults."""
    personal = data.get("personal_info") or {}
    if not isinstance(personal, dict):
        personal = {}

    # Name from multiple possible keys
    name = (
        personal.get("full_name")
        or f"{personal.get('first_name','')} {personal.get('last_name','')}".strip()
        or "Professional"
    )

    # Normalize work experience — support title/job_title key variants
    raw_work = data.get("work_experience") or []
    work = []
    for job in raw_work:
        if not isinstance(job, dict):
            continue
        work.append({
            "job_title":   job.get("job_title") or job.get("title") or "",
            "company":     job.get("company") or "",
            "location":    job.get("location") or "",
            "start_date":  job.get("start_date") or "",
            "end_date":    job.get("end_date") or "Present",
            "description": job.get("description") or "",
            "achievements":job.get("achievements") or [],
        })

    # Normalize education
    raw_edu = data.get("education") or []
    education = []
    for e in raw_edu:
        if not isinstance(e, dict):
            continue
        education.append({
            "degree":      e.get("degree") or "",
            "institution": e.get("institution") or "",
            "location":    e.get("location") or "",
            "year":        e.get("year") or "",
            "grade":       e.get("grade") or "",
        })

    return {
        "name":          name,
        "job_title":     personal.get("job_title") or "",
        "email":         personal.get("email") or "",
        "phone":         personal.get("phone") or "",
        "location":      personal.get("location") or "",
        "linkedin":      personal.get("linkedin") or "",
        "portfolio":     personal.get("portfolio") or personal.get("website") or "",
        "github":        personal.get("github") or "",
        "summary":       data.get("professional_summary") or data.get("objective") or "",
        "work":          work,
        "education":     education,
        "skills":        data.get("skills") or [],
        "skill_groups":  data.get("skill_groups") or [],
        "certifications":data.get("certifications") or [],
        "achievements":  data.get("achievements") or [],
        "languages":     data.get("languages") or [],
        "interests":     data.get("interests") or [],
        "awards":        data.get("awards") or [],
        "publications":  data.get("publications") or [],
        "volunteer":     data.get("volunteer") or "",
        "references":    data.get("references") or "",
        "projects":      data.get("projects") or [],
        "extra_sections":data.get("extra_sections") or {},
    }


# ─────────────────────────────────────────────────────────────
# Style Builder
# ─────────────────────────────────────────────────────────────

def _build_styles(theme: Dict) -> Dict:
    accent = _hex_to_color(theme["accent"])
    header_fg = _hex_to_color(theme["header_fg"])
    gray = colors.HexColor("#374151")
    light_gray = colors.HexColor("#6b7280")
    dark = colors.HexColor("#111827")

    base = getSampleStyleSheet()

    return {
        "name": ParagraphStyle("name",
            fontName="Helvetica-Bold", fontSize=22,
            textColor=header_fg, leading=28, spaceAfter=2),
        "header_title": ParagraphStyle("header_title",
            fontName="Helvetica", fontSize=13,
            textColor=colors.HexColor("#bfdbfe"), leading=18, spaceAfter=0),
        "header_contact": ParagraphStyle("header_contact",
            fontName="Helvetica", fontSize=9,
            textColor=header_fg, leading=13),
        "section_heading": ParagraphStyle("section_heading",
            fontName="Helvetica-Bold", fontSize=11,
            textColor=accent, leading=14, spaceBefore=10, spaceAfter=2,
            textTransform="uppercase", tracking=0.5),
        "skill_group_heading": ParagraphStyle("skill_group_heading",
            fontName="Helvetica-Bold", fontSize=9,
            textColor=gray, leading=12, spaceBefore=6, spaceAfter=2),
        "job_title": ParagraphStyle("job_title",
            fontName="Helvetica-Bold", fontSize=10,
            textColor=dark, leading=13),
        "company": ParagraphStyle("company",
            fontName="Helvetica", fontSize=9.5,
            textColor=accent, leading=12),
        "date": ParagraphStyle("date",
            fontName="Helvetica-Oblique", fontSize=8.5,
            textColor=light_gray, leading=11),
        "bullet": ParagraphStyle("bullet",
            fontName="Helvetica", fontSize=9,
            textColor=gray, leading=13, leftIndent=12,
            bulletIndent=2, bulletText="•", spaceBefore=1),
        "body": ParagraphStyle("body",
            fontName="Helvetica", fontSize=9.5,
            textColor=gray, leading=14, alignment=TA_JUSTIFY),
        "degree": ParagraphStyle("degree",
            fontName="Helvetica-Bold", fontSize=9.5,
            textColor=dark, leading=12),
        "institution": ParagraphStyle("institution",
            fontName="Helvetica", fontSize=9,
            textColor=gray, leading=12),
        "tag": ParagraphStyle("tag",
            fontName="Helvetica", fontSize=8.5,
            textColor=gray, leading=11, spaceAfter=1),
        "list_item": ParagraphStyle("list_item",
            fontName="Helvetica", fontSize=9,
            textColor=gray, leading=13, spaceBefore=1),
    }


# ─────────────────────────────────────────────────────────────
# Section Builders
# ─────────────────────────────────────────────────────────────

def _section_header(label: str, styles: Dict, accent_color) -> List:
    """Returns [AccentBar, Heading paragraph, small spacer]."""
    return [
        Spacer(1, 6),
        AccentBar(6.5 * inch, accent_color, height=2.5),
        Spacer(1, 3),
        Paragraph(_esc(label).upper(), styles["section_heading"]),
        Spacer(1, 3),
    ]


def _build_header(d: Dict, theme: Dict, styles: Dict, page_width: float) -> List:
    header_bg = _hex_to_color(theme["header_bg"])
    margin = 0.65 * inch

    contact_parts = []
    if d["email"]:    contact_parts.append(_esc(d["email"]))
    if d["phone"]:    contact_parts.append(_esc(d["phone"]))
    if d["location"]: contact_parts.append(_esc(d["location"]))
    if d["linkedin"]: contact_parts.append(_esc(d["linkedin"]))
    if d["github"]:   contact_parts.append(_esc(d["github"]))
    if d["portfolio"]:contact_parts.append(_esc(d["portfolio"]))

    contact_str = "  ·  ".join(contact_parts)

    name_para = Paragraph(_esc(d["name"]), styles["name"])
    title_para = Paragraph(_esc(d["job_title"]), styles["header_title"]) if d["job_title"] else None
    contact_para = Paragraph(contact_str, styles["header_contact"]) if contact_str else None

    inner_width = page_width - 2 * margin
    content = [name_para]
    if title_para:  content.append(Spacer(1, 3)); content.append(title_para)
    if contact_para:content.append(Spacer(1, 6)); content.append(contact_para)

    table = Table([[content]], colWidths=[inner_width])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), header_bg),
        ("TOPPADDING",    (0, 0), (-1, -1), 20),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 18),
        ("LEFTPADDING",   (0, 0), (-1, -1), 20),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 20),
        ("ROWBACKGROUNDS",(0, 0), (-1, -1), [header_bg]),
    ]))
    return [table, Spacer(1, 10)]


def _build_summary(d: Dict, styles: Dict) -> List:
    if not d["summary"]:
        return []
    return [Paragraph(_esc(d["summary"]), styles["body"]), Spacer(1, 6)]


def _build_work(d: Dict, styles: Dict, accent_color) -> List:
    if not d["work"]:
        return []
    elements = _section_header("Professional Experience", styles, accent_color)

    for job in d["work"]:
        job_title = job.get("job_title") or job.get("title") or ""
        company   = job.get("company") or ""
        location  = job.get("location") or ""
        start     = job.get("start_date") or ""
        end       = job.get("end_date") or "Present"
        desc      = job.get("description") or ""
        achievements = job.get("achievements") or []

        date_str = f"{start} – {end}" if start else end
        company_loc = f"{_esc(company)}, {_esc(location)}" if company and location else _esc(company) or _esc(location)

        # Job title + date on same row
        title_table = Table(
            [[Paragraph(_esc(job_title), styles["job_title"]),
              Paragraph(_esc(date_str), styles["date"])]],
            colWidths=[4.2 * inch, 2.3 * inch],
        )
        title_table.setStyle(TableStyle([
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ("ALIGN",         (1, 0), (1, 0),   "RIGHT"),
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ]))

        block = [title_table]
        if company_loc:
            block.append(Paragraph(company_loc, styles["company"]))

        # Bullets from description
        bullets = _split_bullets(desc)
        for b in bullets:
            block.append(Paragraph(_esc(b), styles["bullet"]))

        # Extra achievements list
        for a in achievements:
            if isinstance(a, str) and a.strip():
                block.append(Paragraph(_esc(a.strip()), styles["bullet"]))

        elements.append(KeepTogether(block))
        elements.append(Spacer(1, 7))

    return elements


def _build_education(d: Dict, styles: Dict, accent_color) -> List:
    if not d["education"]:
        return []
    elements = _section_header("Education", styles, accent_color)

    for edu in d["education"]:
        degree      = edu.get("degree") or ""
        institution = edu.get("institution") or ""
        location    = edu.get("location") or ""
        year        = edu.get("year") or ""
        grade       = edu.get("grade") or ""

        inst_loc = f"{institution}, {location}" if institution and location else institution
        meta_parts = [p for p in [inst_loc, year, grade] if p]
        meta_str = "  ·  ".join(_esc(p) for p in meta_parts)

        block = []
        if degree:      block.append(Paragraph(_esc(degree), styles["degree"]))
        if meta_str:    block.append(Paragraph(meta_str, styles["institution"]))
        if block:
            elements.append(KeepTogether(block))
            elements.append(Spacer(1, 5))

    return elements


def _build_skills(d: Dict, styles: Dict, accent_color) -> List:
    if not d["skills"] and not d["skill_groups"]:
        return []

    elements = _section_header("Skills", styles, accent_color)

    skill_groups = d.get("skill_groups") or []
    flat_skills  = d.get("skills") or []

    if skill_groups:
        # Render each group with its subtitle
        for group in skill_groups:
            group_name = group.get("group") if isinstance(group, dict) else getattr(group, "group", None)
            skills     = group.get("skills") if isinstance(group, dict) else getattr(group, "skills", [])
            if not skills:
                continue
            if group_name:
                elements.append(Paragraph(_esc(group_name), styles["skill_group_heading"]))
            elements.append(_skill_chips(skills, styles))
            elements.append(Spacer(1, 4))
    elif flat_skills:
        elements.append(_skill_chips(flat_skills, styles))
        elements.append(Spacer(1, 4))

    return elements


def _skill_chips(skills: List[str], styles: Dict) -> Table:
    """Render skills as wrapped chip-style table, 3 per row."""
    CHIPS_PER_ROW = 3
    col_width = (6.5 * inch) / CHIPS_PER_ROW

    chips = [_esc(str(s).strip()) for s in skills if s]
    # Pad to complete last row
    while len(chips) % CHIPS_PER_ROW:
        chips.append("")

    rows = [chips[i:i + CHIPS_PER_ROW] for i in range(0, len(chips), CHIPS_PER_ROW)]
    table_data = [[Paragraph(c, styles["tag"]) for c in row] for row in rows]

    t = Table(table_data, colWidths=[col_width] * CHIPS_PER_ROW)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#f3f4f6")),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("ROWPADDING",    (0, 0), (-1, -1), 2),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.white),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def _build_certifications(d: Dict, styles: Dict, accent_color) -> List:
    items = d.get("certifications") or []
    if not items:
        return []
    elements = _section_header("Certifications", styles, accent_color)
    for item in items:
        if item and str(item).strip():
            elements.append(Paragraph(_esc(str(item).strip()), styles["bullet"]))
    elements.append(Spacer(1, 4))
    return elements


def _build_achievements(d: Dict, styles: Dict, accent_color) -> List:
    items = d.get("achievements") or []
    if not items:
        return []
    elements = _section_header("Key Achievements", styles, accent_color)
    for item in items:
        if item and str(item).strip():
            elements.append(Paragraph(_esc(str(item).strip()), styles["bullet"]))
    elements.append(Spacer(1, 4))
    return elements


def _build_awards(d: Dict, styles: Dict, accent_color) -> List:
    items = d.get("awards") or []
    if not items:
        return []
    elements = _section_header("Awards & Honours", styles, accent_color)
    for item in items:
        if item and str(item).strip():
            elements.append(Paragraph(_esc(str(item).strip()), styles["bullet"]))
    elements.append(Spacer(1, 4))
    return elements


def _build_languages(d: Dict, styles: Dict, accent_color) -> List:
    items = d.get("languages") or []
    if not items:
        return []
    elements = _section_header("Languages", styles, accent_color)
    # Render 2 per row inline
    lang_text = "   ·   ".join(_esc(str(l).strip()) for l in items if l)
    elements.append(Paragraph(lang_text, styles["body"]))
    elements.append(Spacer(1, 4))
    return elements


def _build_interests(d: Dict, styles: Dict, accent_color) -> List:
    items = d.get("interests") or []
    if not items:
        return []
    elements = _section_header("Interests", styles, accent_color)
    for item in items:
        if item and str(item).strip():
            elements.append(Paragraph(_esc(str(item).strip()), styles["bullet"]))
    elements.append(Spacer(1, 4))
    return elements


def _build_publications(d: Dict, styles: Dict, accent_color) -> List:
    items = d.get("publications") or []
    if not items:
        return []
    elements = _section_header("Publications", styles, accent_color)
    for item in items:
        if item and str(item).strip():
            elements.append(Paragraph(_esc(str(item).strip()), styles["bullet"]))
    elements.append(Spacer(1, 4))
    return elements


def _build_volunteer(d: Dict, styles: Dict, accent_color) -> List:
    text = d.get("volunteer") or ""
    if not text.strip():
        return []
    elements = _section_header("Volunteer Experience", styles, accent_color)
    elements.append(Paragraph(_esc(text), styles["body"]))
    elements.append(Spacer(1, 4))
    return elements


def _build_projects(d: Dict, styles: Dict, accent_color) -> List:
    projects = d.get("projects") or []
    if not projects:
        return []
    elements = _section_header("Projects", styles, accent_color)
    for proj in projects:
        if not isinstance(proj, dict):
            continue
        name = proj.get("name") or ""
        desc = proj.get("description") or ""
        url  = proj.get("url") or ""
        if name:
            elements.append(Paragraph(_esc(name), styles["job_title"]))
        if url:
            elements.append(Paragraph(_esc(url), styles["date"]))
        for b in _split_bullets(desc):
            elements.append(Paragraph(_esc(b), styles["bullet"]))
        elements.append(Spacer(1, 5))
    return elements


def _build_references(d: Dict, styles: Dict, accent_color) -> List:
    text = d.get("references") or ""
    if not text.strip():
        return []
    elements = _section_header("References", styles, accent_color)
    for line in text.split("\n"):
        if line.strip():
            elements.append(Paragraph(_esc(line.strip()), styles["list_item"]))
    elements.append(Spacer(1, 4))
    return elements


def _build_extra_sections(d: Dict, styles: Dict, accent_color) -> List:
    """Render any unknown/extra sections captured by the parser."""
    extra = d.get("extra_sections") or {}
    if not extra:
        return []
    elements = []
    for heading, content in extra.items():
        if not content or not str(content).strip():
            continue
        # Capitalize heading nicely
        nice_heading = heading.replace("_", " ").title()
        elements.extend(_section_header(nice_heading, styles, accent_color))
        for line in str(content).split("\n"):
            line = line.strip()
            if not line:
                continue
            cleaned = BULLET_RE.sub("", line).strip()
            if cleaned:
                elements.append(Paragraph(_esc(cleaned), styles["list_item"]))
        elements.append(Spacer(1, 4))
    return elements


# ─────────────────────────────────────────────────────────────
# Cover Letter builder
# ─────────────────────────────────────────────────────────────

def _build_cover_letter_pdf(letter, output_path: str, theme: Dict):
    from reportlab.platypus import Paragraph, Spacer, SimpleDocTemplate
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY
    from reportlab.lib.units import inch

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        topMargin=1 * inch, bottomMargin=1 * inch,
        leftMargin=1.1 * inch, rightMargin=1.1 * inch,
    )
    accent = _hex_to_color(theme["accent"])
    styles_raw = getSampleStyleSheet()

    body_style = ParagraphStyle("cl_body",
        fontName="Helvetica", fontSize=10.5,
        textColor=colors.HexColor("#374151"),
        leading=16, alignment=TA_JUSTIFY, spaceAfter=10)
    heading_style = ParagraphStyle("cl_heading",
        fontName="Helvetica-Bold", fontSize=13,
        textColor=accent, leading=18, spaceAfter=4)

    content = letter.content or ""
    elements = [Paragraph(_esc(letter.title or "Cover Letter"), heading_style),
                AccentBar(6.5 * inch, accent, height=2),
                Spacer(1, 16)]

    for para in content.split("\n\n"):
        para = para.strip()
        if para:
            for line in para.split("\n"):
                line = line.strip()
                if line:
                    elements.append(Paragraph(_esc(line), body_style))
            elements.append(Spacer(1, 6))

    doc.build(elements)


# ─────────────────────────────────────────────────────────────
# Main PDFService
# ─────────────────────────────────────────────────────────────

class PDFService:
    def __init__(self, theme: str = "modern", accent_color: str = None):
        self.theme_name = theme
        self.theme = THEMES.get(theme, THEMES["modern"]).copy()
        if accent_color:
            self.theme["accent"] = accent_color
            self.theme["header_bg"] = accent_color

    @classmethod
    def for_template(cls, template) -> "PDFService":
        """Create PDFService using a Template model's slug and accent_color."""
        theme_name = SLUG_TO_THEME.get(template.slug, "modern")
        accent = getattr(template, "accent_color", None)
        return cls(theme=theme_name, accent_color=accent)

    def generate(self, resume) -> str:
        """Generate PDF from a Resume model instance."""
        data = resume.to_dict()
        data["skill_groups"]  = resume.custom_sections.get("skill_groups", []) \
                                 if resume.custom_sections else []
        data["certifications"]= resume.certifications or []
        data["achievements"]  = resume.custom_sections.get("achievements", []) \
                                 if resume.custom_sections else []
        data["languages"]     = resume.languages or []
        data["awards"]        = resume.awards or []
        data["interests"]     = resume.custom_sections.get("interests", []) \
                                 if resume.custom_sections else []
        data["publications"]  = resume.custom_sections.get("publications", []) \
                                 if resume.custom_sections else []
        data["volunteer"]     = resume.custom_sections.get("volunteer", "") \
                                 if resume.custom_sections else ""
        data["references"]    = resume.references or ""
        data["projects"]      = resume.projects or []
        data["extra_sections"]= {}

        if resume.template:
            svc = PDFService.for_template(resume.template)
            return svc.generate_from_dict(data)

        return self.generate_from_dict(data)

    def generate_from_dict(self, data: Dict[str, Any]) -> str:
        """
        Generate PDF from a raw dict — works with any CV structure.
        Returns temp file path.
        """
        d = _normalize_data(data)
        styles = _build_styles(self.theme)
        accent = _hex_to_color(self.theme["accent"])

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        tmp.close()

        doc = SimpleDocTemplate(
            tmp.name, pagesize=A4,
            topMargin=0, bottomMargin=0.6 * inch,
            leftMargin=0.65 * inch, rightMargin=0.65 * inch,
        )

        elements = []

        # Header always first
        elements += _build_header(d, self.theme, styles, A4[0])

        # Summary / Objective
        if d["summary"]:
            elements += _section_header("Professional Summary", styles, accent)
            elements += _build_summary(d, styles)

        # Work experience
        elements += _build_work(d, styles, accent)

        # Education
        elements += _build_education(d, styles, accent)

        # Skills (with groups if available)
        elements += _build_skills(d, styles, accent)

        # Certifications
        elements += _build_certifications(d, styles, accent)

        # Key Achievements
        elements += _build_achievements(d, styles, accent)

        # Awards
        elements += _build_awards(d, styles, accent)

        # Languages
        elements += _build_languages(d, styles, accent)

        # Projects
        elements += _build_projects(d, styles, accent)

        # Publications
        elements += _build_publications(d, styles, accent)

        # Volunteer
        elements += _build_volunteer(d, styles, accent)

        # Interests
        elements += _build_interests(d, styles, accent)

        # References
        elements += _build_references(d, styles, accent)

        # Any extra/unknown sections the parser found
        elements += _build_extra_sections(d, styles, accent)

        doc.build(elements)
        return tmp.name

    def generate_cover_letter(self, letter) -> str:
        """Generate PDF for a CoverLetter model instance."""
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        tmp.close()
        _build_cover_letter_pdf(letter, tmp.name, self.theme)
        return tmp.name

