"""Discovery fetchers: turn a careers/job URL into clean text (SSRF-guarded).

Primary: Jina Reader (r.jina.ai) — robust, returns LLM-ready markdown.
Fallback: ScrapeGraphAI hosted API. Optional: Google Custom Search for queries.
"""
from __future__ import annotations

import httpx

from app.config import settings
from app.integrations import jina_headers, jina_reader_url
from app.security import assert_safe_url


class DiscoveryError(RuntimeError):
    pass


_MIN_CONTENT_CHARS = 200  # below this, treat as a rate-limit/notice/blocked page


def read_url(target_url: str) -> str:
    """Fetch a page as clean text. Validates the TARGET url for SSRF first."""
    assert_safe_url(target_url)  # raises UnsafeURLError on internal/loopback/etc.

    # 1) Jina Reader — but a thin 200 body usually means rate-limit/notice, so
    #    only accept substantial content; otherwise fall through to the fallback.
    try:
        with httpx.Client(timeout=60, follow_redirects=True) as c:
            r = c.get(jina_reader_url(target_url), headers=jina_headers())
            if r.status_code == 200 and len(r.text.strip()) >= _MIN_CONTENT_CHARS:
                return r.text
    except httpx.HTTPError:
        pass

    # 2) ScrapeGraphAI hosted fallback (if configured)
    if settings.scrapegraphai_api_key:
        try:
            with httpx.Client(timeout=120) as c:
                r = c.post(
                    "https://api.scrapegraphai.com/v1/smartscraper",
                    headers={"SGAI-APIKEY": settings.scrapegraphai_api_key},
                    json={
                        "website_url": target_url,
                        "user_prompt": "Extract all job/opportunity listings with title, company, location, type, description, and apply URL.",
                    },
                )
                if r.status_code == 200:
                    return str(r.json())
        except httpx.HTTPError:
            pass

    raise DiscoveryError(f"Could not fetch content from {target_url}")


def google_search(query: str, num: int = 10) -> list[dict]:
    """Search opportunities via Google Custom Search (returns [] if not configured)."""
    if not (settings.google_cse_api_key and settings.google_cse_cx):
        return []
    with httpx.Client(timeout=30) as c:
        r = c.get(
            "https://www.googleapis.com/customsearch/v1",
            params={
                "key": settings.google_cse_api_key,
                "cx": settings.google_cse_cx,
                "q": query,
                "num": min(num, 10),
            },
        )
        r.raise_for_status()
        items = r.json().get("items", [])
    return [{"title": i.get("title"), "url": i.get("link"), "snippet": i.get("snippet")} for i in items]
