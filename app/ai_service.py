"""
CVForge AI - AI Service (Gemini)

Fixes applied in this pass:
- Every public method now accepts and forwards user_id to _call(). Before,
  _call()'s caching/usage-logging block only ran when user_id was passed,
  but NO caller ever passed it — so the whole AIUsage cache was dead code
  and every "repeat" AI request re-hit Gemini at full cost.
- revamp_resume() now asks for the SAME work_experience shape the rest of
  the app uses (job_title + achievements[]), instead of an unconstrained
  "array of improved job objects" that the model was free to flatten into
  vague prose. This is what was gutting real bullet points during Revamp.
- estimate_salary()'s JSON cleanup used str.strip("```json") which strips
  a *character set*, not the substring — it could silently mangle valid
  JSON. Replaced with the same split("```") pattern the other two JSON
  methods already use correctly.
- ats_check() now accepts an optional resume_text override so it can run
  directly off freshly-uploaded/parsed CV text without requiring a saved
  Resume row (used by the new "upload & check" ATS flow).
"""
import hashlib
import json
from flask import current_app, g


def get_ai_service():
    """Return a per-request cached AIService instance via flask.g."""
    if "ai_service" not in g:
        g.ai_service = AIService()
    return g.ai_service


def _clean_json_fence(raw: str) -> str:
    """
    Strip a ```json ... ``` or ``` ... ``` fence from a model response.
    Uses split("```"), NOT str.strip("```json") — strip() treats its
    argument as a set of characters to remove, not a substring, and will
    silently eat legitimate leading/trailing characters from valid JSON.
    """
    clean = raw.strip()
    if clean.startswith("```"):
        parts = clean.split("```")
        clean = parts[1] if len(parts) > 1 else clean
        if clean.startswith("json"):
            clean = clean[4:]
    return clean.strip()


class AIService:
    # NOTE: verify this is a real, currently-available model id for your
    # google-generativeai SDK version before deploying — model names change
    # and this fallback should match config.py's GEMINI_MODEL default.
    MODEL = "gemini-3.1-flash-lite"

    def __init__(self):
        self.api_key = current_app.config.get("GEMINI_API_KEY", "")
        self.model_name = current_app.config.get("GEMINI_MODEL", self.MODEL)
        self._model = None

    def _get_model(self):
        if self._model is None:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._model = genai.GenerativeModel(self.model_name)
        return self._model

    def _call(self, prompt: str, feature: str = "general", user_id: int = None,
              *, system_instruction: str = None, config: dict = None,
              context_tag: str = None) -> str:
        import google.generativeai as genai
        from app.models import db, AIUsage

        if context_tag and feature == "general":
            feature = context_tag

        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()

        if user_id:
            cached = AIUsage.find_cached(prompt_hash, feature)
            if cached and cached.cached_response:
                current_app.logger.info(f"AI cache hit: {feature}")
                return cached.cached_response

        if system_instruction:
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(self.model_name, system_instruction=system_instruction)
        else:
            model = self._get_model()

        if config:
            response = model.generate_content(prompt, generation_config=config)
        else:
            response = model.generate_content(prompt)

        result = response.text

        if user_id:
            usage = AIUsage(
                user_id=user_id,
                feature=feature,
                prompt_hash=prompt_hash,
                cached_response=result,
                requests_used=1,
            )
            db.session.add(usage)

        return result

    def assist_section(self, section: str, context: str, resume=None, user_id: int = None) -> str:
        prompts = {
            "professional_summary": f"""Write a powerful professional summary (3-4 sentences) for a resume.
Context: {context}
Requirements: ATS-friendly, strong action verbs, quantified achievements where possible.
Return only the summary text, no labels or explanations.""",
            "work_experience": f"""Improve these work experience bullet points for a resume.
Input: {context}
Requirements: Start each bullet with a strong action verb. Add metrics/numbers where logical.
ATS-optimized. Return improved bullet points only, one per line.""",
            "skills": f"""Generate a comprehensive skills list for this professional:
Context: {context}
Return as a JSON array of skill strings only. Example: ["Python", "Project Management"]""",
            "certifications": f"""Suggest relevant professional certifications based on:
{context}
Return as a JSON array of certification name strings.""",
        }
        prompt = prompts.get(section, f"Improve the following resume section '{section}':\n{context}\nReturn improved content only.")
        return self._call(prompt, "cv_generate", user_id=user_id)

    def revamp_resume(self, resume, user_id: int = None) -> dict:
        resume_data = json.dumps(resume.to_dict(), indent=2)
        prompt = f"""You are an expert resume writer and ATS optimization specialist.
Revamp this resume to be more professional, ATS-friendly, and impactful.

RESUME DATA:
{resume_data}

INSTRUCTIONS:
1. Improve the professional_summary (stronger, more impactful)
2. Enhance EVERY existing work_experience entry's bullet points (stronger action
   verbs, quantified achievements) — do NOT remove entries, do NOT collapse bullets
   into a single paragraph, and do NOT drop the job_title or dates.
3. Optimize skills — if the input has skill_groups (grouped by category), return
   skill_groups back in the SAME grouped shape. Only return a flat "skills" array
   if the input had no groups.
4. Improve overall language and clarity
5. Ensure ATS compatibility (no tables, proper keywords)

CRITICAL: work_experience in your response MUST be an array of objects with
EXACTLY this shape, one object per input job, in the same order:
{{
  "job_title": "<same or improved title, never blank>",
  "company": "<unchanged>",
  "location": "<unchanged>",
  "start_date": "<unchanged>",
  "end_date": "<unchanged>",
  "achievements": ["<improved bullet 1>", "<improved bullet 2>", "..."]
}}
Do not use a "description" field — achievements must be a list of separate bullet
strings, matching how the input was structured.

Return ONLY a valid JSON object with these keys:
{{
  "professional_summary": "improved summary text",
  "work_experience": [array of job objects in the exact shape above],
  "skills": [array of skill strings] OR omit if returning skill_groups,
  "skill_groups": [array of {{"group": "...", "skills": [...]}}] OR omit if returning flat skills,
  "revamp_notes": "brief explanation of changes made"
}}"""
        raw = self._call(prompt, "cv_revamp", user_id=user_id)
        try:
            return json.loads(_clean_json_fence(raw))
        except json.JSONDecodeError:
            current_app.logger.warning("Revamp JSON parse failed, returning raw")
            return {"professional_summary": raw}

    def generate_cover_letter(self, job_title: str, company_name: str,
                               job_description: str, tone: str = "professional",
                               resume=None, user_id: int = None) -> str:
        resume_context = ""
        if resume:
            resume_context = f"""
CANDIDATE RESUME SUMMARY:
Name: {(resume.personal_info or {}).get('full_name', 'the candidate')}
Summary: {resume.professional_summary or ''}
Skills: {', '.join((resume.skills or [])[:10])}
"""
        tone_instructions = {
            "formal": "Use formal, traditional business language. Conservative and professional.",
            "professional": "Use confident, professional language. Clear and concise.",
            "executive": "Use executive-level language. Strategic, visionary, leadership-focused.",
            "friendly": "Use warm, approachable language. Personable while remaining professional.",
        }
        prompt = f"""Write a compelling cover letter for a job application.

JOB DETAILS:
Position: {job_title}
Company: {company_name}
Job Description: {job_description[:1000]}

TONE: {tone_instructions.get(tone, tone_instructions['professional'])}
{resume_context}

REQUIREMENTS:
- 3-4 paragraphs
- Opening: hook that shows enthusiasm and fit
- Middle: 2 key achievements/skills that match the role
- Closing: call to action
- ATS-friendly
- No generic phrases like "I am writing to apply"

Return only the cover letter text, ready to use."""
        return self._call(prompt, "cover_letter", user_id=user_id)

    def ats_check(self, resume, job_description: str = "", user_id: int = None,
                  resume_text: str = None) -> dict:
        """
        Analyze a resume against a job description.

        resume_text: optional raw text override — used by the "upload & check"
        flow where the person just uploaded a file and we want to run ATS
        straight off the extracted text without requiring a saved Resume row.

        job_description is now optional: if it's blank, we run a general
        ATS/formatting audit of the resume alone instead of a match-analysis
        against a role.
        """
        if resume_text:
            text = resume_text[:3000]
        elif resume:
            parts = [
                resume.professional_summary or "",
                " ".join(resume.skills or []),
                json.dumps(resume.work_experience or []),
            ]
            text = " ".join(parts)[:2000]
        else:
            text = ""

        has_jd = bool(job_description and job_description.strip())

        if has_jd:
            task_instructions = f"""JOB DESCRIPTION:
{job_description[:1500]}

Analyze how well the resume matches this specific job description: keyword overlap,
skills gap, and fit."""
        else:
            task_instructions = """No job description was provided. Perform a GENERAL ATS audit of the
resume on its own: formatting/parseability issues, missing standard sections,
weak or missing quantification, and keyword density for the candidate's
apparent field. Set match_score to null-equivalent by using 0 and note in
"summary" that no job description was supplied."""

        prompt = f"""You are an ATS (Applicant Tracking System) expert.

RESUME CONTENT:
{text if text else "No resume content provided."}

{task_instructions}

Provide a comprehensive ATS analysis. Return ONLY valid JSON:
{{
  "ats_score": <integer 0-100>,
  "match_score": <integer 0-100>,
  "grade": "<A/B/C/D/F>",
  "matched_keywords": ["keyword1", "keyword2"],
  "missing_keywords": ["keyword1", "keyword2"],
  "skills_gap": ["skill1", "skill2"],
  "strengths": ["strength1", "strength2"],
  "suggestions": [
    {{"priority": "high", "text": "Add X skill to your resume"}},
    {{"priority": "medium", "text": "Quantify your achievements"}}
  ],
  "format_issues": ["issue1"],
  "summary": "Brief 2-sentence summary of the analysis"
}}"""
        raw = self._call(prompt, "ats_check", user_id=user_id)
        try:
            return json.loads(_clean_json_fence(raw))
        except Exception:
            return {
                "ats_score": 50, "match_score": 50, "grade": "C",
                "matched_keywords": [], "missing_keywords": [],
                "suggestions": [{"priority": "high", "text": "Unable to parse full report. Please try again."}],
                "summary": raw[:300],
            }

    def coach_review(self, resume, user_id: int = None) -> str:
        """Directive, whole-resume review used by the Pro+ AI Coach step in
        the CV wizard. Unlike career_coach() (which answers a free-form
        question), this proactively audits the resume and tells the user
        exactly what's wrong and how to fix it — no question required."""
        resume_data = json.dumps(resume.to_dict(), indent=2)
        prompt = f"""You are a blunt, expert resume coach reviewing a client's CV
before they submit it to employers.

RESUME DATA:
{resume_data}

Give direct, specific feedback:
1. Point out exactly what's weak, vague, or missing — name the section.
2. For each issue, say precisely what to change to fix it.
3. Briefly note anything that's genuinely strong.

Address the reader as "you". Be honest, not falsely encouraging. Use short
bullet points. Keep the whole response under 250 words."""
        return self._call(prompt, "career_coach", user_id=user_id)

    def career_coach(self, question: str, resume=None, user_id: int = None) -> str:
        resume_context = ""
        if resume:
            resume_context = f"Candidate profile: {resume.professional_summary or 'Not provided'}"
        prompt = f"""You are an expert career coach with 20 years of experience.
{resume_context}

Career question: {question}

Provide actionable, specific advice. Be encouraging but honest.
Keep response under 300 words. Use bullet points where helpful."""
        return self._call(prompt, "career_coach", user_id=user_id)

    def estimate_salary(self, job_title: str, location: str, experience: int, user_id: int = None) -> dict:
        prompt = f"""Estimate salary range for:
Job Title: {job_title}
Location: {location}
Years of Experience: {experience}

Return ONLY JSON:
{{
  "min_salary": <number in USD>,
  "max_salary": <number in USD>,
  "median_salary": <number in USD>,
  "currency": "USD",
  "notes": "brief context"
}}"""
        raw = self._call(prompt, "salary_estimate", user_id=user_id)
        try:
            return json.loads(_clean_json_fence(raw))
        except Exception:
            return {"min_salary": 0, "max_salary": 0, "notes": "Unable to estimate."}

    def generate_bio(self, resume=None, context: str = "", tone: str = "professional", user_id: int = None) -> str:
        resume_info = ""
        if resume:
            resume_info = f"""
Name: {(resume.personal_info or {}).get('full_name', '')}
Title: {(resume.personal_info or {}).get('job_title', '')}
Summary: {resume.professional_summary or ''}
Skills: {', '.join((resume.skills or [])[:8])}
"""
        prompt = f"""Write a professional bio (2-3 paragraphs, ~150-200 words).
{resume_info}
Additional context: {context}
Tone: {tone}
Write in third person. Highlight expertise, achievements, and value proposition.
Return only the bio text."""
        return self._call(prompt, "bio_generate", user_id=user_id)

    # Static knowledge grounding for the support assistant — keeps answers
    # anchored to what CVForge actually does/costs instead of the model
    # guessing or inventing features/pricing. Update this when plans,
    # limits, or features change; it's the single source of truth the AI
    # is told to defer to.
    SUPPORT_KNOWLEDGE = """
CVForge AI — Product Facts (use these, don't invent anything not listed here):
- CV/resume builder with AI-assisted writing, ATS scoring, and cover letter generation
- Upload an existing CV (PDF/DOCX) to auto-fill the builder, or start from scratch
- AI Revamp rewrites your professional summary, work experience bullets, and skills
- ATS Checker: analyze a saved CV or upload a file directly, with or without a job description
- Download as PDF (all plans) or DOCX (Pro only)
- Free plan: limited daily AI generations, limited templates, no DOCX export
- Pro plan: unlimited AI generations, all templates, DOCX export, version history, AI career coach
- Payment: M-Pesa (STK Push) or card, via IntaSend
- Subscriptions run 30 days from payment and do not auto-renew
- Support contact: use the in-app support page; there is no phone support
"""

    def support_answer(self, question: str, user=None, user_id: int = None) -> str:
        """
        AI support assistant, grounded in SUPPORT_KNOWLEDGE above via
        system_instruction so it answers from what CVForge actually does
        rather than making things up about pricing or features. For
        anything outside that scope (refunds, account-specific issues,
        bugs), it's instructed to say so plainly and hand off rather than
        guess — a wrong confident answer here is worse than "I don't
        know, here's how to reach a human."
        """
        user_context = ""
        if user:
            plan = getattr(user, "plan", "free")
            user_context = f"\nThis user is on the '{plan}' plan."

        system_instruction = f"""You are the support assistant for CVForge AI, a CV/resume builder.
{self.SUPPORT_KNOWLEDGE}

RULES:
- Only answer using the facts above plus general, obviously-safe advice
  (e.g. "try clearing your browser cache").
- If the question is about something not covered above (refunds, a
  specific bug, account/billing disputes, anything you're not certain
  about), say clearly that you don't have that information and suggest
  they contact support directly for a human to help — do not guess or
  invent an answer.
- Never invent pricing, limits, or features not listed above.
- Keep answers short — 2-4 sentences unless genuinely more is needed.
- Friendly, direct, no corporate filler."""

        prompt = f"{user_context}\n\nUser question: {question}"
        return self._call(prompt, "support_chat", user_id=user_id, system_instruction=system_instruction)


