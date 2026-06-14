"""
CVForge AI - CV Parser Engine v3
Fully flexible section detection — handles any CV structure, any heading,
any ordering. Captures subtitled skill groups, achievements, languages,
interests, references, awards, volunteer work, publications, and any
unknown section rather than silently dropping it.

Key upgrades over v2:
- Dynamic section registry — no hardcoded heading whitelist
- Skill group subtitles preserved (Clinical Skills, Digital Health, etc.)
- Pipe-separated skill lists parsed correctly
- Company | Date same-line splitting
- All known CV sections captured: achievements, languages, interests,
  references, volunteer, publications, awards, hobbies, objective
- Unknown sections stored in extra_sections by their actual heading name
- Heuristic confidence scoring for name extraction
- Date range line correctly split into company + start/end
- Certifications parsed as list items not a blob
- Pydantic v2 schemas with graceful validation
"""

import re
import json
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Pydantic Schemas
# ─────────────────────────────────────────────────────────────

try:
    from pydantic import BaseModel, Field, field_validator, model_validator
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    BaseModel = object


if PYDANTIC_AVAILABLE:
    class PersonalInfoSchema(BaseModel):
        full_name: Optional[str] = None
        email: Optional[str] = None
        phone: Optional[str] = None
        location: Optional[str] = None
        job_title: Optional[str] = None
        linkedin: Optional[str] = None
        portfolio: Optional[str] = None
        github: Optional[str] = None
        website: Optional[str] = None

        @field_validator("email", mode="before")
        @classmethod
        def validate_email(cls, v):
            if not v: return None
            v = str(v).strip().lower()
            return v if re.fullmatch(r"[\w.\-+]+@[\w\-]+\.\w{2,}", v) else None

        @field_validator("phone", mode="before")
        @classmethod
        def normalize_phone(cls, v):
            if not v: return None
            digits = re.sub(r"[^\d+]", "", str(v))
            return str(v).strip() if 7 <= len(digits) <= 16 else None

    class WorkExperienceSchema(BaseModel):
        job_title: Optional[str] = None
        company: Optional[str] = None
        location: Optional[str] = None
        start_date: Optional[str] = None
        end_date: Optional[str] = None
        description: Optional[str] = None
        achievements: List[str] = Field(default_factory=list)

        @field_validator("description", mode="before")
        @classmethod
        def handle_list(cls, v):
            if isinstance(v, list):
                return "\n".join(str(i).strip() for i in v if i)
            return str(v).strip() if v else None

    class EducationSchema(BaseModel):
        degree: Optional[str] = None
        institution: Optional[str] = None
        location: Optional[str] = None
        year: Optional[str] = None
        grade: Optional[str] = None

    class SkillGroupSchema(BaseModel):
        """Skills with optional subtitle grouping."""
        group: Optional[str] = None   # e.g. "Clinical Skills", None = ungrouped
        skills: List[str] = Field(default_factory=list)

    class CVOutputSchema(BaseModel):
        personal_info: PersonalInfoSchema = Field(default_factory=PersonalInfoSchema)
        professional_summary: Optional[str] = None
        objective: Optional[str] = None
        work_experience: List[WorkExperienceSchema] = Field(default_factory=list)
        education: List[EducationSchema] = Field(default_factory=list)
        skills: List[str] = Field(default_factory=list)          # flat deduplicated
        skill_groups: List[SkillGroupSchema] = Field(default_factory=list)  # with subtitles
        certifications: List[str] = Field(default_factory=list)
        achievements: List[str] = Field(default_factory=list)
        languages: List[str] = Field(default_factory=list)
        interests: List[str] = Field(default_factory=list)
        references: Optional[str] = None
        volunteer: Optional[str] = None
        publications: List[str] = Field(default_factory=list)
        awards: List[str] = Field(default_factory=list)
        extra_sections: Dict[str, str] = Field(default_factory=dict)

        @field_validator("professional_summary", "objective", "volunteer", mode="before")
        @classmethod
        def cap_text(cls, v):
            if not v: return None
            return " ".join(str(v).split()[:300])

        @field_validator("skills", mode="before")
        @classmethod
        def dedup_skills(cls, v):
            if not v: return []
            seen, out = set(), []
            for s in v:
                k = str(s).strip().lower()
                if k and k not in seen:
                    seen.add(k)
                    out.append(str(s).strip())
            return out

        def model_dump_flat(self) -> Dict[str, Any]:
            """Returns dict compatible with Resume model fields."""
            d = self.model_dump()
            d["work_experience"] = [
                {
                    "job_title": j.get("job_title") or j.get("title") or "",
                    "company":   j.get("company") or "",
                    "location":  j.get("location") or "",
                    "start_date":j.get("start_date") or "",
                    "end_date":  j.get("end_date") or "Present",
                    "description":j.get("description") or "",
                    "achievements": j.get("achievements") or [],
                }
                for j in (d.get("work_experience") or [])
            ]
            return d
else:
    # Fallback plain dict when pydantic unavailable
    class CVOutputSchema:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
        def model_dump(self): return self.__dict__
        def model_dump_flat(self): return self.__dict__


# ─────────────────────────────────────────────────────────────
# Date Normalizer
# ─────────────────────────────────────────────────────────────

class DateNormalizer:
    MONTH_MAP = {
        "jan":"January","feb":"February","mar":"March","apr":"April",
        "may":"May","jun":"June","jul":"July","aug":"August",
        "sep":"September","oct":"October","nov":"November","dec":"December",
    }
    PRESENT = {"present","current","now","ongoing","till date","to date","date"}

    @classmethod
    def normalize(cls, raw: str) -> Optional[str]:
        if not raw: return None
        raw = str(raw).strip()
        if raw.lower() in cls.PRESENT: return "Present"
        m = re.match(r"([A-Za-z]{3,9})[\s.''\-]+[''']?(\d{2,4})", raw)
        if m:
            key = m.group(1).lower()[:3]
            yr = m.group(2)
            yr = ("20" + yr) if len(yr) == 2 else yr
            return f"{cls.MONTH_MAP.get(key, m.group(1).capitalize())} {yr}"
        m = re.match(r"(\d{4})\s*[–\-–]\s*(\d{4}|present|current)", raw, re.I)
        if m:
            end = "Present" if m.group(2).lower() in cls.PRESENT else m.group(2)
            return f"{m.group(1)} – {end}"
        if re.fullmatch(r"\d{4}", raw): return raw
        return raw


# ─────────────────────────────────────────────────────────────
# Dynamic Section Detector
# ─────────────────────────────────────────────────────────────

# Canonical section names mapped to their common aliases
SECTION_ALIASES: Dict[str, List[str]] = {
    "summary": [
        "summary","professional summary","profile","about me","about",
        "career profile","personal statement","executive summary",
        "career summary","overview",
    ],
    "objective": [
        "objective","career objective","professional objective",
        "job objective","career goal","goals",
    ],
    "experience": [
        "experience","work experience","professional experience","employment",
        "work history","career history","employment history",
        "professional background","positions held","relevant experience",
        "professional experience","job history",
    ],
    "education": [
        "education","academic background","qualifications",
        "academic qualifications","educational background",
        "academic history","schooling","training",
    ],
    "skills": [
        "skills","technical skills","core competencies","competencies",
        "key skills","skill set","technologies","tools","expertise",
        "areas of expertise","specialization","capabilities",
    ],
    "certifications": [
        "certifications","certificates","licenses","accreditations",
        "professional certifications","credentials","licensure",
        "professional licenses","training & certifications",
    ],
    "achievements": [
        "achievements","key achievements","accomplishments",
        "key accomplishments","notable achievements","highlights",
        "career highlights","professional achievements","awards & achievements",
    ],
    "awards": [
        "awards","honors","honours","awards & honors","recognition",
        "awards & recognition","prizes",
    ],
    "languages": [
        "languages","language skills","linguistic skills","spoken languages",
    ],
    "interests": [
        "interests","hobbies","hobbies & interests","personal interests",
        "extracurricular","activities","passions",
    ],
    "references": [
        "references","referees","professional references",
    ],
    "volunteer": [
        "volunteer","volunteering","volunteer experience","community service",
        "voluntary work","community involvement","social work",
    ],
    "publications": [
        "publications","research","papers","articles","research publications",
        "journal articles","conference papers",
    ],
    "projects": [
        "projects","key projects","notable projects","personal projects",
        "academic projects","portfolio",
    ],
}

# Build reverse alias → canonical map
ALIAS_TO_CANONICAL: Dict[str, str] = {}
for canonical, aliases in SECTION_ALIASES.items():
    for alias in aliases:
        ALIAS_TO_CANONICAL[alias.lower()] = canonical


def detect_section_heading(line: str) -> Optional[str]:
    """
    Returns canonical section name if the line is a KNOWN CV section heading,
    or the cleaned heading for unknown-but-heading-shaped lines.
    Returns None if the line is not a section heading.

    Conservative: only promotes a line to a heading if it matches known aliases
    OR passes strict heuristics. This prevents names, job titles, and locations
    from being misclassified as section headings.
    """
    stripped = line.strip().rstrip(":").strip()
    if not stripped or len(stripped) > 80:
        return None

    # Step 1: Check known aliases first (exact match after lowercase)
    lower = stripped.lower()
    if lower in ALIAS_TO_CANONICAL:
        return ALIAS_TO_CANONICAL[lower]

    # Step 2: Strict heuristics for unknown section headings
    # Must NOT look like contact info or a name
    if re.search(r"[@/\\|✉📞📧]|https?://|www\.", stripped):
        return None
    if not re.search(r"[A-Za-z]", stripped):
        return None

    words = stripped.split()

    # Reject if too many words (headings are typically 1-4 words)
    if len(words) > 5:
        return None

    # Reject if contains comma (names like "Narok County, Kenya" or sentences)
    if "," in stripped:
        return None

    # Reject if contains digits (years, phone numbers)
    if re.search(r"\d", stripped):
        return None

    # Reject if looks like a job title / name (has known non-heading words)
    NAME_LIKE = {
        "county","kenya","nairobi","mombasa","kisumu","nakuru","eldoret",
        "ltd","limited","inc","llc","corp","company",
    }
    if any(w.lower() in NAME_LIKE for w in words):
        return None

    # For ALL CAPS headings (common in PDFs): accept if ≥ 2 chars
    if stripped.isupper() and len(stripped) >= 4:
        return lower

    # For title-case headings: require at least one known heading keyword
    HEADING_SIGNALS = {
        "experience","education","skills","summary","profile","work",
        "employment","qualifications","competencies","certifications",
        "achievements","accomplishments","languages","interests","references",
        "awards","publications","volunteer","projects","objective","overview",
        "history","background","training","highlights","career","personal",
        "expertise","about",
    }
    is_title = all(w[0].isupper() for w in words if w and w[0].isalpha())
    has_signal = any(w.lower() in HEADING_SIGNALS for w in words)

    if is_title and has_signal:
        return lower

    return None


def chunk_cv(text: str) -> Dict[str, List[str]]:
    """
    Splits CV text into sections. Returns dict of canonical_name → [lines].
    Unknown headings are preserved verbatim as keys.
    """
    sections: Dict[str, List[str]] = {"_header": []}
    current = "_header"

    for line in text.split("\n"):
        stripped = line.strip()
        heading = detect_section_heading(stripped) if stripped else None

        if heading is not None and heading != current:
            current = heading
            sections.setdefault(current, [])
        else:
            sections.setdefault(current, []).append(line)

    return {k: v for k, v in sections.items() if any(l.strip() for l in v)}


# ─────────────────────────────────────────────────────────────
# Skill Group Parser
# ─────────────────────────────────────────────────────────────

def parse_skill_groups(section_lines: List[str]) -> Tuple[List[Dict], List[str]]:
    """
    Parse skills section that may contain subtitled groups like:
        Clinical Skills
        Skill A | Skill B | Skill C

        Digital Health & Technology
        DHIS2 | EMR | Health Data

    Returns (skill_groups, flat_skills_list).
    """
    groups: List[SkillGroupSchema] = []
    flat: List[str] = []
    seen = set()

    current_group: Optional[str] = None
    current_skills: List[str] = []

    def flush():
        nonlocal current_group, current_skills
        if current_skills:
            groups.append({"group": current_group, "skills": current_skills})
            for s in current_skills:
                k = s.lower()
                if k not in seen:
                    seen.add(k)
                    flat.append(s)
        current_group = None
        current_skills = []

    for line in section_lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Split pipe-separated items → skill list line
        if "|" in stripped or "," in stripped:
            sep = "|" if "|" in stripped else ","
            items = [i.strip().strip("·•-") for i in stripped.split(sep)]
            items = [i for i in items if i and len(i) > 1]
            if items:
                current_skills.extend(items)
            continue

        # Bullet-prefixed single skill
        bullet_m = re.match(r"^[·•\-\*–]\s*(.+)", stripped)
        if bullet_m:
            skill = bullet_m.group(1).strip()
            if skill:
                current_skills.append(skill)
            continue

        # Check if this looks like a skill group subtitle
        # (short, title-cased, no digits, no punctuation mid-line)
        words = stripped.split()
        if (
            1 <= len(words) <= 6
            and not re.search(r"[@\d/\\|,]", stripped)
            and all(w[0].isupper() for w in words if w and w[0].isalpha())
            and len(stripped) < 60
        ):
            flush()
            current_group = stripped
            continue

        # Otherwise treat as a plain skill
        if 2 <= len(stripped) <= 60:
            current_skills.append(stripped)

    flush()

    # If no groups were detected, just return flat list
    if not groups or (len(groups) == 1 and groups[0].group is None):
        return [], flat

    return groups, flat


# ─────────────────────────────────────────────────────────────
# Work Experience Parser
# ─────────────────────────────────────────────────────────────

DATE_RANGE_RE = re.compile(
    r"(?:"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"[\s.''\-]+[''']?\d{2,4}"
    r"|\d{4}"
    r")"
    r"\s*[–\-–to]+\s*"
    r"(?:"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"[\s.''\-]+[''']?\d{2,4}"
    r"|\d{4}"
    r"|[Pp]resent|[Cc]urrent|[Nn]ow|[Dd]ate"
    r")",
    re.IGNORECASE,
)

# Pattern for "Company Name | Apr 2025 – Present" or "Company | 2020-2022"
COMPANY_DATE_LINE_RE = re.compile(
    r"^(.+?)\s*\|\s*(" + DATE_RANGE_RE.pattern + r")\s*$",
    re.IGNORECASE,
)



def parse_work_experience(section_lines: List[str]) -> List[Dict]:
    """
    Flexible work experience parser. Handles all common CV formats:
    - Title / Company | Date / bullets  (each on own line, separated by blanks)
    - Title on one line, then company+date on next line
    - Company | Date on same line
    - Title, Company, Date all separated by blank lines
    """
    BULLET_RE = re.compile(r"^[·•\-\*–\u2022\u00b7]\s*")

    # Step 1: Split raw text into non-empty lines, keep blank as separators
    lines = [l.rstrip() for l in section_lines]

    # Step 2: Group lines into "paragraphs" separated by blank lines
    paragraphs: List[List[str]] = []
    cur: List[str] = []
    for line in lines:
        if line.strip():
            cur.append(line.strip())
        else:
            if cur:
                paragraphs.append(cur)
                cur = []
    if cur:
        paragraphs.append(cur)

    # Step 3: Classify each paragraph as:
    #   "title"   — single short non-bullet line with no date
    #   "meta"    — company/date line (has date or pipe)
    #   "bullets" — starts with bullet chars
    #   "mixed"   — title + company|date on consecutive lines

    def has_date(line: str) -> bool:
        return bool(DATE_RANGE_RE.search(line))

    def is_bullet_block(para: List[str]) -> bool:
        return bool(para) and bool(BULLET_RE.match(para[0]))

    def is_meta_line(line: str) -> bool:
        return "|" in line or has_date(line)

    # Step 4: Build job entries by walking paragraphs sequentially
    entries: List[Dict] = []
    job_title: Optional[str] = None
    company:   Optional[str] = None
    location:  Optional[str] = None
    start_date: Optional[str] = None
    end_date:   Optional[str] = None
    desc_lines: List[str] = []

    def flush_entry():
        nonlocal job_title, company, location, start_date, end_date, desc_lines
        if job_title or company:
            clean_desc = "\n".join(
                re.sub(r"^[·•\-\*–\u2022\u00b7]\s*", "• ", l)
                for l in desc_lines
            ).strip()
            entries.append({
                "job_title":   job_title or "",
                "company":     company or "",
                "location":    location or "",
                "start_date":  start_date or "",
                "end_date":    end_date or "Present",
                "description": clean_desc or "",
                "achievements": [],
            })
        job_title = company = location = start_date = end_date = None
        desc_lines = []

    for para in paragraphs:
        if not para:
            continue

        if is_bullet_block(para):
            # These are description bullets for the current job
            desc_lines.extend(para)
            continue

        # Check if this paragraph looks like a new job header
        # (non-bullet, not all bullets)
        all_meta = all(is_meta_line(l) for l in para)
        any_meta = any(is_meta_line(l) for l in para)

        if all_meta:
            # Pure company/date paragraph — attach to current job
            for line in para:
                date_m = DATE_RANGE_RE.search(line)
                company_date_m = COMPANY_DATE_LINE_RE.match(line)
                if company_date_m and not company:
                    raw_company = company_date_m.group(1).strip()
                    loc_split = re.split(r"\s*,\s*|\s*\|\s*", raw_company, maxsplit=1)
                    company = loc_split[0].strip()
                    if len(loc_split) > 1:
                        location = loc_split[1].strip()
                if date_m:
                    date_str = date_m.group(0)
                    parts = re.split(r"\s*[–\-–]\s*|\s+to\s+", date_str, maxsplit=1, flags=re.I)
                    start_date = DateNormalizer.normalize(parts[0].strip()) if parts else None
                    end_date   = DateNormalizer.normalize(parts[1].strip()) if len(parts) > 1 else "Present"
            continue

        # Mixed or pure title paragraph
        # If we already have a job title, this is a new entry
        if job_title and not company:
            # Previous title with no company — flush and start fresh
            flush_entry()
        elif job_title and company:
            flush_entry()

        # Parse lines in this paragraph
        for line in para:
            if BULLET_RE.match(line):
                desc_lines.append(line)
                continue

            date_m = DATE_RANGE_RE.search(line)
            company_date_m = COMPANY_DATE_LINE_RE.match(line)

            if company_date_m and not company:
                raw_company = company_date_m.group(1).strip()
                loc_split = re.split(r"\s*,\s*|\s*\|\s*", raw_company, maxsplit=1)
                company = loc_split[0].strip()
                if len(loc_split) > 1 and not location:
                    location = loc_split[1].strip()
                if date_m:
                    date_str = date_m.group(0)
                    parts = re.split(r"\s*[–\-–]\s*|\s+to\s+", date_str, maxsplit=1, flags=re.I)
                    start_date = DateNormalizer.normalize(parts[0].strip()) if parts else None
                    end_date   = DateNormalizer.normalize(parts[1].strip()) if len(parts) > 1 else "Present"
                continue

            if date_m and not start_date:
                date_str = date_m.group(0)
                parts = re.split(r"\s*[–\-–]\s*|\s+to\s+", date_str, maxsplit=1, flags=re.I)
                start_date = DateNormalizer.normalize(parts[0].strip()) if parts else None
                end_date   = DateNormalizer.normalize(parts[1].strip()) if len(parts) > 1 else "Present"
                remainder = line.replace(date_str, "").strip(" |–-,·")
                if remainder and not company:
                    company = remainder
                continue

            # Plain text line
            if not job_title:
                job_title = line
            elif not company:
                company = line
            else:
                desc_lines.append(line)

    flush_entry()
    return entries



def parse_education(section_lines: List[str]) -> List[Dict]:
    DEGREE_RE = re.compile(
        r"\b(B\.?Sc|B\.?A|B\.?Eng|B\.?Tech|M\.?Sc|M\.?A|M\.?Eng|MBA|Ph\.?D|"
        r"Bachelor[''\s]?s?|Master[''\s]?s?|Doctorate|Diploma|Certificate|"
        r"HND|OND|Associate|KCSE|KCPE|A\s*Level|O\s*Level)\b",
        re.IGNORECASE,
    )
    YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
    GRADE_RE = re.compile(
        r"\b(First Class|Second Class|2:1|2:2|Third Class|Pass|Distinction|"
        r"Merit|GPA\s*:?\s*[\d.]+|[\d.]+\s*/\s*[\d.]+|Cum Laude|"
        r"Magna Cum Laude|Summa Cum Laude|Credit|Fail|Upper|Lower)\b",
        re.IGNORECASE,
    )

    # Pre-process: insert blank lines before degree-starting lines so entries
    # that run together without blank lines still get split into separate blocks.
    # Check first 2 words (handles "Kenya Certificate...", "Diploma...", "KCSE", etc.)
    processed = []
    for line in section_lines:
        stripped = line.strip()
        if stripped and DEGREE_RE.search(stripped):
            words = stripped.split()
            # Match if first OR second word is a degree keyword
            first_two = " ".join(words[:2]) if len(words) >= 2 else (words[0] if words else "")
            if DEGREE_RE.match(words[0]) or (len(words) > 1 and DEGREE_RE.match(words[1])):
                processed.append("")  # force new block
        processed.append(line)

    entries: List[Dict] = []
    blocks: List[List[str]] = []
    cur: List[str] = []

    for line in processed:
        if line.strip():
            cur.append(line.strip())
        else:
            if cur:
                blocks.append(cur)
                cur = []
    if cur:
        blocks.append(cur)

    for block in blocks:
        if not block:
            continue
        degree = institution = year = grade = location = None

        for line in block:
            # "Institution | Year" or "Institution | Month Year"
            pipe_m = re.match(r"^(.+?)\s*\|\s*(.+)$", line)
            if pipe_m:
                left = pipe_m.group(1).strip()
                right = pipe_m.group(2).strip()
                year_m = YEAR_RE.search(right)
                if year_m:
                    if not institution:
                        institution = left
                    year = year_m.group(0)
                    continue

            year_m = YEAR_RE.search(line)
            grade_m = GRADE_RE.search(line)
            degree_m = DEGREE_RE.search(line)

            if grade_m and not grade:
                grade = grade_m.group(0)
            if year_m and not year:
                year = year_m.group(0)
            if degree_m and not degree:
                degree = line
            elif not institution and not degree_m and len(line) < 120:
                institution = line

        if degree or institution:
            entries.append({
                "degree": degree,
                "institution": institution,
                "location": location,
                "year": year,
                "grade": grade,
            })

    return entries


# ─────────────────────────────────────────────────────────────
# List Section Parser (bullets/pipes/commas → list of strings)
# ─────────────────────────────────────────────────────────────

def parse_list_section(section_lines: List[str]) -> List[str]:
    """
    Parse any section that should be a list of items.
    Handles: bullet points, numbered lists, pipe-separated, comma-separated,
    or plain line-by-line items. Also handles ". " (period-space) bullet variant
    and embedded newlines within a single line.
    """
    items: List[str] = []
    # Matches: bullets (·•-*–), numbered (1.), period-space (". "), leading dot+space
    BULLET_RE = re.compile(
        r"^[\d]+\.\s+|^[·•\-\*–\u2022\u00b7]\s*|^\.\.?\s+|^-\s*\.\s*",
        re.UNICODE
    )

    # First split any embedded newlines so multi-bullet paragraphs become separate lines
    expanded = []
    for line in section_lines:
        for sub in line.split("\n"):
            expanded.append(sub)

    for line in expanded:
        stripped = line.strip()
        if not stripped:
            continue

        # Pipe-separated — but only if no date range (avoid splitting company|date)
        if "|" in stripped and not re.search(r"\d{4}", stripped):
            for part in stripped.split("|"):
                part = BULLET_RE.sub("", part).strip()
                if part and len(part) > 1:
                    items.append(part)
            continue

        # Strip bullet prefix
        cleaned = BULLET_RE.sub("", stripped).strip()
        # Also strip a lone leading period that survived
        cleaned = re.sub(r"^\.\.?\s*", "", cleaned).strip()
        if cleaned and len(cleaned) > 1:
            items.append(cleaned)

    return [i for i in items if i]


# ─────────────────────────────────────────────────────────────
# Header Parser (name, contact, job title)
# ─────────────────────────────────────────────────────────────


def parse_header(lines: List[str]) -> Dict:
    """Extract name, email, phone, location, job title from CV header lines."""
    personal: Dict[str, Any] = {
        "full_name": None, "email": None, "phone": None, "location": None,
        "job_title": None, "linkedin": None, "portfolio": None,
        "github": None, "website": None,
    }

    full_text = "\n".join(lines)

    # Email
    m = re.search(r"[\w.\-+]+@[\w.\-]+\.\w{2,}", full_text)
    if m:
        personal["email"] = m.group(0).lower()

    # Phone
    phone_text = re.sub(r"[\w.\-+]+@[\w.\-]+\.\w{2,}", "", full_text)
    m = re.search(
        r"(?:\+?\d{1,3}[\s.\-]?)?(?:\(?\d{2,4}\)?[\s.\-]?)?\d{3,4}[\s.\-]?\d{3,4}[\s.\-]?\d{3,4}",
        phone_text,
    )
    if m:
        candidate = re.sub(r"[^\d+]", "", m.group(0))
        if 7 <= len(candidate) <= 16:
            personal["phone"] = m.group(0).strip()

    # URLs
    for url in re.findall(r"https?://[^\s<>\"\')]+|www\.[^\s<>\"\')]+", full_text):
        url = url.strip(".,;)\'\"")
        if "linkedin.com" in url and not personal["linkedin"]:
            personal["linkedin"] = url
        elif "github.com" in url and not personal["github"]:
            personal["github"] = url
        elif not personal["website"]:
            personal["website"] = url

    # Name heuristic — confident title-cased 2-4 word phrase near top
    NOISE = {"resume","cv","curriculum","vitae","email","phone","mobile","address",
             "contact","profile","summary","linkedin","github","portfolio","tel","fax"}
    TITLE_WORDS = {"engineer","developer","designer","manager","analyst","consultant",
                   "director","officer","specialist","coordinator","architect","lead",
                   "scientist","researcher","executive","associate","intern","registered",
                   "nurse","accountant","teacher","lecturer","administrator","technician",
                   "clinical","registered"}

    candidates: List[tuple] = []
    for idx, line in enumerate(lines[:12]):
        line = re.sub(r"^[^\w\s]+\s*", "", line.strip()).strip()  # strip emoji
        line = re.sub(r"[✉📞📧📱🏠🌍\U0001F300-\U0001FFFF]+", "", line).strip()
        if not line:
            continue
        words = line.split()
        if not (2 <= len(words) <= 5):
            continue
        if not (4 <= len(line) <= 55):
            continue
        if re.search(r"[@\d/\\|]", line):
            continue
        if any(n in line.lower() for n in NOISE):
            continue
        score = 0
        if all(w[0].isupper() for w in words if w and w[0].isalpha()):
            score += 3
        score += max(0, 8 - idx)
        if any(t in line.lower() for t in TITLE_WORDS):
            score -= 2
        if line.isupper():
            score -= 1
        candidates.append((score, line))

    if candidates:
        personal["full_name"] = max(candidates, key=lambda x: x[0])[1]

    # Job title — line containing professional keywords
    TITLE_KW = ["engineer","developer","designer","manager","analyst","consultant",
                "director","officer","specialist","coordinator","architect","lead",
                "scientist","executive","associate","intern","registered","nurse",
                "accountant","teacher","lecturer","administrator","technician","clinical"]
    for line in lines[:8]:
        stripped = re.sub(r"^[^\w\s]+\s*", "", line.strip()).strip()
        stripped = re.sub(r"[✉📞📧📱\U0001F300-\U0001FFFF]+", "", stripped).strip()
        if 5 < len(stripped) < 100:
            lower = stripped.lower()
            if any(kw in lower for kw in TITLE_KW):
                if not re.search(r"[@\d|]", stripped):
                    # Not the name
                    if stripped != personal["full_name"]:
                        personal["job_title"] = stripped
                        break

    # Location — look for "City, Country", "City County, Country" patterns
    # Use line-by-line scan to avoid grabbing the name or title
    for line in lines[:10]:
        stripped = re.sub(r"^[^\w\s]+\s*", "", line.strip()).strip()
        stripped = re.sub(r"[✉📞📧📱\U0001F300-\U0001FFFF|]+", "", stripped).strip()
        if not stripped or stripped == personal.get("full_name") or stripped == personal.get("job_title"):
            continue
        # Match "City, Country", "City County" or "City, Country"
        m = re.match(
            r"^([A-Z][a-zA-Z\s]{1,25}(?:County)?),?\s*([A-Z][a-zA-Z]{2,20})?$",
            stripped
        )
        if m and not re.search(r"[@\d/\\|]", stripped):
            candidate = stripped.strip()
            # Avoid short false positives that are just one word
            if len(candidate) > 4 and candidate != personal.get("full_name"):
                # Make sure it doesn't look like a name (2+ words both title-cased is OK for location too)
                words = candidate.split()
                # If it contains "County" or "Kenya" or known location words, it's a location
                LOC_SIGNALS = {"county","kenya","nairobi","mombasa","uganda","tanzania",
                               "ghana","nigeria","africa","city","district","province"}
                if any(w.lower() in LOC_SIGNALS for w in words):
                    personal["location"] = candidate
                    break
                # Otherwise only accept if it contains a comma (City, Country format)
                if "," in candidate:
                    personal["location"] = candidate
                    break

    return personal



class CVParser:
    """
    Flexible CV parser. Primary path: Gemini AI structured extraction.
    Fallback: dynamic section-aware heuristic engine that handles any
    CV structure, any section ordering, grouped skills with subtitles,
    and unknown sections.
    """

    def __init__(self):
        self._ai = None

    def _get_ai(self):
        if self._ai is None:
            from app.ai_service import AIService
            self._ai = AIService()
        return self._ai

    # ── Public entry point ──────────────────────────────────

    def parse(self, file_path: str, file_ext: str) -> Dict[str, Any]:
        ext = file_ext.lower().strip(".")
        if ext == "pdf":
            raw_text = self._read_pdf(file_path)
        elif ext == "docx":
            raw_text = self._read_docx(file_path)
        else:
            raise ValueError(f"Unsupported format: {ext}")

        if not raw_text or len(raw_text.strip()) < 40:
            logger.warning("Extracted text too short, returning empty result")
            return self._empty()

        # Try AI first, fall back to heuristics
        try:
            result = self._parse_ai(raw_text)
            if result:
                return result
        except Exception as e:
            logger.warning(f"AI parse failed, using heuristics: {e}")

        return self._parse_heuristic(raw_text)

    # ── Text Extractors ─────────────────────────────────────

    def _read_pdf(self, path: str) -> str:
        if not pypdf:
            raise ImportError("pypdf required for PDF parsing")
        chunks = []
        try:
            with open(path, "rb") as f:
                reader = pypdf.PdfReader(f)
                for page in reader.pages:
                    t = page.extract_text()
                    if t:
                        chunks.append(t)
            return re.sub(r"\n{3,}", "\n\n", "\n".join(chunks)).strip()
        except Exception as e:
            logger.error(f"PDF read error: {e}")
            return ""

    def _read_docx(self, path: str) -> str:
        """
        Style-aware DOCX reader. Uses paragraph styles (Heading 1/2, Title)
        to preserve document structure rather than treating everything as plain text.
        Multi-bullet paragraphs (newlines within one para) are split into separate lines.
        """
        if not DocxDocument:
            raise ImportError("python-docx required for DOCX parsing")
        try:
            doc = DocxDocument(path)
            parts = []

            for para in doc.paragraphs:
                text = para.text.strip()
                if not text:
                    parts.append("")  # preserve blank line as separator
                    continue

                style = para.style.name if para.style else "Normal"

                # Title style → name, always first
                if style == "Title":
                    parts.append("")
                    parts.append(text)
                    parts.append("")

                # Heading 1 → major section heading (blank lines around it)
                elif style.startswith("Heading 1") or style == "heading 1":
                    parts.append("")
                    parts.append(text)
                    parts.append("")

                # Heading 2 → sub-heading (job title, skill group name)
                elif style.startswith("Heading 2") or style == "heading 2":
                    parts.append("")
                    parts.append(text)

                # Heading 3+ → treat like sub-heading
                elif style.startswith("Heading"):
                    parts.append(text)

                # Normal text — may contain embedded newlines (multiple bullets in one para)
                else:
                    # Split on newlines within the paragraph
                    for line in text.split("\n"):
                        line = line.strip()
                        if line:
                            parts.append(line)

            # Tables
            for table in doc.tables:
                for row in table.rows:
                    cells = list(dict.fromkeys(
                        c.text.strip() for c in row.cells if c.text.strip()
                    ))
                    if cells:
                        parts.append(" | ".join(cells))

            # Collapse 3+ consecutive blank lines to 2
            result = re.sub(r"\n{3,}", "\n\n", "\n".join(parts))
            return result.strip()
        except Exception as e:
            logger.error(f"DOCX read error: {e}")
            return ""

    # ── AI Path ─────────────────────────────────────────────

    def _parse_ai(self, text: str) -> Optional[Dict[str, Any]]:
        ai = self._get_ai()
        if len(text) > 40_000:
            text = text[:40_000]

        prompt = f"""Extract ALL information from this CV into structured JSON.

CRITICAL INSTRUCTIONS:
1. Extract EVERY section present — skills with subtitles/groups, achievements,
   languages, interests, certifications, references, awards, volunteer work,
   publications, and any other sections
2. For skills with subtitles (like "Clinical Skills", "Digital Health"), preserve
   the group name in skill_groups
3. Work experience: capture job_title, company, location, start_date, end_date,
   and full description with bullet points
4. Return ONLY valid JSON, no markdown fences

JSON structure:
{{
  "personal_info": {{
    "full_name": "", "email": "", "phone": "", "location": "",
    "job_title": "", "linkedin": "", "portfolio": "", "github": "", "website": ""
  }},
  "professional_summary": "",
  "objective": "",
  "work_experience": [{{
    "job_title": "", "company": "", "location": "",
    "start_date": "", "end_date": "", "description": ""
  }}],
  "education": [{{
    "degree": "", "institution": "", "location": "", "year": "", "grade": ""
  }}],
  "skills": ["flat", "deduplicated", "list"],
  "skill_groups": [{{
    "group": "Group Name or null",
    "skills": ["skill1", "skill2"]
  }}],
  "certifications": ["cert1", "cert2"],
  "achievements": ["achievement1"],
  "languages": ["English (Fluent)", "Kiswahili"],
  "interests": ["interest1"],
  "references": "Available upon request or actual references",
  "volunteer": "",
  "publications": [],
  "awards": [],
  "extra_sections": {{}}
}}

CV TEXT:
{text}"""

        try:
            raw = ai._call(prompt, "cv_parse")
            if not raw:
                return None
            # Strip markdown fences if present
            clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
            data = json.loads(clean)
            if PYDANTIC_AVAILABLE:
                schema = CVOutputSchema(**data)
                return schema.model_dump_flat()
            return data
        except Exception as e:
            logger.error(f"AI parse JSON error: {e}")
            return None

    # ── Heuristic Path ──────────────────────────────────────

    def _parse_heuristic(self, text: str) -> Dict[str, Any]:
        sections = chunk_cv(text)
        header_lines = sections.get("_header", [])

        personal = parse_header(header_lines)

        # Summary / Objective
        summary = self._section_text(sections, "summary")
        objective = self._section_text(sections, "objective")

        # Work experience
        work = parse_work_experience(sections.get("experience", []))

        # Education
        education = parse_education(sections.get("education", []))

        # Skills with groups
        # Skill group subtitles (e.g. "Clinical Skills", "Professional Skills")
        # may have been extracted as separate sections by chunk_cv.
        # Merge them back into the skills section.
        SKILL_GROUP_SIGNALS = {
            "clinical skills", "technical skills", "soft skills", "hard skills",
            "professional skills", "core skills", "digital skills", "key skills",
            "public health", "public health & outreach", "digital health",
            "digital health & technology", "management skills", "personal skills",
            "leadership skills", "language skills", "computer skills", "it skills",
            "interpersonal skills", "communication skills", "analytical skills",
        }
        skill_lines = list(sections.get("skills", []))
        for sec_key, sec_lines in list(sections.items()):
            if sec_key in SKILL_GROUP_SIGNALS:
                # Re-insert the heading + its lines into skill_lines
                skill_lines.append("")
                skill_lines.append(sec_key.title())
                skill_lines.extend(sec_lines)

        skill_groups, flat_skills = parse_skill_groups(skill_lines)

        # List sections
        certifications = parse_list_section(sections.get("certifications", []))
        achievements = parse_list_section(sections.get("achievements", []))
        languages = parse_list_section(sections.get("languages", []))
        interests = parse_list_section(sections.get("interests", []))
        awards = parse_list_section(sections.get("awards", []))
        publications = parse_list_section(sections.get("publications", []))
        volunteer_text = self._section_text(sections, "volunteer")

        # References
        ref_lines = sections.get("references", [])
        references = " ".join(l.strip() for l in ref_lines if l.strip()) or None

        # Projects
        projects_lines = sections.get("projects", [])
        projects = self._parse_projects(projects_lines)

        # Extra/unknown sections — everything not in known canonical names
        known = {
            "_header","summary","objective","experience","education","skills",
            "certifications","achievements","languages","interests","references",
            "volunteer","publications","awards","projects",
        }
        extra_sections: Dict[str, str] = {}
        for key, lines in sections.items():
            if key not in known and lines:
                text_val = "\n".join(l for l in lines if l.strip()).strip()
                if text_val:
                    extra_sections[key] = text_val

        # Build output
        result = {
            "personal_info": personal if isinstance(personal, dict) else (personal.__dict__ if not PYDANTIC_AVAILABLE else personal.model_dump()),
            "professional_summary": summary,
            "objective": objective,
            "work_experience": [
                {
                    "job_title":  j.get("job_title","") if isinstance(j,dict) else (j.job_title or ""),
                    "company":    j.get("company","") if isinstance(j,dict) else (j.company or ""),
                    "location":   j.get("location","") if isinstance(j,dict) else (j.location or ""),
                    "start_date": j.get("start_date","") if isinstance(j,dict) else (j.start_date or ""),
                    "end_date":   j.get("end_date","Present") if isinstance(j,dict) else (j.end_date or "Present"),
                    "description":j.get("description","") if isinstance(j,dict) else (j.description or ""),
                    "achievements": j.get("achievements",[]) if isinstance(j,dict) else (j.achievements or []),
                }
                for j in work
            ],
            "education": [
                {
                    "degree":      e.get("degree","") if isinstance(e,dict) else (e.degree or ""),
                    "institution": e.get("institution","") if isinstance(e,dict) else (e.institution or ""),
                    "location":    e.get("location","") if isinstance(e,dict) else (e.location or ""),
                    "year":        e.get("year","") if isinstance(e,dict) else (e.year or ""),
                    "grade":       e.get("grade","") if isinstance(e,dict) else (e.grade or ""),
                }
                for e in education
            ],
            "skills": flat_skills,
            "skill_groups": [
                {"group": g.get("group") if isinstance(g,dict) else g.group,
                 "skills": g.get("skills",[]) if isinstance(g,dict) else g.skills}
                for g in skill_groups
            ],
            "certifications": certifications,
            "achievements": achievements,
            "languages": languages,
            "interests": interests,
            "awards": awards,
            "publications": publications,
            "volunteer": volunteer_text,
            "references": references,
            "projects": projects,
            "extra_sections": extra_sections,
        }
        return result

    def _section_text(self, sections: Dict, key: str) -> Optional[str]:
        lines = sections.get(key, [])
        text = "\n".join(l for l in lines if l.strip()).strip()
        return text or None

    def _parse_projects(self, lines: List[str]) -> List[Dict]:
        """Parse projects section into list of {name, description, url}."""
        if not lines:
            return []
        projects = []
        cur_name = None
        cur_desc = []
        cur_url = None

        for line in lines:
            stripped = line.strip()
            if not stripped:
                if cur_name:
                    projects.append({"name": cur_name, "description": "\n".join(cur_desc).strip(), "url": cur_url})
                    cur_name = cur_desc = None; cur_desc = []; cur_url = None
                continue
            url_m = re.search(r"https?://[^\s]+", stripped)
            if url_m:
                cur_url = url_m.group(0)
                continue
            bullet_m = re.match(r"^[·•\-\*–\u2022\u00b7]\s*(.+)", stripped)
            if bullet_m:
                cur_desc.append(bullet_m.group(1))
            elif not cur_name:
                cur_name = stripped
            else:
                cur_desc.append(stripped)

        if cur_name:
            projects.append({"name": cur_name, "description": "\n".join(cur_desc).strip(), "url": cur_url})

        return projects

    def _empty(self) -> Dict[str, Any]:
        return {
            "personal_info": {}, "professional_summary": None, "objective": None,
            "work_experience": [], "education": [], "skills": [], "skill_groups": [],
            "certifications": [], "achievements": [], "languages": [], "interests": [],
            "awards": [], "publications": [], "volunteer": None, "references": None,
            "projects": [], "extra_sections": {},
        }
