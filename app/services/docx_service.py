"""
DOCX Generation Service — Fixed Edition

Fixes applied in this pass:
- _normalize() now carries EVERY resume field (certifications, achievements,
  languages, interests, awards, publications, volunteer, references, projects,
  skill_groups, github). Previously only 6 fields were read, so every DOCX
  download silently dropped those sections regardless of what was in the DB.
- _add_job() now reads job_title (matching the schema used everywhere else in
  the app) instead of the nonexistent "title" key, and renders the
  achievements[] bullet list, not just a free-text description.
- generate() now pulls custom_sections / certifications / languages / awards /
  references / projects the same way PDFService.generate() already did, so
  DOCX and PDF exports are at parity.
- Skill groups (with subtitles) are rendered when present, falling back to a
  flat comma list otherwise.
- github is read from personal_info.github separately instead of being
  guessed out of the portfolio URL.

Improvements kept from v1:
- generate_from_dict() works with plain dicts (no ORM model needed).
- Style setup is document-scoped — never mutates shared global style objects.
- Section headings use paragraph bottom-border dividers (not heading style mutation).
- Title / date on job entries use tab stops for true left+right alignment.
- Bullet points use List Bullet numbering style (no manual unicode bullet chars).
- LinkedIn / portfolio / GitHub rendered as live hyperlinks via oxml relationship injection.
- Accent color is a single constant — change one value to retheme the whole doc.
- Page number injected into the footer section.
- All fields fail gracefully — None values are skipped, never rendered as "None".
"""

import os
import re
import tempfile
import logging
from typing import Any, Dict, List, Optional

from docx import Document
from docx.shared import Inches, Pt, RGBColor, Twips
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from lxml import etree

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Theme / Constants
# ─────────────────────────────────────────────────────────────

ACCENT_RGB    = RGBColor(0x25, 0x63, 0xEB)   # Blue-600
HEADING_RGB   = RGBColor(0x0F, 0x17, 0x2A)   # Slate-900
MUTED_RGB     = RGBColor(0x47, 0x55, 0x69)   # Slate-600
DIVIDER_HEX   = "CBD5E1"                      # Slate-300 (no #)

CONTENT_WIDTH_INCHES = 6.5
RIGHT_TAB_TWIPS      = int(CONTENT_WIDTH_INCHES * 1440)  # twips


# ─────────────────────────────────────────────────────────────
# Resume Data Normalizer
# ─────────────────────────────────────────────────────────────

def _normalize(resume: Any) -> Dict[str, Any]:
    """
    Accept ORM model or plain dict; return a clean, safe dict with EVERY
    section the app supports. Mirrors pdf_service._normalize_data() so
    DOCX and PDF exports never drift apart again.
    """
    if isinstance(resume, dict):
        data = dict(resume)
    else:
        custom = getattr(resume, "custom_sections", None) or {}
        data = {
            "personal_info":        getattr(resume, "personal_info", {}) or {},
            "professional_summary": getattr(resume, "professional_summary", None),
            "work_experience":      getattr(resume, "work_experience", []) or [],
            "education":            getattr(resume, "education", []) or [],
            "skills":               getattr(resume, "skills", []) or [],
            "skill_groups":         custom.get("skill_groups", []),
            "certifications":       getattr(resume, "certifications", []) or [],
            "achievements":         custom.get("achievements", []),
            "languages":            getattr(resume, "languages", []) or [],
            "interests":            custom.get("interests", []),
            "awards":               getattr(resume, "awards", []) or [],
            "publications":         custom.get("publications", []),
            "volunteer":            custom.get("volunteer", ""),
            "references":           getattr(resume, "references", None),
            "projects":             getattr(resume, "projects", []) or [],
            "title":                getattr(resume, "title", None),
        }

    personal = data.get("personal_info") or {}
    if not isinstance(personal, dict):
        personal = {}

    name = (
        personal.get("full_name")
        or f"{personal.get('first_name', '')} {personal.get('last_name', '')}".strip()
        or data.get("title")
        or "Resume"
    )

    raw_work = data.get("work_experience") or []
    work = []
    for job in raw_work:
        if not isinstance(job, dict):
            continue
        work.append({
            "job_title":    job.get("job_title") or job.get("title") or "",
            "company":      job.get("company") or "",
            "location":     job.get("location") or "",
            "start_date":   job.get("start_date") or "",
            "end_date":     job.get("end_date") or "Present",
            "description":  job.get("description") or "",
            "achievements": job.get("achievements") or [],
        })

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

    raw_projects = data.get("projects") or []
    projects = []
    for p in raw_projects:
        if isinstance(p, dict):
            projects.append({
                "name": p.get("name") or "",
                "description": p.get("description") or "",
                "url": p.get("url") or "",
            })
        elif isinstance(p, str) and p.strip():
            projects.append({"name": p.strip(), "description": "", "url": ""})

    return {
        "name":           name,
        "job_title":      personal.get("job_title") or "",
        "email":          personal.get("email") or "",
        "phone":          personal.get("phone") or "",
        "location":       personal.get("location") or "",
        "linkedin":       personal.get("linkedin") or "",
        "portfolio":      personal.get("portfolio") or personal.get("website") or "",
        "github":         personal.get("github") or "",
        "summary":        data.get("professional_summary") or data.get("objective") or "",
        "work":           work,
        "education":      education,
        "skills":         data.get("skills") or [],
        "skill_groups":   data.get("skill_groups") or [],
        "certifications": data.get("certifications") or [],
        "achievements":   data.get("achievements") or [],
        "languages":      data.get("languages") or [],
        "interests":      data.get("interests") or [],
        "awards":         data.get("awards") or [],
        "publications":   data.get("publications") or [],
        "volunteer":      data.get("volunteer") or "",
        "references":     data.get("references") or "",
        "projects":       projects,
    }


# ─────────────────────────────────────────────────────────────
# oxml Helpers
# ─────────────────────────────────────────────────────────────

def _set_paragraph_bottom_border(para, color_hex: str = DIVIDER_HEX, size: int = 6):
    pPr = para._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(size))
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), color_hex)
    pBdr.append(bottom)
    pPr.append(pBdr)


def _add_hyperlink(para, text: str, url: str, rgb: RGBColor = ACCENT_RGB):
    part = para.part
    r_id = part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)

    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)

    run_elem = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")

    u = OxmlElement("w:u")
    u.set(qn("w:val"), "single")
    rPr.append(u)

    color_elem = OxmlElement("w:color")
    color_elem.set(qn("w:val"), f"{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}")
    rPr.append(color_elem)

    run_elem.append(rPr)
    t = OxmlElement("w:t")
    t.text = text
    run_elem.append(t)
    hyperlink.append(run_elem)
    para._p.append(hyperlink)


def _add_tab_stop(para, position_twips: int, alignment=WD_TAB_ALIGNMENT.RIGHT):
    pPr = para._p.get_or_add_pPr()
    tabs = OxmlElement("w:tabs")
    tab = OxmlElement("w:tab")
    tab.set(qn("w:val"), "right" if alignment == WD_TAB_ALIGNMENT.RIGHT else "left")
    tab.set(qn("w:pos"), str(position_twips))
    tabs.append(tab)
    pPr.append(tabs)


def _add_page_number_field(para):
    run = para.add_run()
    fldChar_begin = OxmlElement("w:fldChar")
    fldChar_begin.set(qn("w:fldCharType"), "begin")
    run._r.append(fldChar_begin)

    instrText = OxmlElement("w:instrText")
    instrText.text = " PAGE "
    run._r.append(instrText)

    fldChar_end = OxmlElement("w:fldChar")
    fldChar_end.set(qn("w:fldCharType"), "end")
    run._r.append(fldChar_end)


# ─────────────────────────────────────────────────────────────
# Main Service
# ─────────────────────────────────────────────────────────────


MAIN_SECTIONS_ALL = ["summary", "work", "education", "skills", "certifications", "achievements",
                     "awards", "projects", "publications", "volunteer", "languages", "interests",
                     "references"]
MAIN_SECTIONS_SIDEBAR = ["summary", "work", "certifications", "achievements", "awards", "projects",
                         "publications", "volunteer", "interests", "references"]


def _insert_ppr_child(pPr, element, before_tags):
    """Insert element into pPr before the first child listed in before_tags (Word's schema order)."""
    for child in pPr:
        if child.tag in [qn(t) for t in before_tags]:
            child.addprevious(element)
            return
    pPr.append(element)


def _shade_paragraph(p, hex_color: str):
    pPr = p._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    _insert_ppr_child(pPr, shd, ["w:tabs", "w:spacing", "w:ind", "w:jc", "w:rPr"])


def _timeline_mark(container, start_index: int, hex_color: str):
    """
    Give one entry a coloured left rule and a dot on its first line. Blank
    spacing paragraphs are skipped, so each entry gets its own rule.
    Bullet paragraphs are rebuilt as plain paragraphs with a typed bullet.
    Word's numbering doesn't reliably carry the rule and indent, so this
    keeps the timeline consistent in every viewer.
    """
    paras = [p for p in container.paragraphs[start_index:] if p.text.strip()]
    if not paras:
        return
    for p in paras:
        pPr = p._p.get_or_add_pPr()
        is_bullet = p.style is not None and p.style.name == "List Bullet"
        if is_bullet:
            pStyle = pPr.find(qn("w:pStyle"))
            if pStyle is not None:
                pPr.remove(pStyle)
            numPr = pPr.find(qn("w:numPr"))
            if numPr is not None:
                pPr.remove(numPr)
            bullet = p.add_run("•  ")
            bullet.font.size = Pt(10)
            _move_run_to_front(p, bullet)
            p.paragraph_format.first_line_indent = Inches(0)
            p.paragraph_format.left_indent = Inches(0.4)
        else:
            p.paragraph_format.left_indent = Inches(0.4)
        pBdr = OxmlElement("w:pBdr")
        left = OxmlElement("w:left")
        left.set(qn("w:val"), "single")
        left.set(qn("w:sz"), "18")
        left.set(qn("w:space"), "10")
        left.set(qn("w:color"), hex_color)
        pBdr.append(left)
        _insert_ppr_child(pPr, pBdr, ["w:shd", "w:tabs", "w:spacing", "w:ind", "w:jc", "w:rPr"])
    first = paras[0]
    if not first.text.startswith("•"):
        dot = first.add_run("●  ")
        dot.font.color.rgb = RGBColor.from_string(hex_color)
        dot.font.size = Pt(8)
        _move_run_to_front(first, dot)


def _move_run_to_front(p, run):
    """Move a run that was just appended to the start of its paragraph, after pPr."""
    p._p.remove(run._r)
    pPr = p._p.pPr
    idx = list(p._p).index(pPr) + 1 if pPr is not None else 0
    p._p.insert(idx, run._r)


def _shade_cell(cell, hex_color: str):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def _cell_margins(cell, top_in: float, bottom_in: float, left_in: float, right_in: float):
    tcPr = cell._tc.get_or_add_tcPr()
    mar = OxmlElement("w:tcMar")
    for side, val in (("top", top_in), ("left", left_in), ("bottom", bottom_in), ("right", right_in)):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:w"), str(int(val * 1440)))
        el.set(qn("w:type"), "dxa")
        mar.append(el)
    tcPr.append(mar)


def _remove_empty_first_paragraph(cell):
    if cell.paragraphs and not cell.paragraphs[0].text:
        el = cell.paragraphs[0]._p
        el.getparent().remove(el)


def _add_photo(paragraph, photo_path: str, width):
    from app.services.photo_service import circle_png
    paragraph.add_run().add_picture(circle_png(photo_path), width=width)


def _photo_path(personal_info, photo_dir):
    """Consent-gated, existing-file-only path to the person's photo, or None."""
    info = personal_info or {}
    if not (photo_dir and info.get("photo") and info.get("photo_consent")):
        return None
    candidate = os.path.join(photo_dir, os.path.basename(info["photo"]))
    return candidate if os.path.isfile(candidate) else None


class DOCXService:
    """
    Generate a polished DOCX resume.

    Usage:
        path = DOCXService().generate(resume_obj)
        path = DOCXService().generate_from_dict(data_dict)
    """

    def __init__(self, theme: str = "modern"):
        from app.services.pdf_service import THEMES
        self.theme_name = theme if theme in THEMES else "modern"
        self.theme = dict(THEMES[self.theme_name])
        self.accent = RGBColor.from_string(self.theme["accent"].lstrip("#").upper())
        self.accent_hex = self.theme["accent"].lstrip("#").upper()
        self.header_style = self.theme.get("header_style", "banner")
        self.section_style = self.theme.get("section_style", "rule")
        self.timeline = bool(self.theme.get("timeline"))

    @classmethod
    def for_template(cls, template) -> "DOCXService":
        from app.services.pdf_service import SLUG_TO_THEME
        return cls(theme=SLUG_TO_THEME.get(getattr(template, "slug", ""), "modern"))

    def generate(self, resume, photo_dir: Optional[str] = None) -> str:
        svc = DOCXService.for_template(resume.template) if getattr(resume, "template", None) else self
        d = _normalize(resume)
        d["photo_file"] = _photo_path(getattr(resume, "personal_info", None), photo_dir)
        return svc._build_docx(d)

    def generate_from_dict(self, data: Dict[str, Any]) -> str:
        d = _normalize(data)
        d["photo_file"] = data.get("photo_file")
        return self._build_docx(d)

    def _build_docx(self, d: Dict[str, Any]) -> str:
        fd, path = tempfile.mkstemp(suffix=".docx")
        os.close(fd)

        doc = Document()
        self._setup_styles(doc)
        self._setup_page(doc)

        if self.header_style == "sidebar":
            self._build_sidebar_layout(doc, d)
        else:
            self._build_header(doc, d)
            self._render_body(doc, d, sections=MAIN_SECTIONS_ALL)

        self._add_footer(doc, d["name"])
        doc.save(path)
        logger.info(f"DOCX generated at: {path}")
        return path

    # ── Header variants ──────────────────────────────────────────

    def _build_header(self, doc: Document, d: Dict[str, Any]):
        if self.header_style == "band":
            self._header_band(doc, d)
        elif self.header_style == "plain":
            self._header_plain(doc, d)
        else:
            self._header_centred(doc, d)

    def _header_centred(self, doc: Document, d: Dict[str, Any]):
        self._add_name(doc, d["name"])
        if d["job_title"]:
            self._add_centered_run(doc, d["job_title"], size=12, rgb=self.accent)
        contact_parts = [v for v in [d["email"], d["phone"], d["location"]] if v]
        if contact_parts:
            self._add_centered_run(doc, "  |  ".join(contact_parts), size=9, rgb=MUTED_RGB)
        self._add_link_line(doc, d, centred=True)
        doc.add_paragraph()

    def _header_plain(self, doc: Document, d: Dict[str, Any]):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        run = p.add_run(d["name"])
        run.bold = True
        run.font.size = Pt(24)
        run.font.name = "Calibri"
        run.font.color.rgb = HEADING_RGB
        if d["job_title"]:
            t = doc.add_paragraph()
            t.paragraph_format.space_after = Pt(2)
            tr = t.add_run(d["job_title"])
            tr.font.size = Pt(12)
            tr.font.name = "Calibri"
            tr.font.color.rgb = self.accent
        contact_parts = [v for v in [d["email"], d["phone"], d["location"]] if v]
        c = doc.add_paragraph()
        c.paragraph_format.space_after = Pt(6)
        if contact_parts:
            cr = c.add_run("  ·  ".join(contact_parts))
            cr.font.size = Pt(9)
            cr.font.name = "Calibri"
            cr.font.color.rgb = MUTED_RGB
        _set_paragraph_bottom_border(c, self.accent_hex, size=12)
        doc.add_paragraph()

    def _header_band(self, doc: Document, d: Dict[str, Any]):
        """Full-width accent band with white name, title and contact. Photo sits in the band."""
        table = doc.add_table(rows=1, cols=2 if d.get("photo_file") else 1)
        table.autofit = False
        total = self._text_width_in()
        if d.get("photo_file"):
            photo_col, text_col = table.rows[0].cells
            photo_col.width = Inches(1.9)
            text_col.width = Inches(total - 1.9)
            _shade_cell(photo_col, self.accent_hex)
            _cell_margins(photo_col, 0.2, 0.15, 0.2, 0.1)
            _remove_empty_first_paragraph(photo_col)
            photo_p = photo_col.add_paragraph()
            _add_photo(photo_p, d["photo_file"], Inches(1.45))
        else:
            text_col = table.rows[0].cells[0]
            text_col.width = Inches(total)
        _shade_cell(text_col, self.accent_hex)
        _cell_margins(text_col, 0.22, 0.2, 0.25, 0.25)

        first = text_col.paragraphs[0]
        r = first.add_run(d["name"])
        r.bold = True
        r.font.size = Pt(26)
        r.font.name = "Calibri"
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        if d["job_title"]:
            t = text_col.add_paragraph()
            tr = t.add_run(d["job_title"])
            tr.font.size = Pt(12.5)
            tr.font.name = "Calibri"
            tr.font.color.rgb = RGBColor(0xF3, 0xF4, 0xF6)
        contact_parts = [v for v in [d["email"], d["phone"], d["location"]] if v]
        if contact_parts:
            c = text_col.add_paragraph()
            c.paragraph_format.space_before = Pt(8)
            cr = c.add_run("  ·  ".join(contact_parts))
            cr.font.size = Pt(9)
            cr.font.name = "Calibri"
            cr.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        doc.add_paragraph()

    def _add_link_line(self, doc: Document, d: Dict[str, Any], centred: bool):
        link_items = []
        if d["linkedin"]:
            link_items.append(("LinkedIn", d["linkedin"]))
        if d["github"]:
            link_items.append(("GitHub", d["github"]))
        if d["portfolio"]:
            link_items.append(("Portfolio", d["portfolio"]))
        if not link_items:
            return
        link_para = doc.add_paragraph()
        if centred:
            link_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for i, (label, url) in enumerate(link_items):
            if i > 0:
                link_para.add_run("  ·  ").font.color.rgb = MUTED_RGB
            url = url if url.startswith("http") else f"https://{url}"
            _add_hyperlink(link_para, label, url, self.accent)

    # ── Sidebar layout ───────────────────────────────────────────

    def _build_sidebar_layout(self, doc: Document, d: Dict[str, Any]):
        total = self._text_width_in()
        side_w = 2.35
        table = doc.add_table(rows=1, cols=2)
        table.autofit = False
        left, right = table.rows[0].cells
        left.width = Inches(side_w)
        right.width = Inches(total - side_w)

        _shade_cell(left, self.accent_hex)
        _cell_margins(left, 0.25, 0.2, 0.2, 0.2)
        _cell_margins(right, 0.05, 0.0, 0.3, 0.0)
        _remove_empty_first_paragraph(left)
        _remove_empty_first_paragraph(right)

        if d.get("photo_file"):
            p = left.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _add_photo(p, d["photo_file"], Inches(1.6))

        white = RGBColor(0xFF, 0xFF, 0xFF)
        contact = [v for v in [d["email"], d["phone"], d["location"], d["linkedin"],
                               d["github"], d["portfolio"]] if v]
        if contact:
            self._sb_heading(left, "Contact")
            for c in contact:
                self._sb_text(left, c, white)
        if d["education"]:
            self._sb_heading(left, "Education")
            for e in d["education"]:
                if e.get("degree"):
                    self._sb_text(left, e["degree"], white, bold=True)
                if e.get("institution"):
                    self._sb_text(left, e["institution"], white)
                meta = " · ".join(x for x in [e.get("year"), e.get("grade")] if x)
                if meta:
                    self._sb_text(left, meta, white)
        if d["skill_groups"] or d["skills"]:
            self._sb_heading(left, "Skills")
            if d["skill_groups"]:
                for g in d["skill_groups"]:
                    gname = g.get("group") if isinstance(g, dict) else None
                    gskills = g.get("skills", []) if isinstance(g, dict) else []
                    if gname:
                        self._sb_text(left, gname, white, bold=True)
                    for x in gskills:
                        if x:
                            self._sb_text(left, "•  " + str(x), white)
            else:
                for x in d["skills"]:
                    if x:
                        self._sb_text(left, "•  " + str(x), white)
        if d["languages"]:
            self._sb_heading(left, "Languages")
            for x in d["languages"]:
                if x:
                    self._sb_text(left, "•  " + str(x), white)

        name_p = right.paragraphs[0] if right.paragraphs else right.add_paragraph()
        nr = name_p.add_run(d["name"])
        nr.bold = True
        nr.font.size = Pt(24)
        nr.font.name = "Calibri"
        nr.font.color.rgb = HEADING_RGB
        if d["job_title"]:
            t = right.add_paragraph()
            tr = t.add_run(d["job_title"])
            tr.font.size = Pt(12)
            tr.font.name = "Calibri"
            tr.font.color.rgb = self.accent
        _set_paragraph_bottom_border(right.add_paragraph(), self.accent_hex, size=12)

        self._render_body(right, d, sections=MAIN_SECTIONS_SIDEBAR)
        # A Word table cell must always contain at least one paragraph.
        if not left.paragraphs:
            left.add_paragraph()
        doc.add_paragraph()

    def _sb_heading(self, cell, label: str):
        p = cell.add_paragraph()
        p.paragraph_format.space_before = Pt(12)
        p.paragraph_format.space_after = Pt(3)
        r = p.add_run(label.upper())
        r.bold = True
        r.font.size = Pt(9.5)
        r.font.name = "Calibri"
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        _set_paragraph_bottom_border(p, "FFFFFF", size=6)

    def _sb_text(self, cell, text: str, color, bold: bool = False):
        p = cell.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run(str(text))
        r.bold = bold
        r.font.size = Pt(9)
        r.font.name = "Calibri"
        r.font.color.rgb = color

    # ── Body (shared by every layout) ────────────────────────────

    def _render_body(self, container, d: Dict[str, Any], sections):
        """Write the body sections into a Document or a table cell, in order."""
        for key in sections:
            if key == "summary" and d["summary"]:
                self._section_heading(container, "PROFESSIONAL SUMMARY")
                container.add_paragraph(d["summary"])
            elif key == "work" and d["work"]:
                self._section_heading(container, "WORK EXPERIENCE")
                for job in d["work"]:
                    mark = len(container.paragraphs)
                    self._add_job(container, job)
                    if self.timeline:
                        _timeline_mark(container, mark, self.accent_hex)
            elif key == "education" and d["education"]:
                self._section_heading(container, "EDUCATION")
                for edu in d["education"]:
                    mark = len(container.paragraphs)
                    self._add_education(container, edu)
                    if self.timeline:
                        _timeline_mark(container, mark, self.accent_hex)
            elif key == "skills" and (d["skill_groups"] or d["skills"]):
                self._section_heading(container, "SKILLS")
                self._add_skills(container, d["skill_groups"], d["skills"])
            elif key == "certifications" and d["certifications"]:
                self._section_heading(container, "CERTIFICATIONS")
                self._add_bullet_list(container, d["certifications"])
            elif key == "achievements" and d["achievements"]:
                self._section_heading(container, "KEY ACHIEVEMENTS")
                self._add_bullet_list(container, d["achievements"])
            elif key == "awards" and d["awards"]:
                self._section_heading(container, "AWARDS")
                self._add_bullet_list(container, d["awards"])
            elif key == "projects" and d["projects"]:
                self._section_heading(container, "PROJECTS")
                for proj in d["projects"]:
                    self._add_project(container, proj)
            elif key == "publications" and d["publications"]:
                self._section_heading(container, "PUBLICATIONS")
                self._add_bullet_list(container, d["publications"])
            elif key == "volunteer" and d["volunteer"]:
                self._section_heading(container, "VOLUNTEER EXPERIENCE")
                container.add_paragraph(d["volunteer"])
            elif key == "languages" and d["languages"]:
                self._section_heading(container, "LANGUAGES")
                p = container.add_paragraph(" · ".join(str(x) for x in d["languages"]))
                for run in p.runs:
                    run.font.name = "Calibri"
            elif key == "interests" and d["interests"]:
                self._section_heading(container, "INTERESTS")
                p = container.add_paragraph(" · ".join(str(x) for x in d["interests"]))
                for run in p.runs:
                    run.font.name = "Calibri"
            elif key == "references" and d["references"]:
                self._section_heading(container, "REFERENCES")
                container.add_paragraph(d["references"])

    def _text_width_in(self) -> float:
        return 8.5 - 1.5  # Letter page with 0.75in side margins (see _setup_page)

    def _setup_page(self, doc: Document):
        section = doc.sections[0]
        section.page_width  = Inches(8.5)
        section.page_height = Inches(11)
        margin = Inches(0.75)
        section.top_margin    = margin
        section.bottom_margin = Inches(0.65)
        section.left_margin   = margin
        section.right_margin  = margin

    def _setup_styles(self, doc: Document):
        try:
            normal = doc.styles["Normal"]
            normal.font.name = "Calibri"
            normal.font.size = Pt(10)

            for level in range(1, 4):
                h = doc.styles[f"Heading {level}"]
                h.font.name = "Calibri"
                h.font.bold = True
                h.font.color.rgb = HEADING_RGB
                h.paragraph_format.space_before = Pt(0)
                h.paragraph_format.space_after  = Pt(2)

            if "List Bullet" in doc.styles:
                lb = doc.styles["List Bullet"]
                lb.font.name = "Calibri"
                lb.font.size = Pt(10)
        except Exception as e:
            logger.warning(f"Style configuration warning: {e}")

    def _add_name(self, doc: Document, name: str):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(name)
        run.bold = True
        run.font.size = Pt(26)
        run.font.name = "Calibri"
        run.font.color.rgb = HEADING_RGB

    def _add_centered_run(self, doc: Document, text: str, size: int = 10, rgb: RGBColor = HEADING_RGB):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(text)
        run.font.size = Pt(size)
        run.font.color.rgb = rgb
        run.font.name = "Calibri"

    def _section_heading(self, doc, title: str):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(12)
        p.paragraph_format.space_after = Pt(4)
        if self.section_style in ("bar", "band"):
            _shade_paragraph(p, self.accent_hex)
            p.paragraph_format.space_before = Pt(10)
            run = p.add_run(f" {title}")
            run.bold = True
            run.font.size = Pt(10.5)
            run.font.name = "Calibri"
            run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            return
        _set_paragraph_bottom_border(p, self.accent_hex if self.section_style == "rule" else DIVIDER_HEX, size=6)
        run = p.add_run(title)
        run.bold = True
        run.font.size = Pt(11)
        run.font.name = "Calibri"
        run.font.color.rgb = self.accent

    def _add_job(self, doc: Document, job: Dict[str, Any]):
        """
        Renders one work experience entry. Fixed: reads job_title (not the
        nonexistent "title" key), and renders the achievements[] bullet
        list in addition to any free-text description.
        """
        title     = job.get("job_title") or job.get("title") or ""
        company   = job.get("company") or ""
        location  = job.get("location") or ""
        start     = job.get("start_date") or ""
        end       = job.get("end_date") or "Present"
        date_str  = f"{start} – {end}" if start else end
        desc      = job.get("description") or ""
        achievements = job.get("achievements") or []

        if title or date_str:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(1)
            _add_tab_stop(p, RIGHT_TAB_TWIPS)

            if title:
                run = p.add_run(title)
                run.bold = True
                run.font.size = Pt(11)
                run.font.name = "Calibri"
                run.font.color.rgb = HEADING_RGB

            if date_str:
                tab_run = p.add_run(f"\t{date_str}")
                tab_run.font.size = Pt(9)
                tab_run.font.color.rgb = MUTED_RGB
                tab_run.font.name = "Calibri"

        company_loc = ", ".join(v for v in [company, location] if v)
        if company_loc:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(2)
            run = p.add_run(company_loc)
            run.font.size = Pt(9.5)
            run.font.color.rgb = MUTED_RGB
            run.font.name = "Calibri"

        if desc:
            self._render_description(doc, desc)

        for a in achievements:
            if isinstance(a, str) and a.strip():
                p = doc.add_paragraph(style="List Bullet")
                run = p.add_run(a.strip())
                run.font.name = "Calibri"
                run.font.size = Pt(10)

        doc.add_paragraph().paragraph_format.space_after = Pt(2)

    def _add_education(self, doc: Document, edu: Dict[str, Any]):
        degree      = edu.get("degree") or ""
        institution = edu.get("institution") or ""
        year        = edu.get("year") or ""
        grade       = edu.get("grade") or ""

        if degree:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(1)

            run = p.add_run(degree)
            run.bold = True
            run.font.name = "Calibri"
            run.font.color.rgb = HEADING_RGB

            if year:
                yr_run = p.add_run(f"  ({year})")
                yr_run.font.size = Pt(9.5)
                yr_run.font.color.rgb = MUTED_RGB
                yr_run.font.name = "Calibri"

        meta_parts = [v for v in [institution, grade] if v]
        if meta_parts:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(4)
            run = p.add_run("  ·  ".join(meta_parts))
            run.font.size = Pt(9.5)
            run.font.color.rgb = MUTED_RGB
            run.font.name = "Calibri"

    def _add_skills(self, doc: Document, skill_groups: List[Dict], flat_skills: List[str]):
        """Render grouped skills with subtitles when available, else a flat comma list."""
        if skill_groups:
            for group in skill_groups:
                group_name = group.get("group") if isinstance(group, dict) else getattr(group, "group", None)
                skills = group.get("skills") if isinstance(group, dict) else getattr(group, "skills", [])
                if not skills:
                    continue
                if group_name:
                    p = doc.add_paragraph()
                    p.paragraph_format.space_before = Pt(4)
                    p.paragraph_format.space_after = Pt(1)
                    run = p.add_run(group_name)
                    run.bold = True
                    run.font.size = Pt(9.5)
                    run.font.name = "Calibri"
                    run.font.color.rgb = MUTED_RGB
                doc.add_paragraph(", ".join(str(s) for s in skills))
        elif flat_skills:
            doc.add_paragraph(", ".join(str(s) for s in flat_skills))

    def _add_bullet_list(self, doc: Document, items: List[str]):
        """Generic bullet-list renderer used by certifications/achievements/awards/publications."""
        for item in items:
            if not item:
                continue
            p = doc.add_paragraph(style="List Bullet")
            run = p.add_run(str(item).strip())
            run.font.name = "Calibri"
            run.font.size = Pt(10)

    def _add_project(self, doc: Document, proj: Dict[str, Any]):
        name = proj.get("name") or ""
        description = proj.get("description") or ""
        url = proj.get("url") or ""
        if not (name or description):
            return
        if name:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(1)
            run = p.add_run(name)
            run.bold = True
            run.font.name = "Calibri"
            run.font.color.rgb = HEADING_RGB
        if url:
            link_p = doc.add_paragraph()
            link_p.paragraph_format.space_after = Pt(1)
            _add_hyperlink(link_p, url, url if url.startswith("http") else f"https://{url}", self.accent)
        if description:
            self._render_description(doc, description)
        doc.add_paragraph().paragraph_format.space_after = Pt(1)

    def _render_description(self, doc: Document, text: str):
        BULLET_RE = re.compile(r"^[\•\-\*\–\u2022]\s*|^\d+\.\s+")
        for line in text.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            if BULLET_RE.match(stripped):
                clean = BULLET_RE.sub("", stripped).strip()
                p = doc.add_paragraph(style="List Bullet")
                run = p.add_run(clean)
                run.font.name = "Calibri"
                run.font.size = Pt(10)
            else:
                p = doc.add_paragraph(stripped)
                p.paragraph_format.space_after = Pt(2)
                for run in p.runs:
                    run.font.name = "Calibri"

    def _add_footer(self, doc: Document, candidate_name: str):
        try:
            section = doc.sections[0]
            footer = section.footer
            footer.is_linked_to_previous = False

            para = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
            para.clear()
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER

            name_run = para.add_run(f"{candidate_name}  ·  Page ")
            name_run.font.size = Pt(8)
            name_run.font.color.rgb = MUTED_RGB
            name_run.font.name = "Calibri"

            _add_page_number_field(para)

        except Exception as e:
            logger.warning(f"Footer injection failed: {e}")

