"""
CVForge section intelligence.

Three jobs:
  1. audit_resume()      - find what is missing or weak, ranked by how much it matters.
  2. next_questions()    - pick at most 3 questions to ask the user (the "cornered" path).
  3. draft_prompt()      - ask the model to draft a section ONLY from facts supplied,
                           and to return questions instead of inventing anything.
Plus apply_section() and build_revamp_payload(), which replace the narrow
summary/work/skills whitelist in cv.revamp and ai_service.revamp_resume.

No Flask imports here, so it is unit-testable on its own.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any

# --------------------------------------------------------------------------
# Section catalogue
# --------------------------------------------------------------------------
# kind: "list_dict" | "list_str" | "text" | "refs"
SECTIONS: dict[str, dict[str, Any]] = {
    "personal_info": {"label": "Contact details", "kind": "dict", "required": True},
    "professional_summary": {"label": "Professional summary", "kind": "text", "required": True},
    "work_experience": {"label": "Work experience", "kind": "list_dict", "required": True},
    "education": {"label": "Education", "kind": "list_dict", "required": True},
    "skills": {"label": "Skills", "kind": "list_str", "required": True},
    "projects": {"label": "Projects", "kind": "list_dict", "required": False},
    "certifications": {"label": "Certifications and licences", "kind": "list_str", "required": False},
    "languages": {"label": "Languages", "kind": "list_str", "required": False},
    "awards": {"label": "Awards and honours", "kind": "list_str", "required": False},
    "references": {"label": "References", "kind": "refs", "required": False},
}

# Each question is written to be answered in one line by a non-expert.
QUESTIONS: dict[str, str] = {
    "professional_summary": "In two or three sentences: what do you do, how long have you done it, and what are you best at?",
    "work_experience": "Tell me about your most recent job: title, company, dates, and the 2 or 3 things you were proudest of. Numbers help a lot (money saved, people managed, customers served, % growth).",
    "education": "What is your highest qualification, the institution, and the year you finished?",
    "skills": "List the tools, software and abilities you use most at work (for example: Excel, Python, customer service, M-Pesa reconciliation).",
    "projects": "Have you built or led anything outside a job: a side project, freelance client work, a school or community project, or an app? Give me the name, what it does, your role, and a link if there is one.",
    "certifications": "Any certificates, licences or short courses you finished? Include the issuer and year if you have them.",
    "languages": "Which languages do you speak, and how well (native, fluent, conversational, basic)?",
    "awards": "Any awards, scholarships, competitions or recognitions? Include the year.",
    "references": "Do you want to list referees, or is 'Available on request' fine? If you list people, I need their name, job title, company and contact.",
}

# Rough weight for how much each missing section hurts a CV.
# Priority is then adjusted by role context (e.g. projects matter more for early-career/tech).
BASE_WEIGHT = {
    "personal_info": 100, "professional_summary": 80, "work_experience": 95,
    "education": 70, "skills": 75, "projects": 45, "certifications": 40,
    "languages": 35, "awards": 25, "references": 15,
}

NUMBER_RE = re.compile(r"\d")


@dataclass
class Gap:
    key: str
    label: str
    status: str            # "missing" | "weak"
    priority: str          # "high" | "medium" | "low"
    question: str
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict)):
        return len(value) == 0
    return False


def _jobs(data: dict) -> list[dict]:
    return [j for j in (data.get("work_experience") or []) if isinstance(j, dict)]


def _career_stage(data: dict) -> str:
    """Rough read of career stage, used only to weight priorities."""
    jobs = _jobs(data)
    if len(jobs) == 0:
        return "early"           # students, graduates, career changers
    if len(jobs) <= 2:
        return "early"
    return "experienced"


def _bullet_count_with_numbers(data: dict) -> tuple[int, int]:
    total, with_num = 0, 0
    for job in _jobs(data):
        for b in job.get("achievements") or []:
            if isinstance(b, str) and b.strip():
                total += 1
                if NUMBER_RE.search(b):
                    with_num += 1
    return total, with_num


def _priority(key: str, stage: str) -> str:
    weight = BASE_WEIGHT.get(key, 20)
    if key == "projects" and stage == "early":
        weight += 40            # projects carry early-career candidates
    if key == "projects" and stage == "experienced":
        weight -= 15
    if key == "certifications" and stage == "early":
        weight += 15
    if weight >= 70:
        return "high"
    if weight >= 40:
        return "medium"
    return "low"


# --------------------------------------------------------------------------
# 1. Audit
# --------------------------------------------------------------------------
def audit_resume(data: dict) -> list[Gap]:
    """Return every missing or weak section, highest priority first.

    `data` is Resume.to_dict(). Works on any resume, including ones parsed from
    an upload, so the same check runs whether the user built the CV or uploaded it.
    """
    stage = _career_stage(data)
    gaps: list[Gap] = []

    def add(key: str, status: str, detail: str = "") -> None:
        gaps.append(Gap(
            key=key,
            label=SECTIONS[key]["label"],
            status=status,
            priority=_priority(key, stage),
            question=QUESTIONS[key],
            detail=detail,
        ))

    pi = data.get("personal_info") or {}
    if not (pi.get("email") or pi.get("phone")):
        gaps.append(Gap("personal_info", "Contact details", "missing", "high",
                        "What email and phone number should recruiters use?",
                        "No email or phone found."))

    summary = (data.get("professional_summary") or "").strip()
    if not summary:
        add("professional_summary", "missing")
    elif len(summary) < 80:
        add("professional_summary", "weak", "Summary is very short.")

    if not _jobs(data):
        add("work_experience", "missing")
    else:
        total, with_num = _bullet_count_with_numbers(data)
        if total and with_num / total < 0.3:
            add("work_experience", "weak",
                f"Only {with_num} of {total} bullets contain a number.")

    if _is_empty(data.get("education")):
        add("education", "missing")
    if _is_empty(data.get("skills")) and not (data.get("custom_sections") or {}).get("skill_groups"):
        add("skills", "missing")
    if _is_empty(data.get("projects")):
        add("projects", "missing")
    if _is_empty(data.get("certifications")):
        add("certifications", "missing")
    if _is_empty(data.get("languages")):
        add("languages", "missing")
    if _is_empty(data.get("awards")):
        add("awards", "missing")
    if _is_empty(data.get("references")):
        add("references", "missing",
            "A CV with no references line needs 'Available on request' at minimum.")

    rank = {"high": 0, "medium": 1, "low": 2}
    gaps.sort(key=lambda g: (rank[g.priority], g.status != "missing"))
    return gaps


# --------------------------------------------------------------------------
# 2. Ask the user (the "cornered" path)
# --------------------------------------------------------------------------
def next_questions(gaps: list[Gap], limit: int = 3) -> list[dict]:
    """At most `limit` questions, so the user is never buried.

    Only high and medium gaps become questions. Low-priority gaps are offered
    as optional at the end of the flow.
    """
    chosen = [g for g in gaps if g.priority in ("high", "medium")][:limit]
    return [{"key": g.key, "label": g.label, "question": g.question, "why": g.detail or ""}
            for g in chosen]


# --------------------------------------------------------------------------
# 3. Drafting with a "ask instead of invent" rule
# --------------------------------------------------------------------------
DRAFT_SYSTEM = """You help job seekers worldwide write CV sections.

RULES
1. Use ONLY facts present in the input. Never invent employers, dates, tools,
   certifications, projects, awards, numbers or references.
2. If the input is not enough to write a strong section, do NOT guess. Return
   "needs_input" with up to 3 specific questions instead.
3. Where a metric would make a bullet stronger and is not given, write a bracketed
   placeholder such as [X%] or [N people], and add a question asking for it.
4. Keep bullets to one sentence, at most 25 words, starting with an action verb.
5. Output ONLY JSON, no preamble, no markdown fences.

OUTPUT SHAPE
{"status": "ready" | "needs_input",
 "items": [...],            // section content, same shape as the target section
 "questions": [string],     // only when status is needs_input
 "notes": string            // one line on what you changed or assumed
}"""


def draft_prompt(section_key: str, data: dict, user_answer: str = "") -> str:
    """Build the user-facing prompt for drafting one section.

    `user_answer` is the free-text answer the user gave to the question for this
    section. If empty, the model is told to ask rather than write.
    """
    if section_key not in SECTIONS:
        raise ValueError(f"Unknown section: {section_key}")
    context = {
        "target_section": section_key,
        "target_label": SECTIONS[section_key]["label"],
        "existing_data": {
            k: data.get(k) for k in (
                "personal_info", "professional_summary", "work_experience",
                "education", "skills", "projects", "certifications", "languages",
                "awards", "references",
            ) if data.get(k)
        },
        "user_answer": user_answer.strip(),
    }
    return (
        "Draft the target section using the context below.\n"
        "If user_answer is empty and existing_data does not contain enough to write "
        "this section well, return status needs_input with questions.\n\n"
        "<context>\n" + json.dumps(context, indent=2, ensure_ascii=False) + "\n</context>"
    )


def parse_draft(raw: str) -> dict:
    """Parse and validate the model's draft. Raises ValueError if unusable."""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    out = json.loads(text)
    if not isinstance(out, dict):
        raise ValueError("Draft is not a JSON object.")
    status = out.get("status")
    if status not in ("ready", "needs_input"):
        raise ValueError("Draft has an invalid status.")
    if status == "needs_input":
        qs = [q for q in (out.get("questions") or []) if isinstance(q, str) and q.strip()]
        if not qs:
            raise ValueError("needs_input without questions.")
        out["questions"] = qs[:3]
    return out


# --------------------------------------------------------------------------
# 4. Safe write-back (whitelist, with type checks)
# --------------------------------------------------------------------------
def _clean_str_list(items: Any, max_len: int = 200, max_items: int = 50) -> list[str]:
    if not isinstance(items, list):
        return []
    out = []
    for i in items:
        if isinstance(i, str) and i.strip():
            out.append(i.strip()[:max_len])
    return out[:max_items]


def _clean_projects(items: Any) -> list[dict]:
    if not isinstance(items, list):
        return []
    out = []
    for p in items:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name") or "").strip()[:150]
        if not name:
            continue
        out.append({
            "name": name,
            "role": str(p.get("role") or "").strip()[:150],
            "description": str(p.get("description") or "").strip()[:600],
            "url": str(p.get("url") or "").strip()[:300],
        })
    return out[:10]


def _clean_references(value: Any) -> list[dict] | str | None:
    if isinstance(value, str):
        v = value.strip()
        return v[:300] or None   # e.g. "Available on request"
    if isinstance(value, list):
        out = []
        for r in value:
            if isinstance(r, dict) and str(r.get("name") or "").strip():
                out.append({
                    "name": str(r["name"]).strip()[:120],
                    "title": str(r.get("title") or "").strip()[:150],
                    "company": str(r.get("company") or "").strip()[:150],
                    "phone": str(r.get("phone") or "").strip()[:40],
                    "email": str(r.get("email") or "").strip()[:120],
                })
        return out[:4] or None
    return None


def apply_section(resume: Any, key: str, items: Any) -> bool:
    """Write a validated section onto the Resume model. Returns True if written.

    Only whitelisted keys are accepted, so arbitrary model output can never
    touch other columns.
    """
    if key == "projects":
        cleaned = _clean_projects(items)
        if cleaned:
            resume.projects = cleaned
            return True
    elif key == "languages":
        cleaned = _clean_str_list(items)
        if cleaned:
            resume.languages = cleaned
            return True
    elif key == "awards":
        cleaned = _clean_str_list(items)
        if cleaned:
            resume.awards = cleaned
            return True
    elif key == "certifications":
        cleaned = _clean_str_list(items)
        if cleaned:
            resume.certifications = cleaned
            return True
    elif key == "references":
        cleaned = _clean_references(items)
        if cleaned:
            resume.references = cleaned
            return True
    return False


# --------------------------------------------------------------------------
# 5. Revamp scope: everything the AI may polish, nothing it may invent
# --------------------------------------------------------------------------
REVAMP_KEYS = ("professional_summary", "work_experience", "skills", "projects", "awards")


def build_revamp_payload(data: dict) -> dict:
    """Send the AI every section it may polish, not just three.

    Projects and awards are included so they get rewritten too, and
    references and personal details are left out on purpose.
    """
    payload = {k: data.get(k) or ([] if k != "professional_summary" else "") for k in REVAMP_KEYS}
    payload["skill_groups"] = (data.get("custom_sections") or {}).get("skill_groups") or []
    return payload
