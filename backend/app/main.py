"""Graphy AI backend — FastAPI entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.db.session import init_db
from app.security import SECURITY_HEADERS, redact


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    init_db()  # dev convenience; Alembic remains source of truth
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.allowed_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "X-API-Key"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    for header, value in SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    return response


@app.exception_handler(Exception)
async def redacting_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Never leak secrets in error bodies/logs."""
    return JSONResponse(status_code=500, content={"detail": redact(str(exc)) or "Internal error"})


@app.get("/health")
def health() -> dict:
    from app.integrations import status as integrations_status
    from app.llm.client import USAGE

    return {
        "status": "ok",
        "app": settings.app_name,
        "llm_provider": settings.llm_provider,
        "gemini_key_set": bool(settings.gemini_api_key),
        "embed_backend": settings.embed_backend,
        "integrations": integrations_status(),
        "llm_usage": USAGE.summary(),  # incl. cached (90%-discounted) tokens
    }


@app.get("/")
def root() -> dict:
    return {"name": settings.app_name, "docs": "/docs", "health": "/health"}


# Routers (mounted as phases land)
from app.routers import (  # noqa: E402
    applications,
    dashboard,
    github,
    jobs,
    notifications,
    resumes,
)

app.include_router(resumes.router)
app.include_router(jobs.router)
app.include_router(github.router)
app.include_router(applications.router)
app.include_router(dashboard.router)
app.include_router(notifications.router)
