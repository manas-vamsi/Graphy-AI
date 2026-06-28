"""Fetch repositories, languages, and READMEs from GitHub for one or more users.

Read-only. Uses the authenticated client from integrations (works across both of
the user's accounts since public repos are visible to any token).
"""
from __future__ import annotations

import base64

from app.config import settings
from app.integrations import github_client


def _decode_readme(payload: dict) -> str:
    if payload.get("encoding") == "base64" and payload.get("content"):
        try:
            return base64.b64decode(payload["content"]).decode("utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            return ""
    return ""


def fetch_user(username: str, *, max_repos: int = 40, include_forks: bool = False) -> dict:
    """Return {profile, repos[]} for a username with languages + README snippets."""
    with github_client() as c:
        prof = c.get(f"/users/{username}")
        profile = prof.json() if prof.status_code == 200 else {"login": username}

        r = c.get(
            f"/users/{username}/repos",
            params={"per_page": 100, "sort": "pushed", "type": "owner"},
        )
        repos_raw = r.json() if r.status_code == 200 else []
        if not include_forks:
            repos_raw = [rp for rp in repos_raw if not rp.get("fork")]
        repos_raw = repos_raw[:max_repos]

        repos = []
        for rp in repos_raw:
            langs_resp = c.get(f"/repos/{username}/{rp['name']}/languages")
            languages = langs_resp.json() if langs_resp.status_code == 200 else {}
            readme_resp = c.get(f"/repos/{username}/{rp['name']}/readme")
            readme = _decode_readme(readme_resp.json()) if readme_resp.status_code == 200 else ""
            repos.append(
                {
                    "name": rp["name"],
                    "description": rp.get("description") or "",
                    "url": rp.get("html_url"),
                    "primary_language": rp.get("language"),
                    "languages": list(languages.keys()),
                    "topics": rp.get("topics", []),
                    "stars": rp.get("stargazers_count", 0),
                    "readme": readme[:6000],
                }
            )
    return {"profile": profile, "repos": repos}


def fetch_all() -> dict[str, dict]:
    """Fetch both configured accounts (primary + secondary)."""
    users = [u for u in (settings.github_username, settings.github_username_secondary) if u]
    return {u: fetch_user(u) for u in users}
