"""Resumes router — upload/parse, match against a job, and truthfully tailor."""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import cover_letter, matching, resume_intelligence, resume_tailoring
from app.config import settings
from app.db.models import CoverLetter, Job, MatchScore, Resume, ResumeVersion, Skill
from app.db.session import get_db
from app.llm.client import LLMError
from app.schemas import (
    CoverLetterIn,
    CoverLetterOut,
    MatchOut,
    ResumeOut,
    ResumeVersionOut,
    TailorIn,
)
from app.security import require_api_key, safe_filename, validate_upload
from app.services.resume_parser import extract_text
from app.services.users import get_default_user
from app.vector import chroma

router = APIRouter(prefix="/resumes", tags=["resumes"], dependencies=[Depends(require_api_key)])


@router.post("/upload", response_model=ResumeOut)
async def upload_resume(
    file: UploadFile = File(...), db: Session = Depends(get_db)
) -> Resume:
    settings.ensure_dirs()
    data = await file.read()
    validate_upload(file.filename, len(data))  # type + size guard
    suffix = Path(safe_filename(file.filename)).suffix or ".pdf"
    stored = Path(settings.upload_dir) / f"{uuid.uuid4().hex}{suffix}"
    stored.write_bytes(data)

    try:
        raw_text = extract_text(str(stored))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    try:
        profile = resume_intelligence.build_profile(raw_text)
    except LLMError as e:
        raise HTTPException(503, f"LLM unavailable: {e}") from e

    user = get_default_user(db)
    resume = Resume(
        user_id=user.id,
        filename=file.filename or stored.name,
        file_path=str(stored),
        raw_text=raw_text,
        parsed_profile=profile,
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)

    # persist skills (replace this user's skills sourced from resume)
    db.query(Skill).filter(Skill.user_id == user.id, Skill.source == "resume").delete()
    for s in profile.get("skills", []):
        if s.get("name"):
            db.add(Skill(user_id=user.id, name=s["name"], category=s.get("category"), source="resume"))
    db.commit()

    # store embedding for matching
    facts = " ".join(resume_intelligence.verified_facts(profile))
    chroma.upsert(
        "resume_embeddings",
        id=f"resume-{resume.id}",
        document=facts or raw_text[:4000],
        metadata={"resume_id": resume.id, "user_id": user.id},
    )
    return resume


@router.get("", response_model=list[ResumeOut])
def list_resumes(db: Session = Depends(get_db)) -> list[Resume]:
    return list(db.scalars(select(Resume).order_by(Resume.created_at.desc())))


@router.get("/{resume_id}", response_model=ResumeOut)
def get_resume(resume_id: int, db: Session = Depends(get_db)) -> Resume:
    resume = db.get(Resume, resume_id)
    if not resume:
        raise HTTPException(404, "Resume not found")
    return resume


@router.post("/{resume_id}/match", response_model=MatchOut)
def match_resume(resume_id: int, job_id: int, db: Session = Depends(get_db)) -> MatchScore:
    resume = db.get(Resume, resume_id)
    job = db.get(Job, job_id)
    if not resume or not job:
        raise HTTPException(404, "Resume or job not found")
    try:
        result = matching.match(resume.parsed_profile or {}, job.description or "")
    except LLMError as e:
        raise HTTPException(503, f"LLM unavailable: {e}") from e

    score = MatchScore(
        user_id=resume.user_id,
        job_id=job.id,
        score=result["score"],
        skill_overlap=result["skill_overlap"],
        missing_skills=result["missing_skills"],
        recommendation=result["recommendation"],
        breakdown=result["breakdown"],
    )
    db.add(score)
    db.commit()
    db.refresh(score)
    return score


@router.post("/{resume_id}/tailor", response_model=ResumeVersionOut)
def tailor_resume(resume_id: int, payload: TailorIn, db: Session = Depends(get_db)) -> ResumeVersion:
    resume = db.get(Resume, resume_id)
    job = db.get(Job, payload.job_id)
    if not resume or not job:
        raise HTTPException(404, "Resume or job not found")
    try:
        result = resume_tailoring.tailor(
            resume.parsed_profile or {}, job.description or "", label=payload.label
        )
    except (LLMError, ValueError) as e:
        raise HTTPException(503, str(e)) from e

    version = ResumeVersion(
        resume_id=resume.id,
        job_id=job.id,
        label=result["label"],
        content=result["content"],
        fact_trace=result["fact_trace"],
        stripped_claims=result["stripped_claims"],
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


@router.get("/{resume_id}/versions", response_model=list[ResumeVersionOut])
def list_versions(resume_id: int, db: Session = Depends(get_db)) -> list[ResumeVersion]:
    return list(
        db.scalars(
            select(ResumeVersion)
            .where(ResumeVersion.resume_id == resume_id)
            .order_by(ResumeVersion.created_at.desc())
        )
    )


@router.post("/{resume_id}/cover-letter", response_model=CoverLetterOut)
def write_cover_letter(
    resume_id: int, payload: CoverLetterIn, db: Session = Depends(get_db)
) -> CoverLetterOut:
    resume = db.get(Resume, resume_id)
    job = db.get(Job, payload.job_id)
    if not resume or not job:
        raise HTTPException(404, "Resume or job not found")
    try:
        result = cover_letter.write(resume.parsed_profile or {}, job.description or "")
    except (LLMError, ValueError) as e:
        raise HTTPException(503, str(e)) from e

    letter = CoverLetter(
        user_id=resume.user_id,
        job_id=job.id,
        content=result["content"],
        fact_trace=result["fact_trace"],
    )
    db.add(letter)
    db.commit()
    db.refresh(letter)

    # store embedding for traceability / future reuse
    chroma.upsert(
        "cover_letter_embeddings",
        id=f"cover-{letter.id}",
        document=result["content"][:4000],
        metadata={"cover_letter_id": letter.id, "job_id": job.id, "user_id": resume.user_id},
    )

    out = CoverLetterOut.model_validate(letter)
    out.stripped_claims = result["stripped_claims"]  # transient audit info
    return out
