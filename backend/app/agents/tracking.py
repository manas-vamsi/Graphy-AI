"""Tracking Agent — records application status, events, and notifications.

Single source of truth for an application's lifecycle so the user always knows
exactly what happened and when.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import Application, ApplicationLog, Notification

VALID_STATUSES = {
    "pending_approval", "approved", "rejected", "prepared",
    "submitted", "confirmed", "interview", "offer", "closed",
}


def log_event(db: Session, application: Application, event: str, detail: str | None = None) -> None:
    db.add(ApplicationLog(application_id=application.id, event=event, detail=detail))


def set_status(db: Session, application: Application, status: str, detail: str | None = None) -> None:
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status {status!r}")
    application.status = status
    if status == "submitted":
        application.submitted_at = datetime.now(timezone.utc)
    log_event(db, application, f"status:{status}", detail)


def notify(db: Session, application: Application, kind: str, subject: str, body: str = "") -> None:
    db.add(
        Notification(
            user_id=application.user_id,
            application_id=application.id,
            kind=kind,
            subject=subject,
            body=body,
        )
    )
