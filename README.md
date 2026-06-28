# Graphy AI

Local-first, **free** AI career-automation platform: discover opportunities, build a
**verified** profile from your resume + GitHub, generate **truthful** tailored resumes,
automate applications with human approval, and track everything in one dashboard.

> **Prime directive:** never fabricate. Tailoring may only reorder, emphasize, rewrite,
> or summarize facts that already exist in your verified profile — and every generated
> claim is fact-checked against that profile before you ever see it.

Full architecture & build plan: [`GRAPHY_AI_CONTEXT.md`](./GRAPHY_AI_CONTEXT.md)

---

## Stack
- **Backend:** FastAPI · Python 3.12 (uv) · SQLAlchemy + Alembic · SQLite
- **Vector DB:** ChromaDB with **local** embeddings (all-MiniLM-L6, on CPU, no key)
- **LLM:** Google **Gemini** free tier (swap to Ollama via one env var)
- **Frontend:** Next.js 16 · TypeScript · Tailwind · shadcn/ui

## Prerequisites
- Node 20+, Python (uv handles 3.12), a free Gemini key → https://aistudio.google.com/apikey

## Run

**1. Backend** (`http://localhost:8000`)
```bash
cd backend
uv sync                                   # installs deps into a 3.12 venv
# paste your key into backend/.env  →  GEMINI_API_KEY=...
uv run alembic upgrade head               # create the SQLite schema
uv run uvicorn app.main:app --reload --port 8000
```
API docs at http://localhost:8000/docs · health at `/health`.

**2. Frontend** (`http://localhost:3000`)
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 → **Resumes** → upload a resume → paste a job → **Match** / **Tailor**.

## Status
- ✅ **Phase 0** — scaffold: backend, frontend, DB (14 tables), Chroma (5 collections), LLM abstraction
- ✅ **Phase 1** — resume upload → verified profile → match → truthful tailoring (with anti-hallucination validator)
- ⬜ **Phase 2** — Job Discovery (ScrapeGraphAI) + GitHub Analyzer
- ⬜ **Phase 3** — Approval Queue + Application agent (Playwright) + Tracking
- ⬜ **Phase 4** — Gmail agent + Cover letters + analytics

## What needs a key
| Feature | Needs |
|---|---|
| Resume parse / match / tailor | `GEMINI_API_KEY` (free) |
| Embeddings, DB, uploads | nothing — fully local |
| GitHub analysis (Phase 2) | `GITHUB_TOKEN` (read-only) |
| Gmail tracking (Phase 4) | Gmail OAuth JSON |
