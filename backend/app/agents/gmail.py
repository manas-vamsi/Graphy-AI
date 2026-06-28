"""Gmail Agent — turns application-related emails into structured notifications.

Reads (never sends) the user's Gmail to surface confirmations, interview
invites, rejections, and recruiter outreach, then files them as Notifications.

Defensive by design:
  - Google libraries are imported lazily, so the backend boots fine without them.
  - If the libs, the OAuth client-secrets JSON, or a valid token are missing,
    every entry point returns a clear "not configured" result instead of raising.
  - Read-only scope. The one interactive step (browser consent) is isolated in
    `authorize()` and only runs when the user explicitly triggers it locally.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Notification, User
from app.llm.client import LLMError, get_llm

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Emails worth classifying (last 30 days, application-flavored).
_QUERY = (
    'newer_than:30d (application OR "your application" OR interview OR '
    "position OR opportunity OR candidate OR recruiter OR hiring)"
)

CLASSIFY_SYSTEM = (
    "You triage job-search emails. Given an email subject and snippet, classify "
    "it and extract the company and role if present. Be conservative: if it is "
    "not clearly about the recipient's own job application/hiring process, use "
    "kind 'other'."
)

CLASSIFY_PROMPT = """Email subject: {subject}
Email snippet: {snippet}

Return STRICT JSON:
{{
  "kind": "confirmation|interview|rejection|recruiter|other",
  "company": "<company or empty>",
  "role": "<role or empty>"
}}
"""


def _import_libs():
    """Return the google modules, or None if they aren't installed."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        return {
            "Request": Request,
            "Credentials": Credentials,
            "InstalledAppFlow": InstalledAppFlow,
            "build": build,
        }
    except ImportError:
        return None


def configured() -> tuple[bool, str | None]:
    """(ready_to_sync, reason_if_not). Ready means libs + a usable token exist."""
    if _import_libs() is None:
        return False, (
            "Gmail libraries not installed. Run: "
            "uv add google-api-python-client google-auth-oauthlib"
        )
    if not Path(settings.google_client_secrets).exists():
        return False, (
            f"OAuth client-secrets JSON not found at {settings.google_client_secrets}. "
            "Create a Desktop OAuth client in Google Cloud, enable the Gmail API, "
            "and download the JSON there."
        )
    if not Path(settings.google_token_path).exists():
        return False, "Not authorized yet — run a one-time Gmail authorization."
    return True, None


def _load_credentials(libs: dict):
    """Load + refresh stored credentials. Returns creds or None (no valid token)."""
    token_path = Path(settings.google_token_path)
    if not token_path.exists():
        return None
    creds = libs["Credentials"].from_authorized_user_file(str(token_path), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(libs["Request"]())
        token_path.write_text(creds.to_json())
    return creds if creds and creds.valid else None


def authorize() -> tuple[bool, str | None]:
    """One-time interactive consent (opens a local browser). Persists the token.

    Intended to be triggered explicitly by the user on their own machine.
    """
    libs = _import_libs()
    if libs is None:
        return False, "Gmail libraries not installed."
    secrets_path = Path(settings.google_client_secrets)
    if not secrets_path.exists():
        return False, f"OAuth client-secrets JSON not found at {secrets_path}."

    flow = libs["InstalledAppFlow"].from_client_secrets_file(str(secrets_path), SCOPES)
    creds = flow.run_local_server(port=0)
    token_path = Path(settings.google_token_path)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())
    return True, None


def _classify(subject: str, snippet: str) -> dict:
    try:
        out = get_llm().chat_json(
            CLASSIFY_PROMPT.format(subject=subject[:300], snippet=snippet[:600]),
            system=CLASSIFY_SYSTEM,
        )
        return out if isinstance(out, dict) else {"kind": "other"}
    except LLMError:
        return {"kind": "other"}


def _header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def sync(db: Session, user: User, max_messages: int = 25) -> dict:
    """Scan recent emails and file new notifications. Returns counts (+configured)."""
    libs = _import_libs()
    if libs is None:
        return {"configured": False, "reason": configured()[1], "scanned": 0,
                "created": 0, "updated": 0}
    creds = _load_credentials(libs)
    if creds is None:
        ok, reason = configured()
        return {"configured": False, "reason": reason or "Not authorized.",
                "scanned": 0, "created": 0, "updated": 0}

    service = libs["build"]("gmail", "v1", credentials=creds, cache_discovery=False)
    listing = (
        service.users()
        .messages()
        .list(userId="me", q=_QUERY, maxResults=max_messages)
        .execute()
    )
    message_ids = [m["id"] for m in listing.get("messages", [])]

    # dedup: skip emails we've already filed (subject already seen for this user)
    existing = set(
        db.scalars(select(Notification.subject).where(Notification.user_id == user.id))
    )

    created = 0
    for mid in message_ids:
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=mid, format="metadata",
                 metadataHeaders=["Subject", "From"])
            .execute()
        )
        headers = msg.get("payload", {}).get("headers", [])
        subject = _header(headers, "Subject") or "(no subject)"
        snippet = msg.get("snippet", "")
        if subject in existing:
            continue

        verdict = _classify(subject, snippet)
        kind = verdict.get("kind", "other")
        if kind == "other":
            continue

        db.add(
            Notification(
                user_id=user.id,
                application_id=None,
                kind=kind,
                subject=subject[:500],
                body=snippet,
            )
        )
        existing.add(subject)
        created += 1

    db.commit()
    return {
        "configured": True,
        "reason": None,
        "scanned": len(message_ids),
        "created": created,
        "updated": 0,
    }
