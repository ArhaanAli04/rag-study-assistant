# RAG Study Assistant — Build Timeline

44 days · 5–6 hours of focused work per day · FastAPI · Gemini · PostgreSQL + pgvector · Redis · LangGraph · Langfuse · Docker · GitHub Actions · React

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
| 5 | 13–17 | Postgres, Alembic (T2), persistent per-user search (I4, I5, I6, I1, I2), I3, CO3, R5 |
| 6 | 18–19 | CI-gated deploys, staging + preview environments, post-deploy checks, releases, rollback |
| 7 | 20–22 | Tracing (O1), token usage + cache-friendly prompts (CO4), feedback scores, prompt management |
| 8 | 23–24 | Golden set as a Langfuse dataset (E3), CI eval gate, confidence + cache threshold tuning |
| 9 | 25–29 | Reranker (R1), RRF (R4), parallelism (CO2), rewriting (C2, R2, R3), tokens (C1), cache (CO5, CO1) |
| 10 | 30–34 | LangGraph port, corrective RAG, verification (G2), moderation (G3), injection (G5), memory (C3), tools (A1) |
| 11 | 35–38 | Auth hardening, rate limits, background ingestion, quizzes from documents (S1), flashcards |
| 12 | 39–42 | Modern chat-AI design system, chat UX, rich answers + citations, study pages, mobile + a11y |
| 13 | 43–44 | Load testing, security review, docs, v1.0 |

## How every day runs

- Start of day: git checkout develop, git pull origin develop, git checkout -b feature/dayNN-<ids>-<slug> (full checklist: rag_daily_command_sequence.pdf)
- In Claude Code: /run-day <N> reads the day from docs/timeline.md, writes docs/briefs/dayNN.md and stops for approval before any code
- End of day: /pre-commit, git status, commit ("day NN - description"), push the branch, open a PR into develop, merge once CI is green
- Release days: PR develop → master, tag the version, confirm the Render and Vercel deploys
- Update docs/improvement-tracker.md (Status + before/after numbers in Notes) and the CLAUDE.md Current Status block
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
- G1 — call sanitize_query() at the top of both chat endpoints and return a friendly refusal over SSE; it is a stop-gap until real moderation lands on Day 32 (G3)
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
- Verify: the Day 5 smoke tests pass unchanged — they are the proof the move kept behaviour identical

### Day 9 — Split main.py into routers, add dependency injection, one chat pipeline

- Branch: feature/day09-routers-di
- One router per area; main.py becomes an app factory whose lifespan creates the LLM client, embedding service, retrieval service and Redis clients on app.state, accessed through Depends
- Decision (open in CLAUDE.md): delete POST /chat vs. share a pipeline
  - Recommended: extract a ChatPipeline service used by /chat/stream and delete POST /chat, since the frontend only streams — confirm with owner first
- B2: the /chat 0.7/0.3 threshold bug disappears with /chat; fix the forced-web confidence cap (0.3 on a 0–100 scale) and define the confidence scale once as a named constant
- Merge the two keyword safety lists into one shared module (prep for G3)
- Verify: SSE contract unchanged — the frontend works with zero edits

### Day 10 — Dead code, dependencies and docs (T3) — release

- Branch: feature/day10-cleanup
- Delete src/frontend.py, document_delete_service.py (replaced by real deletes on Day 15), frontend MessageBubble.js
- Delete the one-off DB scripts (fix_db.py, recreate_db.py, migrate_user_model.py, add_concept_tables.py, add_doc_version.py, run_migration.py, update_existing_sessions.py) — superseded by Alembic on Day 13
- Move eval scripts to backend/eval/ and stop them importing main (they are rewritten on Days 11–12)
- Dependencies (ask before each removal):
  - One UTF-8 requirements file; delete src/requirements.txt
  - Remove langchain*, qdrant-client, streamlit; keep langgraph (Day 30) and tiktoken until Day 28 decides
- Rewrite CLAUDE.md repo structure, module map and commands; update .claude hook paths
- Release: develop → master, tag v0.2.0; update Render's root directory/start command for the new layout before merging
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
- Hosted: Neon or Supabase (free tiers, pgvector available; Render's free Postgres expires) with separate dev / staging / prod databases — choose one
- DATABASE_URL in Settings; Postgres driver psycopg (new dependency — confirm); keep the sync Session for now
- Alembic: URL from Settings, import every model (including ConceptMap, ConceptMapNode) in env.py, baseline revision of the current schema; delete db.py's startup migrate_database()
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
- Note: gemini-embedding-001 returns 3072 dimensions by default and pgvector's HNSW on vector supports up to 2000 — use output_dimensionality=1536 (or halfvec) and confirm with E4
- PgVectorStore + PgKeywordIndex behind the existing vector/keyword interfaces; the user filter is in the WHERE clause, so no over-fetch and post-filter (I1)
- Postgres full-text (ts_rank_cd) replaces BM25Okapi — measure the difference on E4 before deleting rank-bm25
- I5: deleting a document cascades to its chunks and removes the file
- I6: register_document reports new / changed / unchanged; unchanged skips indexing and the doc_version bump; changed deletes the old version's chunks
- Verify: restart the backend → documents are still retrieved (I4); a deleted document is never cited again

### Day 16 — Faster ingestion — batch embeddings, embedding cache (I3, CO3), reindex

- Branch: feature/day16-batch-embeddings
- embed_texts sends batches (embed_content accepts a list) with bounded concurrency and retry
- CO3: look up content_hash in document_chunks and reuse an existing embedding before calling the API
- scripts/reindex_all.py: re-embeds every user's documents from disk into document_chunks (needed once — FAISS only ever lived in memory)
- Remove FAISS / BM25 code and the faiss-cpu and rank-bm25 dependencies once parity is confirmed
- Verify: upload time for a 50-page PDF before vs. after; E4 re-run with pgvector vs. the FAISS baseline recorded in the tracker

### Day 17 — Concept maps use your documents (R5) — release

- Branch: feature/day17-r5-concept-maps
- ConceptMapRetriever receives the shared retrieval service through dependency injection; no second IndexBuilder or embedding call
- Test: a document indexed through the pipeline is returned by the concept-map retriever
- Update CLAUDE.md Data & State: indexes now persist in Postgres
- Release: develop → master; run alembic upgrade, the data migration and reindex on production; tag v0.3.0
- Verify: generate a concept map with "use documents" on — nodes cite the uploaded material

---

## Phase 6 — CONTINUOUS DELIVERY (Days 18–19)

Focus: CI-gated deploys, staging + preview environments, post-deploy checks, releases, rollback

### Day 18 — CI-gated deploys and preview environments

- Branch: feature/day18-cd
- Render: production deploys from master only after CI checks pass (auto-deploy setting — confirm the option in the dashboard)
- Migrations on deploy: Render pre-deploy command running alembic upgrade head — if not available on the instance type, run it from a start script before uvicorn
- render.yaml blueprint committed to the repo for the production and staging services
- Staging: a second Render service deploying develop, pointing at the staging database and the staging Langfuse project
- Vercel: production = master; preview deployments for develop and every PR; REACT_APP_API_URL set per environment
- GitHub environments (staging, production) for any deploy-time secrets
- Verify: merging into develop updates staging; a red CI run never deploys

### Day 19 — Post-deploy checks, release automation and rollback

- Branch: feature/day19-release-automation
- post-deploy.yml: after a staging deploy run a scripted smoke (log in as a test user, upload a tiny PDF, one streamed chat); after production, /health only
- Release workflow: merging to master creates the tag and a GitHub Release with generated notes; keep CHANGELOG.md
- docs/runbooks/deploy.md: Render rollback to the previous deploy, migrations must stay backward compatible for one release
- Verify: deliberately break staging → the post-deploy job fails and notifies

---

## Phase 7 — OBSERVABILITY WITH LANGFUSE (Days 20–22)

Focus: Tracing (O1), token usage + cache-friendly prompts (CO4), feedback scores, prompt management

### Day 20 — Trace every request with Langfuse Cloud (O1)

- Branch: feature/day20-langfuse-tracing
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

### Day 21 — Tokens, cost and cache-friendly prompts (CO4) + feedback scores

- Branch: feature/day21-co4-usage
- Read usage_metadata (prompt, candidates and cached_content token counts) from both streaming and non-streaming calls and report it as Langfuse generation usage → cost dashboards
- CO4: keep the system instruction constant; move the grounding directive into the final user turn; trim history in blocks so it stays append-only between trims
- Store trace_id on Message; thumbs up/down becomes a Langfuse score; failed_queries mirrored as a score
- Verify: cached tokens > 0 on consecutive turns of a long session; cost per chat visible

### Day 22 — Prompt management, structured logs and dashboards

- Branch: feature/day22-prompts-dashboards
- Prompts (system, grounding, answer modes, topic classifier, concept extractor, quiz) move to Langfuse prompt management with versions and production/staging labels; local fallback copies keep the app working if Langfuse is unreachable
- Link generations to prompt versions so scores can be compared per version
- Request-ID middleware; JSON logs carrying request_id and trace_id
- Dashboards: latency p50/p95, error rate, cost per day, thumbs-up ratio
- Verify: relabelling a prompt version in Langfuse changes behaviour without a deploy (after the SDK's cache TTL)

---

## Phase 8 — EVALUATION AT SCALE (Days 23–24)

Focus: Golden set as a Langfuse dataset (E3), CI eval gate, confidence + cache threshold tuning

### Day 23 — Golden eval set as a Langfuse dataset (E3)

- Branch: feature/day23-e3-golden-set
- 30–50 questions from real course material: question, expected answer points, expected document + page, answer mode; include multi-turn conversations
- Upload as a Langfuse dataset; the runner executes the pipeline per item, links runs to the dataset, attaches the Day 12 judge scores and Day 11 retrieval metrics
- Confidence calibration: confidence vs. Recall@5 on the golden set → re-derive the 70 / 30 grounding thresholds (closes B2)
- Verify: two runs on different configs are comparable side by side in Langfuse

### Day 24 — CI eval gate and semantic-cache threshold tuning (CO5, part 1)

- Branch: feature/day24-eval-gate
- Fast subset (~10 questions, retrieval metrics only, no judge) runs in CI on PRs touching retrieval/ or generation/; fails if Recall@5 drops beyond a set tolerance
- Full golden-set eval on a weekly scheduled workflow, with a Gemini budget noted
- Cache threshold: labelled same-intent / different-intent query pairs → precision/recall per threshold; pick one, and decide whether answer caching is worth keeping at all
- Verify: a PR that halves top_k is blocked by the gate

---

## Phase 9 — RETRIEVAL QUALITY (Days 25–29)

Focus: Reranker (R1), RRF (R4), parallelism (CO2), rewriting (C2, R2, R3), tokens (C1), cache (CO5, CO1)

### Day 25 — A real reranker (R1)

- Branch: feature/day25-r1-reranker
- Decision — pick after measuring:
  - Gemini Flash-Lite listwise rerank of the top 20 — no new dependency, adds latency and cost (recommended first)
  - Hosted rerank API (Cohere / Voyage / Jina) — new dependency and key
  - Local cross-encoder — needs torch, too heavy for the current Render instance
- Rerank top 20 → top 5 with a timeout and fallback to fusion order; its own Langfuse span
- Verify: E4 + golden set before/after recorded in the tracker; p95 latency change noted

### Day 26 — Reciprocal Rank Fusion and parallel sub-queries (R4, CO2)

- Branch: feature/day26-r4-co2
- RRF (k = 60) over the vector and keyword ranked lists; web chunks join by rank instead of a flat 0.5 score
- Retrieve sub-queries concurrently with asyncio.gather (sync DB calls through asyncio.to_thread)
- Verify: retrieval metrics vs. min-max fusion; latency of multi-part questions before/after

### Day 27 — History-aware query rewriting and LLM decomposition (C2, R2)

- Branch: feature/day27-c2-r2
- C2: Flash-Lite rewrite of (recent turns + message) → standalone question, skipped when the session has no prior turns; used for retrieval, web search and cache lookups
- R2: LLM decomposition into at most 3 sub-questions with a JSON schema; the regex splitter stays as the fallback
- Verify: multi-turn golden-set conversations — follow-ups like "what are its disadvantages?" now retrieve the right pages

### Day 28 — Query expansion and token-based chunking (R3, C1)

- Branch: feature/day28-r3-c1
- R3: multi-query or HyDE, triggered only when confidence is low
- Decision (C1): tiktoken is OpenAI's tokenizer and only approximates Gemini — use Gemini count_tokens for budgets and tiktoken only as a fast estimate, or drop tiktoken
- Chunk by tokens (e.g. 300–500 with ~15% overlap) and budget the compressed context in tokens instead of 6 × 800 characters
- Re-index with the Day 16 script
- Verify: the biggest retrieval change of the project — compare E4 and judge scores carefully before merging

### Day 29 — Semantic cache redesign (CO5, CO1) — release

- Branch: feature/day29-semantic-cache
- semantic_cache table in Postgres: user_id, doc_version, mode, rewritten query, embedding (HNSW), answer, expires_at — replaces the single Redis JSON blob and the linear scan
- Look up and store by the standalone rewritten query; cache only strictly grounded answers; compute the query embedding once and pass it through
- Track thumbs-down on cached answers as the production false-hit signal
- Update the Redis key schema in CLAUDE.md (the semantic_cache_entries key is gone)
- Release: develop → master, tag v0.4.0

---

## Phase 10 — LANGGRAPH AGENTIC PIPELINE & SAFETY (Days 30–34)

Focus: LangGraph port, corrective RAG, verification (G2), moderation (G3), injection (G5), memory (C3), tools (A1)

### Day 30 — Port the chat pipeline to LangGraph, one to one

- Branch: feature/day30-langgraph-port
- Graph state (TypedDict): query, rewritten query, sub-queries, candidates, confidence, grounding level, context, answer, citations, flags
- Nodes wrap the existing services (rewrite → decompose → retrieve → rerank → compress → generate); edges stay linear today
- Streaming: graph.astream(...) mapped onto the unchanged SSE events (metadata, token, message_id, [DONE])
- Langfuse's LangChain/LangGraph callback handler keeps the traces intact
- Verify: golden-set scores within noise of Day 29 — the port must not change quality

### Day 31 — Conditional edges — corrective RAG

- Branch: feature/day31-corrective-rag
- Grade retrieved chunks (reranker scores or a cheap grader) → weak: rewrite and retry once, or call web search; strong: skip web entirely (today 2–3 web chunks are always fetched)
- Iteration cap and a latency budget so the graph can never loop
- Verify: web calls per query down, faithfulness the same or better

### Day 32 — Answer verification and real moderation (G2, G3)

- Branch: feature/day32-g2-g3
- G2: verify_answer node for loose/none grounding (or a sample) → a warning flag in the metadata event → a badge in the UI
- G3: replace the keyword list and sanitize_query with Gemini safety settings plus a moderation classification call, in one safety node used by every entry point
- Verify: red-team prompts and rephrased unsafe requests are caught; normal study questions are not

### Day 33 — Indirect prompt-injection defences (G5)

- Branch: feature/day33-g5-injection
- Scan chunks at upload (flag column on document_chunks) and web chunks at fetch time for instruction-like text and hidden/zero-width characters
- Spotlighting: per-request random delimiters around each chunk; the constant system instruction says delimited content is data, never instructions
- Canary string in the system prompt; block any response containing it
- Frontend: override ReactMarkdown's img renderer in MessageList.js (drop or allowlist images) to close the exfiltration path
- Red-team set: payloads planted in test documents and web text; attack success rate tracked as an eval metric

### Day 34 — Conversation memory and tool use (C3, A1) — release

- Branch: feature/day34-c3-a1
- C3: embed each Q+A pair into a session_memory table (pgvector); retrieve the top-k older turns with the rewritten query; token-budgeted recent window; deleted with the session
- A1: tools — search_documents, web_search, generate_quiz, make_concept_map — callable by the model for open-ended requests; the deterministic RAG path stays the default
- Verify: a long session recalls something said 30 turns ago; tool calls show up as spans in Langfuse
- Release: develop → master, tag v0.5.0

---

## Phase 11 — BACKEND HARDENING & STUDY FEATURES (Days 35–38)

Focus: Auth hardening, rate limits, background ingestion, quizzes from documents (S1), flashcards

### Day 35 — Auth hardening — header-based streaming, refresh tokens, rate limits

- Branch: feature/day35-auth-hardening
- Fetch-based SSE client sending an Authorization header; remove ?token= from /chat/stream (finishes G8)
- Short-lived access tokens (~15 min) + rotating refresh token in an httpOnly, Secure, SameSite cookie; refresh_tokens table with revocation; /auth/logout revokes
- Rate limiting per user/IP on /chat/stream, /upload, /login, /register backed by Redis (slowapi — new dependency, confirm)
- Verify: an access token is useless after expiry; logout kills the refresh token; the limit returns 429 with Retry-After

### Day 36 — Background document ingestion with progress

- Branch: feature/day36-background-ingestion
- /upload returns 202 with the document id; indexing runs in the background
- Decision: FastAPI BackgroundTasks (no dependency, dies with the process) vs. a Redis-backed worker such as arq or RQ (new dependency, survives restarts)
- documents.status (queued, parsing, embedding, ready, failed) + progress + failure reason; GET /documents/{id}/status
- Verify: a large PDF uploads instantly and the status moves to ready; a corrupt file ends in failed with a reason

### Day 37 — Quizzes built from your documents (S1)

- Branch: feature/day37-s1-quizzes
- S1: Gemini structured output (response schema from Pydantic models) for quizzes and concept maps; delete the hand-written JSON parser
- Quiz questions generated from retrieved chunks of selected documents, each with its source document + page
- Persist quizzes, attempts and answers; score history per topic in /user/stats
- Verify: every question links to a real page; a retaken quiz updates the history

### Day 38 — Flashcards with spaced repetition — release

- Branch: feature/day38-flashcards
- Flashcards generated from documents with citations (structured output)
- SM-2 scheduling (ease factor, interval, due date) and a review endpoint; "due today" count
- Release: develop → master, tag v0.6.0

---

## Phase 12 — UI OVERHAUL (Days 39–42)

Focus: Modern chat-AI design system, chat UX, rich answers + citations, study pages, mobile + a11y

### Day 39 — Design system — fonts, tokens, dark mode, app shell

- Branch: feature/day39-design-system
- Fonts: Inter or Geist Sans for the interface, Geist Mono or JetBrains Mono for code, optional Source Serif 4 for long answers — self-hosted via @fontsource (new dependency) or Google Fonts
- Tailwind theme tokens: colours, radii, spacing, type scale; dark mode with the system preference as default
- Decision: shadcn/ui components (Radix + Tailwind, adds Radix packages) vs. hand-built components on Tailwind; lucide-react icons stay
- App shell: collapsible sidebar with sessions grouped by Today / Previous 7 days, centred ~768px chat column

### Day 40 — Chat experience

- Branch: feature/day40-chat-ux
- Auto-growing composer: Enter to send, Shift+Enter for a newline, attach button, answer-mode selector
- Stop generation (AbortController on the fetch stream), regenerate, edit and resend, copy
- Smooth token rendering, auto-scroll that pauses when the user scrolls up, typing indicator, skeleton loaders
- Verify: stop mid-answer leaves a clean partial message; regenerate replaces it

### Day 41 — Rich answers and citations

- Branch: feature/day41-rich-answers
- Code blocks with syntax highlighting and a copy button (react-syntax-highlighter or shiki — new dependency)
- Math with remark-math + rehype-katex (new dependencies) — essential for STEM study material
- Styled GFM tables; citation chips [1] with a hover card (document, page, snippet); sources panel; confidence/grounding badge; verification warning from Day 32

### Day 42 — Documents and study pages, responsive and accessible — release

- Branch: feature/day42-study-ui
- Drag-and-drop upload with progress and indexing status (Day 36); a documents library page
- Quiz, flashcard and concept-map pages restyled on the new design system
- Mobile layout (sidebar as a drawer), keyboard shortcuts (Ctrl+K new chat, / to focus), focus rings, aria labels; Lighthouse accessibility ≥ 90
- Toasts for errors; designed empty states
- Release: develop → master, tag v0.7.0

---

## Phase 13 — POLISH & LAUNCH (Days 43–44)

Focus: Load testing, security review, docs, v1.0

### Day 43 — Performance and security review

- Branch: feature/day43-perf-security
- Load test chat and upload (locust — new dependency — or k6 run outside the repo); set p95 targets; tune the DB pool
- /security-review over everything since v0.1.0; pip-audit and npm audit
- Decision: purge the Tesseract installer from git history — needs a history rewrite and force-push, so only with explicit agreement

### Day 44 — Docs and v1.0

- Branch: feature/day44-docs-v1
- Rewrite README.md so nothing in it drifts from the code; refresh docs/architecture.png
- Bring CLAUDE.md fully up to date; every tracker item marked Done or Skipped with notes
- Demo GIF/video and live links
- Release: develop → master, tag v1.0.0
