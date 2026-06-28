"""Applications router — the human-in-the-loop apply pipeline.

Lifecycle: pending_approval -> approved -> (submit) -> prepared|submitted.
Nothing is sent to an employer without explicit approval, and submission only
clicks "submit" when the caller passes submit=true.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import application as application_agent
from app.agents import tracking
from app.config import settings
from app.db.models import (
    Application,
    ApplicationEvidence,
    Job,
    Resume,
    ResumeVersion,
)
from app.db.session import get_db
from app.schemas import (
    ApplicationCreateIn,
    ApplicationDetailOut,
    ApplicationOut,
    ApplicationSubmitIn,
)
from app.security import UnsafeURLError, require_api_key
from app.services.users import get_default_user

router = APIRouter(
    prefix="/applications", tags=["applications"], dependencies=[Depends(require_api_key)]
)


def _get(db: Session, app_id: int) -> Application:
    app = db.get(Application, app_id)
    if not app:
        raise HTTPException(404, "Application not found")
    return app


@router.post("", response_model=ApplicationOut)
def create_application(payload: ApplicationCreateIn, db: Session = Depends(get_db)) -> Application:
    user = get_default_user(db)
    if not db.get(Job, payload.job_id):
        raise HTTPException(404, "Job not found")
    app = Application(
        user_id=user.id,
        job_id=payload.job_id,
        resume_version_id=payload.resume_version_id,
        cover_letter_id=payload.cover_letter_id,
        status="pending_approval",
    )
    db.add(app)
    db.commit()
    db.refresh(app)
    tracking.log_event(db, app, "created", "queued for approval")
    db.commit()
    return app


@router.get("", response_model=list[ApplicationOut])
def list_applications(db: Session = Depends(get_db)) -> list[Application]:
    return list(db.scalars(select(Application).order_by(Application.created_at.desc())))


@router.get("/pending", response_model=list[ApplicationOut])
def pending_applications(db: Session = Depends(get_db)) -> list[Application]:
    return list(
        db.scalars(
            select(Application)
            .where(Application.status == "pending_approval")
            .order_by(Application.created_at.desc())
        )
    )


@router.post("/{app_id}/approve", response_model=ApplicationOut)
def approve(app_id: int, db: Session = Depends(get_db)) -> Application:
    app = _get(db, app_id)
    if app.status != "pending_approval":
        raise HTTPException(409, f"Cannot approve from status {app.status!r}")
    tracking.set_status(db, app, "approved", "approved by user")
    db.commit()
    db.refresh(app)
    return app


@router.post("/{app_id}/reject", response_model=ApplicationOut)
def reject(app_id: int, db: Session = Depends(get_db)) -> Application:
    app = _get(db, app_id)
    tracking.set_status(db, app, "rejected", "rejected by user")
    db.commit()
    db.refresh(app)
    return app


@router.post("/{app_id}/submit", response_model=ApplicationDetailOut)
def submit(app_id: int, payload: ApplicationSubmitIn, db: Session = Depends(get_db)) -> Application:
    app = _get(db, app_id)
    if app.status not in ("approved", "prepared"):
        raise HTTPException(409, "Application must be approved before submitting.")
    job = db.get(Job, app.job_id)
    if not job or not job.url:
        raise HTTPException(400, "Job has no application URL to drive.")

    user = get_default_user(db)
    applicant = {
        "name": payload.name or user.name or "",
        "email": payload.email or user.email or "",
        "phone": payload.phone or "",
    }

    resume_file = None
    if app.resume_version_id:
        rv = db.get(ResumeVersion, app.resume_version_id)
        if rv:
            resume = db.get(Resume, rv.resume_id)
            resume_file = resume.file_path if resume else None

    try:
        result = application_agent.apply(
            application_id=app.id,
            job_url=job.url,
            resume_file_path=resume_file,
            applicant=applicant,
            submit=payload.submit,
        )
    except UnsafeURLError as e:
        raise HTTPException(400, f"Blocked URL: {e}") from e
    except Exception as e:  # noqa: BLE001 - surface automation failures cleanly
        tracking.log_event(db, app, "submit_error", str(e)[:500])
        db.commit()
        raise HTTPException(502, f"Automation failed: {str(e)[:200]}") from e

    # persist evidence + payload + logs
    for ev in result["evidence"]:
        db.add(ApplicationEvidence(application_id=app.id, kind=ev["kind"], file_path=ev["file_path"]))
    db.add(
        ApplicationEvidence(
            application_id=app.id, kind="payload", data={"applicant": result["payload"]}
        )
    )
    app.submitted_payload = {"applicant": result["payload"], "resume_file": resume_file}
    for event in result["events"]:
        tracking.log_event(db, app, "automation", event)

    tracking.set_status(db, app, "submitted" if result["submitted"] else "prepared")
    db.commit()
    db.refresh(app)
    return app


@router.get("/{app_id}", response_model=ApplicationDetailOut)
def get_application(app_id: int, db: Session = Depends(get_db)) -> Application:
    return _get(db, app_id)


@router.get("/{app_id}/evidence/{evidence_id}/file")
def get_evidence_file(app_id: int, evidence_id: int, db: Session = Depends(get_db)):
    ev = db.get(ApplicationEvidence, evidence_id)
    if not ev or ev.application_id != app_id or not ev.file_path:
        raise HTTPException(404, "Evidence not found")
    # Path-traversal guard: only serve files that live under the evidence dir.
    base = Path(settings.evidence_dir).resolve()
    target = Path(ev.file_path).resolve()
    if base not in target.parents or not target.exists():
        raise HTTPException(404, "Evidence file missing")
    return FileResponse(str(target))
