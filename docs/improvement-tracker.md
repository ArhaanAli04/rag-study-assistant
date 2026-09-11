# Improvement Tracker

Living status of the items cataloged in `improvements.md`. Update the **Status** and
**Notes** columns as work happens — descriptions stay in `improvements.md` so they
aren't duplicated here.

Status values: `Not Started` / `In Progress` / `Done` / `Skipped`

---

## P0 — Fix first (cheap, and blocks trusting anything else)

| ID | Improvement | Status | Notes |
|----|---|---|---|
| G6 | Scope semantic cache by `user_id` (fixes cross-user leak of answers and document text) | Not Started | |
| G7 | Per-user upload directory with server-generated, sanitized filenames | Not Started | |
| G8 | Stop logging JWTs (full request URLs, OAuth redirect URL) | Not Started | |
| G4 | Fix CORS: use `ALLOWED_ORIGINS` instead of `allow_origins=["*"]` | Not Started | |
| G1 | Wire `sanitize_query()` into `/chat` and `/chat/stream`, or remove it | Not Started | |
| O2 | Remove/convert stray `print("DEBUG: ...")` statements | Not Started | |
| E1 | Fix or replace broken RAGAS integration in `rag_metrics.py` | Not Started | |
| E4 | Retrieval eval harness (Recall@k, MRR, nDCG@k) that exercises the real pipeline | Not Started | |
| R1 | Implement a real reranker (cross-encoder or LLM-based) | Not Started | |
| I4 | Persist and reload FAISS + BM25 indexes so restarts don't wipe search | Not Started | |
| I5 | Remove a deleted document's chunks from FAISS + BM25 (and its file) | Not Started | |
| R5 | Pass the shared `RetrievalService` into `ConceptMapRetriever` so maps can use documents | Not Started | |
| B1 | Fix `DELETE /user/delete` crash and delete all of a user's data | Not Started | |

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
| T1 | Fix `pytest.ini` header so `testpaths` / `pythonpath` apply | Not Started | |
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
| T3 | Repo hygiene: committed installer, stray/dead files, drifted requirements files, unused deps | Not Started | |

---

## Completed

_(none yet)_
