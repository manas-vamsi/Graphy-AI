"""Provider-agnostic LLM client.

Agents call `chat()` / `chat_json()` and never care which backend is configured.
Swap Gemini <-> Ollama via LLM_PROVIDER in .env with no code changes.

Token optimization — context caching:
  Gemini 2.5 models do **implicit context caching** automatically: when two
  requests sent close together share a common prefix (>=1024 tokens for Flash),
  the shared tokens are billed at a 90% discount with no storage cost and no
  code changes. We lean on this rather than explicit caching, whose 32,768-token
  minimum is far larger than any resume/job payload here. To maximize hit rate
  the agents keep the large shared context (verified facts + job) at the START
  of the prompt and the per-call variable bits at the END — so the corrective
  re-generation and re-validation reuse the cached prefix. `USAGE` below records
  how many prompt tokens were cache hits so the savings are observable.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any

from app.config import settings

logger = logging.getLogger("graphy.llm")


class _UsageTracker:
    """Process-wide tally of Gemini token usage, incl. cached (discounted) tokens."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.calls = self.prompt = self.cached = self.output = 0

    def record(self, prompt: int, cached: int, output: int) -> None:
        self.calls += 1
        self.prompt += prompt
        self.cached += cached
        self.output += output

    def summary(self) -> dict:
        return {
            "calls": self.calls,
            "prompt_tokens": self.prompt,
            "cached_tokens": self.cached,            # billed at ~90% discount
            "billable_input_tokens": self.prompt - self.cached,
            "output_tokens": self.output,
            "cache_hit_ratio": round(self.cached / self.prompt, 3) if self.prompt else 0.0,
        }


USAGE = _UsageTracker()


class LLMError(RuntimeError):
    pass


class LLMClient:
    def chat(self, prompt: str, *, system: str | None = None, temperature: float = 0.2) -> str:
        raise NotImplementedError

    def chat_json(self, prompt: str, *, system: str | None = None) -> Any:
        """Return parsed JSON. Strips markdown fences if the model adds them."""
        raw = self.chat(prompt, system=system, temperature=0.0)
        return _parse_json(raw)


class GeminiClient(LLMClient):
    def __init__(self) -> None:
        if not settings.gemini_api_key:
            raise LLMError(
                "GEMINI_API_KEY is not set. Add it to backend/.env "
                "(free key: https://aistudio.google.com/apikey)."
            )
        from google import genai

        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = settings.gemini_model
        self.last_usage: dict = {}

    def chat(self, prompt: str, *, system: str | None = None, temperature: float = 0.2) -> str:
        from google.genai import types

        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system or None,
        )
        resp = self._client.models.generate_content(
            model=self._model, contents=prompt, config=config
        )
        self._record_usage(resp)
        return (resp.text or "").strip()

    def _record_usage(self, resp) -> None:
        """Capture token usage, including implicitly-cached (discounted) tokens."""
        um = getattr(resp, "usage_metadata", None)
        if um is None:
            return
        prompt = getattr(um, "prompt_token_count", 0) or 0
        cached = getattr(um, "cached_content_token_count", 0) or 0
        output = getattr(um, "candidates_token_count", 0) or 0
        self.last_usage = {"prompt": prompt, "cached": cached, "output": output}
        USAGE.record(prompt, cached, output)
        if cached:
            logger.info(
                "Gemini implicit cache hit: %d/%d prompt tokens cached (90%% discount)",
                cached, prompt,
            )


class OllamaClient(LLMClient):
    def __init__(self) -> None:
        self._base = settings.ollama_base_url.rstrip("/")
        self._model = settings.ollama_chat_model

    def chat(self, prompt: str, *, system: str | None = None, temperature: float = 0.2) -> str:
        import httpx

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = httpx.post(
            f"{self._base}/api/chat",
            json={"model": self._model, "messages": messages, "stream": False,
                  "options": {"temperature": temperature}},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()


class OpenAICompatibleClient(LLMClient):
    """Groq and OpenRouter share the OpenAI chat-completions shape."""

    def __init__(self, provider_key: str, model: str) -> None:
        from app.integrations import PROVIDERS

        self._provider_key = provider_key
        self._model = model
        if not PROVIDERS[provider_key].configured:
            raise LLMError(f"{provider_key} API key not set.")

    def chat(self, prompt: str, *, system: str | None = None, temperature: float = 0.2) -> str:
        from app.integrations import openai_compatible_client

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        with openai_compatible_client(self._provider_key) as client:
            resp = client.post(
                "/chat/completions",
                json={"model": self._model, "messages": messages, "temperature": temperature},
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()


class FallbackClient(LLMClient):
    """Try providers in order; on failure (e.g. Gemini 503) fall through to the next."""

    def __init__(self, clients: list[tuple[str, LLMClient]]) -> None:
        self._clients = clients

    def chat(self, prompt: str, *, system: str | None = None, temperature: float = 0.2) -> str:
        errors = []
        for name, client in self._clients:
            try:
                return client.chat(prompt, system=system, temperature=temperature)
            except Exception as e:  # noqa: BLE001 - intentional fallthrough
                errors.append(f"{name}: {type(e).__name__} {str(e)[:120]}")
        raise LLMError("All LLM providers failed -> " + " | ".join(errors))

    def chat_json(self, prompt: str, *, system: str | None = None) -> Any:
        # Fall through on BOTH transport failures and unparseable JSON — every
        # agent uses chat_json, so the fallback must cover it too.
        errors = []
        for name, client in self._clients:
            try:
                return client.chat_json(prompt, system=system)
            except Exception as e:  # noqa: BLE001 - intentional fallthrough
                errors.append(f"{name}: {type(e).__name__} {str(e)[:120]}")
        raise LLMError("All LLM providers failed (json) -> " + " | ".join(errors))


def _parse_json(raw: str) -> Any:
    text = raw.strip()
    # Extract the first fenced block even if the model prepends prose ("Here is...:").
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 3:
            text = parts[1]
            if text.lstrip().lower().startswith("json"):
                text = text.lstrip()[4:]
    text = text.strip().strip("`").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # last resort: grab the outermost {...} or [...]
        for open_c, close_c in (("{", "}"), ("[", "]")):
            if open_c in text and close_c in text:
                snippet = text[text.index(open_c) : text.rindex(close_c) + 1]
                try:
                    return json.loads(snippet)
                except json.JSONDecodeError:
                    pass
        raise LLMError(f"Model did not return valid JSON: {e}\n---\n{raw[:500]}") from e


def _build(name: str) -> LLMClient:
    if name == "gemini":
        return GeminiClient()
    if name == "groq":
        return OpenAICompatibleClient("groq", settings.groq_model)
    if name == "openrouter":
        return OpenAICompatibleClient("openrouter", settings.openrouter_model)
    if name == "ollama":
        return OllamaClient()
    raise LLMError(f"Unknown LLM provider: {name!r}")


@lru_cache(maxsize=1)
def get_llm() -> LLMClient:
    """Primary provider from LLM_PROVIDER, with automatic fallback to any other
    configured provider (so a Gemini 503 transparently falls through to Groq, etc.)."""
    primary = settings.llm_provider.lower()
    order = [primary] + [p for p in ("gemini", "groq", "openrouter", "ollama") if p != primary]
    chain: list[tuple[str, LLMClient]] = []
    for name in order:
        try:
            chain.append((name, _build(name)))
        except Exception:  # noqa: BLE001 - skip unconfigured providers
            continue
    if not chain:
        raise LLMError("No LLM provider is configured. Set GEMINI_API_KEY (or Groq/OpenRouter).")
    return FallbackClient(chain) if len(chain) > 1 else chain[0][1]
