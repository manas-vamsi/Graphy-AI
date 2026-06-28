"""GitHub Analyzer Agent.

Turns fetched repositories into a structured skill/project/interest graph:
detects technologies, frameworks, and project categories, and aggregates
languages. Truthful — it only describes repos that actually exist.
"""
from __future__ import annotations

from collections import Counter

from app.llm.client import get_llm

SYSTEM = (
    "You analyze a developer's real GitHub repositories. Infer technologies, "
    "frameworks, and project categories ONLY from the provided repo data "
    "(names, descriptions, languages, topics, README excerpts). Do not invent "
    "skills that have no basis in the data."
)

PROMPT = """Here are the developer's repositories (JSON-ish digest):
{digest}

Return STRICT JSON:
{{
  "skill_graph": {{
    "languages": ["..."],
    "frameworks": ["..."],
    "libraries": ["..."],
    "tools": ["..."],
    "domains": ["high-level themes e.g. NLP, Quantum Computing, Data Analysis"]
  }},
  "projects": [
    {{"name": "<repo name exactly>", "technologies": ["..."], "category": "<short category>"}}
  ]
}}
Only include repos present in the digest. Base every entry on the evidence.
"""


def _digest(fetched: dict[str, dict]) -> str:
    lines = []
    for user, data in fetched.items():
        for rp in data.get("repos", []):
            lines.append(
                f"- [{user}] {rp['name']} | langs={rp.get('languages')} "
                f"| topics={rp.get('topics')} | desc={rp.get('description', '')[:160]} "
                f"| readme={rp.get('readme', '')[:400]}"
            )
    return "\n".join(lines) if lines else "(no repositories)"


def analyze(fetched: dict[str, dict]) -> dict:
    # Deterministic language aggregation (counts) — independent of the LLM.
    lang_counter: Counter[str] = Counter()
    for data in fetched.values():
        for rp in data.get("repos", []):
            for lang in rp.get("languages", []):
                lang_counter[lang] += 1
            if rp.get("primary_language"):
                lang_counter[rp["primary_language"]] += 1

    result = get_llm().chat_json(PROMPT.format(digest=_digest(fetched)), system=SYSTEM)
    result.setdefault("skill_graph", {})
    result.setdefault("projects", [])
    result["languages"] = dict(lang_counter.most_common())
    return result
