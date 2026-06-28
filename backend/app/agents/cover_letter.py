"""Cover Letter Agent — TRUTHFUL by construction (same guarantee as tailoring).

Prime directive: never fabricate. A cover letter may ONLY draw on facts that
already exist in the verified profile. It generates, then fact-checks every
claim against that fact set, strips anything unsupported, and regenerates once.

Returns content + fact_trace (claim -> source fact) + stripped_claims (audit).
"""
from __future__ import annotations

from app.agents.resume_intelligence import verified_facts
from app.llm.client import get_llm

GEN_SYSTEM = (
    "You are a professional cover-letter writer bound by a strict rule: you may "
    "ONLY use facts from the provided verified-fact list. You may select, frame, "
    "and phrase those facts to argue fit for the role — but you must NEVER add "
    "skills, experience, projects, dates, employers, metrics, or certifications "
    "that are not in the list. When in doubt, leave it out."
)

# Cache-friendly ordering: large stable context (facts, then job) first so the
# implicit cache reuses it across the corrective re-generation; {extra} last.
GEN_PROMPT = """VERIFIED FACTS (the ONLY information you may use), indexed:
{facts}

Target role context:
\"\"\"
{job}
\"\"\"

Write a concise, compelling cover letter (3–4 short paragraphs, professional but
warm). Open by stating interest in the role, make the case for fit using ONLY the
verified facts most relevant to it, and close politely. Do not invent anything —
no fact that is not in the list above. Plain text, no placeholders like
[Company] unless the company name is given in the role context.{extra}
"""

VALIDATE_SYSTEM = (
    "You are a strict fact-checker. Given an allowed fact list and a generated "
    "cover letter, identify every concrete factual claim about the candidate "
    "(skills, employers, titles, dates, projects, technologies, metrics, degrees) "
    "and decide whether each is supported by the allowed facts."
)

VALIDATE_PROMPT = """ALLOWED FACTS (indexed):
{facts}

GENERATED COVER LETTER:
\"\"\"
{letter}
\"\"\"

Return STRICT JSON:
{{
  "claims": [
    {{"claim": "<short text>", "supported": true/false, "source_fact_index": <int or null>}}
  ]
}}
A claim is supported ONLY if it clearly traces to one of the allowed facts.
Generic enthusiasm, greetings, or connective phrasing are not claims — skip them.
"""


def _index_facts(facts: list[str]) -> str:
    return "\n".join(f"[{i}] {f}" for i, f in enumerate(facts))


def _generate(job_text: str, facts: list[str], removed: list[str] | None = None) -> str:
    extra = ""
    if removed:
        joined = "; ".join(removed)
        extra = (
            "\n\nIMPORTANT: A previous draft contained unsupported claims that you "
            f"MUST NOT include this time: {joined}"
        )
    return get_llm().chat(
        GEN_PROMPT.format(job=job_text[:8000], facts=_index_facts(facts), extra=extra),
        system=GEN_SYSTEM,
        temperature=0.4,
    )


def _validate(letter: str, facts: list[str]) -> dict:
    return get_llm().chat_json(
        VALIDATE_PROMPT.format(facts=_index_facts(facts), letter=letter[:12000]),
        system=VALIDATE_SYSTEM,
    )


def write(profile: dict, job_text: str) -> dict:
    """Generate a truthful, fact-checked cover letter from the verified profile."""
    facts = verified_facts(profile)
    if not facts:
        raise ValueError("No verified facts in profile — parse a resume first.")

    content = _generate(job_text, facts)
    report = _validate(content, facts)
    claims = report.get("claims", []) or []
    stripped = [c["claim"] for c in claims if not c.get("supported", False)]

    # one corrective regeneration if hallucinations slipped in
    if stripped:
        content = _generate(job_text, facts, removed=stripped)
        report = _validate(content, facts)
        claims = report.get("claims", []) or []
        stripped = [c["claim"] for c in claims if not c.get("supported", False)]

    fact_trace = {
        c["claim"]: facts[c["source_fact_index"]]
        for c in claims
        if c.get("supported") and isinstance(c.get("source_fact_index"), int)
        and 0 <= c["source_fact_index"] < len(facts)
    }

    return {
        "content": content,
        "fact_trace": fact_trace,
        "stripped_claims": stripped,  # audit: what the validator refused to allow
        "supported_count": len(fact_trace),
    }
