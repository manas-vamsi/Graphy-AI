# Graphy AI — End-to-End Build Context

> **Hand this file to Claude Code (or any coding agent) as the single source of truth for building the platform.**
> Project name is **Graphy AI**. Local-first, fully free, zero recurring cost. Runs on a developer laptop.

---

## 0. Prime Directives (NEVER violate)

These are hard constraints. Every agent, prompt, and code path must enforce them.

1. **Never fabricate** experience, skills, certifications, education, years of experience, or projects.
2. Resume customization may **only**: reorder, emphasize, rewrite wording, or summarize content that **already exists** in the user's verified profile.
3. Every generated resume is **traceable and auditable** — store which facts came from which source (resume PDF / GitHub / user input).
4. Every application is **recorded** with evidence (screenshots, submitted payload, timestamp).
5. The user must **always** be able to see exactly what was submitted, and **approve before submission** (human-in-the-loop Approval Queue).
6. Data stays **local** (SQLite + ChromaDB + local files + local embeddings). **Reasoning/tailoring** uses the **Google Gemini free API**; only the text sent for reasoning leaves the machine — embeddings, DB, and evidence are fully local. (Ollama remains a drop-in alternative behind the provider abstraction for max privacy.)

> **Anti-hallucination mechanism (build this explicitly):** the Resume Tailoring Agent receives a `verified_facts` set (skills, projects, experience bullets extracted from the resume + GitHub). The LLM prompt instructs it to ONLY use facts from that set, and a **post-generation validator** cross-checks every claim in the output against the `verified_facts` set. Any claim not traceable to a source fact is flagged and stripped. Log all strips to `application_logs`.

---

## 1. Environment (verified on target machine)

| Tool | Version | Notes |
|---|---|---|
| Node | v24.11.1 | frontend |
| npm | 11.6.2 | |
| Python | 3.14 system / **pin 3.12 via uv** | ⚠️ ChromaDB & ScrapeGraphAI lack 3.14 wheels — **backend MUST use 3.12** |
| uv | 0.11.3 | use `uv python pin 3.12` for backend venv |
| Git | 2.52 | |
| LLM provider | **Google Gemini free tier** | reasoning/tailoring — get a free key at https://aistudio.google.com/apikey (no card). Ollama NOT required. |
| Embeddings | **local, free** | `fastembed`/`sentence-transformers` (all-MiniLM-L6) on CPU — no API, no key |
| OS | Windows 11 | use PowerShell-compatible commands |

**First-run setup commands:**
```bash
# Backend
cd backend && uv python pin 3.12 && uv venv && uv sync
uv run playwright install chromium

# Get a free Gemini key at https://aistudio.google.com/apikey
# put it in backend/.env as GEMINI_API_KEY=...
# (local embedding model downloads automatically on first use — no key)

# Frontend
cd frontend && npm install
```

---

## 2. Tech Stack (pinned choices)

- **Frontend:** Next.js 15 (App Router) + TypeScript + Tailwind CSS + shadcn/ui
- **Backend:** FastAPI + Python 3.12, managed by `uv`
- **Database:** SQLite (via SQLAlchemy 2.0 + Alembic migrations). Future: PostgreSQL — keep models DB-agnostic.
- **Vector DB:** ChromaDB (persistent client, local on-disk) with a **local embedding function** (`fastembed`/sentence-transformers all-MiniLM-L6 on CPU) — no API key
- **LLM (reasoning/tailoring):** Google **Gemini** free tier (`gemini-2.5-flash`) behind a provider abstraction (`llm/client.py`) — Ollama is a drop-in alternate
- **Scraping:** ScrapeGraphAI (`SmartScraperGraph`, `SearchGraph`, `SmartScraperMultiGraph`) configured with the Gemini provider
- **Browser automation:** Playwright (Python) — Chromium
- **GitHub:** GitHub REST API (`https://api.github.com`) via `httpx`
- **Gmail:** Gmail API (OAuth2 desktop flow) via `google-api-python-client`

### ScrapeGraphAI key facts (from repo review)
- Install: `pip install scrapegraphai` + `playwright install`
- Uses LLM + graph logic to extract **structured** data from pages — no manual CSS selectors.
- Pipelines we use:
  - `SmartScraperGraph` — extract structured data from one job/career page given a prompt + URL.
  - `SearchGraph` — discover listings across top search results.
  - `SmartScraperMultiGraph` — scrape many career pages in parallel.
- Gemini config shape (free tier):
  ```python
  graph_config = {
      "llm": {"model": "google_genai/gemini-2.5-flash", "api_key": GEMINI_API_KEY, "temperature": 0},
      "verbose": True, "headless": True,
  }
  # Ollama alternate: {"model": "ollama/qwen2.5:7b", "base_url": "http://localhost:11434"}
  ```

---

## 3. Monorepo Layout

```
graphy-ai/
├── GRAPHY_AI_CONTEXT.md          # this file
├── README.md
├── .env.example                  # all secrets/config keys documented
├── docker-compose.yml            # optional: ollama + chroma (future)
├── backend/
│   ├── pyproject.toml            # uv-managed, python 3.12
│   ├── alembic/                  # migrations
│   ├── app/
│   │   ├── main.py               # FastAPI app + router mounting
│   │   ├── config.py             # pydantic-settings, reads .env
│   │   ├── db/
│   │   │   ├── session.py        # SQLAlchemy engine/session
│   │   │   └── models.py         # all 14 tables (see §5)
│   │   ├── vector/
│   │   │   └── chroma.py         # ChromaDB client + 5 collections (see §6)
│   │   ├── llm/
│   │   │   └── ollama_client.py  # thin wrapper: chat() + embed()
│   │   ├── agents/               # the 9 agents (see §4)
│   │   │   ├── github_analyzer.py
│   │   │   ├── resume_intelligence.py
│   │   │   ├── job_discovery.py
│   │   │   ├── matching.py
│   │   │   ├── resume_tailoring.py
│   │   │   ├── cover_letter.py
│   │   │   ├── application.py
│   │   │   ├── tracking.py
│   │   │   └── gmail.py
│   │   ├── routers/              # FastAPI routes, 1 per domain
│   │   │   ├── resumes.py  jobs.py  github.py  applications.py
│   │   │   ├── matches.py  dashboard.py  preferences.py
│   │   ├── services/             # business logic shared by routers/agents
│   │   └── schemas/              # pydantic request/response models
│   ├── data/                     # gitignored: sqlite db, chroma store, uploads, evidence
│   └── tests/
└── frontend/
    ├── package.json
    ├── next.config.ts
    ├── app/
    │   ├── (dashboard)/
    │   │   ├── page.tsx                  # Overview
    │   │   ├── applications/page.tsx
    │   │   ├── resumes/page.tsx
    │   │   ├── github/page.tsx
    │   │   ├── jobs/page.tsx
    │   │   └── approvals/page.tsx        # Approval Queue (human-in-the-loop)
    │   └── api/                          # route handlers proxy to FastAPI
    ├── components/ui/                     # shadcn components
    ├── lib/api.ts                         # typed fetch client to backend
    └── ...
```

---

## 4. Agents (responsibilities + I/O contracts)

Each agent is a Python module with a clear `run(...)` entrypoint. All LLM calls go through `llm/ollama_client.py`. All persist to DB + (where relevant) ChromaDB.

| # | Agent | Input | Output | Persists to |
|---|---|---|---|---|
| 1 | **GitHub Analyzer** | github username/token | languages, frameworks, libs, tools, project categories, skill graph | `github_profiles`, `github_projects`, `skills`, `github_project_embeddings` |
| 2 | **Resume Intelligence** | uploaded PDF | structured profile: skills, experience, projects, education | `resumes`, `skills`, `resume_embeddings` |
| 3 | **Job Discovery** | search query / target sites | normalized job/internship/fellowship listings | `jobs`, `job_embeddings` |
| 4 | **Matching** | resume + github + interests + a job | match score, skill overlap, missing skills, recommendation | `match_scores` |
| 5 | **Resume Tailoring** | a job + `verified_facts` set | role-specific resume version (AI/Backend/Quantum/Research) | `resume_versions` |
| 6 | **Cover Letter** (optional) | a job + verified facts | truthful cover letter | `cover_letters`, `cover_letter_embeddings` |
| 7 | **Application** | approved application + tailored resume | submitted form + screenshots + payload | `applications`, `application_logs`, `application_evidence` |
| 8 | **Tracking** | application events | status, confirmations, timestamps | `applications`, `notifications` |
| 9 | **Gmail** | Gmail OAuth | parsed confirmations/interviews/rejections | `notifications`, `applications` |

**Matching score formula (deterministic + LLM hybrid):**
`score = 0.5 * cosine(resume_embedding, job_embedding) + 0.3 * skill_overlap_ratio + 0.2 * llm_judgment(0..1)`. Always return the breakdown, not just the number.

---

## 5. Database Tables (SQLAlchemy models — 14 tables)

`users`, `resumes`, `resume_versions`, `github_profiles`, `github_projects`, `skills`, `jobs`, `applications`, `cover_letters`, `application_logs`, `application_evidence`, `notifications`, `user_preferences`, `match_scores`.

Key relationships:
- `users` 1—N `resumes` 1—N `resume_versions`
- `users` 1—1 `github_profiles` 1—N `github_projects`
- `jobs` 1—N `match_scores`, `jobs` 1—N `applications`
- `applications` 1—N `application_logs`, 1—N `application_evidence`, 1—1 optional `cover_letters`
- `application_evidence` stores file paths to screenshots + a JSON blob of the exact submitted payload (audit trail).

---

## 6. Vector DB Collections (ChromaDB, 5)

`resume_embeddings`, `job_embeddings`, `github_project_embeddings`, `interest_embeddings`, `cover_letter_embeddings`.
- One persistent ChromaDB client at `backend/data/chroma`.
- Embeddings via **local** `fastembed`/sentence-transformers (all-MiniLM-L6, 384-dim) — no API key, runs on CPU.
- Each record stores metadata linking back to its SQLite row id for traceability.

---

## 7. The End-to-End Flow (the pipeline to build)

```
Resume Upload → GitHub Analysis → Job Discovery → Matching → Resume Tailoring
→ Approval Queue (HUMAN APPROVES) → Application Engine → Tracking → Dashboard
                                              ↑
                                    Gmail Agent feeds status updates
```

**Human-in-the-loop is mandatory at the Approval Queue.** Nothing is submitted to a real employer without explicit user approval in the dashboard.

---

## 8. Dashboard (Next.js pages)

- **Overview:** counts of applications / interviews / rejections / pending, response rate, match score distribution.
- **Applications:** table — company, role, date, status, resume used, cover letter used, evidence (screenshot viewer), match score.
- **Resumes:** versions, history, side-by-side comparison, download each version.
- **GitHub Analysis:** projects, languages, skills, tech breakdown, skill graph viz.
- **Job Discovery:** discovered listings with match scores, filters by type (job/internship/research/fellowship/remote).
- **Approvals:** queue of tailored applications awaiting user sign-off → Approve / Reject / Edit.

---

## 9. Build Phases (ORDER OF WORK)

**Phase 0 — Scaffold:** monorepo, backend (uv+FastAPI+SQLAlchemy+Alembic), frontend (Next.js+Tailwind+shadcn), `.env.example`, healthcheck endpoint, base layout. ✅ runnable empty app.

**Phase 1 — Vertical slice (prove it works end-to-end):**
Resume upload (PDF parse) → Resume Intelligence Agent → store profile + embeddings → manually-entered job → Matching Agent → Resume Tailoring Agent (with anti-hallucination validator) → show tailored resume + match breakdown on dashboard. **No real submission yet.** This proves the core value + the truthfulness guarantee.

**Phase 2 — Discovery + GitHub:** Job Discovery Agent (ScrapeGraphAI) + GitHub Analyzer Agent. Populate jobs and skill graph. Wire Job Discovery + GitHub pages.

**Phase 3 — Application + Approval:** Approval Queue UI, Application Agent (Playwright) with screenshot/evidence capture, Tracking Agent. Submit only after approval.

**Phase 4 — Gmail + polish:** Gmail Agent for status updates, Cover Letter Agent, dashboard analytics, comparisons, exports.

> Build each phase to "runnable + tested" before moving on. Use the `feature-dev` plugin's explore→architect→review loop per agent.

---

## 10. Claude Code plugins to install (recommended set)

```
/plugin install playwright@anthropics          # Application Agent engine — ESSENTIAL
/plugin install security-guidance@anthropics   # credential/secret safety
/plugin install typescript-lsp@anthropics      # frontend code intelligence
/plugin install feature-dev@anthropics         # methodical per-agent build workflow
# optional:
/plugin marketplace add thedotmack/claude-mem && /plugin install claude-mem   # cross-session memory (also uses ChromaDB)
```
Skip: `mcp-server-dev` (only for future MCP work), `Superpowers` (redundant with feature-dev), `code-review` (built-in `/code-review` + `/security-review` already exist).

---

## 11. Secrets & config (`.env.example` keys)

```
# Backend
DATABASE_URL=sqlite:///./data/graphy.db
CHROMA_PATH=./data/chroma
LLM_PROVIDER=gemini                       # gemini | ollama  (provider abstraction)
GEMINI_API_KEY=                           # free key from https://aistudio.google.com/apikey
GEMINI_MODEL=gemini-2.5-flash
EMBED_BACKEND=local                       # local fastembed/sentence-transformers, no key
EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2
# Ollama alternate (only if LLM_PROVIDER=ollama):
# OLLAMA_BASE_URL=http://localhost:11434
# OLLAMA_CHAT_MODEL=qwen2.5:7b
UPLOAD_DIR=./data/uploads
EVIDENCE_DIR=./data/evidence

# GitHub (Personal Access Token, read-only public_repo scope)
GITHUB_TOKEN=

# Gmail API (OAuth desktop app credentials JSON path)
GOOGLE_CLIENT_SECRETS=./secrets/gmail_oauth.json
GOOGLE_TOKEN_PATH=./secrets/gmail_token.json

# Frontend
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```
All `secrets/` and `data/` are gitignored. Never log token values.

---

## 12. What the human must provide

1. **Free Gemini API key** from https://aistudio.google.com/apikey (no card) → `GEMINI_API_KEY`. (No Ollama install needed; embeddings run locally with no key.)
2. **GitHub Personal Access Token** (read-only) → `GITHUB_TOKEN`.
3. **Gmail API OAuth credentials** (Google Cloud Console → enable Gmail API → desktop OAuth client → download JSON) → only needed for Phase 4.
4. Their **resume PDF** + **GitHub username** to test the pipeline.
5. Approve applications in the Approval Queue (the platform never auto-submits without sign-off).
