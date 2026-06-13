"""
CVForge AI - AI Service (Gemini)
Fixed: removed monkey-patch, uses flask.g for per-request caching,
consistent import path, clean _call signature.
"""
import hashlib
import json
from flask import current_app, g


def get_ai_service():
    """Return a per-request cached AIService instance via flask.g."""
    if "ai_service" not in g:
        g.ai_service = AIService()
    return g.ai_service


class AIService:
    MODEL = "gemini-1.5-flash"

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

    def assist_section(self, section: str, context: str, resume=None) -> str:
        prompts = {
            "professional_summary": f"""Write a powerful professional summary (3-4 sentences) for a resume.
Context: {context}
Requirements: ATS-friendly, strong action verbs, quantified achievements where possible.
Return only the summary text, no labels or explanations.""",
            "work_experience": f"""Improve these work experience bullet points for a resume.
Input: {context}
Requirements: Start each bullet with a strong action verb. Add metrics/numbers where logical.
ATS-optimized. Return improved bullet points only.""",
            "skills": f"""Generate a comprehensive skills list for this professional:
Context: {context}
Return as a JSON array of skill strings only. Example: ["Python", "Project Management"]""",
            "certifications": f"""Suggest relevant professional certifications based on:
{context}
Return as a JSON array of certification name strings.""",
        }
        prompt = prompts.get(section, f"Improve the following resume section '{section}':\n{context}\nReturn improved content only.")
        return self._call(prompt, "cv_generate")

    def revamp_resume(self, resume) -> dict:
        resume_data = json.dumps(resume.to_dict(), indent=2)
        prompt = f"""You are an expert resume writer and ATS optimization specialist.
Revamp this resume to be more professional, ATS-friendly, and impactful.

RESUME DATA:
{resume_data}

INSTRUCTIONS:
1. Improve the professional_summary (stronger, more impactful)
2. Enhance work_experience bullet points (action verbs, quantified achievements)
3. Optimize skills section
4. Improve overall language and clarity
5. Ensure ATS compatibility (no tables, proper keywords)

Return ONLY a valid JSON object with these keys:
{{
  "professional_summary": "improved summary text",
  "work_experience": [array of improved job objects],
  "skills": [array of skill strings],
  "revamp_notes": "brief explanation of changes made"
}}"""
        raw = self._call(prompt, "cv_revamp")
        try:
            clean = raw.strip()
            if clean.startswith("```"):
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
            return json.loads(clean.strip())
        except json.JSONDecodeError:
            current_app.logger.warning("Revamp JSON parse failed, returning raw")
            return {"professional_summary": raw}

    def generate_cover_letter(self, job_title: str, company_name: str,
                               job_description: str, tone: str = "professional",
                               resume=None) -> str:
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
        return self._call(prompt, "cover_letter")

    def ats_check(self, resume, job_description: str) -> dict:
        resume_text = ""
        if resume:
            parts = [
                resume.professional_summary or "",
                " ".join(resume.skills or []),
                json.dumps(resume.work_experience or []),
            ]
            resume_text = " ".join(parts)[:2000]

        prompt = f"""You are an ATS (Applicant Tracking System) expert.
Analyze this resume against the job description.

RESUME CONTENT:
{resume_text if resume_text else "No resume provided - analyze job description only"}

JOB DESCRIPTION:
{job_description[:1500]}

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
        raw = self._call(prompt, "ats_check")
        try:
            clean = raw.strip()
            if clean.startswith("```"):
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
            return json.loads(clean.strip())
        except Exception:
            return {
                "ats_score": 50, "match_score": 50, "grade": "C",
                "matched_keywords": [], "missing_keywords": [],
                "suggestions": [{"priority": "high", "text": "Unable to parse full report. Please try again."}],
                "summary": raw[:300],
            }

    def career_coach(self, question: str, resume=None) -> str:
        resume_context = ""
        if resume:
            resume_context = f"Candidate profile: {resume.professional_summary or 'Not provided'}"
        prompt = f"""You are an expert career coach with 20 years of experience.
{resume_context}

Career question: {question}

Provide actionable, specific advice. Be encouraging but honest.
Keep response under 300 words. Use bullet points where helpful."""
        return self._call(prompt, "career_coach")

    def estimate_salary(self, job_title: str, location: str, experience: int) -> dict:
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
        raw = self._call(prompt, "salary_estimate")
        try:
            clean = raw.strip().strip("```json").strip("```").strip()
            return json.loads(clean)
        except Exception:
            return {"min_salary": 0, "max_salary": 0, "notes": "Unable to estimate."}

    def generate_bio(self, resume=None, context: str = "", tone: str = "professional") -> str:
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
        return self._call(prompt, "bio_generate")
