"""Job Discovery Agent.

Extracts normalized opportunity listings from fetched page text. Truthful — it
only returns listings actually present in the source content.
"""
from __future__ import annotations

from app.llm.client import get_llm

SYSTEM = (
    "You extract job/internship/research/fellowship listings from web page text. "
    "Only extract opportunities that are actually present in the text. Do not "
    "invent listings, companies, or links."
)

PROMPT = """Source URL: {url}

Page content:
\"\"\"
{content}
\"\"\"

Extract every distinct opportunity. Return STRICT JSON:
{{
  "jobs": [
    {{
      "title": "...",
      "company": "...",
      "location": "...",
      "opportunity_type": "job|internship|research|fellowship|remote|other",
      "description": "<concise summary from the text>",
      "url": "<apply/details URL if present, else the source URL>"
    }}
  ]
}}
If no opportunities are present, return {{"jobs": []}}.
"""


def extract_jobs(page_text: str, source_url: str) -> list[dict]:
    result = get_llm().chat_json(
        PROMPT.format(url=source_url, content=page_text[:16000]), system=SYSTEM
    )
    jobs = result.get("jobs", []) if isinstance(result, dict) else []
    cleaned = []
    for j in jobs:
        if not j.get("title"):
            continue
        cleaned.append(
            {
                "title": j.get("title", "").strip(),
                "company": (j.get("company") or "").strip() or None,
                "location": (j.get("location") or "").strip() or None,
                "opportunity_type": (j.get("opportunity_type") or "job").strip().lower(),
                "description": (j.get("description") or "").strip(),
                "url": (j.get("url") or source_url).strip(),
            }
        )
    return cleaned
