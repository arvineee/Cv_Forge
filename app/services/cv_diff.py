"""
Human-readable differences between two CV snapshots (ResumeVersion.snapshot).

Used by the version history page so users can see exactly what an AI revamp
changed before they accept it. Pure functions, no Flask or database access.
"""
import difflib
from typing import Any, Dict, List


def _words_diff(old: str, new: str) -> List[Dict[str, str]]:
    """Word-level diff: returns segments of {op, text} where op is equal|insert|delete."""
    a, b = (old or "").split(), (new or "").split()
    segments: List[Dict[str, str]] = []
    matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            segments.append({"op": "equal", "text": " ".join(a[i1:i2])})
        else:
            if i2 > i1:
                segments.append({"op": "delete", "text": " ".join(a[i1:i2])})
            if j2 > j1:
                segments.append({"op": "insert", "text": " ".join(b[j1:j2])})
    return [s for s in segments if s["text"]]


def _bullet_diff(old: List[str], new: List[str]) -> List[Dict[str, str]]:
    """Line-level diff of bullet lists. Each item: {op: equal|insert|delete, text}."""
    old, new = [str(x) for x in old or []], [str(x) for x in new or []]
    out: List[Dict[str, str]] = []
    matcher = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            out += [{"op": "equal", "text": t} for t in old[i1:i2]]
        else:
            out += [{"op": "delete", "text": t} for t in old[i1:i2]]
            out += [{"op": "insert", "text": t} for t in new[j1:j2]]
    return out


def _jobs(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    jobs = snapshot.get("work_experience") or []
    return [j for j in jobs if isinstance(j, dict)]


def _flat_skills(snapshot: Dict[str, Any]) -> List[str]:
    groups = (snapshot.get("custom_sections") or {}).get("skill_groups") or []
    names: List[str] = []
    for g in groups:
        if isinstance(g, dict):
            names += [str(s) for s in g.get("skills") or []]
    names += [str(s) for s in snapshot.get("skills") or []]
    seen, unique = set(), []
    for n in names:
        key = n.strip().lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(n.strip())
    return unique


def diff_snapshots(old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compare two snapshots. Returns:
      {
        "summary": [segments] or None if unchanged,
        "jobs": [{"title": str, "company": str, "bullets": [items]}] for changed jobs,
        "skills": {"added": [...], "removed": [...]},
        "changed": bool,
      }
    """
    old, new = old or {}, new or {}

    summary_old = old.get("professional_summary") or ""
    summary_new = new.get("professional_summary") or ""
    summary = _words_diff(summary_old, summary_new) if summary_old != summary_new else None

    jobs_changed = []
    old_jobs, new_jobs = _jobs(old), _jobs(new)
    for i in range(max(len(old_jobs), len(new_jobs))):
        o = old_jobs[i] if i < len(old_jobs) else {}
        n = new_jobs[i] if i < len(new_jobs) else {}
        bullets = _bullet_diff(o.get("achievements"), n.get("achievements"))
        if any(item["op"] != "equal" for item in bullets):
            jobs_changed.append({
                "title": n.get("job_title") or o.get("job_title") or "Role",
                "company": n.get("company") or o.get("company") or "",
                "bullets": bullets,
            })

    old_sk, new_sk = _flat_skills(old), _flat_skills(new)
    old_set = {s.lower() for s in old_sk}
    new_set = {s.lower() for s in new_sk}
    skills = {
        "added": [s for s in new_sk if s.lower() not in old_set],
        "removed": [s for s in old_sk if s.lower() not in new_set],
    }

    changed = bool(summary) or bool(jobs_changed) or bool(skills["added"]) or bool(skills["removed"])
    return {"summary": summary, "jobs": jobs_changed, "skills": skills, "changed": changed}
