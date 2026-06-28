"""Central registry of every external API Graphy AI can use.

This is the one place that documents each provider, its purpose, base URL, the
env var that holds its key, and a ready-to-use client/headers helper. Phases 2-4
import from here instead of scattering keys and URLs across the codebase.

Nothing here sends data on import — clients are built lazily. Secrets come from
`backend/.env` (gitignored). ROTATE keys periodically.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.config import settings


@dataclass(frozen=True)
class Provider:
    name: str
    purpose: str
    base_url: str
    env_var: str
    docs: str

    @property
    def key(self) -> str:
        return getattr(settings, self.env_var.lower(), "") or ""

    @property
    def configured(self) -> bool:
        return bool(self.key)


# ---- Provider catalogue (single source of truth) ----
PROVIDERS: dict[str, Provider] = {
    "gemini": Provider(
        "Google Gemini", "Primary reasoning / resume tailoring LLM",
        "https://generativelanguage.googleapis.com", "GEMINI_API_KEY",
        "https://ai.google.dev/api",
    ),
    "groq": Provider(
        "Groq", "Fast LLM fallback (OpenAI-compatible)",
        "https://api.groq.com/openai/v1", "GROQ_API_KEY",
        "https://console.groq.com/docs",
    ),
    "openrouter": Provider(
        "OpenRouter", "Multi-model LLM fallback (OpenAI-compatible)",
        "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY",
        "https://openrouter.ai/docs",
    ),
    "ollama": Provider(
        "Ollama (local)", "Fully-local LLM + embeddings (gemma4 / embeddinggemma)",
        settings.ollama_base_url, "OLLAMA_BASE_URL",
        "https://docs.ollama.com/api",
    ),
    "scrapegraphai": Provider(
        "ScrapeGraphAI", "Structured job/career-page scraping",
        "https://api.scrapegraphai.com/v1", "SCRAPEGRAPHAI_API_KEY",
        "https://docs.scrapegraphai.com",
    ),
    "jina": Provider(
        "Jina AI", "Web reader (r.jina.ai) + embeddings for discovery",
        "https://api.jina.ai/v1", "JINA_API_KEY",
        "https://jina.ai/reader",
    ),
    "google_cse": Provider(
        "Google Custom Search", "Job/opportunity web search",
        "https://www.googleapis.com/customsearch/v1", "GOOGLE_CSE_API_KEY",
        "https://developers.google.com/custom-search/v1/overview",
    ),
    "github": Provider(
        "GitHub REST", "Repo/commit analysis (primary account)",
        "https://api.github.com", "GITHUB_TOKEN",
        "https://docs.github.com/en/rest",
    ),
    "github_secondary": Provider(
        "GitHub REST (2nd acct)", "Repo/commit analysis (secondary account)",
        "https://api.github.com", "GITHUB_TOKEN_SECONDARY",
        "https://docs.github.com/en/rest",
    ),
}


def status() -> dict[str, bool]:
    """Which providers have a key configured (for /health and dashboards)."""
    return {k: p.configured for k, p in PROVIDERS.items()}


# ---- Ready-to-use clients ----
def openai_compatible_client(provider_key: str) -> httpx.Client:
    """httpx client for OpenAI-compatible providers (groq, openrouter)."""
    p = PROVIDERS[provider_key]
    headers = {"Authorization": f"Bearer {p.key}", "Content-Type": "application/json"}
    if provider_key == "openrouter":
        headers["HTTP-Referer"] = "http://localhost:3000"
        headers["X-Title"] = "Graphy AI"
    return httpx.Client(base_url=p.base_url, headers=headers, timeout=120)


def github_client(secondary: bool = False) -> httpx.Client:
    """Authenticated GitHub REST client."""
    token = settings.github_token_secondary if secondary else settings.github_token
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(base_url="https://api.github.com", headers=headers, timeout=30)


def jina_reader_url(target_url: str) -> str:
    """Jina Reader turns any page into clean LLM-ready text: https://r.jina.ai/<url>."""
    return f"https://r.jina.ai/{target_url}"


def jina_headers() -> dict:
    return {"Authorization": f"Bearer {settings.jina_api_key}"} if settings.jina_api_key else {}
