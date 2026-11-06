# RAG Study Assistant
# CLAUDE.md — Project Memory & Conventions

> Read this entire file before touching any code in any session.
> It describes the code **as it actually is** (reviewed 2026-09-11). Where `README.md`
> disagrees, trust this file and the code. Line numbers cited here and in `docs/` drift —
> always read the real file before editing.
> The owner's global rules in `~/.claude/CLAUDE.md` (plan before multi-file changes, type
> hints, `logging` not `print`, no bare `except`, no new dependencies without asking,
> delete dead code) apply here and are not repeated.

---

## What This System Is

An AI study assistant. Users upload PDF/PPTX/DOCX study material; the backend chunks it,
embeds it with Gemini, and indexes it per user in FAISS + BM25. Chat answers questions with
hybrid retrieval plus Tavily web results, generates a cited answer with Gemini 2.5
Flash-Lite, and streams it to a React app over SSE. Also: concept-map generation, quiz
generation, chat sessions with export, thumbs feedback, and email/password + Google OAuth
login.

- Backend: Render — https://rag-study-assistant-api.onrender.com
- Frontend: Vercel — https://rag-study-assistant-chi.vercel.app
- Repo: https://github.com/ArhaanAli04/rag-study-assistant (branch `master`)

---

## Current Status

Update this block at the start and end of every session.

```
Last commit:  day 07 - docs (Checkpoint 6: CLAUDE.md paths and commands, Day 7 outcome, post 9
              line) on feature/day07-refactor-core → PR #8 (draft) into develop. Before it:
              ac99840 Settings + request ID, fbbea8d core/ moves, a467435 src/ → backend/app/
              move (90 renames), cbd20e9 layout doc + brief
Pushed:       master = v0.1.1 (60f52bf), tags v0.1.0 + v0.1.1, 2026-11-02. v0.1.0 = Days 0–3;
              v0.1.1 = unused frontend imports removed (Vercel builds with CI=true, which fails
              on ESLint warnings). Days 4–7 reach master with the Day 10 release (v0.2.0) — the
              first PR-based release (PR develop → master, merge commit, then tag)
Uncommitted:  none
Untracked:    none (planning docx/pdf files, the Tesseract installer — now alone in the old
              root tests/samples/ — and post screenshots in docs/posts/assets/ are gitignored)
Day 7:        The backend is the package backend/app/ (CWD backend/: uvicorn app.main:app;
              tests in backend/tests, pytest from the repo root). Absolute app.* imports, no
              sys.path hacks. core/: config.py (one pydantic-settings Settings for every env
              var, SecretStr secrets, absolute repo-root .env; no os.getenv/load_dotenv left in
              app/), logging.py, request_id.py (pure ASGI middleware: X-Request-ID on every
              response, [request_id] on every app log line), security.py, errors.py. Dockerfile,
              compose, dev.ps1, pytest.ini, alembic and hooks on the new paths; Render needs no
              dashboard change (it runs the Dockerfile CMD). Tests 111 → 134 passed + 1 xfail
              on host and in the container. Map: docs/architecture/layout.md; notes in
              docs/briefs/day07.md
Next:         merge PR #8 into develop, then Day 8 (/run-day 8): regroup modules into
              ingestion/ retrieval/ generation/ services/ schemas/ db/ (pure moves), lazy OCR
              and table imports, test_docx_pdf_utils sample paths
Blockers:     none. Local runtime state was moved by hand to backend/{data,uploads,logs}; a
              checkout from before Day 7 must do the same (Move-Item src\data, src\uploads,
              src\logs backend\) or the app starts with an empty database
```

---

## Repo Structure

```
rag-study-assistant/
├── backend/                  ← the Python project; run the app from here (CWD = backend/)
│   ├── app/                  ← the package, imported as `app.*` (Day 7); flat until Day 8 regroups it
│   │   ├── main.py           ← FastAPI app: all routes, most chat logic, global singletons
│   │   ├── core/             ← config.py (Settings), logging.py, request_id.py, security.py, errors.py
│   │   ├── routes/auth_routes.py ← Google OAuth login/callback, /auth/logout
│   │   └── services/         ← oauth_service.py (Authlib client)
│   ├── tests/                ← offline pytest suite (conftest fakes Gemini, Tavily, Redis) + samples/
│   ├── data/                 ← app.db (SQLite), faiss_indexes/ — gitignored
│   └── logs/, uploads/       ← runtime output — gitignored
├── src/requirements.txt      ← older local pin set that differs from the root file (T3); unused by Docker; deleted Day 10
├── frontend/                 ← React 19 (react-scripts), Tailwind, React Flow, react-markdown
│   └── src/                  ← pages/ components/ contexts/ hooks/ services/ config/ utils/ lib/
├── scripts/                  ← dev.ps1 (Docker dev helper); manual/ (live-service scripts, pre-Day 7 paths until Day 10)
├── alembic/, alembic.ini     ← one revision (feedback fields); not the real migration path
├── docs/                     ← timeline.md (61-day build plan), architecture/layout.md (target package layout + module map), posts/ (LinkedIn series material), improvements.md (gap audit), improvement-tracker.md (status), briefs/, claude-cheatsheet.md, architecture.png
├── .claude/                  ← skills/ (/run-item, /pre-commit), hooks/*.py, settings.json
├── .github/workflows/ci.yml  ← CI: backend, frontend, docker jobs (the required checks)
├── ruff.toml                 ← lint rules for CI, the edit hook and local `ruff check .`
├── fix_db.py, recreate_db.py, migrate_user_model.py   ← one-off SQLite repair scripts
├── Dockerfile, docker-compose.yml                      ← backend + frontend + redis
├── pytest.ini                ← testpaths = backend/tests, pythonpath = backend
└── requirements.txt          ← pinned deps; UTF-16LE with CRLF (the Dockerfile installs this one)
```

### Backend module map (`backend/app/`)

Paths are relative to `backend/app/`. Day 8 regroups the flat modules into `ingestion/`,
`retrieval/`, `generation/`, `services/`, `schemas/` and `db/`; the target path and day of every
module are in `docs/architecture/layout.md`.

| Area | Modules | Notes |
|---|---|---|
| Core (Day 7) | `core/config.py`, `core/logging.py`, `core/request_id.py`, `core/security.py`, `core/errors.py` | `Settings`: every env var, read once at import. `request_id`: per-request ID (`X-Request-ID`) stamped on log lines by `RequestIdFilter`. `security`: JWT, password hashing, and (until Day 9's `api/deps.py`) `get_db` / `get_current_user*`. `logging`: rotating file + console handlers, G8 redaction |
| App & data | `main.py`, `db.py`, `concept_models.py`, `models.py`, `account_service.py` | `db.py`: Base, SQLite engine, ORM models, startup column migrations. `models.py`: `DocumentChunk` data model. `account_service.py`: `delete_user_account` — rows in one transaction, then files, index tombstones, caches (B1) |
| Auth | `core/security.py`, `routes/auth_routes.py`, `services/oauth_service.py` | JWT (HS256, 7-day, no refresh token), pbkdf2_sha256, Google OAuth |
| Ingestion | `indexing_pipeline.py`, `chunk_builder.py`, `chunking.py`, `pdf_utils.py`, `pptx_pipeline.py`, `pptx_utils.py`, `docx_utils.py`, `text_preprocessing.py`, `document_service.py`, `utils_file.py`, `upload_storage.py` | character-based chunks (1000 chars / 100 overlap); hash-based document versioning; `upload_storage.py`: per-user UUID paths + containment check (G7) |
| OCR / tables | `unified_parser.py`, `ocr_utils.py`, `image_preprocessing.py`, `pdf_table_utils.py`, `table_utils.py` | not reachable from `/upload` (images are rejected) |
| Indexes | `embedding_service.py`, `index_builder.py`, `vector_store.py`, `keyword_index.py` | in-memory FAISS + BM25 (see Known Issues) |
| Retrieval | `retrieval_service.py`, `query_decomposer.py`, `query_preprocessor.py`, `reranker.py`, `context_compressor.py`, `web_search_client.py`, `web_scraper.py` | `reranker.py` does no real reranking |
| Generation | `llm_client.py`, `topic_classifier.py`; user-facing error messages in `core/errors.py` | retry + circuit breaker live in `LLMClient` |
| Sessions & caches | `session_service.py`, `semantic_cache.py`, `cache.py`, `web_cache.py` | |
| Concept maps | `concept_map_service.py`, `hybrid_retriever.py`, `concept_extractor.py`, `concept_map_schemas.py` | |
| Eval / experiments | `rag_metrics.py`, `rag_eval_runner.py`, `sample_eval_data.py`, `manual_eval.py`, `cache_tuner.py` | non-functional or print-only; all import `main` |
| Ad-hoc scripts | `add_concept_tables.py`, `add_doc_version.py`, `run_migration.py`, `update_existing_sessions.py`; the old `src/test_*.py` manual scripts now live in `scripts/manual/` (Day 5) | the `app/` scripts run as `python -m app.<name>` from `backend/`; the manual scripts call live services, still use pre-Day 7 paths (Day 10) and are never collected by pytest (`pytest.ini` → `backend/tests/` only) |
| Dead code | `frontend.py` (Streamlit stub), `document_delete_service.py` (never called) | |

Frontend dead code: `components/MessageBubble.js` — the chat renders `components/MessageList.js`.

---

## Tech Stack (actual)

| Layer | Technology |
|---|---|
| Backend | FastAPI, SQLAlchemy (sync `Session`), Pydantic v2; Python 3.11 (Docker) / 3.12 (local `venv`); code needs ≥ 3.10 |
| LLM | Gemini `gemini-2.5-flash-lite` via `google-genai` |
| Embeddings | Gemini `gemini-embedding-001`, L2-normalized, one API call per text |
| Vector search | FAISS `IndexFlatL2`, one global index, user filter applied after search |
| Keyword search | `rank-bm25` (`BM25Okapi`), rebuilt over the full corpus on every add |
| Web search | Tavily (`search_depth="advanced"`) + domain allowlist + BeautifulSoup scraping |
| Cache | Redis (`redis-py`) |
| Database | SQLite at `backend/data/app.db` |
| Auth | python-jose JWT, passlib, Authlib Google OAuth; token kept in browser `localStorage` |
| Parsing | PDF/PPTX/DOCX utilities, camelot + pdfplumber tables, Tesseract OCR |
| Frontend | React 19, react-scripts 5, Tailwind 3, React Flow 11 + dagre, react-markdown + remark-gfm, jsPDF, html-to-image, lucide-react |
| Deploy | Docker; Render (backend), Vercel (frontend); `docker-compose.yml` for the local full stack |
| CI | GitHub Actions (`.github/workflows/ci.yml`); ruff 0.15.18 pinned in the CI job only (not in `requirements.txt`), rules in `ruff.toml` |

Installed but never imported in `backend/app/`: `langchain*`, `langgraph*`, `langsmith`, `instructor`,
`tiktoken`, `qdrant-client`. `ragas` is imported only by the broken `rag_metrics.py`;
`streamlit` only by the dead `frontend.py`.

**README drift** — claimed in `README.md` but not true today: sentence-transformers MiniLM
embeddings (now Gemini), cross-encoder / BM25 "reranking" (it is score fusion plus a no-op),
PostgreSQL, refresh tokens, rate limiting, image / handwritten-note upload, quizzes built from
uploaded documents with source references, persisted quiz performance tracking, Python 3.9+,
React 18.

---

## How Requests Flow

**Upload** — `POST /upload`: extension check (`.pdf` / `.pptx` / `.docx`, ≤ 50 MB) → save to a
server-generated `uploads/{user_id}/{uuid}{ext}` (resolved path must stay inside `uploads/`; the
client's basename is kept only as the display name) → `register_upload`: a new name or hash
creates a new version of `(user_id, file_name)`; an identical re-upload returns the existing row —
if that row is already per-user the new copy is deleted, if it points at a pre-Day 3 flat path the
row is moved to the new per-user copy (the shared legacy file is left alone) →
`IndexingPipeline` on the row's `file_path`, with `file_name` passed for citations: chunk → embed →
FAISS add + BM25 rebuild → `User.doc_version += 1`. An identical re-upload is still re-indexed
(duplicate chunks, I6).

**Chat** — the frontend only calls `GET /chat/stream` (`ChatWindow.js`); `POST /chat` is an
older, divergent copy of the same pipeline.
1. Auth from the `?token=` query param → keyword safety check → semantic cache lookup (a hit is replayed as SSE)
2. Get/create session → load the last 20 messages → log the user message → LLM topic tagging while the session topic is "General"
3. `QueryDecomposer` (regex split) → for each sub-query, `hybrid_retrieve`: L1 in-process cache → FAISS + BM25 → min-max normalize → 0.6/0.4 fusion → confidence heuristic (0–100) → Tavily chunks (always: 3 if confidence < 60, else 2) → "rerank" (re-sort by existing score) → top 5 → parent-page expansion
4. `SimpleContextCompressor`: top 6 chunks, 800 characters each
5. Grounding level from confidence: strict ≥ 70, loose ≥ 30, else none (model knowledge allowed)
6. Gemini payload: system instruction (grounding + answer-mode rules) + prior turns as `contents` + a final user turn holding the retrieved context and the question
7. SSE events: `metadata` → `token`… → `message_id` → `[DONE]`; then the answer is stored in the semantic cache. Queries with confidence < 30 are logged to `failed_queries`.

**Concept map** — `POST /api/concepts/generate` → `ConceptMapService` → `ConceptMapRetriever`
(web by default; the documents path is broken, see Known Issues) → `ConceptExtractor` (Gemini,
JSON parsed by hand) → saved as `ConceptMap` / `ConceptMapNode` → React Flow + dagre layout.

**Quiz** — `POST /quiz`: a single Gemini prompt built from the topic alone (general knowledge,
not the user's documents); returns plain text, unparsed and not persisted.

---

## Feature Status

### Working
- Email/password and Google OAuth login; profile, change password, user stats
- PDF/PPTX/DOCX upload, hash-based versioning, per-user hybrid retrieval
- Streaming chat with citations, confidence, grounding levels, three answer modes (`quick` / `detailed` / `step_by_step`; the frontend sends `step-by-step`, normalized since Day 2 — before that it silently got the detailed prompt), multi-turn history (commit 73d8bae)
- Tavily web augmentation with a domain allowlist; Redis web-result cache (1 h)
- Sessions: list, rename, delete, automatic topic tags; chat export to Markdown / PDF (frontend)
- Thumbs up/down feedback → `messages.feedback` and `failed_queries`; `GET /analytics/failed-queries`
- Concept maps from web context: generate, list, view, delete, statistics; PNG / JPEG export
- Quiz generation by topic and difficulty
- LLM retry with backoff (non-streaming) and a circuit breaker; user-friendly error messages
- Docker images and docker-compose (backend, frontend, Redis)
- CI on GitHub Actions (Day 6, `.github/workflows/ci.yml`): `backend` (Python 3.11, ruff, offline pytest — no secrets), `frontend` (Node 24, `npm ci`, Jest, CRA build with `CI=true`), `docker` (both images, no push); required on `master` and `develop` by branch protection

### Present but partial, stubbed, or broken (IDs → `docs/improvements.md`)
- Reranker only re-sorts by the existing score (R1); query decomposition is regex (R2); fusion is min-max + fixed weights (R4)
- Semantic cache (per-user since Day 1, G6) ignores the conversation, has no TTL, unvalidated threshold (CO5); linear scan (CO1)
- Prompt-injection guard (G1, Day 2) is a narrow phrase blocklist in `chat_guards.py` (replaces `sanitize_query()`), called at the top of both chat endpoints; refusals go out over SSE and are not stored — a stop-gap until G3. `verify_answer()` is never called (G2); keyword safety lists differ between endpoints (G3)
- RAGAS eval is non-functional (E1); word-overlap metrics (E2); hardcoded sample eval data and no retrieval metrics (E4)
- Concept extraction hand-parses JSON (S1); embeddings use one call per chunk (I3); sub-queries are retrieved serially (CO2)
- Alembic is configured but effectively unused (see Known Issues)

### Not present
- Persistent vector / keyword indexes; token counting and budgets (C1); token-usage logging (CO4)
- History-aware query rewriting (C2); retrieval-based conversation memory (C3)
- Indirect prompt-injection defenses (G5); request tracing (O1)
- Retrieval eval harness (E4); golden eval set + CI eval gate (E3); CD — deploys gated on CI, staging, post-deploy checks (Days 21–22; Render and Vercel still auto-deploy `master` on push)
- Query expansion / HyDE (R3); agentic tool use (A1); ANN or per-user indexes (I1); embedding cache (CO3)
- Rate limiting, refresh tokens, PostgreSQL, quiz persistence
- Frontend tests beyond 5 files / 11 tests: `components/MessageList.test.js`, `components/ChatWindow.test.js` (refusal and normal stream), `components/AccountSettingsModal.test.js`, `AccountDeletionFlow.test.js`, `pages/LoginPage.test.js` (login + App smoke test, Day 5). No tests for documents, concept maps, quiz or sessions sidebar. Run with `cd frontend; npm test -- --watchAll=false`

---

## Planned & Deferred

`docs/improvement-tracker.md` is the source of truth for status; `docs/improvements.md` holds
the evidence and direction for each ID. When status changes, update the tracker, not this file.

- **P0 — do first:** G6, G7, G8, G4, G1, O2, E1, E4, R1, I4, I5, R5, B1
- **P1 — planned:** G2, G3, G5, E2, S1, O1, R2, R3, C1, C2, I3, CO1, CO2, CO4, CO5, I6, B2, T1, T2
- **P2 — deferred until usage grows:** R4, E3, C3, A1, I1, I2, CO3, T3

Order: `docs/timeline.md` sequences every item (plus Docker, refactor, CI/CD, Langfuse,
LangGraph, study-feature and UI work) into 61 days — one day per session, started with
`/run-day <N>`. It moves I4/I5/I6 to the pgvector migration (Day 15) and E4 to just after the
refactor (Day 11). Hosting decided 2026-11-04: **Supabase** for Postgres + pgvector (Day 13) and
file storage (Day 15), kept awake by a scheduled GitHub workflow. Added 2026-11-04:
**Projects** (Days 18–20, a project = a course: its own files, instructions and chats),
**Connectors** (Days 40–43: Google Drive Docs/Sheets/Slides import, Google export, web page by
URL, YouTube lectures, Notion) and **memory across chats** (Days 53–55, with a Memory page).
New study features (Days 44–52, project-aware): concept catalogue, mastery model + Progress
page, adaptive Practice quiz, flashcards, living concept map, PDF citation viewer, Feynman mode,
study guide. Deferred: exam planner (builds on the mastery model), Google Calendar, OneDrive.
See `docs/claude-cheatsheet.md` for groupings and prerequisites.

---

## Known Issues (tracked in `docs/improvements.md`)

Found while writing this file; evidence and direction live under each ID.

| Issue | ID | Priority |
|---|---|---|
| FAISS and BM25 indexes vanish on every restart or deploy | I4 | P0 |
| Concept maps search a separate, empty index, so "use documents" finds nothing | R5 | P0 |
| Deleting a document leaves its chunks searchable | I5 | P0 |
| Re-uploading an identical file duplicates its chunks | I6 | P1 |
| Fixed Day 3: uploads go to `uploads/{user_id}/{uuid}{ext}` with a containment check. Residual: rows created before Day 3 still point at flat `uploads/<name>` paths, one of them shared by users 1 and 2 (rebuilt Day 16) | G7 | Done |
| Fixed Day 3: `DELETE /user/delete` removes all 7 tables' rows, files, FAISS + BM25 entries (tombstones) and caches. Residuals: tombstoned vectors stay in memory until restart; a deleted user's `query_cache:*` keys live ≤ 1 h; SQLite reuses freed user ids (Postgres, Day 13) | B1 | Done |
| Confidence compared on the wrong scale (`/chat` thresholds, forced-web cap) | B2 | P1 |
| Fixed Day 5: `pytest.ini` uses `[pytest]`, so `testpaths` / `pythonpath` apply; the manual `src/test_*.py` scripts moved to `scripts/manual/` and are never collected | T1 | Done |
| Image and PPTX-slide table extraction silently returns nothing: three OpenCV wheels share `cv2` and a non-contrib build wins (confirmed in the backend image too); `test_table_extraction_on_image` is a strict xfail until the Day 10 fix | B3 | P1 |
| Fixed Day 5: concept-map generation returned 500 whenever a node had empty sources (`concept_extractor` wrapped the whole source list) | B4 | Done |
| Alembic targets the wrong database and misses the concept-map models | T2 | P1 |
| Dead code, drifted requirements files, unused deps, installer still in git history | T3 | P2 |

---

## Conventions for This Repo

- **No backend work without its UI (owner's rule).** Every user-visible backend capability — a new endpoint, response field, status, flag, score, or feature — ships with its frontend integration **in the same day/PR**: the screen or control that uses it, plus loading, empty, and error states. Never "UI later". Briefs list the UI changes for every deliverable; if something is genuinely backend-only (internal refactor, tracing, migrations), the brief says so explicitly. The UI overhaul phase restyles existing screens — it is not where features first get wired in.
- **Run the backend from `backend/`** (`uvicorn app.main:app`). The package is `app`: imports are absolute (`from app.db import User`), never bare module names or relative imports, and nothing inside `backend/` edits `sys.path`. `pytest.ini` puts `backend/` on the path for tests; Alembic adds it itself. Dependencies point down only (`api` → `services` → `retrieval` / `generation` / `ingestion` → `db` → `core`); rules and the module map are in `docs/architecture/layout.md`.
- **Configuration comes only from `app.core.config.settings`** (Day 7). No `os.getenv` or `load_dotenv` in `backend/app/`; a new variable is a `Settings` field plus an `.env.example` entry. Secrets are `SecretStr`: read them with `.get_secret_value()` at the call site and never log `settings`. `settings` is built once at import, so tests override fields with `monkeypatch.setattr(settings, ...)`; a later `setenv` doesn't reach it.
- **Scope all user data by `user_id`.** Every search filter, cache key, and stored file path must include the user. Index metadata stores `user_id` as a **string** (`str(user.id)`); filters must use the same type. Prefer scoping the Redis key itself (as `semantic_cache:{user_id}` does) over filtering a shared list.
- **Bump `User.doc_version`** whenever a user's document set changes — the L1 retrieval cache, Redis query cache, and semantic cache all key on it.
- **`/chat` and `/chat/stream` duplicate the pipeline.** Mirror any change in both until they are consolidated (see Open Decisions). The frontend uses only `/chat/stream`.
- **Retrieved text is untrusted** (uploaded documents and web pages). Never put it in the system instruction; keep it delimited in the final user turn (G5).
- **Keep the prompt prefix stable.** Don't add new per-turn variation to the system instruction or the start of history; variable content belongs in the final user turn (CO4).
- **Eval and experiment code must not `import main`.** Importing `main` builds the whole app (a Gemini embedding call, Redis and LLM clients). Construct `IndexBuilder` / `RetrievalService` directly.
- **Measure retrieval and prompt changes** with the eval harness once E4 exists, and record before/after numbers in the tracker's Notes column.
- **`requirements.txt` is UTF-16LE with CRLF.** Preserve the encoding when editing. Docker installs the root file; `src/requirements.txt` is a different, older local pin set (it adds `torch` and `transformers` and lacks `Authlib` and `bcrypt`), so don't treat it as a mirror (T3).
- **Secrets live only in the root `.env`** (gitignored). `frontend/.env.production` **is tracked** and must hold only public values (API URL, Google client ID).
- **Git flow** (since Day 1): `master` = released code, `develop` = integration branch.
  - **Branch protection (since Day 6), on both `master` and `develop`:** every change lands through a PR (0 approvals — solo repo); the required checks are exactly the three CI jobs `backend`, `frontend`, `docker` (bound to the GitHub Actions app; Vercel and GitGuardian checks are not required); branches need not be up to date; force-pushes and deletions are blocked; **administrators included** — direct pushes to either branch are rejected, for the owner too. Renaming a CI job means updating both protection rules first, or every PR waits forever.
  - Each timeline day runs on `feature/dayNN-<ids>-<slug>`, branched from `develop`, and is merged back into `develop` through a PR (`gh pr create --base develop`, then `gh pr merge <N> --merge --delete-branch`) once CI is green.
  - **Release** (every 3–5 days, marked in `docs/timeline.md`): a PR `develop` → `master`, merged with a merge commit (`gh pr merge <N> --merge` — the PR equivalent of `--no-ff`; never squash or rebase a release), then tag the merge commit on `master`: `git checkout master; git pull origin master; git tag vX.Y.Z; git push origin vX.Y.Z`.
  - **Hotfix:** branch `hotfix/<slug>` from `master`, PR into `master` (merge commit), tag a patch version, then a PR `master` → `develop` so `develop` gets the fix too.
  - Nothing was pushed before the Day 3 release (commit 972bfc3 documents the G6/G7/G8 holes).
  - Commit messages use the "day NN - description" style. Never force-push `develop` or `master` (also blocked by protection).

---

## Key Commands (PowerShell, from repo root)

There is no Makefile.

```powershell
# Backend — GEMINI_API_KEY must be set: IndexBuilder makes an embedding call at startup
.\venv\Scripts\Activate.ps1
cd backend; uvicorn app.main:app --reload  # http://localhost:8000  (Swagger UI at /docs)

# Redis — must be running before the first chat request
docker compose up redis                   # or a local redis-server

# Frontend
cd frontend; npm install; npm start       # http://localhost:3000

# Docker-first dev (Day 4): docker-compose.yml + docker-compose.override.yml
#   backend http://localhost:8000 (backend/app/ bind-mounted, --reload), frontend http://localhost:3000
#   (CRA dev server), Redis on host port 6380. Data, uploads, logs live in named volumes.
Copy-Item .env.example .env               # first time only; fill in the REQUIRED values
.\scripts\dev.ps1 up                      # build + start; also: down, logs [service], test, shell [service]
docker compose up --build                 # the same, in the foreground

# The stack as deployed (Render builds this backend image): base file only, no override
docker compose -f docker-compose.yml up --build

# Tests — offline: no API keys, no network, no Redis (backend/tests/conftest.py fakes them); from the
# repo root, pytest.ini limits collection to backend/tests/ and puts backend/ on the path
python -m pytest
.\scripts\dev.ps1 test                    # the same suite in the backend container (Linux, Python 3.11)

# Lint — the same ruff.toml rules CI and the edit hook enforce (bug-only today; Day 10 tightens them)
ruff check .

# CI (GitHub Actions, .github/workflows/ci.yml) — runs on every PR into and push to develop/master
gh pr checks <N>                          # the three required jobs: backend, frontend, docker
gh run list --branch develop --limit 5    # recent runs; gh run view <id> --log-failed for a red one

# Ad-hoc eval scripts (need live Gemini + Redis; run from backend/ as modules until Day 10 moves them)
cd backend; python -m app.rag_eval_runner
```

---

## Environment Variables

Every backend variable is a field of one pydantic-settings class, `Settings` in
`backend/app/core/config.py` (Day 7), built once at import as `settings`. Precedence: real
environment variables → the repo-root `.env` (an absolute path, so the CWD doesn't matter; skipped
when absent, as in Docker and CI) → field defaults. A missing required variable stops startup
with one `ValidationError` that lists all of them.

| Variable | Required | Used by / default |
|---|---|---|
| `GEMINI_API_KEY` | yes — startup fails without it | LLM, embeddings, topic classifier, concept extractor |
| `TAVILY_API_KEY` | for web search | `web_search_client.py`; if missing, web chunks are silently skipped |
| `JWT_SECRET_KEY` | yes | JWT signing (`core/security.py`) and `SessionMiddleware` |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` | yes — settings validation fails without them | `services/oauth_service.py` |
| `JWT_ALGORITHM`, `JWT_EXPIRATION_MINUTES` | no | `HS256`, `10080` (7 days) |
| `REDIS_URL` | no | Query cache (`cache.py`) and web cache (`web_cache.py`); default `redis://localhost:6379/0`. Locally `.env` sets `redis://localhost:6380/0` (compose maps Redis to host port 6380); in Docker compose sets `redis://redis:6379/0` |
| `SEMANTIC_CACHE_REDIS_URL` | no | Semantic cache (`semantic_cache.py`). Unset → `REDIS_URL` → `redis://localhost:6379/1`. Docker: `redis://redis:6379/1`. Render sets only `REDIS_URL`, so there the semantic cache still shares DB 0 |
| `BASE_URL`, `FRONTEND_URL` | no | OAuth redirects; `http://localhost:8000`, `http://localhost:3000` |
| `ALLOWED_ORIGINS` | no | Comma-separated CORS allowlist (entries trimmed). Default: `http://localhost:3000,http://localhost:8000,https://rag-study-assistant-chi.vercel.app`. On Render: only `https://rag-study-assistant-chi.vercel.app` |
| `TESSERACT_PATH`, `PORT` | no | OCR binary path, set as pytesseract's `tesseract_cmd` by `ocr_utils.py`; unset → `tesseract` on `PATH`. Windows host `.env`: the `tesseract.exe` path; the Docker image sets `ENV TESSERACT_PATH=/usr/bin/tesseract` (so Render gets it without compose), and compose sets it again because `env_file: .env` would otherwise pass the Windows path in. uvicorn port in the Dockerfile (default 8000) |

`.env.example` lists every backend variable with placeholders; keep it in sync when adding one.
`DATABASE_URL` is not read by anything (SQLite path is hardcoded in `db.py`) — it returns on Day 13.

Frontend (`frontend/.env`, `frontend/.env.production`): `REACT_APP_API_URL` (default
`http://localhost:8000`), `REACT_APP_GOOGLE_CLIENT_ID`. CRA inlines these at **build** time; the
Docker nginx build takes `REACT_APP_API_URL` as a build arg (compose passes localhost) because
otherwise `.env.production` points it at Render.

**Node.js version — keep three places in sync:** Vercel's project setting *Node.js Version* is
**24.x** (production builds), CI uses Node 24 (`ci.yml`, `setup-node`), and `frontend/Dockerfile`
uses `node:24-alpine`. Changing one means changing all three. (The local machine runs Node 22.)

---

## Data & State

| What | Where | Survives restart? |
|---|---|---|
| Users, sessions, messages, documents, failed queries, concept maps | SQLite `backend/data/app.db` (Docker: named volume `data` at `/app/backend/data`, separate from the venv's file) | yes on local disk / Docker volume |
| Uploaded files | `backend/uploads/{user_id}/{uuid}{ext}` (since Day 3; older rows: flat `uploads/<name>`); `Document.file_path` is relative to the CWD (`backend/`); display name in `Document.file_name` | yes locally; Docker: named volume `uploads` at `/app/backend/uploads`; Render: no disk, lost on every deploy |
| FAISS vectors + chunk metadata (including chunk text) | process memory | **no** |
| BM25 corpus | process memory | **no** |
| L1 retrieval cache (≤ 256 entries) | class-level dict in `RetrievalService` | no |
| Logs | `backend/logs/app.log` (rotating, 5 MB × 3, `[request_id]` on every line since Day 7; Docker: named volume `logs` at `/app/backend/logs`) | yes |

On Render, local files (including SQLite) persist across deploys only if a persistent disk is
attached — not verified for this deployment.

### Redis key schema

```
query_cache:{sha256(user_id::doc_version::query)}  DB 0            TTL 3600s  /search results                cache.py
websearch:{query}                                  DB 0            TTL 3600s  Tavily chunks, no embeddings   web_cache.py
semantic_cache:{user_id}                           SEMANTIC_CACHE  no TTL     one JSON list of ≤ 64 entries
                                                   _REDIS_URL's DB            per user; entries also carry
                                                   (Docker: 1;                user_id, doc_version, mode     semantic_cache.py
                                                   Render: 0)
```

**Legacy key (pre–Day 1):** `semantic_cache_entries` held every user's entries in one list.
The code no longer reads it, but it still holds leaked data. Delete it on **both DB 0 and DB 1**,
because which DB it landed in depended on whether `REDIS_URL` was set:
- Locally: `docker exec rag-redis redis-cli -n 0 DEL semantic_cache_entries` and the same with `-n 1`.
- On Render's Redis: the same `DEL` on DB 0 and DB 1 (Day 3 release checklist).

When adding a key: list it here with its TTL and how it is scoped to the user.

---

## API Endpoints

No version prefix; concept-map routes live under `/api/concepts`.

```
Auth       POST /register · POST /login · POST /change-password · GET /me
           GET /auth/google/login · GET /auth/google/callback · POST /auth/logout
User       GET /user/profile · PUT /user/profile · GET /user/stats · DELETE /user/delete
Documents  POST /upload · GET /documents · DELETE /documents/{doc_id} · POST /search
Chat       GET /chat/stream (SSE, ?token=) · POST /chat · POST /messages/{message_id}/feedback
           GET /analytics/failed-queries
Sessions   GET /sessions · GET /sessions/{session_id}/messages · DELETE /sessions/{session_id}
           PATCH /sessions/{session_id}/rename
Quiz       POST /quiz
Concepts   POST /api/concepts/generate · GET /api/concepts/maps · GET /api/concepts/maps/{map_id}
           DELETE /api/concepts/maps/{map_id} · GET /api/concepts/statistics
Health     GET /health
```

---

## Design Choices (as implemented — understand before proposing alternatives)

**Hybrid vector + BM25.** Embeddings capture meaning but miss exact tokens (acronyms, formula
names, identifiers); BM25 catches those. Current fusion is min-max normalization with fixed
0.6 / 0.4 weights; R4 proposes Reciprocal Rank Fusion.

**Confidence-based grounding levels.** When retrieval looks strong, the model is held to the
context ("strict"); when it doesn't, the model may fall back to general knowledge instead of
refusing. The confidence score driving this is a heuristic that has never been validated
against retrieval quality (E4).

**`doc_version` in cache keys.** Invalidation by versioning: uploading or deleting a document
bumps a per-user counter, so stale cache entries simply stop matching — nothing has to be
found and deleted.

**Parent-page expansion.** Small chunks match precisely; candidates sharing a page with a top
hit are then grouped into one larger "parent" block so the model gets surrounding context
(small-to-big retrieval).

**Native multi-turn `contents`.** Prior turns are sent as real user/model turns
and retrieved context is attached only to the current turn, so old context isn't re-sent
every turn and the model can resolve references across turns.

**Web-domain allowlist.** Limits web augmentation to academic and reference sources — but
several allowlisted sites host user-editable content, so it is not a trust boundary (G5).

**Circuit breaker in `LLMClient`.** After 3 consecutive failures, calls are refused for 60 s
so a Gemini outage fails fast instead of stacking retries. State is per process.

---

## Open Decisions (ask the owner before acting)

- **Migrations:** make Alembic the real path (fix the URL, import all models in `env.py`) vs. keep the `db.py` startup migrations. Either way, retire the one-off scripts.
- **Chat endpoints:** delete `POST /chat` (the frontend only streams) vs. extract a shared pipeline that both call.
- **Index persistence — decided 2026-11-04:** pgvector + Postgres full-text on Supabase (Days 13–16), uploaded files in Supabase Storage (Day 15). Render's filesystem is ephemeral, so nothing durable stays on it; `qdrant-client` can go with the Day 10 dependency cleanup.
- **Dependencies:** remove unused packages vs. keep those tied to planned items (`tiktoken` → C1, `instructor` → S1, `langsmith` → O1, `langgraph` → A1); reconcile or delete `src/requirements.txt`, which has drifted from the root file.
- **Dead code and repo hygiene:** delete `MessageBubble.js`, `backend/app/frontend.py`, and `document_delete_service.py` (or wire it in). The Tesseract installer is untracked now but still in git history; purging it would need a history rewrite and force-push.

---

## Claude Code Setup

- **Skills** (`.claude/skills/`, user-invoked only): `/run-day <N>` reads Day N of `docs/timeline.md`, writes a brief to `docs/briefs/dayNN.md`, stops for approval, then implements checkpoint by checkpoint — the default way to start a day; `/run-item <ID>` does the same for a single tracker item outside the timeline; `/pre-commit` runs checks and reports, with no git writes.
- **Hooks** (`.claude/settings.json` → `.claude/hooks/*.py`): destructive-command guard (Bash and PowerShell), session-start context (git state and In Progress items), ruff check on edited `.py` files (rules from `ruff.toml`, the same set CI enforces), and reminders after editing this repo's trap files.
- **Workflow, anchor and resume prompts:** `docs/claude-cheatsheet.md`.

## What Claude Must Do at the Start of Every Session

1. Read this file in full (it is loaded automatically).
2. Use the session-context hook output, or run `git status` and `git log --oneline -10` — there is often uncommitted work.
3. Read **Current Status** above, the relevant rows of `docs/improvement-tracker.md`, and the item's brief in `docs/briefs/` if one exists.
4. Read the actual source files before editing — never rely on line numbers from docs.
5. Then, and only then, start the task.

At the end of a session the user updates **Current Status** here and the Status / Notes columns in the tracker; Claude doesn't edit them unless asked.
