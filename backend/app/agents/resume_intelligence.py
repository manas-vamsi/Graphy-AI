"""Resume Intelligence Agent.

Turns raw resume text into a STRUCTURED, VERIFIED profile. This profile is the
single source of truth for everything downstream — tailoring may only use facts
that originate here (or from GitHub in Phase 2). It never invents content.
"""
from __future__ import annotations

from app.llm.client import get_llm

SYSTEM = (
    "You are a precise resume parser. Extract ONLY information explicitly present "
    "in the resume text. Never infer, embellish, or add skills/experience/dates "
    "that are not literally stated. If a field is absent, return an empty value."
)

PROMPT = """Extract a structured profile from the resume below.

Return STRICT JSON with this exact shape:
{{
  "summary": "<1-2 sentence factual summary, or empty string>",
  "skills": [{{"name": "...", "category": "language|framework|library|tool|concept|other"}}],
  "experience": [{{"title": "...", "company": "...", "start": "...", "end": "...", "bullets": ["..."]}}],
  "projects": [{{"name": "...", "description": "...", "technologies": ["..."]}}],
  "education": [{{"degree": "...", "institution": "...", "year": "..."}}]
}}

Rules:
- Use ONLY text that appears in the resume. Do not invent dates, employers, or skills.
- Keep bullets close to the original wording.
- If something is not present, omit it from its list (or use "" for summary).

RESUME TEXT:
\"\"\"
{resume_text}
\"\"\"
"""


def build_profile(resume_text: str) -> dict:
    llm = get_llm()
    profile = llm.chat_json(PROMPT.format(resume_text=resume_text[:20000]), system=SYSTEM)
    # normalize missing keys
    for key in ("skills", "experience", "projects", "education"):
        profile.setdefault(key, [])
    profile.setdefault("summary", "")
    return profile


def verified_facts(profile: dict) -> list[str]:
    """Flatten the profile into atomic, traceable fact strings.

    The Resume Tailoring Agent may ONLY use facts from this set; the validator
    checks every generated claim against it.
    """
    facts: list[str] = []
    if profile.get("summary"):
        facts.append(f"summary: {profile['summary']}")
    for s in profile.get("skills", []):
        if s.get("name"):
            facts.append(f"skill: {s['name']} ({s.get('category', 'other')})")
    for e in profile.get("experience", []):
        head = f"experience: {e.get('title', '')} at {e.get('company', '')} ({e.get('start', '')}-{e.get('end', '')})"
        facts.append(head.strip())
        for b in e.get("bullets", []):
            facts.append(f"experience-detail: {b}")
    for p in profile.get("projects", []):
        techs = ", ".join(p.get("technologies", []))
        facts.append(f"project: {p.get('name', '')} — {p.get('description', '')} [tech: {techs}]")
    for ed in profile.get("education", []):
        facts.append(
            f"education: {ed.get('degree', '')} from {ed.get('institution', '')} ({ed.get('year', '')})"
        )
    return [f for f in facts if f.strip(": -")]
