"""All 14 Graphy AI tables (SQLAlchemy 2.0 typed models).

Traceability is first-class: tailored content links back to source facts, and
applications carry full evidence + logs so the user always knows what was submitted.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(200))
    github_username: Mapped[str | None] = mapped_column(String(100))

    resumes: Mapped[list["Resume"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    github_profile: Mapped["GithubProfile | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    preferences: Mapped["UserPreference | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )


class Resume(TimestampMixin, Base):
    __tablename__ = "resumes"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    filename: Mapped[str] = mapped_column(String(500))
    file_path: Mapped[str] = mapped_column(String(1000))
    raw_text: Mapped[str | None] = mapped_column(Text)
    # Structured profile extracted by Resume Intelligence Agent (verified facts source).
    parsed_profile: Mapped[dict | None] = mapped_column(JSON)

    user: Mapped["User"] = relationship(back_populates="resumes")
    versions: Mapped[list["ResumeVersion"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )


class ResumeVersion(TimestampMixin, Base):
    __tablename__ = "resume_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id"), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"))
    label: Mapped[str] = mapped_column(String(100))  # AI / Backend / Quantum / Research
    content: Mapped[str] = mapped_column(Text)
    # Audit trail: maps each generated claim -> source fact id (anti-hallucination).
    fact_trace: Mapped[dict | None] = mapped_column(JSON)
    stripped_claims: Mapped[list | None] = mapped_column(JSON)  # claims removed by validator

    resume: Mapped["Resume"] = relationship(back_populates="versions")


class GithubProfile(TimestampMixin, Base):
    __tablename__ = "github_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, unique=True)
    username: Mapped[str] = mapped_column(String(100))
    languages: Mapped[dict | None] = mapped_column(JSON)
    skill_graph: Mapped[dict | None] = mapped_column(JSON)

    user: Mapped["User"] = relationship(back_populates="github_profile")
    projects: Mapped[list["GithubProject"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )


class GithubProject(TimestampMixin, Base):
    __tablename__ = "github_projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("github_profiles.id"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    readme: Mapped[str | None] = mapped_column(Text)
    primary_language: Mapped[str | None] = mapped_column(String(100))
    topics: Mapped[list | None] = mapped_column(JSON)
    technologies: Mapped[list | None] = mapped_column(JSON)
    category: Mapped[str | None] = mapped_column(String(100))

    profile: Mapped["GithubProfile"] = relationship(back_populates="projects")


class Skill(TimestampMixin, Base):
    __tablename__ = "skills"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    category: Mapped[str | None] = mapped_column(String(100))  # language/framework/tool/...
    source: Mapped[str] = mapped_column(String(50))  # "resume" | "github" | "user"


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    company: Mapped[str | None] = mapped_column(String(300))
    location: Mapped[str | None] = mapped_column(String(300))
    opportunity_type: Mapped[str] = mapped_column(String(50), default="job")  # job/internship/research/fellowship/...
    description: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(1000))
    source: Mapped[str | None] = mapped_column(String(100))
    raw: Mapped[dict | None] = mapped_column(JSON)

    applications: Mapped[list["Application"]] = relationship(back_populates="job")
    match_scores: Mapped[list["MatchScore"]] = relationship(back_populates="job")


class MatchScore(TimestampMixin, Base):
    __tablename__ = "match_scores"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    score: Mapped[float] = mapped_column(Float)
    skill_overlap: Mapped[list | None] = mapped_column(JSON)
    missing_skills: Mapped[list | None] = mapped_column(JSON)
    recommendation: Mapped[str | None] = mapped_column(Text)
    breakdown: Mapped[dict | None] = mapped_column(JSON)  # semantic/overlap/llm components

    job: Mapped["Job"] = relationship(back_populates="match_scores")


class Application(TimestampMixin, Base):
    __tablename__ = "applications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    resume_version_id: Mapped[int | None] = mapped_column(ForeignKey("resume_versions.id"))
    cover_letter_id: Mapped[int | None] = mapped_column(ForeignKey("cover_letters.id"))
    # pending_approval -> approved -> submitted -> confirmed / interview / rejected
    status: Mapped[str] = mapped_column(String(50), default="pending_approval", index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_payload: Mapped[dict | None] = mapped_column(JSON)  # exact data sent

    job: Mapped["Job"] = relationship(back_populates="applications")
    logs: Mapped[list["ApplicationLog"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    evidence: Mapped[list["ApplicationEvidence"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )


class CoverLetter(TimestampMixin, Base):
    __tablename__ = "cover_letters"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"))
    content: Mapped[str] = mapped_column(Text)
    fact_trace: Mapped[dict | None] = mapped_column(JSON)


class ApplicationLog(TimestampMixin, Base):
    __tablename__ = "application_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    event: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str | None] = mapped_column(Text)

    application: Mapped["Application"] = relationship(back_populates="logs")


class ApplicationEvidence(TimestampMixin, Base):
    __tablename__ = "application_evidence"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    kind: Mapped[str] = mapped_column(String(50))  # screenshot | payload | confirmation
    file_path: Mapped[str | None] = mapped_column(String(1000))
    data: Mapped[dict | None] = mapped_column(JSON)

    application: Mapped["Application"] = relationship(back_populates="evidence")


class Notification(TimestampMixin, Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    application_id: Mapped[int | None] = mapped_column(ForeignKey("applications.id"))
    kind: Mapped[str] = mapped_column(String(50))  # confirmation/interview/rejection/recruiter
    subject: Mapped[str | None] = mapped_column(String(500))
    body: Mapped[str | None] = mapped_column(Text)
    read: Mapped[bool] = mapped_column(Boolean, default=False)


class UserPreference(TimestampMixin, Base):
    __tablename__ = "user_preferences"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, unique=True)
    interests: Mapped[list | None] = mapped_column(JSON)
    desired_roles: Mapped[list | None] = mapped_column(JSON)
    locations: Mapped[list | None] = mapped_column(JSON)
    opportunity_types: Mapped[list | None] = mapped_column(JSON)
    auto_apply: Mapped[bool] = mapped_column(Boolean, default=False)  # always requires approval

    user: Mapped["User"] = relationship(back_populates="preferences")
