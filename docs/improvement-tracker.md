# Improvement Tracker

Living status of the items cataloged in `improvements.md`. Update the **Status** and
**Notes** columns as work happens — descriptions stay in `improvements.md` so they
aren't duplicated here.

Status values: `Not Started` / `In Progress` / `Done` / `Skipped`

---

## P0 — Fix first (cheap, and blocks trusting anything else)

| ID | Improvement | Status | Notes |
|----|---|---|---|
| G6 | Scope semantic cache by `user_id` (fixes cross-user leak of answers and document text) | Done | Day 1. Per-user key `semantic_cache:{user_id}` plus a `user_id` check per entry; exact `doc_version` match. 7/7 offline tests. Live: user B got 0 of A's sources; A's repeat was a HIT (score 1.000). Legacy key flushed locally; Render flush (DB 0 and 1) on Day 3 |
| G7 | Per-user upload directory with server-generated, sanitized filenames | Done | Day 3. `uploads/{user_id}/{uuid}{ext}` + resolve/containment check; client name only in `Document.file_name` and citations. Identical re-upload over a legacy flat path moves the row to a per-user copy. 15 offline tests. Live: two demo accounts, B got 0 of A's sources. Existing rows keep their old flat `file_path` (rebuilt on Day 16). Docker named volume `uploads` |
| G8 | Stop logging JWTs (full request URLs, OAuth redirect URL) | Done | token= lines in app.log 420 → 0; redaction filter on all handlers; uvicorn query strings stripped |
| G4 | Fix CORS: use `ALLOWED_ORIGINS` instead of `allow_origins=["*"]` | Done | Day 1. With the allowlist, a foreign origin's preflight returns 400 and no allow-origin header (before: 200 and its origin echoed back). Render: Vercel URL only, set at the Day 3 release |
| G1 | Wire `sanitize_query()` into `/chat` and `/chat/stream`, or remove it | Done | 9/9 attack phrasings refused, 6/6 study questions allowed; refusals over SSE |
| O2 | Remove/convert stray `print("DEBUG: ...")` statements | Done | Day 1. 3 prints removed: 2 deleted (`main.py` cached stream), 1 now `logger.debug` (`retrieval_service.py`). Day 2: 1 more found and deleted (`session_service.py`, `DEBUG session_service: Created message ID` on every stored message) |
| E1 | Fix or replace broken RAGAS integration in `rag_metrics.py` | Not Started | |
| E4 | Retrieval eval harness (Recall@k, MRR, nDCG@k) that exercises the real pipeline | Not Started | |
| R1 | Implement a real reranker (cross-encoder or LLM-based) | Not Started | |
| I4 | Persist and reload FAISS + BM25 indexes so restarts don't wipe search | Not Started | |
| I5 | Remove a deleted document's chunks from FAISS + BM25 (and its file) | Not Started | |
| R5 | Pass the shared `RetrievalService` into `ConceptMapRetriever` so maps can use documents | Not Started | |
| B1 | Fix `DELETE /user/delete` crash and delete all of a user's data | Done | Day 3. `account_service.delete_user_account`: 7 tables in one transaction, then files, FAISS + BM25 tombstones, semantic + L1 cache. Live UI deletes: 200 in 57–198 ms, `index_entries_removed` 6/10/6, 0 rows left. SQLite reused freed id 3 for a new account — the purge is what keeps it clean. Test accounts 3–7 deleted |

## P1 — High-value, moderate effort

| ID | Improvement | Status | Notes |
|----|---|---|---|
| G2 | Call `verify_answer()` for low/loose-grounding responses | Not Started | |
| G3 | Replace 6-keyword safety blocklist with real moderation, unify `/chat` + `/chat/stream` | Not Started | |
| G5 | Indirect prompt-injection defenses (chunk scanning, spotlighting, canary, markdown `img` override, red-team set) | Not Started | |
| E2 | Replace word-overlap "manual metrics" with LLM-as-judge (or retire once E1 fixed) | Not Started | |
| S1 | Schema-validated structured output (`instructor` or Gemini JSON mode) for concept maps/quiz | Not Started | |
| O1 | Add request-level tracing across retrieval → rerank → compress → generate | Not Started | |
| R2 | LLM-based query decomposition (keep regex as fallback) | Not Started | |
| R3 | Query rewriting / expansion (HyDE or multi-query) | Not Started | |
| C1 | Token-based chunking and context-budget accounting (`tiktoken`) | Not Started | |
| C2 | History-aware query rewriting so follow-up questions retrieve correctly | Not Started | |
| I3 | Batch embedding API calls instead of one-per-chunk loop | Not Started | |
| CO1 | Replace linear-scan semantic cache with a small local vector index | Not Started | |
| CO2 | Parallelize sub-query retrieval with `asyncio.gather` | Not Started | |
| CO4 | Cache-friendly prompt layout (constant system instruction) + log token/cached-token usage | Not Started | |
| CO5 | Conversation-aware semantic cache with per-entry TTLs and a threshold tuned on labelled pairs | Not Started | |
| I6 | Skip re-indexing unchanged re-uploads; remove old versions' chunks | Not Started | |
| B2 | Fix confidence-scale mismatches (`/chat` grounding thresholds, forced-web cap) | Not Started | |
| B4 | Concept-map generation 500s when a node has empty sources | Done | Day 5: found by the API smoke test; `concept_extractor._add_source_attribution` now assigns the first source, not the whole list. Unit tests for both fallbacks in `tests/test_concept_extractor.py` |
| B3 | Fix the OpenCV wheel clash that silently disables image/PPTX table extraction | Not Started | Found Day 5; scheduled Day 10. `test_table_extraction_on_image` is `xfail(strict=True)` until then |
| T1 | Fix `pytest.ini` header so `testpaths` / `pythonpath` apply | Done | Day 5: `[pytest]` header; 11 `src/test_*.py` → `scripts/manual/`; bare `pytest` collects only `tests/` (112 items). Suite 84 → 111 tests (+1 strict xfail), 42.6 s → 23.3 s on the host with no keys or network; container 77.7 s (Day 8 lazy loading). |
| T2 | Pick one migration mechanism; if Alembic, fix its URL and model imports | Not Started | |

## P2 — Scale/architecture, revisit as usage grows

| ID | Improvement | Status | Notes |
|----|---|---|---|
| R4 | Switch score fusion from ad-hoc min-max+weights to RRF | Not Started | |
| E3 | Build a persisted golden eval set + CI regression gate | Not Started | |
| C3 | Hybrid conversation memory: token-budgeted window + per-session vector recall of older turns | Not Started | |
| A1 | Move from hard-wired pipeline to agentic tool-use (LangGraph) | Not Started | |
| I1 | Per-user/ANN FAISS indexing instead of brute-force + post-hoc filter | Not Started | |
| I2 | Persist BM25 index to disk; avoid full rebuild on every add | Not Started | |
| CO3 | Content-hash embedding cache | Not Started | |
| B5 | Fix `preprocess_image` deskew, which rotates scans 90° so the unified parser's OCR returns nothing | Not Started | Found Day 8; scheduled Day 10. Not reachable from any user path today (`/upload` rejects images; PPTX OCR uses a different preprocessing function). `test_unified_parser_image` is `xfail(strict=True)` until then |
| T3 | Repo hygiene: committed installer, stray/dead files, drifted requirements files, unused deps | In Progress | 2026-09-12 (69ae920): installer untracked and now ignored via `*.exe` (still in git history); stray `stop` and unused resume sample deleted; .gitignore extended. 2026-11-03 (Day 4): Docker items done — semantic cache on its own Redis DB via `SEMANTIC_CACHE_REDIS_URL` (Docker DB 1; Render unchanged until set), `DATABASE_URL` removed from compose. Also: image no longer bakes app.db/uploads (16 MB → 480 KB src), non-root, 3.4 → 3.05 GB. Remaining: dead code, requirements reconcile, unused deps (Day 10) |

---

## Completed

_(none yet)_
