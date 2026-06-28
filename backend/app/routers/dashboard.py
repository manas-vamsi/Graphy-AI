"""Dashboard router — read-only analytics aggregated from the local DB.

Pure SQL aggregation over what's already stored; no external calls. Powers the
Overview page (counts, response rate, match-score distribution, recent activity).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Application,
    ApplicationLog,
    CoverLetter,
    GithubProfile,
    Job,
    MatchScore,
    Notification,
    Resume,
    ResumeVersion,
)
from app.db.session import get_db
from app.schemas import ActivityItem, DashboardSummaryOut, MatchBucket
from app.security import require_api_key

router = APIRouter(prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(require_api_key)])

# Statuses that mean the application reached an employer.
_SUBMITTED = {"submitted", "confirmed", "interview", "offer"}
# Statuses that count as a real response from an employer.
_RESPONDED = {"confirmed", "interview", "offer"}

_MATCH_BUCKETS = [
    ("0–50%", 0.0, 0.5),
    ("50–70%", 0.5, 0.7),
    ("70–85%", 0.7, 0.85),
    ("85–100%", 0.85, 1.01),
]


@router.get("/summary", response_model=DashboardSummaryOut)
def summary(db: Session = Depends(get_db)) -> DashboardSummaryOut:
    # counts per lifecycle status
    by_status: dict[str, int] = {
        status: count
        for status, count in db.execute(
            select(Application.status, func.count()).group_by(Application.status)
        ).all()
    }

    def n(*statuses: str) -> int:
        return sum(by_status.get(s, 0) for s in statuses)

    total = sum(by_status.values())
    submitted = n(*_SUBMITTED)
    responded = n(*_RESPONDED)
    interviews = n("interview", "offer")

    totals = {
        "applications": total,
        "pending": by_status.get("pending_approval", 0),
        "approved": by_status.get("approved", 0),
        "prepared": by_status.get("prepared", 0),
        "submitted": submitted,
        "interviews": interviews,
        "offers": by_status.get("offer", 0),
        "rejected": by_status.get("rejected", 0),
    }
    response_rate = round(100 * responded / submitted, 1) if submitted else 0.0

    # match-score distribution (every score on record)
    scores = list(db.scalars(select(MatchScore.score)))
    match_distribution = [
        MatchBucket(label=label, count=sum(1 for s in scores if lo <= (s or 0) < hi))
        for label, lo, hi in _MATCH_BUCKETS
    ]

    library = {
        "resumes": db.scalar(select(func.count()).select_from(Resume)) or 0,
        "resume_versions": db.scalar(select(func.count()).select_from(ResumeVersion)) or 0,
        "cover_letters": db.scalar(select(func.count()).select_from(CoverLetter)) or 0,
        "jobs": db.scalar(select(func.count()).select_from(Job)) or 0,
    }

    unread = db.scalar(
        select(func.count()).select_from(Notification).where(Notification.read.is_(False))
    ) or 0

    github_analyzed = (db.scalar(select(func.count()).select_from(GithubProfile)) or 0) > 0

    recent = db.scalars(
        select(ApplicationLog).order_by(ApplicationLog.created_at.desc()).limit(8)
    )
    recent_activity = [
        ActivityItem(
            application_id=log.application_id,
            event=log.event,
            detail=log.detail,
            created_at=log.created_at,
        )
        for log in recent
    ]

    return DashboardSummaryOut(
        totals=totals,
        by_status=by_status,
        response_rate=response_rate,
        match_distribution=match_distribution,
        library=library,
        unread_notifications=unread,
        github_analyzed=github_analyzed,
        recent_activity=recent_activity,
    )
