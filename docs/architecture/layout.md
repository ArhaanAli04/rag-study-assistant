# Backend package layout

Status: **proposed on Day 7 (2026-11-06), awaiting approval.** Days 7–10 (Phase 3) move the
backend from 62 flat modules in `src/` into the package below. This file is the map for those
moves: each module has one target path and one day.

## Target tree

```
rag-study-assistant/
├── backend/                     ← the Python project; run everything from here (CWD = backend/)
│   ├── app/                     ← the package; imported as `app.*`, never by bare module name
│   │   ├── main.py              ← FastAPI app (Day 9: app factory + lifespan)
│   │   ├── api/
│   │   │   ├── deps.py          ← Depends(): db session, current user, services from app.state
│   │   │   └── routes/          ← auth, users, documents, chat, sessions, quiz, concepts, health
│   │   ├── core/                ← config, logging, request_id, security, errors — imports nothing else from app
│   │   ├── db/                  ← engine/session, models/, repositories/
│   │   ├── ingestion/           ← parsers/ (pdf, pptx, docx), chunking, ocr/, tables/, upload storage
│   │   ├── retrieval/           ← embeddings, vector store, keyword index, fusion, rerank,
│   │   │                          decomposition, compression, web/
│   │   ├── generation/          ← LLM client, prompts, topic classifier, concept extractor
│   │   ├── services/            ← chat pipeline, documents, sessions, caches/, concept maps,
│   │   │                          quiz, accounts, OAuth client
│   │   └── schemas/             ← Pydantic request/response models
│   ├── tests/                   ← pytest suite + samples/ + fakes.py (offline, Day 5)
│   ├── eval/                    ← eval harness and experiments (Days 10–12)
│   ├── scripts/                 ← one-off and manual scripts
│   ├── data/  uploads/  logs/   ← runtime state, gitignored (Docker: named volumes)
├── frontend/                    ← unchanged
├── alembic/  alembic.ini        ← stays at the root until Day 13 (T2)
├── docs/  .github/  .claude/  scripts/dev.ps1
├── Dockerfile  docker-compose*.yml  requirements.txt  pytest.ini  ruff.toml
```

## Rules

1. **Dependencies point down only:** `api` → `services` → `retrieval` / `generation` / `ingestion` → `db` → `core`.
   - **`core` imports nothing from `app`.**
   - **No lower layer imports `api` or `main`.** That ends "eval code must `import main`".
   - **`retrieval`, `generation` and `ingestion` don't import each other.** The exceptions are explicit and listed here as they arise.
2. **Absolute imports only:** `from app.retrieval.vector_store import FaissVectorStore`.
   - **No relative imports** (`from .x import`).
   - **No `sys.path` edits.** `backend/` is the only root: `pytest.ini`'s `pythonpath`, uvicorn's CWD and the Dockerfile's `WORKDIR`.
3. **Routers are thin:** parse the request → call a service → shape the response. No retrieval, LLM or SQL logic in `api/`.
4. **Configuration comes only from `app.core.config.settings`.** No `os.getenv` or `load_dotenv` anywhere else in `app/`.
5. **Runtime state** (`data/`, `uploads/`, `logs/`) stays CWD-relative, so it lives in `backend/` locally and at `/app/backend/{data,uploads,logs}` in Docker. It never moves inside `app/`.
6. **Moves and rewrites go in separate commits** so `git log --follow` keeps each file's history. Rename detection is by content similarity, and PRs merge with a merge commit, never squash.

## Module map

Day 7 moves all of `src/` flat into `backend/app/` (same file names). The "Target" column is
where each module ends up, and "Day" is when it gets there. A module whose target is
`app/<same name>` with Day 7 stays flat until its listed day.

### core
| Current (`src/`) | Target (`backend/app/`) | Day |
|---|---|---|
| `config/oauth_config.py` | `core/config.py` (one `Settings` for every env var) | 7 |
| `logger.py` | `core/logging.py` (+ request-ID filter) | 7 |
| — | `core/request_id.py` (new: contextvar + ASGI middleware) | 7 |
| `auth.py` | `core/security.py`; `get_db`, `get_current_user*` move to `api/deps.py` | 7 / 9 |
| `error_handler.py` | `core/errors.py` | 7 |

### db
| Current | Target | Day |
|---|---|---|
| `db.py` | `db/database.py` (pure move). The split into `db/session.py` (engine, `SessionLocal`, startup migrations) and `db/models/` (user, session, message, document, failed_query) comes on Day 9 with `api/deps.py` | 8 / 9 |
| `concept_models.py` | `db/models/concept_map.py` | 8 |
| — | `db/repositories/` | created when first needed (Postgres, Day 13+); no empty package before |

### ingestion
| Current | Target | Day |
|---|---|---|
| `indexing_pipeline.py` | `ingestion/indexing_pipeline.py` | 8 |
| `chunk_builder.py` | `ingestion/chunk_builder.py` | 8 |
| `chunking.py` | `ingestion/chunking.py` | 8 |
| `models.py` (`DocumentChunk`) | `ingestion/models.py` | 8 |
| `text_preprocessing.py` | `ingestion/text_preprocessing.py` | 8 |
| `utils_file.py` (`compute_file_hash`) | `ingestion/file_hash.py` | 8 |
| `upload_storage.py` | `ingestion/upload_storage.py` | 8 |
| `pdf_utils.py` | `ingestion/parsers/pdf.py` | 8 |
| `pptx_utils.py` | `ingestion/parsers/pptx.py` | 8 |
| `pptx_pipeline.py` | `ingestion/parsers/pptx_pipeline.py` | 8 |
| `docx_utils.py` | `ingestion/parsers/docx.py` | 8 |
| `unified_parser.py` | `ingestion/parsers/unified.py` | 8 |
| `ocr_utils.py` | `ingestion/ocr/ocr.py` | 8 |
| `image_preprocessing.py` | `ingestion/ocr/image_preprocessing.py` | 8 |
| `pdf_table_utils.py` | `ingestion/tables/pdf_tables.py` | 8 |
| `table_utils.py` | `ingestion/tables/tables.py` | 8 |

The Day 8 lazy-loading of OCR and table libraries happens in these files, as its own commit after the pure moves.

### retrieval
| Current | Target | Day |
|---|---|---|
| `embedding_service.py` | `retrieval/embeddings.py` | 8 |
| `index_builder.py` | `retrieval/index_builder.py` | 8 |
| `vector_store.py` | `retrieval/vector_store.py` | 8 |
| `keyword_index.py` | `retrieval/keyword_index.py` | 8 |
| `retrieval_service.py` | `retrieval/retrieval_service.py` (fusion stays inside it until R4, Day 29) | 8 |
| `reranker.py` | `retrieval/reranker.py` | 8 |
| `query_decomposer.py` | `retrieval/query_decomposer.py` | 8 |
| `query_preprocessor.py` | `retrieval/query_preprocessor.py` | 8 |
| `context_compressor.py` | `retrieval/context_compressor.py` | 8 |
| `hybrid_retriever.py` (`ConceptMapRetriever`) | `retrieval/concept_map_retriever.py` | 8 |
| `web_search_client.py` | `retrieval/web/search_client.py` | 8 |
| `web_scraper.py` | `retrieval/web/scraper.py` | 8 |

### generation
| Current | Target | Day |
|---|---|---|
| `llm_client.py` | `generation/llm_client.py` | 8 |
| prompts inside `llm_client.py`, `topic_classifier.py`, `concept_extractor.py`, `main.py` (quiz) | `generation/prompts.py`, then Langfuse prompt management with local fallbacks | 25 |
| `topic_classifier.py` | `generation/topic_classifier.py` | 8 |
| `concept_extractor.py` | `generation/concept_extractor.py` | 8 |

### services
| Current | Target | Day |
|---|---|---|
| chat logic in `main.py` (`/chat/stream`, `/chat`) | `services/chat_pipeline.py`; `POST /chat` deleted (decision confirmed on Day 9) | 9 |
| `chat_guards.py` | `services/chat_guards.py`; Day 9 merges the two keyword safety lists into it | 8 / 9 |
| quiz logic in `main.py` | `services/quiz_service.py` | 9 |
| `document_service.py` | `services/document_service.py` | 8 |
| `session_service.py` | `services/session_service.py` | 8 |
| `account_service.py` | `services/account_service.py` | 8 |
| `concept_map_service.py` | `services/concept_map_service.py` | 8 |
| `semantic_cache.py` | `services/caches/semantic_cache.py` | 8 |
| `cache.py` | `services/caches/query_cache.py` | 8 |
| `web_cache.py` | `services/caches/web_cache.py` | 8 |
| `services/oauth_service.py` | `services/oauth_service.py` (already there) | 7 |

### schemas
| Current | Target | Day |
|---|---|---|
| `concept_map_schemas.py` | `schemas/concept_maps.py` | 8 |
| Pydantic models in `main.py` (`SearchRequest`, `ChatRequest`, `ChatResponse`, `QuizRequest`, `FeedbackRequest`, `UserCreate`, `PasswordChange`, …) | `schemas/{documents,chat,quiz,feedback,auth,users}.py` | 8 |

### api
| Current | Target | Day |
|---|---|---|
| `routes/auth_routes.py` | `api/routes/auth.py` (Google OAuth + `/auth/logout`, joined by `/register`, `/login`, `/change-password`, `/me`) | 9 |
| routes in `main.py` | `api/routes/{users,documents,chat,sessions,quiz,concepts,health}.py` | 9 |
| `main.py` | `app/main.py`: app factory; lifespan builds the LLM client, embedding service, retrieval service and Redis clients on `app.state` | 9 |

### eval, scripts, dead code
| Current | Target | Day |
|---|---|---|
| `rag_metrics.py`, `rag_eval_runner.py`, `sample_eval_data.py`, `manual_eval.py`, `cache_tuner.py` | `backend/eval/`, no longer importing `main` (rewritten on Days 11–12) | 10 |
| `add_concept_tables.py`, `add_doc_version.py`, `run_migration.py`, `update_existing_sessions.py`; root `fix_db.py`, `recreate_db.py`, `migrate_user_model.py` | deleted (superseded by Alembic, Day 13) | 10 |
| `scripts/manual/*` | `backend/scripts/manual/` | 10 |
| `frontend.py`, `document_delete_service.py` | deleted | 10 |
| `src/requirements.txt` | deleted (one UTF-8 root requirements file) | 10 |
| `tests/` | `backend/tests/` | 7 |

## What runs where after Day 7

| Context | Command | CWD |
|---|---|---|
| Local backend | `uvicorn app.main:app --reload` | `backend/` |
| Tests (host, CI) | `python -m pytest` (`pytest.ini`: `testpaths = backend/tests`, `pythonpath = backend`) | repo root |
| Docker (Render, compose) | `CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}` | `/app/backend` |
| Docker dev (override) | the same with `--reload --reload-dir /app/backend/app` | `/app/backend` |
| Tests in Docker | `.\scripts\dev.ps1 test` → `pytest /app/backend/tests` | `/app/backend` |

Render: Root Directory empty, Dockerfile Path `./Dockerfile`, build context `.`, Docker Command
empty. Render runs the Dockerfile's `CMD`, so no dashboard change is needed for this layout.
