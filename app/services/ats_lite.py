"""CVForge AI - quick ATS-style check for the public free checker.

A fast, rule-based review of pasted CV text. It makes NO AI calls, so it costs
nothing per use and cannot burn the Gemini quota. It checks formatting and
content signals that screening software and recruiters commonly rely on.
It is NOT a prediction of how any employer's system will rank a CV, and the
page says so.

Pure Python (no Flask) so it can be unit-tested anywhere.

Score (100): contact 15 + sections 20 + length 10 + numbers 20 + style 20 + dates 15.
Optional job-description keyword match is reported separately.
"""
import re
from collections import Counter

MIN_CV_CHARS = 150
MAX_CV_CHARS = 25000
MAX_JD_CHARS = 15000

_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_YEAR = r"(?:19|20)\d{2}"

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<!\w)\+?\(?\d[\d\s().\-]{7,}\d(?!\w)")
LINK_RE = re.compile(r"(?i)linkedin\.com|github\.com|gitlab\.com|behance\.net|portfolio|https?://|www\.")
BULLET_RE = re.compile(r"^\s*(?:[\-\u2022\u2023\u25CF\u25AA\u25E6\u2013\u00B7\*]|\d{1,2}[.)])\s+")
DATE_RANGE_RE = re.compile(
    rf"(?i)(?:{_MONTH}\s+)?{_YEAR}\s*(?:-|\u2013|\u2014|to|until)\s*(?:present|current|now|(?:{_MONTH}\s+)?{_YEAR})")
MONTH_YEAR_RE = re.compile(rf"(?i)\b{_MONTH}\s+{_YEAR}\b")
NUMERIC_DATE_RE = re.compile(rf"\b(?:0?[1-9]|1[0-2])[/.\-]{_YEAR}\b")
YEAR_RE = re.compile(rf"\b{_YEAR}\b")
NUMBER_RE = re.compile(r"(?<![\w/])\d+(?:[.,]\d+)*%?(?![\w/])")
FIRST_PERSON_RE = re.compile(r"\b(?:I|I'm|I've|I'll|my|me)\b", re.I)

SECTIONS = {
    "summary": ("summary", "professional summary", "profile", "personal profile", "career objective",
                "objective", "about me", "personal statement", "career summary"),
    "experience": ("experience", "work experience", "professional experience", "employment history",
                   "work history", "employment", "career history", "relevant experience"),
    "education": ("education", "education and training", "academic background", "qualifications",
                  "academic qualifications", "education and qualifications"),
    "skills": ("skills", "key skills", "core skills", "technical skills", "skills and competencies",
               "core competencies", "competencies", "skills summary"),
}
SECTION_LABELS = {"summary": "Summary or profile", "experience": "Work experience",
                  "education": "Education", "skills": "Skills"}
SECTION_POINTS = {"summary": 3, "experience": 7, "education": 5, "skills": 5}

ACTION_VERBS = frozenset("""
achieved administered analysed analyzed arranged assembled assisted audited authored automated balanced
budgeted built calculated coached collaborated compiled completed conducted configured consolidated
coordinated created cut debugged decreased defined delivered deployed designed developed directed
documented drafted drove earned edited enabled engineered established evaluated exceeded executed expanded
facilitated forecasted founded generated guided handled headed identified implemented improved increased
initiated installed integrated introduced investigated launched led maintained managed mentored migrated
modernised modernized monitored negotiated onboarded operated optimised optimized organised organized
oversaw owned partnered performed piloted planned prepared presented prioritised prioritized processed
produced programmed promoted proposed provided published raised reconciled recruited redesigned reduced
refined reorganised reorganized replaced reported researched resolved restructured reviewed revised
scheduled secured selected served shipped simplified sold solved sourced spearheaded standardised
standardized streamlined strengthened supervised supported tested tracked trained transformed translated
tripled troubleshot updated upgraded utilised utilized validated verified wrote won
""".split())
NOT_VERBS = frozenset(("based", "skilled", "experienced", "detailed", "motivated", "dedicated", "qualified",
                       "talented", "committed", "certified", "seasoned", "accomplished", "organized-minded"))
WEAK_PHRASES = ("responsible for", "duties included", "duties include", "worked on", "helped with",
                "tasked with", "in charge of")
CLICHES = ("team player", "hard worker", "hard-working", "self-motivated", "go-getter", "think outside the box",
           "references available upon request", "references available on request")

STOPWORDS = frozenset("""
a about above after again all also am an and any are as at be because been before being below between both
but by can could did do does doing down during each few for from further had has have having he her here
hers him his how i if in into is it its just me more most my no nor not of off on once only or other our
out over own same she should so some such than that the their them then there these they this those through
to too under until up very was we were what when where which while who whom why will with would you your
""".split())
JD_FLUFF = frozenset("""
ability able across additional applicants applicant apply based benefits candidate candidates company
competitive complete day demonstrated desired detail duties environment equal excellent experience
experienced expected familiarity fast good great help including include includes job join knowledge
looking must need needed new opportunity paced part passion plus position preferred prior proven
qualifications required requirements responsibilities responsible role seeking skills solid strong team
teams time understanding united us using want well within work working year years hiring hire hired
write writes writing
""".split())

_SUFFIXES = ("ments", "ment", "ings", "ing", "ers", "er", "ies", "ied", "ions", "ion", "ed", "es", "ly", "s")


def clean_text(raw):
    """Normalise newlines, drop control characters, collapse long blank runs."""
    text = (raw or "").replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    return re.sub(r"\n{4,}", "\n\n\n", text).strip()


def validate_inputs(cv_text, jd_text=""):
    """Return an error message, or None when the inputs are acceptable."""
    if len(cv_text) < MIN_CV_CHARS:
        return "Paste more of your CV so we can check it properly (at least a short paragraph or two)."
    if len(cv_text) > MAX_CV_CHARS:
        return f"That CV is too long to check here (limit {MAX_CV_CHARS:,} characters)."
    if len(jd_text) > MAX_JD_CHARS:
        return f"The job description is too long (limit {MAX_JD_CHARS:,} characters)."
    return None


def _norm_heading(line):
    s = re.sub(r"[^A-Za-z& ]+", " ", line).lower().replace("&", " and ")
    return re.sub(r"\s+", " ", s).strip()


def _looks_like_phone(candidate):
    groups = re.findall(r"\d+", candidate)
    if sum(len(g) for g in groups) < 9:
        return False
    # A run of years such as "2019 2020 2021" is not a phone number.
    return not all(len(g) == 4 and g[:2] in ("19", "20") for g in groups)


def _find_sections(lines):
    found = {}
    for idx, line in enumerate(lines):
        if not line.strip() or len(line.strip()) > 40:
            continue
        norm = _norm_heading(line)
        for key, names in SECTIONS.items():
            if norm in names and key not in found:
                found[key] = idx
    return found


def _root(token):
    t = token
    for suf in _SUFFIXES:
        if t.endswith(suf) and len(t) - len(suf) >= 4:
            t = t[:-len(suf)]
            break
    if len(t) > 4 and t.endswith("e"):
        t = t[:-1]
    return t


def _tokens(text):
    out = []
    for tok in re.findall(r"[A-Za-z][A-Za-z0-9+#./\-]*", text.lower()):
        tok = tok.strip(".-/")
        if len(tok) >= 2:
            out.append(tok)
    return out


def keyword_match(cv_text, jd_text, top_n=20):
    """Compare the top job-description terms with the CV. None if the JD has too little text."""
    jd_tokens = [t for t in _tokens(jd_text) if t not in STOPWORDS and t not in JD_FLUFF and not t.isdigit()]
    if len(jd_tokens) < 8:
        return None
    counts = Counter(jd_tokens)
    first_seen = {}
    for i, t in enumerate(jd_tokens):
        first_seen.setdefault(t, i)
    ranked = sorted(counts, key=lambda t: (-counts[t], first_seen[t]))[:top_n]
    cv_roots = {_root(t) for t in _tokens(cv_text)}
    cv_exact = set(_tokens(cv_text))
    matched = [t for t in ranked if t in cv_exact or _root(t) in cv_roots]
    missing = [t for t in ranked if t not in matched]
    return {"total": len(ranked), "matched": matched, "missing": missing,
            "percent": round(100 * len(matched) / len(ranked))}


def _issue(key, category, lost, title, fix):
    severity = "high" if lost >= 6 else "medium" if lost >= 3 else "low"
    return {"key": key, "category": category, "lost": lost, "severity": severity, "title": title, "fix": fix}


def analyse(cv_text, jd_text=""):
    text = clean_text(cv_text)
    lines = [ln.rstrip() for ln in text.split("\n")]
    nonblank = [ln for ln in lines if ln.strip()]
    words = text.split()
    issues, strengths, cats = [], [], []

    # 1) Contact (15)
    has_email = bool(EMAIL_RE.search(text))
    phone_ok = any(_looks_like_phone(m.group()) for m in PHONE_RE.finditer(text))
    has_link = bool(LINK_RE.search(text))
    contact = (7 if has_email else 0) + (5 if phone_ok else 0) + (3 if has_link else 0)
    if not has_email:
        issues.append(_issue("email", "Contact details", 7, "No email address found",
                             "Add a professional email address near the top. Employers and screening tools look for it first."))
    if not phone_ok:
        issues.append(_issue("phone", "Contact details", 5, "No phone number found",
                             "Add a phone number with your country code so recruiters can reach you quickly."))
    if not has_link:
        issues.append(_issue("link", "Contact details", 3, "No LinkedIn or portfolio link found",
                             "Add your LinkedIn profile or a portfolio link if you have one."))
    if contact == 15:
        strengths.append("Your email, phone and a profile link are all easy to find.")
    cats.append(("contact", "Contact details", contact, 15,
                 "Email, phone and a profile link"))

    # 2) Sections (20)
    found = _find_sections(lines)
    sec_score = sum(SECTION_POINTS[k] for k in found)
    for key in ("experience", "education", "skills", "summary"):
        if key not in found:
            lost = SECTION_POINTS[key]
            issues.append(_issue(f"section_{key}", "Structure", lost, f"No clear \"{SECTION_LABELS[key]}\" heading",
                                 f"Add a plain heading such as \"{SECTIONS[key][1].title()}\". Screening software uses standard headings to sort your information."))
    if len(found) == 4:
        strengths.append("All the standard section headings are present.")
    cats.append(("sections", "Section headings", sec_score, 20, "Summary, experience, education and skills"))

    # 3) Length (10)
    wc = len(words)
    if wc < 150:
        length, lmsg = 3, "Very short"
        issues.append(_issue("length", "Length", 7, f"Your CV is very short ({wc} words)",
                             "Aim for roughly 300 to 900 words. Add detail about what you did and what resulted."))
    elif wc < 300:
        length, lmsg = 6, "A little short"
        issues.append(_issue("length", "Length", 4, f"Your CV is a little short ({wc} words)",
                             "Add more detail to your experience, such as tasks, tools and results."))
    elif wc <= 900:
        length, lmsg = 10, "Good length"
        strengths.append(f"Good length ({wc} words), which fits one or two pages.")
    elif wc <= 1300:
        length, lmsg = 6, "A little long"
        issues.append(_issue("length", "Length", 4, f"Your CV is a little long ({wc} words)",
                             "Trim older or less relevant roles. Most CVs work best at one or two pages."))
    else:
        length, lmsg = 3, "Too long"
        issues.append(_issue("length", "Length", 7, f"Your CV is very long ({wc} words)",
                             "Cut it down to the most relevant roles and results. Long CVs are rarely read in full."))
    cats.append(("length", "Length", length, 10, lmsg))

    # 4) Numbers and results (20)
    stripped = EMAIL_RE.sub(" ", text)
    stripped = PHONE_RE.sub(" ", stripped)
    stripped = DATE_RANGE_RE.sub(" ", stripped)
    stripped = YEAR_RE.sub(" ", stripped)
    numbers = len(NUMBER_RE.findall(stripped))
    num_score = min(20, round(numbers * 2.5))
    if num_score < 20:
        lost = 20 - num_score
        issues.append(_issue("numbers", "Results", lost, f"Only {numbers} number{'s' if numbers != 1 else ''} found to show results",
                             "Add real figures where you can: how many customers or projects, how much time or money you saved, or how much something grew."))
    else:
        strengths.append("You back up your work with numbers.")
    cats.append(("numbers", "Numbers and results", num_score, 20, f"{numbers} figures found"))

    # 5) Writing style (20)
    bullets = [BULLET_RE.sub("", ln).strip() for ln in lines if BULLET_RE.match(ln)]
    if len(bullets) >= 3:
        cand = bullets
    else:
        start = found.get("experience", 0)
        cand = [BULLET_RE.sub("", ln).strip() for ln in lines[start:] if len(ln.split()) >= 6]
    verb_hits = 0
    for ln in cand:
        first = re.sub(r"[^a-z]", "", (ln.split() or [""])[0].lower())
        if first in ACTION_VERBS or (first.endswith("ed") and len(first) > 4 and first not in NOT_VERBS):
            verb_hits += 1
    ratio = verb_hits / len(cand) if cand else 0
    b_score = 6 if len(bullets) >= 5 else 3 if len(bullets) >= 1 else 0
    v_score = round(8 * min(1, ratio / 0.6))
    fp = len(FIRST_PERSON_RE.findall(text))
    fp_score = 3 if fp <= 1 else 1 if fp <= 4 else 0
    low = text.lower()
    weak = sum(low.count(p) for p in WEAK_PHRASES) + sum(low.count(p) for p in CLICHES)
    w_score = 3 if weak == 0 else 1 if weak <= 2 else 0
    style = b_score + v_score + fp_score + w_score
    if b_score < 6:
        issues.append(_issue("bullets", "Writing style", 6 - b_score, "Use bullet points for your achievements",
                             "Put each achievement on its own bullet line, starting with a strong verb. Bullets are easier for people and software to read."))
    if v_score < 8:
        issues.append(_issue("verbs", "Writing style", 8 - v_score, "Start more lines with strong action verbs",
                             "Begin each bullet with a verb such as Led, Built, Reduced or Managed, instead of phrases like \"responsible for\"."))
    if fp_score < 3:
        issues.append(_issue("first_person", "Writing style", 3 - fp_score, "Avoid \"I\" and \"my\" in your CV",
                             "Write in short, direct phrases without first-person words, for example \"Managed a team of 5\"."))
    if w_score < 3:
        issues.append(_issue("weak", "Writing style", 3 - w_score, "Replace weak phrases and clichés",
                             "Swap \"responsible for\", \"worked on\" and clichés like \"team player\" for specific actions and results."))
    if style >= 18:
        strengths.append("Your writing is direct and uses strong action verbs.")
    cats.append(("style", "Writing style", style, 20, f"{len(bullets)} bullet lines, {round(ratio * 100)}% start with action verbs"))

    # 6) Dates (15)
    ranges = len(DATE_RANGE_RE.findall(text))
    d_score = min(10, round(ranges * 3.4))
    has_named = bool(MONTH_YEAR_RE.search(text))
    has_numeric = bool(NUMERIC_DATE_RE.search(text))
    mixed = has_named and has_numeric
    c_score = 0 if (ranges == 0 and not has_named and not has_numeric) else (2 if mixed else 5)
    dates = d_score + c_score
    if d_score < 10:
        issues.append(_issue("dates", "Dates", 10 - d_score, "Add start and end dates to your roles",
                             "Show dates for each job or course, for example \"2021 to present\", so your timeline is clear."))
    if c_score < 5:
        issues.append(_issue("date_format", "Dates", 5 - c_score,
                             "Mixed date formats" if mixed else "Dates are hard to find",
                             "Use one date style throughout, such as \"Mar 2021 to Jun 2023\"." if mixed else
                             "Use a clear date style throughout, such as \"Mar 2021 to Jun 2023\"."))
    if dates == 15:
        strengths.append("Your dates are present and consistent.")
    cats.append(("dates", "Dates", dates, 15, f"{ranges} date range{'s' if ranges != 1 else ''} found"))

    score = contact + sec_score + length + num_score + style + dates
    if score >= 80:
        band, note = "Strong", "Well structured, with only small fixes left."
    elif score >= 60:
        band, note = "Good, with fixes to make", "A solid base. The fixes below will lift it."
    elif score >= 40:
        band, note = "Needs work", "Several important things are missing or unclear."
    else:
        band, note = "Early draft", "It needs structure and detail before you send it out."

    issues.sort(key=lambda i: -i["lost"])
    return {
        "score": score, "band": band, "band_note": note,
        "categories": [{"key": k, "label": lab, "score": s, "max": m, "note": n} for k, lab, s, m, n in cats],
        "issues": issues, "strengths": strengths[:3],
        "stats": {"words": wc, "bullets": len(bullets), "numbers": numbers, "date_ranges": ranges},
        "keywords": keyword_match(text, clean_text(jd_text)) if (jd_text or "").strip() else None,
    }
