"""Security layer for Graphy AI.

Centralizes the defenses that matter for a local-first app that handles personal
data, API keys, and (later) automated logins:

  - SSRF guard for every outbound fetch (job pages, scraping, GitHub).
  - At-rest encryption (Fernet) for credentials / OAuth tokens.
  - Secret redaction so keys never leak into logs or error responses.
  - Optional API-key gate (X-API-Key) for when the backend is exposed beyond localhost.
  - Upload validation (size + type) and filename sanitization.
  - Security-response-headers helper (wired as middleware in main.py).
"""
from __future__ import annotations

import ipaddress
import re
import secrets
import socket
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Header, HTTPException, status

from app.config import DATA_DIR, settings

# ---------------------------------------------------------------------------
# 1. SSRF guard — refuse to fetch internal/metadata/loopback targets
# ---------------------------------------------------------------------------
_ALLOWED_SCHEMES = {"http", "https"}
_BLOCKED_HOST_SUBSTRINGS = (
    "metadata.google.internal",
    "169.254.169.254",  # cloud metadata
)
# Policy blocklist — domains the platform must never fetch/automate (account-ban risk).
_BLOCKED_POLICY_DOMAINS = (
    "linkedin.com",
)


class UnsafeURLError(ValueError):
    pass


def _is_public_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def assert_safe_url(url: str) -> str:
    """Validate a user-supplied URL before any server-side fetch (anti-SSRF).

    Blocks non-http(s) schemes, credentials in URL, and hosts that resolve to
    private/loopback/link-local/metadata addresses. Returns the URL if safe.
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise UnsafeURLError(f"Only http/https allowed, got {parsed.scheme!r}")
    if parsed.username or parsed.password:
        raise UnsafeURLError("Credentials in URL are not allowed")
    host = parsed.hostname
    if not host:
        raise UnsafeURLError("URL has no host")
    low = host.lower()
    if low in {"localhost"} or any(b in low for b in _BLOCKED_HOST_SUBSTRINGS):
        raise UnsafeURLError(f"Blocked host: {host}")
    if any(low == d or low.endswith("." + d) for d in _BLOCKED_POLICY_DOMAINS):
        raise UnsafeURLError(f"Policy-blocked domain (never automated): {host}")
    # Resolve and verify every A/AAAA record is a public address.
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as e:
        raise UnsafeURLError(f"Cannot resolve host {host!r}") from e
    for info in infos:
        ip = info[4][0]
        if not _is_public_ip(ip):
            raise UnsafeURLError(f"Host {host} resolves to non-public address {ip}")
    return url


# ---------------------------------------------------------------------------
# 2. At-rest encryption (Fernet) for credentials / tokens
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _fernet():
    from cryptography.fernet import Fernet

    key = settings.encryption_key.strip()
    if not key:
        key_path = DATA_DIR / "encryption.key"
        if key_path.exists():
            key = key_path.read_text().strip()
        else:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            key = Fernet.generate_key().decode()
            key_path.write_text(key)
            try:
                key_path.chmod(0o600)  # best-effort on Windows
            except OSError:
                pass
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str) -> str:
    """Encrypt a secret for storage (e.g. employer-portal credentials)."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


# ---------------------------------------------------------------------------
# 3. Secret redaction for logs / error messages
# ---------------------------------------------------------------------------
_SECRET_PATTERNS = [
    re.compile(r"(AIza[0-9A-Za-z_\-]{10,})"),
    re.compile(r"(AQ\.[0-9A-Za-z_\-]{10,})"),
    re.compile(r"(sk-or-v1-[0-9a-f]{16,})"),
    re.compile(r"(gsk_[0-9A-Za-z]{20,})"),
    re.compile(r"(sgai-[0-9a-f\-]{16,})"),
    re.compile(r"(jina_[0-9A-Za-z_\-]{16,})"),
    re.compile(r"(github_pat_[0-9A-Za-z_]{20,})"),
    re.compile(r"(ghp_[0-9A-Za-z]{20,})"),
    re.compile(r"(Bearer\s+[0-9A-Za-z._\-]{16,})"),
]


def redact(text: str) -> str:
    """Replace any secret-looking token with a masked placeholder."""
    out = text
    for pat in _SECRET_PATTERNS:
        out = pat.sub(lambda m: m.group(1)[:6] + "…REDACTED", out)
    return out


# ---------------------------------------------------------------------------
# 4. Optional API-key gate (X-API-Key)
# ---------------------------------------------------------------------------
def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """FastAPI dependency. No-op if GRAPHY_API_KEY is unset (local-only mode)."""
    expected = settings.api_key
    if not expected:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing API key")


# ---------------------------------------------------------------------------
# 5. Upload validation
# ---------------------------------------------------------------------------
_ALLOWED_RESUME_EXT = {".pdf", ".txt", ".md"}
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")


def validate_upload(filename: str | None, size_bytes: int) -> None:
    ext = Path(filename or "").suffix.lower()
    if ext not in _ALLOWED_RESUME_EXT:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unsupported file type {ext!r}. Allowed: {sorted(_ALLOWED_RESUME_EXT)}",
        )
    limit = settings.max_upload_mb * 1024 * 1024
    if size_bytes > limit:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"File too large ({size_bytes // 1024} KB). Max {settings.max_upload_mb} MB.",
        )


def safe_filename(filename: str | None) -> str:
    base = Path(filename or "upload").name
    return _SAFE_NAME.sub("_", base)[:200] or "upload"


# ---------------------------------------------------------------------------
# 6. Security response headers
# ---------------------------------------------------------------------------
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    # API returns JSON only; lock the page CSP down hard.
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}
