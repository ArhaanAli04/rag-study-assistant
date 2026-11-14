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
hybrid retrieval plus Tavily web results, generates a cited answer with Gemini 3.5
Flash-Lite (since v0.2.1, B9), and streams it to a React app over SSE. Also: concept-map generation, quiz
generation, chat sessions with export, thumbs feedback, and email/password + Google OAuth
login.

- Backend: Render — https://rag-study-assistant-api.onrender.com
- Frontend: Vercel — https://rag-study-assistant-chi.vercel.app
- Repo: https://github.com/ArhaanAli04/rag-study-assistant (branch `master`)

---

## Current Status

Update this block at the start and end of every session.

```
Last commit:  ed0fd3e on feature/day15-pgvector-chunks (draft PR #21 → develop, CI green on every push):
              de45311 schema + Postgres-only suite, 6eb47de search in Postgres (E4 parity), a936138 I5/I6 + UI
              + keyword fallback, ed0fd3e Supabase Storage. develop = 553c11a (Day 14 outcome, PR #20)
Pushed:       master = v0.2.2 (tagged on 1e84de8; production still FAISS in memory + files on Render's disk).
              develop = Day 14. Day 15 = PR #21, not merged yet
Uncommitted:  Checkpoint 5 (docs only): brief Outcome + UI table, CLAUDE.md, layout.md, timeline (Day 17
              runbook notes), guard-hook wording, posts 3 and 9. docs/learning/ updated (gitignored)
Untracked:    none. Local only (gitignored): the old SQLite files + backups in backend/data/ (refused by
              Settings since Day 15); backend/eval/corpus/* except manifest.json, eval/.cache/,
              eval/results/*.json, eval/datasets/{drafts, sheets, hard_candidates.jsonl}, docs/learning/.
              .env holds DATABASE_URL / DATABASE_SCHEMA (venv → compose Postgres), POSTGRES_PASSWORD,
              RAG_APP_PASSWORD, RAG_STAGING_DATABASE_URL, STORAGE_BUCKET=rag-staging + the four SUPABASE_S3_*
              values (never STORAGE_BACKEND). Compose Postgres has rag (dev), rag_test, rag_eval
Day 15:       Chunks table + Supabase Storage (I4, I5, I6, I1, I2, B10). document_chunks: halfvec(3072) +
              HNSW cosine, generated tsvector + GIN, CHECKs against zero vectors / blank text; every user_id FK
              CASCADE, failed_queries.session_id SET NULL, concept_map_nodes CASCADE (found: it blocked user
              deletes) — revisions 9e72706d7449 + 500c410270f5, both on rag_staging (at head). Postgres-only
              app and suite. PgChunkSearch (user filter in the query, one session per retrieval) replaced FAISS
              + BM25 after E4 parity (hybrid Hit@5 50→50/55, MRR@5 0.801→0.806; vector-only 0 flips;
              keyword-only MRR −0.043); faiss-cpu / rank-bm25 removed; HNSW recall@10 = 1.000. IndexingService
              in services/; query-embedding failure → keyword-only (not cached). Uploads: new / changed /
              unchanged / reindexed; delete = all versions + chunks + files; UI notice + "Not searchable yet"
              badge. FileStorage: local or Supabase S3 (boto3; DeleteObjects rejected → per-object deletes).
              Live: Docker stack and rag_staging + rag-staging bucket — restart keeps search (new question
              still cites), re-upload unchanged, delete leaves 0 files. CO6: a chat turn = 33 round trips
              (≈ 2.1 s on Render). Suite 271 → 325, frontend 11 → 19. Notes in docs/briefs/day15.md
Next:         /pre-commit + /ship commit Checkpoint 5 (tracker rows I4, I5, I6, I1, I2, B10 → Done included;
              rag_staging_app's password was rotated 2026-11-14), then /ship merge PR #21. Then Day 16 (/run-day 16): batch embeddings (I3), CO3 embedding
              cache on content_hash, CO6 round-trip cuts (33 → ?), reindex script, B7. Day 17 release runbook
              notes are in the timeline (Render STORAGE_* vars, no Redis flush, v0.2.2 rows need a re-upload)
Blockers:     none. Every `docker compose` command needs POSTGRES_PASSWORD and RAG_APP_PASSWORD in .env. Every
              pytest run needs TEST_DATABASE_URL / TEST_DATABASE_SCHEMA (rag_test); evals need EVAL_DATABASE_URL
              (rag_eval) and $env:GEMINI_API_KEY = the eval key. Never print .env values, connection strings
              or S3 credentials. GitGuardian flags compose *PASSWORD= lines: triage as false positives
```

---

## Repo Structure

```
rag-study-assistant/
├── backend/                  ← the Python project; run the app from here (CWD = backend/)
│   ├── app/                  ← the package, imported as `app.*` (Day 7), regrouped Day 8
│   │   ├── main.py           ← create_app() + lifespan (Day 9); `app = create_app()` is what uvicorn serves
│   │   ├── api/              ← deps.py (get_db, current user, services from app.state); routes/ — one router per area
│   │   ├── core/             ← config.py (Settings), logging.py, request_id.py, security.py, errors.py, gemini.py
│   │   ├── db/               ← base.py (Base + naming convention), session.py (engine, SessionLocal), migrations.py (head check), models/ (one file per table), repositories/ (queries) — Day 13
│   │   ├── ingestion/        ← chunking, upload storage (keys + local/S3 FileStorage); parsers/, ocr/, tables/
│   │   ├── retrieval/        ← embeddings, PgChunkSearch (pgvector + full-text), retrieval service, rerank, decomposition, web/
│   │   ├── generation/       ← llm_client.py, topic_classifier.py, concept_extractor.py
│   │   ├── services/         ← container.py (composition root), chat_pipeline, indexing, quiz, documents, sessions, accounts, concept maps, chat guards, oauth; caches/
│   │   └── schemas/          ← Pydantic request/response models (concept_maps, auth, documents, …)
│   ├── eval/                 ← retrieval/ (E4, Day 11; on its own rag_eval database since Day 15), generation/ (judge, E1/E2, Day 12), corpus/ (manifest only), datasets/, results/, cache_tuner.py; not in the image
│   ├── tests/                ← offline pytest suite on a Postgres *_test database (conftest fakes Gemini, Tavily, Redis, S3) + samples/
│   ├── data/                 ← the old SQLite files only (unused since Day 14, backups) — gitignored
│   └── logs/, uploads/       ← runtime output — gitignored
├── frontend/                 ← React 19 (react-scripts), Tailwind, React Flow, react-markdown
│   └── src/                  ← pages/ components/ contexts/ hooks/ services/ config/ utils/ lib/
├── scripts/                  ← dev.ps1 (Docker dev helper); postgres/init-rag-schema.sh (local + CI role/schema); supabase/ (setup SQL, scram_verifier.py)
├── alembic/, alembic.ini     ← the only schema path since Day 13 (T2): baseline 7cb8829683ab; URL from Settings; shipped in the image
├── docs/                     ← timeline.md (61-day build plan), architecture/layout.md (target package layout + module map), posts/ (LinkedIn series material), improvements.md (gap audit), improvement-tracker.md (status), briefs/, claude-cheatsheet.md, architecture.png
├── .claude/                  ← skills/ (/run-item, /pre-commit), hooks/*.py, settings.json
├── .github/workflows/        ← ci.yml: backend (+ Postgres service), frontend, docker — the required checks; supabase-keepalive.yml (Day 13)
├── ruff.toml                 ← lint rules for CI, the edit hook and local `ruff check .`
├── Dockerfile, docker-compose.yml                      ← backend + frontend + redis + postgres (local, Day 13)
├── pytest.ini                ← testpaths = backend/tests, pythonpath = backend
├── requirements.in           ← direct dependencies, one reason each — the file to edit (Day 10)
└── requirements.txt          ← generated UTF-8 lock (Linux, Python 3.11); the Dockerfile and CI install it
```

### Backend module map (`backend/app/`)

Paths are relative to `backend/app/`. Day 8 regrouped the modules into `db/`, `ingestion/`,
`retrieval/`, `generation/`, `services/` and `schemas/`; the target path and day of every module,
and the known exceptions to the downward-only dependency rule, are in `docs/architecture/layout.md`.

| Area | Modules | Notes |
|---|---|---|
| Core (Day 7) | `core/config.py`, `core/logging.py`, `core/request_id.py`, `core/security.py`, `core/errors.py`, `core/gemini.py` | `Settings`: every env var, read once at import. `request_id`: per-request ID (`X-Request-ID`) stamped on log lines by `RequestIdFilter`. `security`: JWT encode/decode and password hashing only — no DB access since Day 9. `gemini.py`: `build_gemini_client()`, the only place a `genai.Client` is built. `logging`: rotating file + console handlers, G8 redaction |
| App & wiring (Day 9) | `main.py`, `services/container.py`, `api/deps.py`, `api/routes/{health,auth,users,documents,chat,sessions,feedback,quiz,concepts}.py` | `main.py`: `create_app()` (middleware, routers, handlers — no I/O) and the lifespan (`assert_schema_at_head` — refuses a database not at Alembic head, Day 13; `build_services()` onto `app.state.services`, Redis closed on shutdown). `container.py`: the `Services` dataclass — one Gemini client, one FAISS + BM25, caches, `ChatPipeline`, `ConceptMapService`. `deps.py`: `get_db`, `get_current_user` (Bearer), `get_user_from_query_token` (SSE `?token=`), `get_services`. Routers hold HTTP only; their SQL moved to `db/repositories/` on Day 13 |
| Data (Day 13, T2) | `db/{base,session,migrations}.py`, `db/models/{user,chat_session,message,document,failed_query,concept_map}.py`, `db/repositories/{users,sessions,documents,messages,failed_queries}.py`, `ingestion/models.py`, `services/account_service.py`, `schemas/` | `base.py`: `Base` with a constraint naming convention (`pk_`, `fk_`, `uq_`, `ix_`). `session.py`: `build_engine(url)` — Postgres only since Day 15 (`pool_pre_ping`, pool 5 + 5, recycle 300 s) — plus `engine`, `SessionLocal` from `settings.DATABASE_URL`. `migrations.py`: `assert_schema_at_head`, `assert_expected_schema` (Postgres `current_schema()` must equal `DATABASE_SCHEMA`), `alembic_config()`. `models/__init__.py` imports all 8 models (what `alembic/env.py` imports); `Session` lives in `chat_session.py`; `Chunk` (Day 15) in `document_chunk.py` — `document_chunks`: halfvec(3072) embedding + HNSW (cosine), generated `tsv` + GIN, CHECKs against zero vectors and blank text. Repositories: plain functions taking the session, `user_id: int`, never commit (the caller does), return `None` for a missing row; `chunks.py` holds the two searches (user filter in the query, I1). `ingestion/models.py`: `DocumentChunk` (parser output, not a table). `account_service.py`: `authenticate_user`, `delete_user_account` — rows in one transaction, then files, index tombstones, caches (B1) |
| Auth | `core/security.py`, `api/routes/auth.py`, `api/deps.py`, `services/oauth_service.py` | JWT (HS256, 7-day, no refresh token), pbkdf2_sha256, Google OAuth |
| Ingestion | `ingestion/{chunk_builder,chunking,text_preprocessing,upload_storage}.py`, `ingestion/parsers/{pdf,pptx,pptx_pipeline,docx}.py`, `services/{indexing_service,document_service}.py` | character-based chunks (1000 chars / 100 overlap). `IndexingService` (Day 15): parse → skip blank chunks (B10) → embed → replace the document's `document_chunks` rows; caller commits. `document_service`: `register_upload` → `new` / `changed` / `unchanged` / `reindexed` (I6), `delete_document` removes every version + chunks + files (I5). `upload_storage.py`: keys `uploads/{user_id}/{uuid}{ext}` + `check_key` (G7), `FileStorage` with `LocalFileStorage` and `S3FileStorage` (Supabase Storage, Day 15) |
| OCR / tables | `ingestion/parsers/unified.py`, `ingestion/ocr/{ocr,image_preprocessing}.py`, `ingestion/tables/{pdf_tables,tables}.py` | not reachable from `/upload` (images are rejected) |
| Indexes | `retrieval/{embeddings,pg_chunk_search}.py`, `db/repositories/chunks.py` | Postgres since Day 15 (FAISS / BM25 deleted after the E4 parity run): pgvector cosine search + full-text (`ts_rank_cd` over an OR-ed `plainto_tsquery`), both filtered to the user in the query and run in one session per retrieval (`PgChunkSearch.search`). `EMBEDDING_DIM = 3072` in `embeddings.py` (= the column's halfvec size, checked by a test), sent as `output_dimensionality`. `EmbeddingService` raises `EmbeddingError` instead of returning zero vectors |
| Retrieval | `retrieval/{retrieval_service,context_assembly,confidence,query_decomposer,query_preprocessor,reranker,context_compressor}.py`, `retrieval/web/{search_client,scraper}.py` | `context_assembly.py` (Day 11): `assemble_context()` — decompose → `hybrid_retrieve` per sub-query → parent expansion → compress; the chat and the retrieval eval both call it, so the eval measures what the chat sends. `confidence.py`: the 0–100 scale and every threshold on it (B2) — compare only against these names; E4 (Day 11) found the score doesn't predict a hit (AUC 0.332 after B8), so it is replaced, not re-tuned, on Day 26. `RetrievalService` takes an embedder, a `ChunkSearch` and its Redis caches by injection (typed by `Protocol`s) and has switches for web search, the L1 cache and the fusion weights (production defaults: on, on, 0.6 / 0.4). Scores are higher-is-better on both halves (cosine similarity; `ts_rank_cd`). A failed query embedding degrades to keyword-only search for that query and is not L1-cached (Day 15). `reranker.py` does no real reranking |
| Generation | `generation/{llm_client,topic_classifier}.py`; user-facing error messages in `core/errors.py` | retry + circuit breaker live in `LLMClient`; every class takes the shared `genai.Client` and its model name from `services/container.py` (`settings.GEMINI_GENERATION_MODEL`, B9 — no class has a default model since Day 12) |
| Chat & caches | `services/chat_pipeline.py`, `services/answer_preparation.py`, `services/session_service.py`, `services/chat_guards.py`, `services/quiz_service.py`, `services/caches/{semantic_cache,query_cache,web_cache}.py` | `ChatPipeline`: the one chat pipeline (behind `/chat/stream`). `answer_preparation.py` (Day 12): `prepare_answer()` — `assemble_context` → grounding level → `LLMClient.build_prompt`; the chat and the generation eval both call it, so the judge grades the prompt the chat sends. `chat_guards.py`: the injection phrases and the one unsafe-keyword list (G3 replaces both) |
| Concept maps | `services/concept_map_service.py`, `retrieval/concept_map_retriever.py`, `generation/concept_extractor.py`, `schemas/concept_maps.py` | |
| Retrieval eval (Day 11, E4) | `backend/eval/retrieval/{__main__,runner,metrics,dataset,configs,corpus,embedding_cache,rate_limit,key_guard,generate_questions,mine_feedback}.py`; `eval/corpus/manifest.json`, `eval/datasets/retrieval_v1.jsonl`, `eval/results/*.md` | `python -m eval.retrieval --config …` builds `RetrievalService` directly (no `app.main`, no Redis), web search + L1 off, indexes the corpus through the real `IndexingService` into its own database (`EVAL_DATABASE_URL`, name `*_eval`; it re-creates one eval user per run, Day 15), then per question a served pass (production `top_k` 5), a deep pass (10) and `assemble_context`. Metrics in plain Python (Hit@5 headline, MRR, Recall@k, nDCG@10, bootstrap CIs, confidence AUC). Labels are (document, page). Corpus files (gitignored) are pinned by sha256; the dataset is checked against them before every run. `key_guard.py` refuses `.env`'s production Gemini key; `embedding_cache.py` (sqlite, `eval/.cache/`, gitignored) paces embeddings under the eval project's free tier and resumes after a stop. Result JSON is gitignored, Markdown summaries are committed |
| Generation eval (Day 12, E1/E2) | `backend/eval/generation/{__main__,runner,judge,citations,metrics,answer_cache,calibrate}.py`; `eval/datasets/generation_calibration_v1.labels.jsonl`, `eval/results/*-generation-*.md`, `*-calibration-*.md` | `python -m eval.generation` answers `retrieval_v1` through the chat's own `prepare_answer` + `LLMClient.stream_answer` (web off, `quick` mode), then an LLM judge (`gemini-3.5-flash-lite`, schema JSON, no temperature — 3.5 ignores it): faithfulness per claim (`faith-v2`: supported / not_in_context / contradicted, plus citation support) and relevance (`rel-v1`); citation validity is checked in code against the context labels. Answers and verdicts are cached in `eval/.cache/generation.sqlite` (key: model, prompt, mode, prompt version, replica), so re-runs are free and a daily-quota stop resumes. `calibrate sample/score/compare`: 20 blind reference labels (Claude, adjudicated by the owner), each answer judged twice. Refuses to overwrite a results file without `--force` (the baseline's Markdown carries a hand-written owner review). Reuses `eval/retrieval`'s corpus, embedding cache, key guard and pacing |
| `eval/cache_tuner.py` (outside `app/`) | `backend/eval/cache_tuner.py` | Day 10: moved out of `app/`, `main()` builds its objects with `build_services()`; `python -m eval.cache_tuner` from `backend/` (live Gemini + Redis). Print-only lookup counts; CO5 (Day 32) replaces it. The RAGAS / word-overlap scripts were deleted on Day 12. `.dockerignore` keeps all of `eval/` out of the image (`docker-compose.override.yml` mounts it read-only for the container test run) |

The one-off DB scripts, `scripts/manual/`, `frontend.py`, `document_delete_service.py` and
`MessageBubble.js` were deleted on Day 10 (git history has them).

---

## Tech Stack (actual)

| Layer | Technology |
|---|---|
| Backend | FastAPI, SQLAlchemy (sync `Session`), Pydantic v2; Python 3.11 (Docker) / 3.12 (local `venv`); code needs ≥ 3.10 |
| LLM | Gemini `gemini-3.5-flash-lite` via `google-genai` (Day 12, B9: `GEMINI_GENERATION_MODEL`, default; reaches production with v0.2.1 — until then production runs `gemini-2.5-flash-lite`) |
| Embeddings | Gemini `gemini-embedding-001`, 3072 dimensions, L2-normalized, one API call per text (I3, Day 16) |
| Vector search | pgvector in Postgres (Day 15): `document_chunks.embedding` halfvec(3072), HNSW `halfvec_cosine_ops`; user filter in the query (I1). At today's sizes the planner picks an exact scan; forced HNSW recall@10 = 1.000 on the eval corpus |
| Keyword search | Postgres full-text (Day 15): generated `tsv` (`english`) + GIN, `ts_rank_cd` over an OR-ed `plainto_tsquery` (replaced `rank-bm25`; no IDF) |
| File storage | `FileStorage` (Day 15): local `backend/uploads/` (dev, tests, Docker volume) or Supabase Storage over its S3 API (`boto3`, private buckets `rag-prod` / `rag-staging`) |
| Web search | Tavily (`search_depth="advanced"`) + domain allowlist + BeautifulSoup scraping |
| Cache | Redis (`redis-py`) |
| Database | Postgres since Day 14. Production: Supabase (Postgres 17.11, pgvector 0.8.2, `ap-south-1` Mumbai) in the owner's existing project, isolated by schema — `rag` (production, role `rag_app`, from release v0.2.2; started empty) and `rag_staging` (role `rag_staging_app`, at head). Local dev (Docker backend and venv): `pgvector/pgvector:0.8.2-pg17` in compose, schema `rag`, started empty — no data was copied (Render had no disk; Day 14 brief). Driver `psycopg[binary]` 3.3.8, `pgvector` 0.5.1 (SQLAlchemy `HALFVEC`); schema only through Alembic. Postgres only since Day 15: `DATABASE_URL` has no default and SQLite is refused (pgvector, full-text and the generated column don't exist there) |
| Auth | python-jose JWT, passlib, Authlib Google OAuth; token kept in browser `localStorage` |
| Parsing | PDF/PPTX/DOCX utilities, camelot + pdfplumber tables, Tesseract OCR |
| Frontend | React 19, react-scripts 5, Tailwind 3, React Flow 11 + dagre, react-markdown + remark-gfm, jsPDF, html-to-image, lucide-react |
| Deploy | Docker; Render (backend), Vercel (frontend); `docker-compose.yml` for the local full stack |
| CI | GitHub Actions (`.github/workflows/ci.yml`); ruff 0.15.18 pinned in the CI job only (not in `requirements.txt`), rules in `ruff.toml`. The `backend` job has a Postgres service (database `rag_test`): `alembic upgrade head` + `alembic check` (Day 13), then the **whole pytest suite on Postgres** (Day 14, `TEST_DATABASE_URL`; the only way it runs since Day 15); `supabase-keepalive.yml` pings production every 3 days (runs only from `master`) |

Kept but not imported by `backend/app/` (Day 10, each with its reason in `requirements.in`):
`langgraph` (A1), `langsmith` (O1), `instructor` (S1; it also pulls in `openai`), `tiktoken` (C1; also
required by `tavily-python`). Removed Day 10: `streamlit`, `qdrant-client`, `opencv-python`,
`scikit-learn`, `sympy`, `safetensors`, `tokenizers`, `pdf2image`, `oauth`, `bcrypt` (+ orphans).
Day 15: added `pgvector` (HALFVEC type) and `boto3` (Supabase Storage); removed `faiss-cpu` and `rank-bm25`
after the E4 parity run (`tqdm` stays as a transitive dependency).
Removed Day 12 (E1, Gemini judge chosen over RAGAS): `ragas`, `datasets` and the 20 packages only they
needed — `langchain`, `langchain-classic`, `langchain-community`, `langchain-openai`,
`langchain-text-splitters`, `huggingface-hub`, `scipy`, `networkx`, `scikit-network` among them (lock
158 → 136 pins, no version moved).

**README drift** — claimed in `README.md` but not true today: sentence-transformers MiniLM
embeddings (now Gemini), cross-encoder / BM25 "reranking" (it is score fusion plus a no-op; and BM25 is
Postgres full-text since Day 15), refresh tokens, rate limiting, image / handwritten-note upload, quizzes built from
uploaded documents with source references, persisted quiz performance tracking, Python 3.9+,
React 18.

---

## How Requests Flow

**Upload** — `POST /upload` (Day 15): extension check (`.pdf` / `.pptx` / `.docx`, ≤ 50 MB) → read
the bytes, sha256 → `register_upload` (`services/document_service.py`) against the latest version of
`(user_id, file_name)`:
- **identical, already indexed** → `unchanged`: nothing stored, nothing indexed, no `doc_version`
  bump (I6). If the row's file is gone (Render before Day 15) or is a pre-G7 shared flat key, a
  fresh copy is stored and the row re-linked first.
- **identical, no chunks** → `reindexed` (v0.2.2 rows, or a failed earlier indexing).
- **new name** → `new`; **new hash** → `changed`: the old version goes inactive and its chunks are
  deleted in the same transaction.

New and changed files are written to `FileStorage` under a server-generated key
`uploads/{user_id}/{uuid}{ext}` *before* the row is committed (the client's basename is display
metadata only). Then, unless `unchanged`: `local_copy` of the stored file → `IndexingService`
(chunk → skip blank chunks → embed → replace the document's `document_chunks` rows) → one commit with
`User.doc_version += 1`. A failed embedding returns 502 and writes no chunks (re-upload → `reindexed`);
a storage failure on write returns 503. The response's `status` drives the notice on the
Documents page.

**Chat** — `GET /chat/stream` (`api/routes/chat.py`) → `ChatPipeline.answer` (`services/chat_pipeline.py`);
the only chat endpoint since Day 9 (`POST /chat`, a divergent copy, was deleted). Steps 1–6 run
before the response starts, so a retrieval failure is a normal HTTP 500; generation runs while streaming.
1. Auth from the `?token=` query param (`get_user_from_query_token`) → injection-phrase and unsafe-keyword checks (`chat_guards.py`) → semantic cache lookup (a hit is replayed as SSE; an embedding failure counts as a miss)
2. Get/create session → load the last 20 messages → log the user message (`session_service.add_message` → `messages_repo.add`, committed at once; its id is the `message_id` frame — Day 13 replaced a raw INSERT whose `lastrowid` is not the row id on Postgres) → LLM topic tagging while the session topic is "General"
3. `assemble_context` (`retrieval/context_assembly.py`): `QueryDecomposer` (regex split) → for each sub-query, `hybrid_retrieve`: L1 in-process cache → embed the query (a failure → keyword-only, Day 15) → `PgChunkSearch.search`: pgvector cosine top-k + full-text `ts_rank_cd` top-k, this user only, one DB session → min-max normalize → 0.6/0.4 fusion → confidence heuristic (0–100) → Tavily chunks (always: 3 if confidence < 60, else 2) → "rerank" (re-sort by existing score) → top 5 → parent-page expansion
4. `SimpleContextCompressor`: top 6 chunks, 800 characters each
5. Grounding level from confidence (`retrieval/confidence.py`): strict ≥ 70, loose ≥ 30, else none (model knowledge allowed)
6. Gemini payload: system instruction (grounding + answer-mode rules) + prior turns as `contents` + a final user turn holding the retrieved context and the question
7. SSE events: `metadata` → `token`… → `message_id` → `[DONE]`; then the answer is stored in the semantic cache. Queries with confidence < 30 are logged to `failed_queries`.

**Concept map** — `POST /api/concepts/generate` → `ConceptMapService` → `ConceptMapRetriever`
(web by default; since Day 9 it shares the app's `RetrievalService`, but the UI hard-codes
`useDocuments = false` — R5, Day 17) → `ConceptExtractor` (Gemini,
JSON parsed by hand) → saved as `ConceptMap` / `ConceptMapNode` → React Flow + dagre layout.

**Quiz** — `POST /quiz`: a single Gemini prompt built from the topic alone (general knowledge,
not the user's documents); returns plain text, unparsed and not persisted.

---

## Feature Status

### Working
- Email/password and Google OAuth login; profile, change password, user stats
- PDF/PPTX/DOCX upload, hash-based versioning, per-user hybrid retrieval — persistent since Day 15: chunks and vectors in Postgres (`document_chunks`), files in `FileStorage` (Supabase Storage in production from v0.3.0, Day 17). Re-uploads report `new` / `changed` / `unchanged` / `reindexed` (I6); deleting a document removes every version, its chunks and files (I5); the Documents page shows the upload notice and a "Not searchable yet" badge for rows without chunks
- Streaming chat with citations, confidence, grounding levels, three answer modes (`quick` / `detailed` / `step_by_step`; the frontend sends `step-by-step`, normalized since Day 2 — before that it silently got the detailed prompt), multi-turn history (commit 73d8bae)
- Tavily web augmentation with a domain allowlist; Redis web-result cache (1 h)
- Sessions: list, rename, delete, automatic topic tags; chat export to Markdown / PDF (frontend)
- Thumbs up/down feedback → `messages.feedback` and `failed_queries`; `GET /analytics/failed-queries`
- Concept maps from web context: generate, list, view, delete, statistics; PNG / JPEG export
- Quiz generation by topic and difficulty
- LLM retry with backoff (non-streaming) and a circuit breaker; user-friendly error messages
- Docker images and docker-compose (backend, frontend, Redis)
- CI on GitHub Actions (Day 6, `.github/workflows/ci.yml`): `backend` (Python 3.11, ruff, a Postgres service — `alembic upgrade head` + `alembic check` since Day 13, the whole offline pytest suite on it since Day 14 — no secrets), `frontend` (Node 24, `npm ci`, Jest, CRA build with `CI=true`), `docker` (both images, no push); required on `master` and `develop` by branch protection
- Alembic as the only schema path (Day 13, T2): baseline `7cb8829683ab`, migrations before uvicorn (image `CMD`, compose dev command), startup refuses a database not at head
- Postgres everywhere (Day 14): production on Supabase `rag` from v0.2.2, local dev on the compose Postgres. Accounts, sessions, messages, feedback, concept maps and document rows survive restarts and deploys (on Render they were wiped by every deploy, restart and idle spin-down before)

### Present but partial, stubbed, or broken (IDs → `docs/improvements.md`)
- Reranker only re-sorts by the existing score (R1); query decomposition is regex (R2); fusion is min-max + fixed weights (R4)
- Semantic cache (per-user since Day 1, G6) ignores the conversation, has no TTL, unvalidated threshold (CO5); linear scan (CO1)
- Prompt-injection guard (G1, Day 2) is a narrow phrase blocklist in `chat_guards.py` (replaces `sanitize_query()`), called first in `ChatPipeline`; refusals go out over SSE and are not stored — a stop-gap until G3. `verify_answer()` is never called (G2); the unsafe-topic check is one 6-keyword substring list in `chat_guards.py` since Day 9 ("bomb" still matches "bombardment") — G3 replaces it
- Evaluation: retrieval eval since Day 11 (E4; its `web` config hasn't been run yet) and generation eval with a calibrated Gemini judge since Day 12 (E1/E2 done; RAGAS and the word-overlap metrics were removed). Partial: the judge is the same model as the generator, `faith-v2` was tuned on its 20-answer calibration set, and there is no answer-correctness metric or CI gate yet (E3, Day 26)
- Concept extraction hand-parses JSON (S1); embeddings use one call per chunk (I3); sub-queries are retrieved serially (CO2)
- Production still runs v0.2.2 until the Day 17 release: there, rows persist but files and vectors don't (Render has no disk; FAISS/BM25 in memory). `develop` has the fix since Day 15 (pgvector + Supabase Storage). v0.2.2's documents have no chunks and no stored file, so after v0.3.0 they show "Not searchable yet" until the user re-uploads them (the Day 16 reindex can't help: their files are gone)

### Not present
- Token counting and budgets (C1); token-usage logging (CO4)
- History-aware query rewriting (C2); retrieval-based conversation memory (C3)
- Indirect prompt-injection defenses (G5); request tracing (O1)
- Golden eval set + CI eval gate (E3); CD — deploys gated on CI, staging, post-deploy checks (Days 21–22; Render and Vercel still auto-deploy `master` on push)
- Query expansion / HyDE (R3); agentic tool use (A1); embedding cache (CO3, Day 16). (I1 — an ANN index with the user filter inside the query — exists since Day 15)
- Rate limiting, refresh tokens, quiz persistence
- Frontend tests beyond 6 files / 19 tests: `components/MessageList.test.js`, `components/ChatWindow.test.js` (refusal and normal stream), `components/AccountSettingsModal.test.js`, `AccountDeletionFlow.test.js`, `pages/LoginPage.test.js` (login + App smoke test, Day 5), `pages/DocumentsPage.test.js` (upload notices, 502 error, "Not searchable yet" badge, Day 15). No tests for concept maps, quiz or sessions sidebar. Run with `cd frontend; npm test -- --watchAll=false`

---

## Planned & Deferred

`docs/improvement-tracker.md` is the source of truth for status; `docs/improvements.md` holds
the evidence and direction for each ID. When status changes, update the tracker, not this file.

- **P0 — do first:** G6, G7, G8, G4, G1, O2, E1, E4, R1, I4, I5, R5, B1, G9
- **P1 — planned:** G2, G3, G5, E2, S1, O1, R2, R3, C1, C2, I3, CO1, CO2, CO4, CO5, CO6, I6, B2, T1, T2
- **P2 — deferred until usage grows:** R4, E3, C3, A1, I1, I2, CO3, T3, B11, B12

Order: `docs/timeline.md` sequences every item (plus Docker, refactor, CI/CD, Langfuse,
LangGraph, study-feature and UI work) into 61 days — one day per session, started with
`/run-day <N>`. It moves I4/I5/I6 to the pgvector migration (Day 15) and E4 to just after the
refactor (Day 11). Hosting decided 2026-11-04: **Supabase** for Postgres + pgvector (Day 13) and
file storage (Day 15), kept awake by a scheduled GitHub workflow. Changed 2026-11-11 (Day 13): no new
Supabase projects — the owner's **existing project** (it also hosts another app), isolated by schema:
`rag` / `rag_staging`, each owned by its own login role, not exposed to the Data API; Storage buckets
`rag-prod` / `rag-staging` in the same project (Day 15). Added 2026-11-04:
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
| Fixed Day 15 (in production from v0.3.0, Day 17): chunks and vectors live in Postgres (`document_chunks`) and files in `FileStorage`, so a restart keeps search. Verified on the Docker stack and on `rag_staging` + the `rag-staging` bucket: after a restart a *new* question still cites the uploaded PDF | I4 | Done |
| Concept maps search a separate, empty index, so "use documents" finds nothing | R5 | P0 |
| Fixed Day 15: deleting a document removes every version of that file name, their chunks (ON DELETE CASCADE) and the stored files, then bumps `doc_version`; it is never cited again (API test + live checks: 0 files left in the volume / bucket) | I5 | Done |
| Fixed Day 15: an identical re-upload with chunks is `unchanged` (no re-embedding, no `doc_version` bump, same chunk count); a changed file deletes the previous version's chunks | I6 | Done |
| Fixed Day 3: uploads go to `uploads/{user_id}/{uuid}{ext}` with a containment check. Residual: rows created before Day 3 still point at flat `uploads/<name>` paths, one of them shared by users 1 and 2 (rebuilt Day 16) | G7 | Done |
| Fixed Day 3: `DELETE /user/delete` removes all the user's rows (since Day 15 `document_chunks` too, in the same transaction, with ON DELETE CASCADE on every `user_id` as the safety net), stored files (through `FileStorage`) and caches. Residual: a deleted user's `query_cache:*` keys live ≤ 1 h. (SQLite's reuse of freed user ids ended with Postgres, Day 14: sequences never reuse an id) | B1 | Done |
| Fixed Day 9: confidence compared on the wrong scale. `POST /chat`'s 0.7 / 0.3 grounding went with the endpoint; the forced-web cap is 30, not 0.3; every threshold is a named constant in `retrieval/confidence.py`. Day 11 (E4): the score doesn't predict a hit (AUC 0.638 → 0.332 after B8; strict band hits less often than loose; 2 of 6 out-of-corpus questions get strict) — replace the heuristic on Day 26 | B2 | Done |
| Fixed Day 5: `pytest.ini` uses `[pytest]`, so `testpaths` / `pythonpath` apply; the manual `src/test_*.py` scripts moved to `scripts/manual/` (deleted Day 10) and are never collected | T1 | Done |
| Fixed Day 10: the contrib OpenCV build is reinstalled last (Dockerfile, CI, venv setup), so `cv2.ximgproc` is complete and ruled tables in images / PPTX slide images extract again; the Docker build asserts it | B3 | Done |
| Fixed Day 10: deskew fits the ink (inverted Otsu), not the paper, and folds OpenCV's (0, 90] angle; `scan_handwritten.png` OCR 0 → 29 words | B5 | Done |
| `preprocess_image` names its output with `.replace('.png', …)`, so a `.jpeg` / `.tif` input is overwritten by its own preprocessed copy. Not reachable from any user path today | B6 | P2 |
| img2table's defaults (used by `extract_tables_from_image`) miss tables without ruling lines (`tableimage2.jpg`: 0 → 1 table with `borderless_tables=True`); measure false positives on real slide decks first (Day 16) | B7 | P2 |
| Fixed Day 5: concept-map generation returned 500 whenever a node had empty sources (`concept_extractor` wrapped the whole source list) | B4 | Done |
| Fixed Day 11: FAISS's squared L2 distances were fused as if higher = better, ranking the vector half backwards. `hybrid_retrieve` converts to cosine (`1 − d²/2`). E4: Hit@5 0.782 → 0.909, MRR@5 0.339 → 0.801. The residual (`POST /search` returned raw distances) ended Day 15: pgvector returns cosine similarity | B8 | Done |
| Fixed Day 12: the generation model is `GEMINI_GENERATION_MODEL` (passed to `LLMClient`, `TopicClassifier`, `ConceptExtractor`), default `gemini-3.5-flash-lite` (500 RPD; 2.5-flash-lite's free tier was 20 and production's peak 28 requests in one day). It passed the generation eval's absolute gate (strict faithfulness 0.956, 0 contradicted claims, relevance 0.982); not a paired comparison — 2.5-flash-lite is not served to new projects. Reaches production with v0.2.1; rollback: `GEMINI_GENERATION_MODEL=gemini-2.5-flash-lite` on Render | B9 | Done |
| Fixed Day 15 (pulled forward from Day 16): `IndexingService` skips blank chunks (and strips NUL characters) before embedding, and `document_chunks` refuses zero vectors and blank text by CHECK; the eval corpus indexes 419 chunks (3 blank PPTX chunks skipped). The PPTX chunker still emits them | B10 | Done |
| Fixed Day 13: Alembic is the only schema path — URL from `Settings` (absolute SQLite default, so no side database), every model imported (`app.db.models`), baseline `7cb8829683ab` autogenerated on Postgres; startup `ALTER`s and `create_all` deleted; migrations run before uvicorn and the app refuses a database not at head. Verified: empty Postgres → `upgrade head` + `alembic check` no diff (local, CI, Supabase `rag_staging`); both local SQLite files schema-checked and stamped (backups in `backend/data/`). Also found: five `str(user_id)` DB filters, three string-id inserts and a raw-INSERT `lastrowid` that break on Postgres — fixed with the repositories, guarded by repository tests on Postgres in CI | T2 | Done |
| Done Day 10 except the Tesseract installer still in git history (purge decided on Day 60) | T3 | P2 |
| Fixed Day 14: `DELETE /sessions/{id}` returned 500 on Postgres for a session with failed queries (`fk_failed_queries_session_id_sessions`; SQLite never enforced foreign keys). `sessions_repo.delete_with_messages` now detaches them (`session_id = NULL`). Day 15's revision adds `ON DELETE SET NULL` there and `ON DELETE CASCADE` on every `user_id` foreign key (delete-path audit in the Day 14 brief) | — | Done |
| Fixed Day 14: an identical re-upload whose existing row's file was gone (Render has no disk) deleted the new copy and indexed a missing file, so that file could never be uploaded again. `register_upload` re-links the row to the new copy | — | Done |
| Found Day 14 (security): Render's SQLite reset user ids on every deploy / restart / idle spin-down while Render's Redis kept `semantic_cache:{user_id}` (no TTL), so a new user with a reused id could get a previous user's cached answers and their document text. Fixed by flushing Render Redis right before the v0.2.2 deploy (2026-11-13: DB 0 5 → 0 keys, DB 1 empty), after which Postgres never reuses an id; any future database reset needs the same flush | G9 | Done |
| `GET /sessions/{id}/messages` omits each message's `feedback`, so a reloaded chat shows no thumb already given (and a repeat thumbs-down logs a second failed query). Fix the backend field and `ChatWindow.js` rendering the same day | B11 | P2 |
| Every DB round trip crosses regions (Render Singapore → Supabase Mumbai, ~63 ms); server-side statement time is ≤ 0.05 ms. `/me` = 4 round trips counted Day 15 (pre-ping, BEGIN, query, ROLLBACK); on Render it measured +190 ms over `/health` on Day 14. A chat turn = **33 round trips** — 6 pool pre-pings, 6 BEGIN, 15 statements, 6 COMMIT/ROLLBACK ≈ 2.1 s on Render (counted Day 15 after the move to pgvector; retrieval's share is 5). Day 16 cuts it | CO6 | P1 |
| Source chips list retrieved chunks, not cited sources: duplicates (one URL ×4, p.1 ×2) and pages the answer cites can be missing (answer "Page 2", chips only p.1) | B12 | P2 |
| A semantic-cache hit replays its original `sources`. After a Render restart (rows and `doc_version` kept, index gone, I4) a repeated question still cites a document that is no longer indexed; a new question shows the real state. Day 15 removes the gap in `develop` (the index persists; deletes bump `doc_version`); production keeps it until v0.3.0. Noted under CO5 | CO5 | P1 |
| Fixed Day 15: `concept_map_nodes.map_id` had no ON DELETE rule, so once every `user_id` cascaded, a user delete through the schema was blocked by the user's concept-map nodes. Revision `500c410270f5` cascades it (on `rag_staging` already) | — | Done |
| Found Day 15: Supabase's S3 endpoint rejects `DeleteObjects` from boto3 1.44.3 (`InvalidRequest`, also with `request_checksum_calculation="when_required"`); CRC32 vs `Content-MD5` suspected, unconfirmed. `S3FileStorage.delete_prefix` lists and deletes one object at a time (account deletion only); the fake S3 client has no `delete_objects`, so batch delete can't come back unnoticed. Revisit on a boto3 / Supabase change (brief Risk 17) | — | P2 |

---

## Conventions for This Repo

- **No backend work without its UI (owner's rule).** Every user-visible backend capability — a new endpoint, response field, status, flag, score, or feature — ships with its frontend integration **in the same day/PR**: the screen or control that uses it, plus loading, empty, and error states. Never "UI later". Briefs list the UI changes for every deliverable; if something is genuinely backend-only (internal refactor, tracing, migrations), the brief says so explicitly. The UI overhaul phase restyles existing screens — it is not where features first get wired in.
- **Run the backend from `backend/`** (`uvicorn app.main:app`). The package is `app`: imports are absolute (`from app.db.models import User`), never bare module names or relative imports, and nothing inside `backend/` edits `sys.path`. `pytest.ini` puts `backend/` on the path for tests; Alembic adds it itself. Dependencies point down only (`api` → `services` → `retrieval` / `generation` / `ingestion` → `db` → `core`); rules and the module map are in `docs/architecture/layout.md`.
- **Configuration comes only from `app.core.config.settings`** (Day 7). No `os.getenv` or `load_dotenv` in `backend/app/`; a new variable is a `Settings` field plus an `.env.example` entry. Secrets are `SecretStr`: read them with `.get_secret_value()` at the call site and never log `settings`. `settings` is built once at import, so tests override fields with `monkeypatch.setattr(settings, ...)`; a later `setenv` doesn't reach it.
- **Scope all user data by `user_id`.** Every search filter, cache key, and stored file path must include the user. Retrieval results' metadata carries `user_id` as a **string** (`str(user.id)`), and `RetrievalService` takes string ids; the database filter in `db/repositories/chunks.py` uses the int (`PgChunkSearch` converts at the boundary). Prefer scoping the Redis key itself (as `semantic_cache:{user_id}` does) over filtering a shared list.
- **Schema changes only through Alembic revisions** (Day 13, T2). Change the model, run `alembic revision --autogenerate -m "…"` against the local Postgres, review the file by hand (no `drop_table` / `drop_column` you didn't mean, renames are drop + add), then `alembic upgrade head` + `alembic check`. Never `create_all`, never hand-run DDL, never edit a revision that has run anywhere. Every model module is imported in `db/models/__init__.py`, or autogenerate thinks its table was deleted.
- **SQL lives in `db/repositories/`** (Day 13). Plain functions taking the `Session` first; `user_id` is an `int` in every database filter (Postgres refuses `integer = text`); the caller commits; no HTTP errors inside. Postgres enforces foreign keys (SQLite never did), so every delete removes or detaches children before their parent. Routers keep validation, status codes and response shapes. Index and retrieval metadata keep their **string** user ids (next rule).
- **Bump `User.doc_version`** whenever a user's document set changes — the L1 retrieval cache, Redis query cache, and semantic cache all key on it.
- **One chat pipeline, one SSE contract.** All chat logic lives in `services/chat_pipeline.py`; the frame order (`metadata` → `token`… → `message_id` → `[DONE]`; refusals without `message_id`) is a contract with `ChatWindow.js`, checked by `test_api_smoke.py`. Change both sides the same day or not at all.
- **Long-lived objects are built only in `services/container.py`** (called from the lifespan) and reached through `Depends(get_services)`. No module-level clients or singletons, and no class builds its own `genai.Client` or Redis client — take it as a constructor argument. Importing `app.main` must stay free of network calls (`test_app_factory.py`).
- **Retrieved text is untrusted** (uploaded documents and web pages). Never put it in the system instruction; keep it delimited in the final user turn (G5).
- **Keep the prompt prefix stable.** Don't add new per-turn variation to the system instruction or the start of history; variable content belongs in the final user turn (CO4).
- **Eval and experiment code must not `import main`.** It gets its objects from `build_services()` (`services/container.py`) or constructs `IndexBuilder` / `RetrievalService` directly — `app.main` no longer exposes any of them.
- **Tests run only on Postgres** (Day 14 in CI; the only way since Day 15). `TEST_DATABASE_URL` + `TEST_DATABASE_SCHEMA` are required (conftest stops with a setup message without them), and conftest accepts only a database named `*_test` because it wipes it (`downgrade base` + `upgrade head`) every run. Tests that need a database use the suite's (`SessionLocal`, or the `client` fixture), never fixed ids: the database is shared, so give rows unique emails and let the sequence assign ids. `test_migrations.py` runs on the same database, and every test that downgrades it upgrades back to head. conftest pins `STORAGE_BACKEND=local` and fakes S3 (`FakeS3Client`), so no test reaches a real bucket.
- **Files only through `FileStorage`** (Day 15). `Document.file_path` holds a key `uploads/{user_id}/{uuid}{ext}`, checked by `check_key`; nothing opens it as a path directly. Parsers read through `storage.local_copy(key)`. Write the object before committing its row; delete objects after the row's commit and log failures. `STORAGE_BACKEND=supabase` belongs on Render and in one-off staging shells, never in `.env` (compose passes `.env` into the Docker backend).
- **Measure retrieval and prompt changes** with the eval harness once E4 exists, and record before/after numbers in the tracker's Notes column.
- **Dependencies: edit `requirements.in`, regenerate `requirements.txt`** (Day 10). The `.in` file lists direct dependencies with a reason each; the lock is generated in `python:3.11-slim` with the old lock as constraints (command in its header) and is never hand-edited. Both are UTF-8. A new dependency still needs the owner's OK. After any `pip install -r requirements.txt`, reinstall the contrib OpenCV build last (B3): `pip install --no-deps --force-reinstall opencv-contrib-python-headless==4.12.0.88`.
- **The host venv is not the lock.** It is Python 3.12; camelot-py requires `pypdf>=4,<6` on Python ≥ 3.12 and `pypdf<4` below, so the venv keeps `pypdf` 5.9.0 while the image and CI have 3.17.4. Windows also adds `colorama`. CI and the container (`.\scripts\dev.ps1 test`) run the exact Linux / 3.11 lock and are the reference.
- **Secrets live only in the root `.env`** (gitignored). `frontend/.env.production` **is tracked** and must hold only public values (API URL, Google client ID). No passwords in tracked files, not even dev defaults (GitGuardian flags them): compose requires `POSTGRES_PASSWORD` / `RAG_APP_PASSWORD` from `.env`, CI generates its own. Postgres role passwords reach Supabase only as SCRAM verifiers (`scripts/supabase/scram_verifier.py`) — its SQL editor logs the whole script (`log_statement = ddl`).
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
# Backend venv setup / after requirements.txt changes (B3: contrib OpenCV must be written last)
.\venv\Scripts\Activate.ps1
# The lock pins pypdf 3.17.4 (Python 3.11); on the 3.12 venv camelot needs pypdf>=4, so a plain
# `pip install -r requirements.txt` fails with ResolutionImpossible. Install everything but that pin:
Get-Content requirements.txt | Where-Object { $_ -notmatch '^pypdf==' } | Set-Content $env:TEMP\req-host.txt
pip install -r $env:TEMP\req-host.txt     # pip then picks a pypdf 4.x/5.x that camelot accepts
pip install --no-deps --force-reinstall opencv-contrib-python-headless==4.12.0.88

# Backend — GEMINI_API_KEY must be set (settings validation); startup makes no Gemini call since Day 9
.\venv\Scripts\Activate.ps1
cd backend; uvicorn app.main:app --reload  # http://localhost:8000  (Swagger UI at /docs)

# Database schema (Day 13, T2) — Alembic from the repo root; the URL comes from Settings (DATABASE_URL,
# required, Postgres only since Day 15). The app refuses to start on a database that isn't at head.
alembic upgrade head                      # Docker runs this before uvicorn (image CMD, compose dev command)
alembic check                             # "No new upgrade operations detected." = models and schema agree
alembic current                           # the database's revision
alembic revision --autogenerate -m "add x"   # against the local Postgres (below), then review the file by hand
# alembic downgrade: the guard hook allows it only against a local Postgres (rag holds disposable dev data)

# Local Postgres — the app's database since Day 14 (compose, host port 5433; .env must set
# POSTGRES_PASSWORD and RAG_APP_PASSWORD — every `docker compose` command fails without them — plus
# DATABASE_URL=postgresql+psycopg://rag_app:<RAG_APP_PASSWORD>@localhost:5433/rag and DATABASE_SCHEMA=rag
# for the venv). The init script creates role rag_app owning schema rag.
docker compose up -d postgres
alembic upgrade head; alembic check       # from the repo root, against .env's DATABASE_URL (local rag)

# The test suite — Postgres only since Day 15 (a run without TEST_DATABASE_URL stops with a setup message).
# Once per pgdata volume, create the rag_test and rag_eval databases (the init script is re-runnable; it
# reads RAG_APP_PASSWORD inside the container). Run these from Git Bash; PowerShell mangles the nested quotes:
docker exec rag-postgres sh -c 'createdb -U postgres rag_test && POSTGRES_DB=rag_test sh /docker-entrypoint-initdb.d/10-rag-schema.sh'
docker exec rag-postgres sh -c 'createdb -U postgres rag_eval && POSTGRES_DB=rag_eval sh /docker-entrypoint-initdb.d/10-rag-schema.sh'
$env:TEST_DATABASE_URL = "postgresql+psycopg://rag_app:<RAG_APP_PASSWORD>@localhost:5433/rag_test"; $env:TEST_DATABASE_SCHEMA = "rag"
python -m pytest -q                       # conftest wipes + re-migrates rag_test; refuses a name not ending in _test
Remove-Item Env:TEST_DATABASE_URL, Env:TEST_DATABASE_SCHEMA

# Supabase staging (rag_staging): .env holds RAG_STAGING_DATABASE_URL (not read by the app); copy it
# into $env:DATABASE_URL for one session with $env:DATABASE_SCHEMA = "rag_staging". For uploads into
# the rag-staging bucket in that session also set $env:STORAGE_BACKEND = "supabase" (.env holds the
# bucket and the four S3 values; never STORAGE_BACKEND itself). Never print any of these values. Roles and schemas
# come from scripts/supabase/setup_rag_schemas.sql (run by the owner in the SQL editor, verifiers only:
# python scripts/supabase/scram_verifier.py rag_app)

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

# Tests — offline: no API keys, no network, no Redis, no real bucket (backend/tests/conftest.py fakes
# Gemini, Tavily, Redis and S3, and pins STORAGE_BACKEND=local); from the repo root, pytest.ini limits
# collection to backend/tests/ and puts backend/ on the path. Needs TEST_DATABASE_URL (see above).
python -m pytest
.\scripts\dev.ps1 test                    # the same suite in the backend container (Linux, Python 3.11) on the compose rag_test
                                          # (after a requirements change: docker compose build backend first)

# Lint — the same ruff.toml rules CI and the edit hook enforce (bug-only today; Day 10 tightens them)
ruff check .

# CI (GitHub Actions, .github/workflows/ci.yml) — runs on every PR into and push to develop/master
gh pr checks <N>                          # the three required jobs: backend, frontend, docker
gh run list --branch develop --limit 5    # recent runs; gh run view <id> --log-failed for a red one

# Retrieval eval (E4, Day 11) — from backend/. Set $env:GEMINI_API_KEY to the EVAL project's key first
# (a real env var overrides .env); the key guard refuses production's. No Redis. Since Day 15 it needs
# its own database: EVAL_DATABASE_URL (name must end in _eval; migrated to head and its eval user
# re-created every run). Corpus vectors come from the embedding cache (0 API calls since Day 11).
$env:GEMINI_API_KEY = "<eval project key>"
$env:EVAL_DATABASE_URL = "postgresql+psycopg://rag_app:<RAG_APP_PASSWORD>@localhost:5433/rag_eval"
cd backend; python -m eval.retrieval --config baseline            # also vector_only, keyword_only
python -m eval.retrieval --config baseline --label after-x        # results/{date}-{config}-{label}.{json,md}
python -m eval.retrieval --config web --limit 10                  # Tavily on; embeds every web chunk — run last
python -m eval.retrieval.corpus                                   # rewrite corpus/manifest.json after changing corpus files
python -m eval.retrieval.generate_questions --plan                # quotas + request bound; drop --plan to generate (resumable)
# Free tier on the eval project (AI Studio, 2026-11-09): gemini-embedding-001 100 RPM / 30K TPM / 1K RPD;
# gemini-3.5-flash-lite 15 RPM / 500 RPD. A first run embeds the corpus (~392 calls); later runs hit eval/.cache/

# Generation eval (E1/E2, Day 12) — from backend/, same eval key. Answers + verdicts are cached in
# eval/.cache/generation.sqlite, so a re-run is free and a daily-quota stop resumes where it stopped.
python -m eval.generation --model gemini-3.5-flash-lite --label after-x   # results/{date}-generation-{model}-{label}.{json,md}
python -m eval.generation --ids g-001,h-01,n-01 --label smoke              # a few questions; --limit N also works
python -m eval.generation --probe gemini-2.5-flash-lite                    # one call: is this model served to the key?
# A results file that already exists is refused (the 2026-11-10 baseline holds a hand-written owner
# review); use --label, or --force to overwrite. ~3 requests a question (answer + 2 judge calls).
python -m eval.generation.calibrate score --faith-version faith-v2         # judge vs the 20 reference labels, 2 passes
python -m eval.generation.calibrate compare <older>.json <newer>.json      # prompt version vs prompt version

# Semantic cache lookups (needs live Gemini + Redis; CO5 replaces it on Day 32)
cd backend; python -m eval.cache_tuner
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
| `TAVILY_API_KEY` | for web search | `retrieval/web/search_client.py`; if missing, web chunks are silently skipped |
| `JWT_SECRET_KEY` | yes | JWT signing (`core/security.py`) and `SessionMiddleware` |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` | yes — settings validation fails without them | `services/oauth_service.py` |
| `JWT_ALGORITHM`, `JWT_EXPIRATION_MINUTES` | no | `HS256`, `10080` (7 days) |
| `REDIS_URL` | no | Query cache (`services/caches/query_cache.py`) and web cache (`services/caches/web_cache.py`); default `redis://localhost:6379/0`. Locally `.env` sets `redis://localhost:6380/0` (compose maps Redis to host port 6380); in Docker compose sets `redis://redis:6379/0` |
| `SEMANTIC_CACHE_REDIS_URL` | no | Semantic cache (`services/caches/semantic_cache.py`). Unset → `REDIS_URL` → `redis://localhost:6379/1`. Docker: `redis://redis:6379/1`. Render sets only `REDIS_URL`, so there the semantic cache still shares DB 0 |
| `BASE_URL`, `FRONTEND_URL` | no | OAuth redirects; `http://localhost:8000`, `http://localhost:3000` |
| `ALLOWED_ORIGINS` | no | Comma-separated CORS allowlist (entries trimmed). Default: `http://localhost:3000,http://localhost:8000,https://rag-study-assistant-chi.vercel.app`. On Render: only `https://rag-study-assistant-chi.vercel.app` |
| `DATABASE_URL` | **yes** (no default since Day 15) | `SecretStr`. Postgres only: it must use `postgresql+psycopg://` — `postgresql://` is refused with the corrected prefix; Supabase via the **session pooler** (`<role>.<project-ref>@aws-0-<region>.pooler.supabase.com:5432/postgres`). Read by `db/session.py` and `alembic/env.py`. **Render** (from v0.2.2): `rag_app`'s session-pooler URL. **Venv**: `.env`, `rag_app@localhost:5433/rag`. **Docker**: compose sets `postgresql+psycopg://rag_app@postgres:5432/rag` with **no password in the URL** — libpq reads `PGPASSWORD` (compose sets it from `RAG_APP_PASSWORD`), so no credential-shaped string is tracked (GitGuardian flagged the `user:${VAR}@host` form, Day 14) |
| `DATABASE_SCHEMA` | **yes** (since Day 15) | the schema the role's `search_path` resolves to (`rag`, `rag_staging`); Alembic and the app refuse a connection whose `current_schema()` differs, and `alembic_version` lives in it. `rag` on Render, in `.env` and in compose |
| `TEST_DATABASE_URL`, `TEST_DATABASE_SCHEMA` | for tests | not `Settings` fields: read by `backend/tests/conftest.py`; required since Day 15 (the suite runs only on Postgres). The database name must end in `_test` (it is wiped every run). CI: `rag_app@localhost:5432/rag_test`, schema `rag`; `dev.ps1 test`: `rag_app@postgres:5432/rag_test` (password from `PGPASSWORD`). Never put them in `.env` |
| `EVAL_DATABASE_URL` | for the retrieval / generation eval | not a `Settings` field: read by `backend/eval/retrieval/database.py` (Day 15). The database name must end in `_eval`; the eval migrates it and re-creates its eval user every run. Locally the compose Postgres's `rag_eval`. Set per shell |
| `STORAGE_BACKEND` | no | `local` (default: `backend/uploads/`, the Docker `uploads` volume) or `supabase` (Day 15). **Render** sets `supabase` from v0.3.0 (Day 17). Never in `.env`: compose passes `.env` into the Docker backend, and tests pin `local` |
| `STORAGE_BUCKET`, `SUPABASE_S3_ENDPOINT`, `SUPABASE_S3_REGION`, `SUPABASE_S3_ACCESS_KEY_ID`, `SUPABASE_S3_SECRET_ACCESS_KEY` | with `STORAGE_BACKEND=supabase` | Supabase Storage over its S3 API (the secret is a `SecretStr`). Buckets `rag-prod` (Render) and `rag-staging` (`.env`, manual checks), both private. The S3 key reaches Storage only (not the database), but every bucket in the project — today only these two (the other app has none; revisit if it adds some) |
| `POSTGRES_PASSWORD`, `RAG_APP_PASSWORD` | for compose | not `Settings` fields: compose reads them for the local `postgres` service (superuser and `rag_app`); used once, when the `pgdata` volume is first initialised. No defaults — compose refuses to run without them |
| `RAG_STAGING_DATABASE_URL` | no | not a `Settings` field: the Supabase staging URL kept in `.env` for manual Alembic runs (copied into `DATABASE_URL` for one session) |
| `TESSERACT_PATH`, `PORT` | no | OCR binary path, set as pytesseract's `tesseract_cmd` by `ingestion/ocr/ocr.py`; unset → `tesseract` on `PATH`. Windows host `.env`: the `tesseract.exe` path; the Docker image sets `ENV TESSERACT_PATH=/usr/bin/tesseract` (so Render gets it without compose), and compose sets it again because `env_file: .env` would otherwise pass the Windows path in. uvicorn port in the Dockerfile (default 8000) |

`.env.example` lists every backend variable with placeholders; keep it in sync when adding one.
Tests set their own `DATABASE_URL` (from `TEST_DATABASE_URL`, in `conftest.py`) and `STORAGE_BACKEND=local`, so `.env`'s values never reach them.
`env_file: .env` passes **every** `.env` variable into the Docker backend, including ones the app never reads (`RAG_STAGING_DATABASE_URL`, `POSTGRES_PASSWORD`) — never print a resolved `docker compose config` or a container's environment, even filtered (Day 14 brief, Risks 11–12).
GitHub Actions secret: `SUPABASE_RAG_DB_URL` (`rag_app`, psql form) for `supabase-keepalive.yml`.

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
| Users, sessions, messages, documents, failed queries, concept maps | Postgres since Day 14: Supabase `rag` in production (from v0.2.2), the compose Postgres's `rag` locally (Docker backend and venv). Both started empty — nothing was copied. The old SQLite files are unused: `backend/data/app.db` (stamped Day 13), the Docker `data` volume, and the backups `backend/data/app.backup-2026-11-11.db`, `app.docker-backup-2026-11-11.db` | yes |
| Local Postgres | compose `postgres` service, named volume `pgdata`, host port 5433: database `rag` (the app's dev data, disposable), `rag_test` (the suite's, wiped every run) and `rag_eval` (the eval's, Day 15); schema `rag`, role `rag_app` in both; `scripts/postgres/init-rag-schema.sh` (re-runnable since Day 14) creates them | yes (volume) |
| Supabase | existing project (`ap-south-1`): schemas `rag` (production since v0.2.2) and `rag_staging` (at head, Day 13); `vector` in `extensions` | yes |
| Uploaded files | `FileStorage` (Day 15) under the key `uploads/{user_id}/{uuid}{ext}` (older rows: flat `uploads/<name>`), held in `Document.file_path`; display name in `Document.file_name`. Local backend: relative to the CWD (`backend/`); Docker: named volume `uploads` at `/app/backend/uploads`. Supabase: private bucket `rag-prod` (Render, from v0.3.0) / `rag-staging` | yes (Render until v0.3.0: no disk, lost on every restart while the row survives; an identical re-upload re-links it) |
| Chunks: text, embedding (halfvec 3072), full-text `tsv`, metadata | Postgres `document_chunks` (Day 15; replaced in-memory FAISS + BM25) | yes |
| L1 retrieval cache (≤ 256 entries) | class-level dict in `RetrievalService` | no |
| Logs | `backend/logs/app.log` (rotating, 5 MB × 3, `[request_id]` on every line since Day 7; Docker: named volume `logs` at `/app/backend/logs`) | yes |

Render (free plan, region Singapore) has **no persistent disk** — confirmed 2026-11-13 ("Disks
are not supported"). Its filesystem is wiped on every deploy, restart and idle spin-down, so
nothing durable may live there: the database is Supabase, and files go to Supabase Storage
(`STORAGE_BACKEND=supabase`, bucket `rag-prod`) from the Day 17 release.

### Redis key schema

```
query_cache:{sha256(user_id::doc_version::query)}  DB 0            TTL 3600s  /search results                query_cache.py
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

**Whenever user ids restart** (switching the app to a new or emptied database, as at the v0.2.2
cutover to Postgres): flush the cache DBs first. Keys embed the user id, and `semantic_cache:{id}` has
no TTL, so a new user who receives an old id could be served another person's cached answers. The
exact Render steps are in the Day 14 brief's release runbook (step 2).

When adding a key: list it here with its TTL and how it is scoped to the user.

---

## API Endpoints

No version prefix; concept-map routes live under `/api/concepts`.

```
Auth       POST /register · POST /login · POST /change-password · GET /me
           GET /auth/google/login · GET /auth/google/callback · POST /auth/logout
User       GET /user/profile · PUT /user/profile · GET /user/stats · DELETE /user/delete
Documents  POST /upload · GET /documents · DELETE /documents/{doc_id} · POST /search
Chat       GET /chat/stream (SSE, ?token=) · POST /messages/{message_id}/feedback
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

**Hybrid vector + keyword.** Embeddings capture meaning but miss exact tokens (acronyms, formula
names, identifiers); keyword search catches those. Since Day 15 both halves run in Postgres —
pgvector cosine search and full-text `ts_rank_cd` (OR semantics, English stemming; unlike BM25 it
has no IDF: on E4 keyword-only found more pages, Hit@5 47 → 49/55, but ranked them lower, MRR@5
0.602 → 0.559; hybrid held, 50/55 and 0.801 → 0.806). Current fusion is min-max normalization with
fixed 0.6 / 0.4 weights; R4 proposes Reciprocal Rank Fusion.

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

- **Migrations — decided 2026-11-11 (Day 13, T2):** Alembic is the only path. Migrations run as their own step (`alembic upgrade head` before uvicorn), never from the app; the app only checks it is at head. Driver psycopg 3; repositories are plain functions and the caller commits.
- **Database hosting — decided 2026-11-11 (Day 13):** the owner's existing Supabase project, isolated by schema (`rag` / `rag_staging`, one login role each, `search_path` set on the role as `<schema>, extensions`, not exposed to the Data API). `USAGE` on `public` stays inherited from `PUBLIC` (no project-wide revoke: another app shares the project). Through MCP, Claude reads catalog metadata only, never rows outside `rag` / `rag_staging`; schema and role changes go through reviewed SQL the owner runs.
- **Chat endpoints — decided 2026-11-08 (Day 9):** `POST /chat` deleted; one `ChatPipeline` behind `/chat/stream`. A JSON endpoint, if one is ever needed, must call the same pipeline.
- **Index persistence — decided 2026-11-04, built Day 15:** pgvector (halfvec(3072), HNSW) + Postgres full-text in `document_chunks`, uploaded files in Supabase Storage over its S3 API with S3 access keys (Storage only, not the database — Day 15 Decision 5B), local disk in dev and tests. Render's filesystem is ephemeral, so nothing durable stays on it. Reaches production with v0.3.0 (Day 17).
- **Dependencies — decided 2026-11-08 (Day 10):** unused packages removed; those tied to planned items kept (`tiktoken` → C1, `instructor` → S1, `langsmith` → O1, `langgraph` → A1); `src/requirements.txt` deleted. `ragas` (and the langchain packages it pulls in) waits for the Day 12 RAGAS-vs-judge decision.
- **Dead code — done Day 10.** Still open: the Tesseract installer is untracked but still in git history; purging it needs a history rewrite and force-push (decided on Day 60).

---

## Claude Code Setup

- **Skills** (`.claude/skills/`, user-invoked only): `/run-day <N>` reads Day N of `docs/timeline.md`, writes a brief to `docs/briefs/dayNN.md`, stops for approval, then implements checkpoint by checkpoint — the default way to start a day; `/run-item <ID>` does the same for a single tracker item outside the timeline; `/pre-commit` runs checks and reports, with no git writes; `/ship commit "day NN - …"` / `/ship merge` is the only skill that writes to git — commit + push + draft PR + watch CI, or merge a green PR into `develop` with a merge commit — with a safety scan (no `.env`, runtime data, `*.db` or secret-looking lines staged) and an explicit "yes" before every commit and merge. Releases (`develop` → `master` + tag) stay manual.
- **Hooks** (`.claude/settings.json` → `.claude/hooks/*.py`): destructive-command guard (Bash and PowerShell; since Day 13 `alembic downgrade` is allowed only against a temp SQLite file or a local Postgres — the real `app.db`, the default, Supabase and any unreadable `DATABASE_URL` stay blocked), session-start context (git state and In Progress items), ruff check on edited `.py` files (rules from `ruff.toml`, the same set CI enforces), and reminders after editing this repo's trap files.
- **Workflow, anchor and resume prompts:** `docs/claude-cheatsheet.md`.

## What Claude Must Do at the Start of Every Session

1. Read this file in full (it is loaded automatically).
2. Use the session-context hook output, or run `git status` and `git log --oneline -10` — there is often uncommitted work.
3. Read **Current Status** above, the relevant rows of `docs/improvement-tracker.md`, and the item's brief in `docs/briefs/` if one exists.
4. Read the actual source files before editing — never rely on line numbers from docs.
5. Then, and only then, start the task.

At the end of a session the user updates **Current Status** here and the Status / Notes columns in the tracker; Claude doesn't edit them unless asked.
