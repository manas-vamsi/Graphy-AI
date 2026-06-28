from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ResumeOut(BaseModel):
    id: int
    filename: str
    parsed_profile: dict | None
    created_at: datetime

    class Config:
        from_attributes = True


class JobIn(BaseModel):
    title: str
    company: str | None = None
    location: str | None = None
    opportunity_type: str = "job"
    description: str
    url: str | None = None


class DiscoverIn(BaseModel):
    url: str | None = None
    query: str | None = None
    opportunity_type: str = "job"


class JobOut(BaseModel):
    id: int
    title: str
    company: str | None
    location: str | None
    opportunity_type: str
    description: str | None
    url: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class MatchOut(BaseModel):
    id: int
    job_id: int
    score: float
    skill_overlap: list | None
    missing_skills: list | None
    recommendation: str | None
    breakdown: dict | None

    class Config:
        from_attributes = True


class TailorIn(BaseModel):
    job_id: int
    label: str = "General"


class GithubProfileOut(BaseModel):
    id: int
    username: str
    languages: dict | None
    skill_graph: dict | None

    class Config:
        from_attributes = True


class GithubProjectOut(BaseModel):
    id: int
    name: str
    description: str | None
    primary_language: str | None
    topics: list | None
    technologies: list | None
    category: str | None

    class Config:
        from_attributes = True


class GithubAnalysisOut(BaseModel):
    profile: GithubProfileOut
    projects: list[GithubProjectOut]
    repo_count: int


class ApplicationCreateIn(BaseModel):
    job_id: int
    resume_version_id: int | None = None
    cover_letter_id: int | None = None


class ApplicationSubmitIn(BaseModel):
    submit: bool = False  # False = prepare + screenshot only (no real submission)
    name: str | None = None
    email: str | None = None
    phone: str | None = None


class ApplicationOut(BaseModel):
    id: int
    job_id: int
    resume_version_id: int | None
    cover_letter_id: int | None
    status: str
    submitted_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class ApplicationLogOut(BaseModel):
    id: int
    event: str
    detail: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class ApplicationEvidenceOut(BaseModel):
    id: int
    kind: str
    file_path: str | None
    data: dict | None
    created_at: datetime

    class Config:
        from_attributes = True


class ApplicationDetailOut(ApplicationOut):
    logs: list[ApplicationLogOut]
    evidence: list[ApplicationEvidenceOut]


class ResumeVersionOut(BaseModel):
    id: int
    resume_id: int
    job_id: int | None
    label: str
    content: str
    fact_trace: dict | None
    stripped_claims: list | None
    created_at: datetime

    class Config:
        from_attributes = True


# --- Phase 4: cover letters ---
class CoverLetterIn(BaseModel):
    job_id: int


class CoverLetterOut(BaseModel):
    id: int
    job_id: int | None
    content: str
    fact_trace: dict | None
    created_at: datetime
    # transient (not persisted — no column): what the validator refused to allow
    stripped_claims: list | None = None

    class Config:
        from_attributes = True


# --- Phase 4: notifications ---
class NotificationOut(BaseModel):
    id: int
    application_id: int | None
    kind: str
    subject: str | None
    body: str | None
    read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class GmailSyncOut(BaseModel):
    configured: bool
    reason: str | None = None
    scanned: int = 0
    created: int = 0
    updated: int = 0


# --- Phase 4: dashboard analytics ---
class MatchBucket(BaseModel):
    label: str
    count: int


class ActivityItem(BaseModel):
    application_id: int | None
    event: str
    detail: str | None
    created_at: datetime


class DashboardSummaryOut(BaseModel):
    totals: dict[str, int]          # applications, submitted, interviews, offers, pending, rejected
    by_status: dict[str, int]       # raw count per lifecycle status
    response_rate: float            # percent 0..100 (responses / submitted)
    match_distribution: list[MatchBucket]
    library: dict[str, int]         # resumes, resume_versions, cover_letters, jobs
    unread_notifications: int
    github_analyzed: bool
    recent_activity: list[ActivityItem]
