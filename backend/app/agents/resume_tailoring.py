"""Resume Tailoring Agent — TRUTHFUL by construction.

Prime directive: never fabricate. Tailoring may ONLY reorder, emphasize,
rewrite wording, or summarize facts that already exist in the verified profile.

Flow:
  1. generate a role-targeted resume using ONLY the verified fact set
  2. VALIDATE every factual claim in the output against that fact set
  3. if any claim is unsupported, regenerate once with those claims removed
  4. return content + fact_trace (claim -> source fact) + stripped_claims (audit)
"""
from __future__ import annotations

from app.agents.resume_intelligence import verified_facts
from app.llm.client import get_llm

GEN_SYSTEM = (
    "You are a resume writer bound by a strict rule: you may ONLY use facts from "
    "the provided verified-fact list. You may reorder, emphasize, rewrite wording, "
    "and summarize those facts to target the role — but you must NEVER add skills, "
    "experience, projects, dates, employers, metrics, or certifications that are "
    "not in the list. When in doubt, leave it out."
)

# Cache-friendly ordering: the large, stable shared context (verified facts,
# then the job) goes first so Gemini's implicit cache reuses it across the
# corrective re-generation; the only per-call-variable text ({extra}) is last.
GEN_PROMPT = """VERIFIED FACTS (the ONLY information you may use), indexed:
{facts}

Target role context:
\"\"\"
{job}
\"\"\"

Write a clean, role-targeted resume in Markdown emphasizing the facts most
relevant to the target role. Do not invent anything. Do not add a fact that is
not in the list above.{extra}
"""

VALIDATE_SYSTEM = (
    "You are a strict fact-checker. You will be given an allowed fact list and a "
    "generated resume. Identify every concrete factual claim in the resume "
    "(skills, employers, titles, dates, projects, technologies, metrics, degrees) "
    "and decide whether each is supported by the allowed facts."
)

VALIDATE_PROMPT = """ALLOWED FACTS (indexed):
{facts}

GENERATED RESUME:
\"\"\"
{resume}
\"\"\"

Return STRICT JSON:
{{
  "claims": [
    {{"claim": "<short text>", "supported": true/false, "source_fact_index": <int or null>}}
  ]
}}
A claim is supported ONLY if it clearly traces to one of the allowed facts.
Generic section headers or connective phrasing are not claims — skip them.
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
        temperature=0.3,
    )


def _validate(resume_md: str, facts: list[str]) -> dict:
    return get_llm().chat_json(
        VALIDATE_PROMPT.format(facts=_index_facts(facts), resume=resume_md[:12000]),
        system=VALIDATE_SYSTEM,
    )


def tailor(profile: dict, job_text: str, label: str = "General") -> dict:
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
        "label": label,
        "content": content,
        "fact_trace": fact_trace,
        "stripped_claims": stripped,  # audit: what the validator refused to allow
        "supported_count": len(fact_trace),
    }
