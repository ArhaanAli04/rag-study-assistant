# RAG Study Assistant — Build Timeline

61 days · 5–6 hours of focused work per day · FastAPI · Gemini · PostgreSQL + pgvector (Supabase) · Redis · LangGraph · Langfuse · Docker · GitHub Actions · React

> Source of truth for the day-by-day plan. `/run-day <N>` reads the `### Day N` section below.
> `rag_build_timeline.docx` (gitignored) is a printable copy generated from this file — edit
> here, then regenerate the docx. Item IDs refer to `docs/improvements.md`; status lives in
> `docs/improvement-tracker.md`.

## Overview

| Phase | Days | Focus |
|---|---|---|
| 1 | 1–3 | Security P0s (G6, G8, G7, G4, G1, O2, B1), branching model, first push |
| 2 | 4–6 | Docker-first local dev, offline test suite, GitHub Actions CI, branch protection |
| 3 | 7–10 | Package layout, routers + dependency injection, one chat pipeline, dead code (T3) |
| 4 | 11–12 | Retrieval eval harness (E4), LLM-as-judge generation eval (E1, E2) |
| 5 | 13–17 | Supabase Postgres + Storage, Alembic (T2), persistent per-user search (I4, I5, I6, I1, I2), I3, CO3, R5 |
| 6 | 18–20 | Projects: files, instructions and chats scoped to a project (a course), project-aware retrieval and caches |
| 7 | 21–22 | CI-gated deploys, staging + preview environments, post-deploy checks, releases, rollback |
| 8 | 23–25 | Tracing (O1), token usage + cache-friendly prompts (CO4), feedback scores, prompt management |
| 9 | 26–27 | Golden set as a Langfuse dataset (E3), CI eval gate, confidence + cache threshold tuning |
| 10 | 28–32 | Reranker (R1), RRF (R4), parallelism (CO2), rewriting (C2, R2, R3), tokens (C1), cache (CO5, CO1) |
| 11 | 33–37 | LangGraph port, corrective RAG, verification (G2), moderation (G3), injection (G5), session memory (C3), tools (A1) |
| 12 | 38–39 | Header-based streaming, refresh tokens, rate limits, background ingestion with progress |
| 13 | 40–43 | Connectors: Google Drive (Docs, Sheets, Slides) import, Google export, web page by URL, YouTube lectures, Notion |
| 14 | 44–52 | Concept catalogue (S1), mastery + Progress, adaptive Practice, flashcards, living map, PDF viewer, Feynman mode, study guide — all project-aware |
| 15 | 53–55 | Per-user memory across chats (global + per project) with a Memory page to view, edit and delete |
| 16 | 56–59 | Design system, new navigation, chat UX, rich answers, restyle of every page incl. Projects, Progress, Practice, Memory and the viewer, mobile + a11y |
| 17 | 60–61 | UI integration audit, load testing, security review, docs, v1.0 |

Releases: Day 3 v0.1.0 · Day 10 v0.2.0 · Day 17 v0.3.0 · Day 20 v0.4.0 · Day 32 v0.5.0 · Day 37 v0.6.0 · Day 43 v0.7.0 · Day 52 v0.8.0 · Day 59 v0.9.0 · Day 61 v1.0.0

## How every day runs

- Start of day: git checkout develop, git pull origin develop, git checkout -b feature/dayNN-<ids>-<slug> (full checklist: rag_daily_command_sequence.pdf)
- In Claude Code: /run-day <N> reads the day from docs/timeline.md, writes docs/briefs/dayNN.md and stops for approval before any code
- End of day: /pre-commit, git status, commit ("day NN - description"), push the branch, open a PR into develop, merge once CI is green
- Release days: PR develop → master, tag the version, confirm the Render and Vercel deploys
- Update docs/improvement-tracker.md (Status + before/after numbers in Notes) and the CLAUDE.md Current Status block
- Every user-visible backend change ships with its UI the same day (CLAUDE.md rule): briefs list the UI work, the Outcome confirms it
- Never force-push develop or master; every new dependency is confirmed before it is added

---

## Phase 1 — SECURITY FIXES & GIT WORKFLOW (Days 1–3)

Focus: Security P0s (G6, G8, G7, G4, G1, O2, B1), branching model, first push

### Day 1 — Git workflow, semantic-cache isolation (G6), CORS (G4), debug prints (O2)

- Branch: feature/day01-g6-g4-o2 from develop
- Branching model (develop already created locally from master at 34c03f4):
  - Daily: feature/dayNN-<ids>-<slug> branched from develop, merged back into develop at the end of the day
  - Every 3–5 days (days marked Release): merge develop → master, push, tag
  - Do not push master or develop until the Day 3 release — commit 972bfc3 documents the G6/G7/G8 holes
  - Update the CLAUDE.md "Git history" convention and Current Status block to describe this flow
- G6 — scope the semantic cache by user in semantic_cache.py:
  - store(): write user_id into every entry alongside doc_version and mode
  - lookup(): filter on user_id + doc_version + mode; replace the falsy `if not user_doc_version` check with `is not None` (version 0 currently disables the filter)
  - Pass user.id from both /chat and /chat/stream (mirror rule until Day 9 consolidates them)
  - Document a one-off flush of the semantic_cache_entries key for deploy — existing entries carry no user scope
  - Update the Redis key schema table in CLAUDE.md
- Test: tests/test_semantic_cache.py — a query cached for user A is a miss for user B; two users at doc_version 0 stay isolated (small in-memory Redis stub, no new dependency)
- G4 — pass ALLOWED_ORIGINS (comma-separated) into CORSMiddleware instead of ["*"]; set it on Render to the Vercel URL + localhost:3000
- O2 — remove the print("DEBUG ...") calls in retrieval_service.py and main.py, or convert to logger.debug where the information is worth keeping
- Verify: two accounts ask the same question → the second gets a fresh answer and its metadata event contains no foreign sources; the frontend still connects (CORS)

### Day 2 — Stop logging JWTs (G8) and wire in sanitize_query (G1)

- Branch: feature/day02-g8-g1
- G8 — tokens out of every log:
  - log_requests middleware: log method, request.url.path, status and duration — never the query string
  - routes/auth_routes.py OAuth callback: drop the token from the redirect-URL log line
  - Uvicorn access log also records query strings: add a logging filter that strips them (or run with --no-access-log) in both the Dockerfile CMD and the local command
  - Treat already-logged tokens as exposed: delete local src/logs/app.log*, and plan to rotate JWT_SECRET_KEY on release day (every user logs in again)
- G1 — call sanitize_query() at the top of both chat endpoints and return a friendly refusal over SSE; it is a stop-gap until real moderation lands on Day 35 (G3)
- UI: ChatWindow.js renders the refusal as a normal assistant message, not a broken stream or a blank bubble
- Test: a log-formatter test asserting no record ever contains "token="; an SSE test that an injection phrase is refused
- Verify: run a streamed chat locally, then search app.log and the console output for "token=" — zero hits

### Day 3 — Per-user uploads (G7), account deletion (B1) and first release

- Branch: feature/day03-g7-b1
- G7 — safe upload storage:
  - Save to uploads/{user_id}/{uuid4}{ext} with a server-generated name; keep the client name only in Document.file_name
  - Resolve the final path and refuse anything outside the upload root
  - docker-compose.yml: mount the uploads directory as a named volume so files survive container recreation
  - Existing rows: leave old file_path values as-is (indexes are rebuilt on Day 16 anyway) and note it in the tracker
- B1 — DELETE /user/delete:
  - Query ChatSession (main.py's Session is SQLAlchemy's) — that is the crash
  - Move deletion into an account service that removes sessions, messages, documents, concept maps + nodes, failed_queries and files on disk in one transaction
  - Index entries: mark FAISS chunks deleted for now; true removal arrives with pgvector on Day 15
- Test: register → upload → chat → delete account → assert nothing of that user remains; a "../evil.pdf" upload lands inside uploads/<user_id>/
- After the B1 fix, delete the g6-*@example.com test accounts from Day 1 and day02-check@example.com (user 7, from the Day 2 API check) via DELETE /user/delete and confirm their uploads and rows are gone
- Release: develop → master (first push of both branches)
  - git status, merge with --no-ff, push master and develop, tag v0.1.0
  - Rotate JWT_SECRET_KEY on Render and flush the semantic cache key
  - Mark G6, G8, G7, G4, G1, O2, B1 Done in docs/improvement-tracker.md
- Verify: Render deploy is healthy, Vercel login (email + Google) works, chat streams

---

## Phase 2 — DEV FOUNDATION — DOCKER, TESTS & CI (Days 4–6)

Focus: Docker-first local dev, offline test suite, GitHub Actions CI, branch protection

### Day 4 — Docker-first local development

- Branch: feature/day04-docker-dev
- docker-compose.yml (shared) + docker-compose.override.yml (dev only):
  - backend: ./src bind-mounted, uvicorn --reload, depends_on redis
  - frontend: npm start with hot reload (CHOKIDAR_USEPOLLING=true for Windows bind mounts)
  - redis:7-alpine with a named volume
  - Named volumes for src/data, src/uploads, src/logs
- T3 Docker items: give the semantic cache its own Redis DB in Docker (today REDIS_URL=/0 makes it share DB 0); drop the unused DATABASE_URL (it returns properly on Day 13)
- Backend Dockerfile: multi-stage build, non-root user, HEALTHCHECK on /health; add .dockerignore (venv, node_modules, data, logs, uploads)
- Write .env.example covering every variable in CLAUDE.md's environment table, with placeholders only
- scripts/dev.ps1 helper (up, down, logs, test, shell) — PowerShell because there is no make on this machine
- Verify: fresh clone → copy .env.example → docker compose up → upload a PDF and chat end-to-end; a backend code edit reloads in a few seconds

### Day 5 — Offline test safety net (T1 + API smoke tests)

- Branch: feature/day05-tests
- T1: change the pytest.ini header to [pytest]; move the manual src/test_*.py scripts to scripts/manual/ so they are never collected
- tests/conftest.py:
  - FastAPI TestClient with a temporary database
  - Fake LLM and fake embedding service (deterministic vectors) injected through dependency overrides; in-memory Redis stub
  - main.py builds singletons at import time (IndexBuilder makes an embedding call) — add the smallest seam needed to import it without network; full dependency injection comes on Day 9
- Smoke tests: register/login/me, upload a sample PDF, list/delete documents, /chat/stream event order (metadata → token… → message_id → [DONE]), sessions list/rename/delete, feedback, concept-map generate with mocked LLM, /health
- Frontend: replace the default CRA App.test.js with render tests for the login page and the chat window
  - Since Day 3 the router works in Jest: `frontend/package.json` maps react-router-dom / react-router / react-router/dom to their CJS builds (CRA's Jest 27 ignores package `exports`), `App.js` exports `AppRoutes`, and `src/AccountDeletionFlow.test.js` is a working example (MemoryRouter + AuthProvider + AppRoutes; tests still need the TextEncoder polyfill at the top)
- Fix test_table_extraction_on_image: write outputs to tmp_path instead of tests/samples/, stop double-cleaning the image, move the existence check first, assert real table output; then remove the *_cleaned*.jpg ignore line
- Verify: python -m pytest tests passes with no API keys set and no network, in under a minute
- Note: these tests are the safety net for the Phase 3 refactor — the refactor does not start until they are green

### Day 6 — Continuous integration on GitHub Actions

- Branch: feature/day06-ci
- .github/workflows/ci.yml on pull_request to develop/master and on push:
  - backend: Python 3.11 (matches Docker), pip cache, install requirements, ruff check, pytest
  - frontend: Node LTS, npm ci, npm test -- --watchAll=false, npm run build
  - docker: build the backend and frontend images (no push)
- Decision: requirements.txt is UTF-16LE with CRLF — if pip in CI chokes on it, convert to UTF-8 now (T3); ask before changing
- Branch protection: master requires a PR + green CI; develop requires green CI; force-push disabled on both
- From here on, feature → develop merges go through a PR (gh pr create) so CI runs on every change
- Verify: a PR with a deliberately failing test is blocked; fixing it turns CI green and allows the merge

---

## Phase 3 — CODEBASE REFACTOR — PROPER PACKAGE STRUCTURE (Days 7–10)

Focus: Package layout, routers + dependency injection, one chat pipeline, dead code (T3)

### Day 7 — Target layout and the core package

- Branch: feature/day07-refactor-core
- Write docs/architecture/layout.md with the target tree and get approval before moving anything:
  - backend/app/api/routes/ — auth, users, documents, chat, sessions, quiz, concepts, health
  - backend/app/core/ — config, logging, security, errors
  - backend/app/db/ — engine/session, models/, repositories/
  - backend/app/ingestion/ — parsers (pdf, pptx, docx), chunking, OCR, tables
  - backend/app/retrieval/ — embeddings, vector store, keyword index, fusion, rerank, decomposition, compression, web search
  - backend/app/generation/ — LLM client, prompts, topic classifier
  - backend/app/services/ — chat pipeline, documents, sessions, caches, concept maps, quiz, accounts
  - backend/app/schemas/ — Pydantic request/response models
  - backend/tests/, backend/eval/, backend/scripts/; frontend/ unchanged
- One pydantic-settings Settings class for every environment variable (oauth_config.py already uses pydantic-settings); remove scattered os.getenv calls
- core/logging.py: rotating file + console handlers, with a request-ID filter ready for Langfuse
- Use git mv so file history follows the moves; package imports (from app.core.config import settings) replace bare-name imports
- Verify: CI green after each move; uvicorn app.main:app starts

### Day 8 — Move ingestion, indexes, retrieval and generation modules

- Branch: feature/day08-refactor-modules
- git mv each module group from CLAUDE.md's module map into its new package and fix imports
- Pure moves — no behaviour changes today, so any test failure is an import problem, not a logic problem
- Move the Pydantic models defined in main.py into schemas/
- Update Dockerfile WORKDIR/CMD, docker-compose, alembic/env.py sys.path and root scripts for the new paths
- Lazy-load OCR/table libraries (img2table, camelot, pytesseract): ~10 s of the 12 s import time; target backend reload < 5 s. Measured Day 4: `indexing_pipeline → chunk_builder → pptx_pipeline → table_utils → img2table` = 9.9 s of a 12.3 s import; reload 13.5–15.1 s. Do it as its own commit after the pure moves, so a test failure in the move commit is still only an import problem
- Fix backend/tests/test_docx_pdf_utils.py's sample paths: they are CWD-relative ("tests/samples/..."), and conftest chdirs to a temp dir, so every `if os.path.exists(...)` is False and its tests pass while checking nothing (found Day 7; the same silent-pass pattern as B3). Anchor them to `__file__` like test_pdf_utils.py; expect real OCR / camelot results, so do it as its own commit after the pure moves
- Verify: the Day 5 smoke tests pass unchanged — they are the proof the move kept behaviour identical

### Day 9 — Split main.py into routers, add dependency injection, one chat pipeline

- Branch: feature/day09-routers-di
- One router per area; main.py becomes an app factory whose lifespan creates the LLM client, embedding service, retrieval service and Redis clients on app.state, accessed through Depends
- Decision (open in CLAUDE.md): delete POST /chat vs. share a pipeline
  - Recommended: extract a ChatPipeline service used by /chat/stream and delete POST /chat, since the frontend only streams — confirm with owner first
- B2: the /chat 0.7/0.3 threshold bug disappears with /chat; fix the forced-web confidence cap (0.3 on a 0–100 scale) and define the confidence scale once as a named constant
- Merge the two keyword safety lists into one shared module (prep for G3)
- Startup cost: build one shared google.genai client in the lifespan and drop IndexBuilder's startup embedding call (use the known embedding dimension); measure app.main import against Day 8's 23–25 s
- Verify: SSE contract unchanged — the frontend works with zero edits

### Day 10 — Dead code, dependencies and docs (T3) — release

- Branch: feature/day10-cleanup
- Delete src/frontend.py, document_delete_service.py (replaced by real deletes on Day 15), frontend MessageBubble.js
- Delete the one-off DB scripts (fix_db.py, recreate_db.py, migrate_user_model.py, add_concept_tables.py, add_doc_version.py, run_migration.py, update_existing_sessions.py) — superseded by Alembic on Day 13
- Move eval scripts to backend/eval/ and stop them importing main (they are rewritten on Days 11–12)
- Dependencies (ask before each removal):
  - One UTF-8 requirements file; delete src/requirements.txt
  - Remove langchain*, qdrant-client, streamlit; keep langgraph (Day 33) and tiktoken until Day 31 decides
- B3: drop the unused opencv-python pin and make the contrib build win (install order or constraints), then remove the strict xfail on test_table_extraction_on_image (ask the owner before touching requirements)
- B5: fix preprocess_image deskew (threshold text pixels with inverted Otsu, handle OpenCV's 0–90° angle convention, keep the original size) and remove the strict xfail on test_unified_parser_image; record OCR output before/after
- Rewrite CLAUDE.md repo structure, module map and commands; update .claude hook paths
- Release: develop → master, tag v0.2.0. Render needs no dashboard change for the new layout (confirmed Day 7): Root Directory empty, Dockerfile Path ./Dockerfile, build context . (repo root), Docker Command empty, so Render runs the Dockerfile's CMD (`uvicorn app.main:app` from /app/backend since Day 7)
- Verify: Render and Vercel deploy green from the new layout

---

## Phase 4 — EVALUATION BASELINE (Days 11–12)

Focus: Retrieval eval harness (E4), LLM-as-judge generation eval (E1, E2)

### Day 11 — Retrieval eval harness (E4)

- Branch: feature/day11-e4-retrieval-eval
- backend/eval/retrieval/: constructs RetrievalService directly (never imports main), with web search and the L1 cache disabled
- Corpus: 3–5 real course PDFs/PPTX in eval/corpus/ (gitignored if private)
- Question set eval/datasets/retrieval_v1.jsonl:
  - LLM-generated questions over sampled chunks, prompted to paraphrase so BM25 isn't favoured by copied wording
  - Real hard queries from failed_queries and thumbs-down messages
  - Relevance labelled at document + page level so labels survive re-chunking
- Metrics in plain Python: Recall@5, Recall@10, MRR, nDCG@10
- Also answer the open questions: does the confidence score predict a hit? does the 800-character compression cut answer spans? where does the flat 0.5 web score land?
- CLI: python -m eval.retrieval --config baseline → results/{date}-{config}.json plus a Markdown summary
- Verify: baseline numbers recorded in the tracker's Notes column for E4

### Day 12 — Generation eval with an LLM judge (E1, E2)

- Branch: feature/day12-e1-e2-judge
- Decision: drop RAGAS (removes the OPENAI_API_KEY="dummy" hack and a heavy dependency) and build a Gemini judge — recommended — or wrap LLMClient for RAGAS properly; ask owner
- Judges: faithfulness (claims supported by context), answer relevance, citation correctness — Gemini structured JSON output, temperature 0
- Calibrate on ~20 hand-labelled answers and record judge/human agreement
- Retire the word-overlap manual metrics (E2)
- End-to-end runner: question → real pipeline (web off) → judge scores
- Verify: baseline generation scores recorded next to the retrieval baseline — every later phase compares against these

---

## Phase 5 — POSTGRES + PGVECTOR DATA LAYER (Days 13–17)

Focus: Postgres, Alembic (T2), persistent per-user search (I4, I5, I6, I1, I2), I3, CO3, R5

### Day 13 — Postgres provisioning and Alembic as the real migration path (T2)

- Branch: feature/day13-postgres
- Local: pgvector/pgvector:pg16 image in docker-compose with a named volume
- Hosted: Supabase (decided 2026-11-04) — Postgres with pgvector plus Supabase Storage (Day 15), one vendor. Free plan allows 2 active projects: production and staging on Supabase, dev on the local Docker Postgres
- Keep-alive: free projects pause after ~7 days without activity — .github/workflows/supabase-keepalive.yml on a schedule (every 3 days) runs one cheap read against each project, with the URL/key as GitHub secrets (same pattern as the F1 project). Note: GitHub disables scheduled workflows after 60 days without repo activity
- DATABASE_URL in Settings; Postgres driver psycopg (new dependency — confirm); keep the sync Session for now
- Alembic: URL from Settings, import every model (including ConceptMap, ConceptMapNode) in env.py, baseline revision of the current schema; delete db.py's startup migrate_database()
- Split db/database.py into db/session.py (engine, SessionLocal) and db/models/ (user, session, message, document, failed_query) — deferred from Day 9 so the engine is rewritten for Postgres only once
- db/repositories/: move the CRUD SQL still inside the sessions, documents, users and feedback routers (a known layering exception since Day 9) into repositories the routers call
- Verify: alembic upgrade head on an empty database creates every table and autogenerate reports no diff

### Day 14 — Migrate the data off SQLite

- Branch: feature/day14-sqlite-to-postgres
- scripts/migrate_sqlite_to_postgres.py: users, sessions, messages, documents, failed_queries, concept maps — IDs preserved, sequences reset, --dry-run with a row-count report
- Run against a copy of src/data/app.db first, then production; keep the SQLite file as a backup
- Tests and CI run against a Postgres service container (GitHub Actions services:)
- Verify: row counts match table by table; an existing account logs in and sees its sessions

### Day 15 — Chunks table — vector + keyword search in Postgres (I4, I5, I6, I1, I2)

- Branch: feature/day15-pgvector-chunks
- Alembic revision: document_chunks
  - id, user_id FK, document_id FK ON DELETE CASCADE, document_version, page, chunk_index, text, content_hash, embedding, tsv (generated tsvector), metadata jsonb
  - Indexes: HNSW on embedding (cosine), GIN on tsv, btree on (user_id, document_id)
- Note: EMBEDDING_DIM changes 3072 → 1536 (pgvector HNSW limit); re-embed on Day 16. gemini-embedding-001 returns 3072 by default (confirmed Day 9) and pgvector's HNSW on vector supports up to 2000; the constant lives in retrieval/embeddings.py and is sent as output_dimensionality on every call. Confirm the quality cost with E4
- Indexing orchestration moves out of ingestion/indexing_pipeline.py (which writes into retrieval's indexes, a known sideways layering exception since Day 8) into a services/ use case — deferred from Day 9 because the indexes are rewritten for pgvector today
- PgVectorStore + PgKeywordIndex behind the existing vector/keyword interfaces; the user filter is in the WHERE clause, so no over-fetch and post-filter (I1)
- Postgres full-text (ts_rank_cd) replaces BM25Okapi — measure the difference on E4 before deleting rank-bm25
- Uploaded files move to Supabase Storage (private bucket, object key uploads/{user_id}/{uuid}{ext} as on Day 3): upload writes to Storage, indexing reads from it, Document.file_path holds the object key; a one-off script copies existing local files up. Render's disk is ephemeral, so without this every restart loses the files that reindexing (Day 16), the viewer (Day 50) and connectors depend on
- I5: deleting a document cascades to its chunks and removes the file from Storage
- I6: register_document reports new / changed / unchanged; unchanged skips indexing and the doc_version bump; changed deletes the old version's chunks
- UI: deleted documents disappear from the list and from citations immediately; re-uploading an unchanged file shows "already indexed" instead of a duplicate
- Verify: restart the backend → documents are still retrieved (I4); a deleted document is never cited again

### Day 16 — Faster ingestion — batch embeddings, embedding cache (I3, CO3), reindex

- Branch: feature/day16-batch-embeddings
- embed_texts sends batches (embed_content accepts a list) with bounded concurrency and retry
- CO3: look up content_hash in document_chunks and reuse an existing embedding before calling the API
- scripts/reindex_all.py: re-embeds every user's documents from Supabase Storage into document_chunks (needed once — FAISS only ever lived in memory)
- Remove FAISS / BM25 code and the faiss-cpu and rank-bm25 dependencies once parity is confirmed
- Verify: upload time for a 50-page PDF before vs. after; E4 re-run with pgvector vs. the FAISS baseline recorded in the tracker

### Day 17 — Concept maps use your documents (R5) — release

- Branch: feature/day17-r5-concept-maps
- ConceptMapRetriever receives the shared retrieval service through dependency injection; no second IndexBuilder or embedding call
- Test: a document indexed through the pipeline is returned by the concept-map retriever
- UI: CreateMapForm's existing "use documents" toggle now works; ConceptNodeDetails shows the source document and page for document-derived nodes
- Update CLAUDE.md Data & State: indexes now persist in Postgres, files in Supabase Storage
- Release: develop → master; run alembic upgrade, the data migration and reindex on production; tag v0.3.0
- Verify: generate a concept map with "use documents" on — nodes cite the uploaded material

---

## Phase 6 — PROJECTS (Days 18–20)

Focus: Projects: files, instructions and chats scoped to a project (a course), project-aware retrieval and caches

A project is a course or subject ("DL Unit 5", "BDA"): its own files, its own instructions and its own chats, and every chat inside it searches only that project's files. It comes right after the Postgres release so every later feature (caches, eval, tools, connectors, study features, memory) is project-aware from the start instead of being retrofitted.

### Day 18 — Projects data model, API and project-scoped retrieval

- Branch: feature/day18-projects-core
- Alembic revision: projects table (id, user_id FK, name, description, instructions text, created_at, archived_at); nullable project_id FK on documents and chat sessions — NULL means "no project" (today's behaviour, so existing data needs no backfill)
- API: POST/GET/PATCH/DELETE /projects, GET /projects/{id} (files, chats, counts); upload and session creation accept project_id; moving a document or chat between projects
- Ownership checks on every project route (another user's project id → 404); deleting a project asks what to do with its documents (delete or move to "no project") and is covered by account deletion (B1)
- Retrieval: project_id joins user_id in the pgvector/full-text WHERE clause; a project chat searches only that project's documents, a chat outside any project searches the user's unassigned documents only (decision — or all documents; confirm with owner)
- Project instructions are user-written text: they go in the final user turn as delimited data, never the system instruction (CLAUDE.md rule, CO4/G5)
- UI: a project selector on the Documents page upload and a "Project" column/filter in the document list, so the API is usable the same day
- Test: two projects of one user retrieve disjointly; another user's project id is refused
- Verify: a chat in project A never cites a document from project B

### Day 19 — Projects UI

- Branch: feature/day19-projects-ui
- /projects page: project cards (name, file count, chat count, last activity), create / rename / archive / delete with confirmation
- /projects/:id: files panel (upload into the project, remove), instructions editor (save state, character limit), the project's chat list, "New chat in this project"
- Sidebar and top navigation: Projects link; the chat header shows which project a chat belongs to, with a switcher for new chats
- Loading, empty ("create your first project — e.g. one per course") and error states throughout
- Verify: create a project, upload two files, start a chat — answers cite only those files and follow the instructions

### Day 20 — Project scope everywhere — release

- Branch: feature/day20-projects-scope
- Caches include the project: semantic cache key/filter and the L1 retrieval cache gain project_id; doc_version bumps stay per user (any change invalidates), noted as a cache-efficiency follow-up
- Concept maps and quizzes can be generated from a project's documents; ConceptMap and quiz requests take project_id
- Session list and search filter by project; chat export includes the project name
- UI: concept-map and quiz forms get a "from project" option; the Projects page lists the project's maps
- Update CLAUDE.md (data model, Data & State, API endpoints) and the posts mapping
- Release: develop → master, alembic upgrade on production, tag v0.4.0
- Verify: semantic-cache hits never cross projects; a project-scoped concept map cites only that project's files

---

## Phase 7 — CONTINUOUS DELIVERY (Days 21–22)

Focus: CI-gated deploys, staging + preview environments, post-deploy checks, releases, rollback

### Day 21 — CI-gated deploys and preview environments

- Branch: feature/day21-cd
- Render: production deploys from master only after CI checks pass (auto-deploy setting — confirm the option in the dashboard)
- Migrations on deploy: Render pre-deploy command running alembic upgrade head — if not available on the instance type, run it from a start script before uvicorn
- render.yaml blueprint committed to the repo for the production and staging services
- Staging: a second Render service deploying develop, pointing at the staging database and the staging Langfuse project
- Vercel: production = master; preview deployments for develop and every PR; REACT_APP_API_URL set per environment
- GitHub environments (staging, production) for any deploy-time secrets
- Verify: merging into develop updates staging; a red CI run never deploys

### Day 22 — Post-deploy checks, release automation and rollback

- Branch: feature/day22-release-automation
- post-deploy.yml: after a staging deploy run a scripted smoke (log in as a test user, upload a tiny PDF, one streamed chat); after production, /health only
- Release workflow: merging to master creates the tag and a GitHub Release with generated notes; keep CHANGELOG.md
- docs/runbooks/deploy.md: Render rollback to the previous deploy, migrations must stay backward compatible for one release
- Verify: deliberately break staging → the post-deploy job fails and notifies

---

## Phase 8 — OBSERVABILITY WITH LANGFUSE (Days 23–25)

Focus: Tracing (O1), token usage + cache-friendly prompts (CO4), feedback scores, prompt management

### Day 23 — Trace every request with Langfuse Cloud (O1)

- Branch: feature/day23-langfuse-tracing
- Langfuse Cloud projects for dev, staging, prod; LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST in .env, Render and CLAUDE.md's env table
- langfuse Python SDK (new dependency — confirm)
- One trace per chat request, with spans for:
  - safety check, semantic-cache lookup, topic tagging, decomposition
  - retrieval per sub-query (vector, keyword, fusion, web), rerank, compression
  - generation (streamed) and cache store
- Trace metadata: internal user_id (never email), session_id, doc_version, answer mode, grounding level, confidence
- Also trace /upload indexing and concept-map generation
- Privacy: mask JWTs and emails; document that retrieved chunk text is sent to Langfuse
- Verify: one chat shows a full span tree with per-stage latency in the Langfuse UI

### Day 24 — Tokens, cost and cache-friendly prompts (CO4) + feedback scores

- Branch: feature/day24-co4-usage
- Read usage_metadata (prompt, candidates and cached_content token counts) from both streaming and non-streaming calls and report it as Langfuse generation usage → cost dashboards
- CO4: keep the system instruction constant; move the grounding directive into the final user turn; trim history in blocks so it stays append-only between trims
- Store trace_id on Message; thumbs up/down becomes a Langfuse score; failed_queries mirrored as a score
- Verify: cached tokens > 0 on consecutive turns of a long session; cost per chat visible

### Day 25 — Prompt management, structured logs and dashboards

- Branch: feature/day25-prompts-dashboards
- Prompts (system, grounding, answer modes, topic classifier, concept extractor, quiz) move to Langfuse prompt management with versions and production/staging labels; local fallback copies keep the app working if Langfuse is unreachable
- Link generations to prompt versions so scores can be compared per version
- Request-ID middleware; JSON logs carrying request_id and trace_id
- Dashboards: latency p50/p95, error rate, cost per day, thumbs-up ratio
- Verify: relabelling a prompt version in Langfuse changes behaviour without a deploy (after the SDK's cache TTL)

---

## Phase 9 — EVALUATION AT SCALE (Days 26–27)

Focus: Golden set as a Langfuse dataset (E3), CI eval gate, confidence + cache threshold tuning

### Day 26 — Golden eval set as a Langfuse dataset (E3)

- Branch: feature/day26-e3-golden-set
- 30–50 questions from real course material: question, expected answer points, expected document + page, answer mode; include multi-turn conversations
- Upload as a Langfuse dataset; the runner executes the pipeline per item, links runs to the dataset, attaches the Day 12 judge scores and Day 11 retrieval metrics
- Confidence calibration: confidence vs. Recall@5 on the golden set → re-derive the 70 / 30 grounding thresholds (closes B2)
- Verify: two runs on different configs are comparable side by side in Langfuse

### Day 27 — CI eval gate and semantic-cache threshold tuning (CO5, part 1)

- Branch: feature/day27-eval-gate
- Fast subset (~10 questions, retrieval metrics only, no judge) runs in CI on PRs touching retrieval/ or generation/; fails if Recall@5 drops beyond a set tolerance
- Full golden-set eval on a weekly scheduled workflow, with a Gemini budget noted
- Cache threshold: labelled same-intent / different-intent query pairs → precision/recall per threshold; pick one, and decide whether answer caching is worth keeping at all
- Verify: a PR that halves top_k is blocked by the gate

---

## Phase 10 — RETRIEVAL QUALITY (Days 28–32)

Focus: Reranker (R1), RRF (R4), parallelism (CO2), rewriting (C2, R2, R3), tokens (C1), cache (CO5, CO1)

### Day 28 — A real reranker (R1)

- Branch: feature/day28-r1-reranker
- Decision — pick after measuring:
  - Gemini Flash-Lite listwise rerank of the top 20 — no new dependency, adds latency and cost (recommended first)
  - Hosted rerank API (Cohere / Voyage / Jina) — new dependency and key
  - Local cross-encoder — needs torch, too heavy for the current Render instance
- Rerank top 20 → top 5 with a timeout and fallback to fusion order; its own Langfuse span
- Verify: E4 + golden set before/after recorded in the tracker; p95 latency change noted

### Day 29 — Reciprocal Rank Fusion and parallel sub-queries (R4, CO2)

- Branch: feature/day29-r4-co2
- RRF (k = 60) over the vector and keyword ranked lists; web chunks join by rank instead of a flat 0.5 score
- Retrieve sub-queries concurrently with asyncio.gather (sync DB calls through asyncio.to_thread)
- Verify: retrieval metrics vs. min-max fusion; latency of multi-part questions before/after

### Day 30 — History-aware query rewriting and LLM decomposition (C2, R2)

- Branch: feature/day30-c2-r2
- C2: Flash-Lite rewrite of (recent turns + message) → standalone question, skipped when the session has no prior turns; used for retrieval, web search and cache lookups
- R2: LLM decomposition into at most 3 sub-questions with a JSON schema; the regex splitter stays as the fallback
- Verify: multi-turn golden-set conversations — follow-ups like "what are its disadvantages?" now retrieve the right pages

### Day 31 — Query expansion and token-based chunking (R3, C1)

- Branch: feature/day31-r3-c1
- R3: multi-query or HyDE, triggered only when confidence is low
- Decision (C1): tiktoken is OpenAI's tokenizer and only approximates Gemini — use Gemini count_tokens for budgets and tiktoken only as a fast estimate, or drop tiktoken
- Chunk by tokens (e.g. 300–500 with ~15% overlap) and budget the compressed context in tokens instead of 6 × 800 characters
- Re-index with the Day 16 script
- Verify: the biggest retrieval change of the project — compare E4 and judge scores carefully before merging

### Day 32 — Semantic cache redesign (CO5, CO1) — release

- Branch: feature/day32-semantic-cache
- semantic_cache table in Postgres: user_id, doc_version, mode, rewritten query, embedding (HNSW), answer, expires_at — replaces the single Redis JSON blob and the linear scan
- Look up and store by the standalone rewritten query; cache only strictly grounded answers; compute the query embedding once and pass it through
- Track thumbs-down on cached answers as the production false-hit signal
- Update the Redis key schema in CLAUDE.md (the semantic_cache_entries key is gone)
- Release: develop → master, tag v0.5.0

---

## Phase 11 — LANGGRAPH AGENTIC PIPELINE & SAFETY (Days 33–37)

Focus: LangGraph port, corrective RAG, verification (G2), moderation (G3), injection (G5), memory (C3), tools (A1)

### Day 33 — Port the chat pipeline to LangGraph, one to one

- Branch: feature/day33-langgraph-port
- Graph state (TypedDict): query, rewritten query, sub-queries, candidates, confidence, grounding level, context, answer, citations, flags
- Nodes wrap the existing services (rewrite → decompose → retrieve → rerank → compress → generate); edges stay linear today
- Streaming: graph.astream(...) mapped onto the unchanged SSE events (metadata, token, message_id, [DONE])
- Langfuse's LangChain/LangGraph callback handler keeps the traces intact
- Verify: golden-set scores within noise of Day 32 — the port must not change quality

### Day 34 — Conditional edges — corrective RAG

- Branch: feature/day34-corrective-rag
- Grade retrieved chunks (reranker scores or a cheap grader) → weak: rewrite and retry once, or call web search; strong: skip web entirely (today 2–3 web chunks are always fetched)
- Iteration cap and a latency budget so the graph can never loop
- Verify: web calls per query down, faithfulness the same or better

### Day 35 — Answer verification and real moderation (G2, G3)

- Branch: feature/day35-g2-g3
- G2: verify_answer node for loose/none grounding (or a sample) → a warning flag in the metadata event
- UI: MessageList.js shows a "some claims may not be supported by your sources" badge on flagged answers; a moderation refusal renders as a normal message
- G3: replace the keyword list and sanitize_query with Gemini safety settings plus a moderation classification call, in one safety node used by every entry point
- Verify: red-team prompts and rephrased unsafe requests are caught; normal study questions are not

### Day 36 — Indirect prompt-injection defences (G5)

- Branch: feature/day36-g5-injection
- Scan chunks at upload (flag column on document_chunks) and web chunks at fetch time for instruction-like text and hidden/zero-width characters
- Spotlighting: per-request random delimiters around each chunk; the constant system instruction says delimited content is data, never instructions
- Canary string in the system prompt; block any response containing it
- Frontend: override ReactMarkdown's img renderer in MessageList.js (drop or allowlist images) to close the exfiltration path
- Red-team set: payloads planted in test documents and web text; attack success rate tracked as an eval metric

### Day 37 — Conversation memory and tool use (C3, A1) — release

- Branch: feature/day37-c3-a1
- C3: embed each Q+A pair into a session_memory table (pgvector); retrieve the top-k older turns with the rewritten query; token-budgeted recent window; deleted with the session
- A1: tools — search_documents, web_search, generate_quiz, make_concept_map — callable by the model for open-ended requests; the deterministic RAG path stays the default
- UI: a small "searched your notes / searched the web / made a quiz" indicator above answers when tools ran; tool results (a quiz, a map) open on their own page
- Verify: a long session recalls something said 30 turns ago; tool calls show up as spans in Langfuse and as indicators in the chat
- Release: develop → master, tag v0.6.0

---

## Phase 12 — BACKEND HARDENING (Days 38–39)

Focus: Header-based streaming, refresh tokens, rate limits, background ingestion with progress

### Day 38 — Auth hardening — header-based streaming, refresh tokens, rate limits

- Branch: feature/day38-auth-hardening
- Fetch-based SSE client sending an Authorization header; remove ?token= from /chat/stream (finishes G8)
- Move the OAuth callback token from ?token= to a URL fragment (#token=) so it never reaches server or proxy logs; update AuthCallback.js to read it from the hash
- Short-lived access tokens (~15 min) + rotating refresh token in an httpOnly, Secure, SameSite cookie; refresh_tokens table with revocation; /auth/logout revokes
- Rate limiting per user/IP on /chat/stream, /upload, /login, /register backed by Redis (slowapi — new dependency, confirm)
- UI:
  - ChatWindow.js switches to the fetch-based stream; the API client refreshes the access token silently and retries once
  - A clear "too many requests — try again in N s" message on 429, using Retry-After
  - Session expiry sends the user to login with a message instead of failing silently
- Verify: an access token is useless after expiry; logout kills the refresh token; the limit returns 429 with Retry-After and the UI shows it

### Day 39 — Background document ingestion with progress

- Branch: feature/day39-background-ingestion
- /upload returns 202 with the document id; indexing runs in the background
- Decision: FastAPI BackgroundTasks (no dependency, dies with the process) vs. a Redis-backed worker such as arq or RQ (new dependency, survives restarts)
- documents.status (queued, parsing, embedding, ready, failed) + progress + failure reason; GET /documents/{id}/status
- UI:
  - DocumentUpload.js / DocumentList.js show a progress bar and status per document, polling the status endpoint
  - Failed documents show the reason and a retry button; chat notes when a document is still indexing
- Verify: a large PDF uploads instantly and the status moves to ready in the UI; a corrupt file ends in failed with a reason

---

## Phase 13 — CONNECTORS (Days 40–43)

Focus: Connectors: Google Drive (Docs, Sheets, Slides) import, Google export, web page by URL, YouTube lectures, Notion

All five are free at this scale. They sit after refresh tokens (Day 38), which stored connector tokens need, and tool calling (Day 37), which lets the agent use them. Imported content is untrusted like any upload: it goes through the same ingestion, G5 scanning and project scoping.

### Day 40 — Connector framework and Google consent

- Branch: feature/day40-connectors-core
- Connector interface: connect (OAuth), list, import, sync, disconnect — one implementation per source, so adding a source later is one class plus its UI card
- connector_accounts table: user_id, provider, scopes, encrypted access/refresh tokens (key from Settings, never logged), status, last_sync; imported documents record source, external id and last synced version
- Google: incremental authorization — the existing login keeps openid/email/profile; connecting Drive asks for drive.file only (per-file access granted through the Google Picker, a non-restricted scope, so no paid security assessment — confirm on the consent-screen page)
- Move the Google OAuth consent screen from Testing to In production: in Testing, refresh tokens expire after 7 days and only test users can connect
- UI: Settings → Connections page — one card per connector with Connect / Disconnect, status, last sync; disconnect revokes the token
- Verify: connect and disconnect Google; tokens are encrypted at rest and absent from logs

### Day 41 — Google Drive import (Docs, Sheets, Slides)

- Branch: feature/day41-google-drive-import
- Google Picker in the frontend (Picker API key + client id are public values) → the backend fetches only the picked files
- Docs → exported as text/HTML with headings; Sheets → one table chunk per sheet range (header row kept with every chunk); Slides → text per slide, like PPTX
- Sync: re-import when the Drive file's version changes (manual "Sync now" plus a check on open); a changed file becomes a new document version (I6 rules)
- Imports land in the chosen project; citations show the Drive file name and link back to it
- UI: "Import from Google Drive" button on Documents and on a project's files panel; source badge on imported documents; sync state and errors per document
- Verify: a Doc, a Sheet and a Slides deck imported into a project are cited correctly; editing the Doc and syncing updates the answer

### Day 42 — Google export, web page by URL, YouTube lectures

- Branch: feature/day42-export-web-youtube
- Google export (same drive.file scope — the app may write files it creates): quiz → Google Sheet, study guide and chat → Google Doc; returns the new file's link
- Web page by URL: fetch with the existing scraper, SSRF guard (block private/loopback/link-local addresses and non-http schemes, follow redirects only to public hosts), size and time limits, readable-text extraction, stored as a document with the URL as its source
- YouTube lectures: public video URL → Gemini's native YouTube input produces a timestamped transcript + lecture notes, stored as a document; citations link to the timestamp. Avoids transcript-scraping libraries, which cloud IPs usually get blocked from; free within Gemini free-tier limits (check the current limits on the day)
- UI: "Export to Google" menu on quiz results, study guides and chats; "Add from URL" and "Add YouTube lecture" in the upload dialog, with progress and clear errors (private video, page blocked, too long)
- Verify: an exported quiz opens as a Sheet; a URL and a lecture are cited with working links

### Day 43 — Notion and connector hardening — release

- Branch: feature/day43-notion
- Notion public integration (free): OAuth, the user picks pages/databases to share; pages → text with headings, databases → table chunks; sync like Drive
- Connector hardening: token refresh and revocation handling, per-connector rate limits and retries, an import job per item so one failure doesn't stop the rest (background ingestion from Day 39)
- Account deletion (B1) and disconnect remove connector tokens and, on request, imported documents
- UI: Notion card on Connections; "Import from Notion" picker; a per-connector activity list (imported, failed with reason)
- Release: develop → master, tag v0.7.0
- Verify: a Notion page is imported into a project and cited; disconnecting stops sync and deletes the stored token

---

## Phase 14 — STUDY FEATURES (Days 44–52)

Focus: Concept catalogue (S1), mastery + Progress, adaptive Practice, flashcards, living map, PDF viewer, Feynman mode, study guide — all project-aware

Every feature in this phase takes a project scope (default: all of the user's documents): concepts belong to documents, so they inherit the project; Progress, Practice, the living map and study guides can be filtered by project.

### Day 44 — Concept catalogue and structured output (S1)

- Branch: feature/day44-s1-concepts
- S1: Gemini structured output (response schema from Pydantic models) for quizzes, concept maps and study guides; delete the hand-written JSON parser
- At indexing time, extract each document's concepts into a concepts table: name, definition, document + pages, prerequisite links — the shared backbone for mastery, Practice, the living map, Feynman mode and study guides
- Re-extraction when a document version changes; concepts deleted with their document
- UI:
  - Documents page shows each document's concept count and an expandable concept list, with an "extracting concepts…" status while the job runs
- Verify: concepts for a sample PDF all point to real pages; deleting the document removes them

### Day 45 — Mastery model (#1) and the Progress page

- Branch: feature/day45-mastery-progress
- mastery_events table (quiz answer, flashcard review, Feynman result, chat question about a concept) feeding a mastery score per user × concept
- Start simple: an Elo-style update with time decay — knowledge tracing is the concept to explain; keep the update function isolated so it can be swapped later
- GET /progress: mastery per concept grouped by document, weakest first, trend over time
- UI:
  - New /progress page and a Progress link in the top navigation
  - Concepts grouped by document with a mastery bar each; a weakest-five section with a "Practise these" button; trend sparkline
  - Empty state ("take a quiz to start tracking"), loading and error states
- Verify: answering questions moves the scores in the expected direction and the Progress page reflects it

### Day 46 — Adaptive quiz (#2) — backend, with a working flow on the current Quiz page

- Branch: feature/day46-adaptive-quiz
- Questions generated from retrieved chunks of the chosen concepts or documents, each citing its source document + page
- Question types:
  - Multiple choice with wrong options built from common misconceptions, so a wrong answer reveals which misunderstanding it is
  - Fill-in-the-blank and numeric
  - Short answer graded by an LLM against a rubric, with feedback on what was missing
- Concept selection targets weak mastery first; difficulty moves with your answers
- Persist quizzes, attempts and answers; every answer writes a mastery event
- UI:
  - The current QuizGenerator / QuizDisplay run an adaptive quiz end to end today (every question type answerable, explanation shown after each) — Day 47 redesigns it as Practice
- Verify: a quiz on a weak concept generates cited questions; the short-answer grader gives specific feedback

### Day 47 — Practice page (#2) — quiz UI

- Branch: feature/day47-practice-page
- Quiz becomes Practice: /practice route with /quiz redirecting; navigation label updated
- Modes: adaptive (weakest concepts), by topic, by document, by project
- Renderers for every question type; after each answer an explanation with a citation link to the source page (opens the viewer once Day 50 lands — document + page text until then)
- Results screen: score, mastery change per concept, "practise the misses again"; quiz history list
- Loading, empty and error states for every step
- Verify: a full adaptive quiz in the browser updates the Progress page

### Day 48 — Flashcards with spaced repetition

- Branch: feature/day48-flashcards
- Cards generated from concepts with citations (structured output); SM-2 scheduling (ease factor, interval, due date); every review writes a mastery event
- UI:
  - Flashcards tab on Practice: flip card, Again / Hard / Good / Easy, cards remaining
  - "N cards due today" on the Progress page and as a badge on the Practice nav link
- Verify: a reviewed card's next due date follows SM-2; due counts update in both places

### Day 49 — Living concept map (#3)

- Branch: feature/day49-living-map
- Maps built from the concept catalogue, so documents are a real source (builds on R5); prerequisite edges produce a suggested learning path
- Map endpoint returns mastery per node
- UI:
  - Mastery colour overlay (red → green) with an on/off toggle and legend
  - Learning-path view highlighting the next concept to study
  - ConceptNodeDetails.js actions: explain it, quiz me (Practice filtered to that concept), open source page, chat about it
- Verify: after a quiz the quizzed nodes change colour; every node action opens the right place

### Day 50 — PDF citation viewer (#8)

- Branch: feature/day50-citation-viewer
- Store each chunk's page and character position at indexing time (reindex once with the Day 16 script)
- Authenticated file endpoint serving the user's own document from Supabase Storage — the backend checks ownership, then streams the object or returns a short-lived signed URL (user-scoped, never a public bucket)
- Highlight by locating the chunk's text in the PDF text layer — needs a PDF renderer such as react-pdf (new dependency — confirm)
- UI:
  - Chat: clicking a citation opens a side panel at the highlighted passage, without leaving the conversation
  - /documents/:id: full viewer; select text → "explain this" / "quiz me on this"
  - Citations on Practice (Day 47) and the concept map (Day 49) now open the same viewer
- Note: PPTX and DOCX open at the slide/section with the text shown — no PDF page to render; converting them to PDF is a later improvement
- Verify: a citation from chat lands on the right page with the passage highlighted; another user's document id returns 404

### Day 51 — Feynman mode (#4) — explain it back

- Branch: feature/day51-feynman-mode
- "Explain back" chat mode: the student explains a concept; a judge compares it with the concept's source chunks and returns covered / missing / wrong points, each with a citation; writes a mastery event
- Judge rubric and calibration reuse the Day 12 LLM-as-judge work
- UI:
  - Fourth option in the Chat mode selector
  - Structured feedback card: covered / missing / wrong, with citation chips that open the viewer
  - Launch points: a concept-map node and a weak concept on Progress, pre-focused on that concept
- Verify: a deliberately incomplete explanation gets the missing points flagged with correct citations

### Day 52 — Study guide per document (#10) — release

- Branch: feature/day52-study-guide
- One study guide per document version (structured output): summary, key definitions, formula sheet, likely exam questions — every item cited; cached and regenerated when the document changes
- UI:
  - "Study guide" tab in the document viewer, citations clickable to the page
  - Generate / regenerate button with progress; export to PDF
- Verify: every cited page contains the claim; a new document version gets a fresh guide
- Release: develop → master, tag v0.8.0

---

## Phase 15 — MEMORY ACROSS CHATS (Days 53–55)

Focus: Per-user memory across chats (global + per project) with a Memory page to view, edit and delete

Day 37's session memory (C3) recalls earlier turns of one chat; this phase remembers durable facts about the student across all chats — level, goals, preferences, courses, exam dates — the way Claude's memory does. The mastery model (Day 45) already tracks what they know; memory tracks who they are and how they like to learn.

### Day 53 — Memory extraction and storage

- Branch: feature/day53-memory-store
- memories table: user_id, project_id (NULL = global), text, kind (preference, goal, background, schedule), source message id, embedding, created/updated, last_used_at, pinned
- Extraction runs in the background after a chat turn (batched, e.g. at most once per session per few minutes): Gemini structured output proposes add / update / delete operations against the user's existing memories, deduplicated by embedding similarity
- Safety rule: memories come only from the user's own messages — never from uploaded documents, web pages, connector imports or model output (memory poisoning is indirect prompt injection that persists, G5); explicit "remember that…" / "forget that…" requests are honoured directly
- Never store secrets or sensitive categories; a user-level "memory off" switch stops extraction and use
- Test: an injected instruction inside an uploaded document never becomes a memory; "forget X" removes it
- Verify: after a few chats stating a goal and a preference, the right memories exist with their source messages

### Day 54 — Using memory in chats

- Branch: feature/day54-memory-retrieval
- Retrieve the top-k relevant memories (global + the chat's project) with the rewritten query; token-budgeted; placed in the final user turn as delimited "what you know about this student", never in the system instruction (CO4 stable prefix, G5)
- Answers adapt (explanation level, examples from their course, exam timing); last_used_at updated; an "incognito chat" option skips memory entirely
- Langfuse span for memory retrieval; golden-set check that answers stay grounded with memory on
- UI: a "used N memories" indicator on answers that used memory, expandable to show which; incognito toggle in the chat header
- Verify: a new chat in another session uses a stated preference; incognito chats neither read nor write memory

### Day 55 — Memory page and controls

- Branch: feature/day55-memory-page
- /memory page: memories grouped global / per project, each editable, deletable and pinnable; "add a memory" manually; search; "delete all"
- Settings: memory on/off, per-project memory on/off; account deletion (B1) and project deletion remove the matching memories
- A short "Memory updated" notice in chat when a turn adds or changes a memory, linking to the page
- Loading, empty ("memories appear as you chat — or add one") and error states
- Verify: editing a memory changes the next answer; deleting it means it is never used again

---

## Phase 16 — UI OVERHAUL (Days 56–59)

Focus: Design system, new navigation, chat UX, rich answers, restyle of every page incl. Projects, Progress, Practice, Memory and the viewer, mobile + a11y

### Day 56 — Design system — fonts, tokens, dark mode, app shell, navigation

- Branch: feature/day56-design-system
- Fonts: Inter or Geist Sans for the interface, Geist Mono or JetBrains Mono for code, optional Source Serif 4 for long answers — self-hosted via @fontsource (new dependency) or Google Fonts
- Tailwind theme tokens: colours, radii, spacing, type scale; dark mode with the system preference as default
- Decision: shadcn/ui components (Radix + Tailwind, adds Radix packages) vs. hand-built components on Tailwind; lucide-react icons stay
- App shell and navigation: Chat · Projects · Documents · Practice · Concept Maps · Progress, with Memory and Connections under Settings; collapsible sidebar with projects and sessions grouped by Today / Previous 7 days; centred ~768px chat column
- Note: this phase restyles screens that already work — no feature is wired in for the first time here

### Day 57 — Chat experience

- Branch: feature/day57-chat-ux
- Auto-growing composer: Enter to send, Shift+Enter for a newline, attach button, mode selector (quick / detailed / step-by-step / explain back)
- Stop generation (AbortController on the fetch stream), regenerate, edit and resend, copy
- Smooth token rendering, auto-scroll that pauses when the user scrolls up, typing indicator, skeleton loaders
- Verify: stop mid-answer leaves a clean partial message; regenerate replaces it

### Day 58 — Rich answers and citations

- Branch: feature/day58-rich-answers
- Code blocks with syntax highlighting and a copy button (react-syntax-highlighter or shiki — new dependency)
- Math with remark-math + rehype-katex (new dependencies) — essential for STEM material; also in Practice, flashcards and study guides
- Styled GFM tables; citation chips [1] with a hover card (document, page, snippet) opening the viewer panel; restyled confidence, grounding and verification badges and the Feynman feedback card

### Day 59 — Study pages, responsive and accessible — release

- Branch: feature/day59-study-ui
- Restyle Projects (cards, project page), Documents (library, upload progress, import sources, viewer, study guide), Practice (quiz + flashcards), Concept Maps, Progress, Memory and Settings → Connections on the new design system
- Mobile layout (sidebar and viewer panel as drawers), keyboard shortcuts (Ctrl+K new chat, / to focus), focus rings, aria labels; Lighthouse accessibility ≥ 90
- Toasts for errors; designed empty states everywhere
- Release: develop → master, tag v0.9.0

---

## Phase 17 — POLISH & LAUNCH (Days 60–61)

Focus: UI integration audit, load testing, security review, docs, v1.0

### Day 60 — Integration audit, performance and security review

- Branch: feature/day60-audit-perf-security
- UI integration audit: list every endpoint and response field and confirm each has a frontend caller with loading, empty and error states — fix any gap before launch
- Load test chat and upload (locust — new dependency — or k6 run outside the repo); set p95 targets; tune the DB pool
- /security-review over everything since v0.1.0 — with extra attention on project ownership checks, connector token storage and scopes, the URL importer's SSRF guard and memory-poisoning paths; pip-audit and npm audit
- Pin every GitHub Action in .github/workflows/ to a full commit SHA (Day 6 uses major-version tags such as actions/checkout@v4), with the tag kept in a trailing comment so updates stay readable
- Decision: purge the Tesseract installer from git history — needs a history rewrite and force-push, so only with explicit agreement
  - Branch protection blocks force-pushes even for admins: lift protection on master and develop temporarily, purge, force-push, then restore the exact rules (re-run the Day 6 gh api commands from docs/briefs/day06.md) and read them back

### Day 61 — Docs and v1.0

- Branch: feature/day61-docs-v1
- Rewrite README.md so nothing in it drifts from the code; refresh docs/architecture.png
- Bring CLAUDE.md fully up to date; every tracker item marked Done or Skipped with notes
- Demo GIF/video and live links
- Release: develop → master, tag v1.0.0
