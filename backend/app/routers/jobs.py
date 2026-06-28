"""Jobs router — manual job entry for the Phase 1 slice (discovery comes in Phase 2)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import job_discovery
from app.db.models import Job
from app.db.session import get_db
from app.llm.client import LLMError
from app.schemas import DiscoverIn, JobIn, JobOut
from app.security import UnsafeURLError, require_api_key
from app.services.discovery import DiscoveryError, google_search, read_url
from app.vector import chroma

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(require_api_key)])


def _persist_job(db: Session, data: dict) -> Job:
    job = Job(**data)
    db.add(job)
    db.commit()
    db.refresh(job)
    chroma.upsert(
        "job_embeddings",
        id=f"job-{job.id}",
        document=f"{job.title}\n{job.company or ''}\n{job.description or ''}",
        metadata={"job_id": job.id, "type": job.opportunity_type},
    )
    return job


@router.post("", response_model=JobOut)
def create_job(payload: JobIn, db: Session = Depends(get_db)) -> Job:
    return _persist_job(db, payload.model_dump())


@router.post("/discover", response_model=list[JobOut])
def discover_jobs(payload: DiscoverIn, db: Session = Depends(get_db)) -> list[Job]:
    """Discover opportunities from a careers/job URL (or a search query if Google CSE
    is configured). Fetches via Jina Reader (SSRF-guarded) and extracts with the LLM."""
    target = payload.url
    if not target and payload.query:
        hits = google_search(payload.query)
        if not hits:
            raise HTTPException(
                400,
                "Search needs Google CSE (API key + cx). Provide a direct URL instead.",
            )
        target = hits[0]["url"]
    if not target:
        raise HTTPException(400, "Provide a `url` (or a `query` with Google CSE configured).")

    try:
        content = read_url(target)
        found = job_discovery.extract_jobs(content, target)
    except UnsafeURLError as e:
        raise HTTPException(400, f"Unsafe URL blocked: {e}") from e
    except DiscoveryError as e:
        raise HTTPException(502, str(e)) from e
    except LLMError as e:
        raise HTTPException(503, str(e)) from e

    # Honor the requested type when the extractor couldn't classify ("other"/missing).
    for j in found:
        if j.get("opportunity_type") in (None, "", "other"):
            j["opportunity_type"] = payload.opportunity_type
    return [_persist_job(db, j) for j in found]


@router.get("", response_model=list[JobOut])
def list_jobs(db: Session = Depends(get_db)) -> list[Job]:
    return list(db.scalars(select(Job).order_by(Job.created_at.desc())))


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)) -> Job:
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job
