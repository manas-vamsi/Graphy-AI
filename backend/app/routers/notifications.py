"""Notifications router — the Gmail-fed inbox of application status updates.

The sync/authorize endpoints degrade gracefully: if the Gmail libraries,
OAuth client-secrets, or token are missing, they return {configured: false}
with a human-readable reason instead of erroring.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import gmail
from app.db.models import Notification
from app.db.session import get_db
from app.llm.client import LLMError
from app.schemas import GmailSyncOut, NotificationOut
from app.security import require_api_key
from app.services.users import get_default_user

router = APIRouter(
    prefix="/notifications", tags=["notifications"], dependencies=[Depends(require_api_key)]
)


@router.get("", response_model=list[NotificationOut])
def list_notifications(db: Session = Depends(get_db)) -> list[Notification]:
    return list(db.scalars(select(Notification).order_by(Notification.created_at.desc())))


@router.get("/gmail/status", response_model=GmailSyncOut)
def gmail_status() -> GmailSyncOut:
    ok, reason = gmail.configured()
    return GmailSyncOut(configured=ok, reason=reason)


@router.post("/sync", response_model=GmailSyncOut)
def sync_inbox(db: Session = Depends(get_db)) -> GmailSyncOut:
    user = get_default_user(db)
    try:
        result = gmail.sync(db, user)
    except LLMError as e:
        raise HTTPException(503, f"LLM unavailable for email triage: {e}") from e
    except Exception as e:  # noqa: BLE001 - surface Gmail/API failures cleanly
        raise HTTPException(502, f"Gmail sync failed: {str(e)[:200]}") from e
    return GmailSyncOut(**result)


@router.post("/gmail/authorize", response_model=GmailSyncOut)
def gmail_authorize() -> GmailSyncOut:
    """One-time interactive consent — opens a browser on the machine running the
    backend. Local-first only; safe to call repeatedly (re-mints the token)."""
    try:
        ok, reason = gmail.authorize()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Gmail authorization failed: {str(e)[:200]}") from e
    return GmailSyncOut(configured=ok, reason=reason)


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: int, db: Session = Depends(get_db)) -> Notification:
    note = db.get(Notification, notification_id)
    if not note:
        raise HTTPException(404, "Notification not found")
    note.read = True
    db.commit()
    db.refresh(note)
    return note
