"""GitHub router — analyze repositories into a skill/project graph."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import github_analyzer
from app.db.models import GithubProfile, GithubProject, Skill
from app.db.session import get_db
from app.llm.client import LLMError
from app.schemas import GithubAnalysisOut, GithubProfileOut, GithubProjectOut
from app.security import require_api_key
from app.services import github_fetch
from app.services.users import get_default_user
from app.vector import chroma

router = APIRouter(prefix="/github", tags=["github"], dependencies=[Depends(require_api_key)])


@router.post("/analyze", response_model=GithubAnalysisOut)
def analyze_github(db: Session = Depends(get_db)) -> GithubAnalysisOut:
    user = get_default_user(db)
    fetched = github_fetch.fetch_all()
    if not any(d.get("repos") for d in fetched.values()):
        raise HTTPException(400, "No repositories found / GitHub token not configured.")

    try:
        analysis = github_analyzer.analyze(fetched)
    except LLMError as e:
        raise HTTPException(503, str(e)) from e

    # lookup fetched repo metadata by name to enrich persisted projects
    repo_meta: dict[str, dict] = {}
    for data in fetched.values():
        for rp in data.get("repos", []):
            repo_meta[rp["name"]] = rp

    # upsert single profile for the local user
    profile = db.scalar(select(GithubProfile).where(GithubProfile.user_id == user.id))
    primary_username = next(iter(fetched.keys()), "")
    if profile is None:
        profile = GithubProfile(user_id=user.id, username=primary_username)
        db.add(profile)
    profile.username = primary_username
    profile.languages = analysis["languages"]
    profile.skill_graph = analysis["skill_graph"]
    db.commit()
    db.refresh(profile)

    # replace projects
    db.query(GithubProject).filter(GithubProject.profile_id == profile.id).delete()
    persisted: list[GithubProject] = []
    for proj in analysis["projects"]:
        meta = repo_meta.get(proj.get("name", ""), {})
        gp = GithubProject(
            profile_id=profile.id,
            name=proj.get("name", ""),
            description=meta.get("description"),
            readme=meta.get("readme"),
            primary_language=meta.get("primary_language"),
            topics=meta.get("topics"),
            technologies=proj.get("technologies", []),
            category=proj.get("category"),
        )
        db.add(gp)
        persisted.append(gp)
    db.commit()

    # refresh github-sourced skills
    db.query(Skill).filter(Skill.user_id == user.id, Skill.source == "github").delete()
    sg = analysis["skill_graph"]
    singular = {"languages": "language", "frameworks": "framework",
                "libraries": "library", "tools": "tool"}
    for cat, category in singular.items():
        for name in sg.get(cat, []):
            db.add(Skill(user_id=user.id, name=name, category=category, source="github"))
    db.commit()

    # embeddings for project semantic search
    for gp in persisted:
        db.refresh(gp)
        doc = f"{gp.name}\n{gp.description or ''}\n{' '.join(gp.technologies or [])}\n{gp.category or ''}"
        chroma.upsert(
            "github_project_embeddings",
            id=f"ghproj-{gp.id}",
            document=doc,
            metadata={"project_id": gp.id, "category": gp.category or ""},
        )

    return GithubAnalysisOut(
        profile=GithubProfileOut.model_validate(profile),
        projects=[GithubProjectOut.model_validate(p) for p in persisted],
        repo_count=sum(len(d.get("repos", [])) for d in fetched.values()),
    )


@router.get("/profile", response_model=GithubProfileOut | None)
def get_profile(db: Session = Depends(get_db)) -> GithubProfile | None:
    user = get_default_user(db)
    return db.scalar(select(GithubProfile).where(GithubProfile.user_id == user.id))


@router.get("/projects", response_model=list[GithubProjectOut])
def get_projects(db: Session = Depends(get_db)) -> list[GithubProject]:
    user = get_default_user(db)
    profile = db.scalar(select(GithubProfile).where(GithubProfile.user_id == user.id))
    if not profile:
        return []
    return list(
        db.scalars(select(GithubProject).where(GithubProject.profile_id == profile.id))
    )
