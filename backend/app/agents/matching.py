"""Matching Agent.

Hybrid score = 0.5*semantic(cosine) + 0.3*skill_overlap + 0.2*llm_judgment.
Always returns the full breakdown, never just a number.
"""
from __future__ import annotations

from app.llm.client import get_llm
from app.vector import chroma

SYSTEM = (
    "You assess fit between a candidate's verified skills and a job description. "
    "Only consider skills the candidate actually has; do not assume unstated ones."
)

PROMPT = """Candidate verified skills:
{skills}

Job description:
\"\"\"
{job}
\"\"\"

Return STRICT JSON:
{{
  "matched_skills": ["skills the candidate has that the job wants"],
  "missing_skills": ["skills the job wants that the candidate lacks"],
  "llm_fit": <number 0..1 overall suitability>,
  "recommendation": "<one concise sentence>"
}}
"""


def _profile_text(profile: dict) -> str:
    parts = [profile.get("summary", "")]
    parts += [s.get("name", "") for s in profile.get("skills", [])]
    parts += [p.get("name", "") + " " + p.get("description", "") for p in profile.get("projects", [])]
    return " ".join(p for p in parts if p).strip() or "n/a"


def match(profile: dict, job_text: str) -> dict:
    # 1. semantic similarity (local embeddings). Skip if the profile is empty,
    #    so the "n/a" placeholder can't inflate the score for an unparsed resume.
    ptext = _profile_text(profile)
    if ptext == "n/a" or not job_text.strip():
        semantic = 0.0
    else:
        vecs = chroma.embed([ptext, job_text[:8000]])
        semantic = max(0.0, chroma.cosine(vecs[0], vecs[1]))

    # 2 + 3. LLM-derived skill overlap & judgment
    skills = ", ".join(s.get("name", "") for s in profile.get("skills", [])) or "none listed"
    judged = get_llm().chat_json(
        PROMPT.format(skills=skills, job=job_text[:8000]), system=SYSTEM
    )
    matched = judged.get("matched_skills", []) or []
    missing = judged.get("missing_skills", []) or []
    denom = len(matched) + len(missing)
    overlap = (len(matched) / denom) if denom else 0.0
    llm_fit = float(judged.get("llm_fit", 0.0) or 0.0)
    llm_fit = min(max(llm_fit, 0.0), 1.0)

    score = 0.5 * semantic + 0.3 * overlap + 0.2 * llm_fit
    return {
        "score": round(score, 4),
        "skill_overlap": matched,
        "missing_skills": missing,
        "recommendation": judged.get("recommendation", ""),
        "breakdown": {
            "semantic": round(semantic, 4),
            "skill_overlap_ratio": round(overlap, 4),
            "llm_fit": round(llm_fit, 4),
            "weights": {"semantic": 0.5, "skill_overlap": 0.3, "llm_fit": 0.2},
        },
    }
