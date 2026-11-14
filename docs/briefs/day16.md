# Day 16 — Faster ingestion — batch embeddings, embedding cache (I3, CO3), reindex
Date: 2026-11-14 · Phase 5 — Postgres + pgvector data layer · Items: I3, CO3, CO6, B7
Branch: feature/day16-batch-embeddings

## Scope
1. **I3 — batch embeddings.** `EmbeddingService.embed_texts` sends batches (`embed_content` takes a list), with retry on transient errors. Bounded concurrency is a decision (Decision 1).
2. **CO3 — reuse embeddings by `content_hash`.** Before calling the API, look up the chunk texts' hashes in `document_chunks` and reuse the stored vectors.
3. **CO6 — fewer database round trips per request.** Today a chat turn makes 33 and `/me` makes 4. Merge the chat's transactions, drop `pool_pre_ping` (Decision 3), and count before and after.
4. **Reindex script.** It re-embeds documents from `FileStorage` into `document_chunks`.
   - The timeline's reason ("FAISS only ever lived in memory") is gone. v0.2.2's production rows have **no files**, so no reindex can help them (CLAUDE.md, Day 15 brief Risk 2).
   - What is left for it: rows with a stored file but no chunks (a failed indexing), and a forced re-chunk / re-embed after a future parser or model change. Its shape is Decision 4.
5. **B7 — measure img2table's `borderless_tables=True`** on the corpus's slide deck (`HPC Lecture.pptx`): tables found and false positives.
   - **New finding, read today:** PPTX slide-image tables are extracted and then **thrown away**. `process_pptx` returns `"tables"` (`ingestion/parsers/pptx_pipeline.py:22,51`). `build_chunks_from_pptx` (`ingestion/chunk_builder.py:63-`) only reads `"slides"`.
   - So enabling the flag changes nothing that is searchable. It would only make uploads slower. See Decision 5.
6. **Already done, dropped from today:**
   - "Remove FAISS / BM25 and faiss-cpu / rank-bm25": done Day 15 (Decision 4A).
   - "E4 re-run with pgvector vs the FAISS baseline": done Day 15 (hybrid Hit@5 50 → 50/55, MRR@5 0.801 → 0.806).
   - B10 (blank chunks): done Day 15.
   - The timeline's `EMBEDDING_DIM 3072 → 1536` note: superseded on Day 15 by halfvec(3072).
7. **Verify:** upload time for a ~50-page PDF, before vs after. The corpus has `BCT mod2,3,6.pdf` (63 pages) and `DL_Unit5_RNN.pdf` (107 pages).

## Current behavior
- **Embeddings** (`retrieval/embeddings.py:31-56`): one `embed_content` call per text, in a loop, with no retry. Any failure raises `EmbeddingError`. A 150-chunk PDF means 150 sequential HTTPS calls.
- **Indexing** (`services/indexing_service.py:47-91`): parse → drop blank chunks → `embed_texts(all)` → delete the document's chunks → insert. It already computes `content_hash` (sha256 of the text) per row, but never reads it back.
- **Changed re-upload** (`services/document_service.py:96-104`): `register_upload` deletes **every version's chunks** and commits *before* indexing starts. So by the time `IndexingService` runs, the old vectors are already gone and CO3 has nothing to reuse.
- **Callers of `embed_texts`** (all would get batching):
  - `IndexingService` (uploads)
  - `RetrievalService._embed_texts` (the query, plus web chunks: `retrieval_service.py:118,140,196,248`)
  - `SemanticCache.lookup` / `store` (one text each)
  - eval's `CachedEmbeddingService` (`eval/retrieval/embedding_cache.py`). It deliberately embeds one text per paced request, so it is unaffected.
- **DB round trips:**
  - `db/session.py:24-30`: `pool_pre_ping=True`, so there is a ping on every checkout. A `Session` checks a connection out again after every commit.
  - `ChatPipeline.answer` (`services/chat_pipeline.py:94-123`) commits at several points:
    - `get_or_create_session` → `create_session`: commit + refresh
    - a separate `count(*)` (`:103`)
    - `add_message`: commit
    - `_tag_topic`: commit
    - `_generate`: the failed query commits (`:197`), then the assistant message commits (`:204`)
  - Retrieval opens its own session (`pg_chunk_search.py:63`): ping, BEGIN, 2 SELECTs, ROLLBACK.
  - Day 15 count: **33** = 6 pings + 6 BEGIN + 15 statements + 4 COMMIT + 2 ROLLBACK.
- **Reindex:** nothing exists.
- **B7** (`ingestion/tables/tables.py:21-46`): `extract_tables()` with defaults, run on every picture of every uploaded PPTX. Its output is discarded (Scope 5). The function also uses `print()` and a bare `except Exception`.

## Why it matters
- **I3:** uploading `DL_Unit5_RNN.pdf` (107 pages, a few hundred chunks) means a few hundred serial calls. At ~100–300 ms each, that is a minute or more of upload spinner, and one 429 halfway through fails the whole upload (502) with no retry.
- **CO3:** a student fixes a typo on one slide and re-uploads a 200-chunk deck. Today all 200 chunks are re-embedded, although 199 have identical text. That costs time and quota (the free tier allows 1K embedding requests per day).
- **CO6:** every chat turn waits ≈ 33 × 63 ms ≈ 2.1 s on network round trips to Mumbai before and after Gemini. Every authenticated request pays ≥ 4 round trips.
- **Reindex:** a document whose indexing failed (502) keeps its file but shows "Not searchable yet" until the user notices and re-uploads it. After a future chunker or model change, every stored document would be stale, with no way to rebuild.
- **B7:** borderless tables on slides are missed. But since tables never reach chunks anyway, today's real cost is upload time spent on table extraction whose output nobody uses.

## The concept

**Batching remote calls.** Most of a small API call's time is fixed overhead: TLS, request routing, queueing at the provider. Payload processing is a small part. Sending N texts in one request pays that overhead once instead of N times.
- Providers cap batch size. Gemini's `batchEmbedContents` (what `embed_content(contents=[…])` calls on the Gemini API) takes up to 100 inputs per request, and each input is capped at 2,048 tokens.
- Rate limits are counted in requests *and* tokens. A batch saves requests but not tokens. On the free tier (30K tokens per minute), one 100-chunk batch of ~250 tokens per chunk is ~25K tokens, almost a minute's budget. So concurrency on top of batching mostly converts into 429s.
- Standard pattern: chunk the input into fixed-size batches, run them with a small bounded pool (a semaphore or a `ThreadPoolExecutor(max_workers=k)`), and retry transient errors (429, 5xx, timeouts) with exponential backoff plus jitter. Never retry 4xx validation errors.
- Pitfalls:
  - Partial failure: batch 3 of 5 fails. Make the whole operation all-or-nothing, as `IndexingService` already does.
  - Output order: the API returns embeddings in input order, so zip by position and assert the counts match.
  - Retrying forever on a daily-quota 429.

**Content-addressed caching.** Key a cached computation by a hash of its *inputs*, not by an identity such as a document id. Identical text yields an identical embedding (same model, same dimension, deterministic). So `sha256(text)` is a correct cache key *as long as the model and dimension are fixed*: they are part of the real key.
- Production systems store the model name / version next to the vector, or namespace the cache by it, so a model upgrade can't silently mix vector spaces.
- Here the vectors already live in Postgres with their hash, so "the cache" is just a lookup on `document_chunks`. No Redis and nothing to invalidate.
- Pitfalls:
  - Normalize before hashing the same way you embed (NUL stripping already happens before both).
  - Cross-tenant reuse can leak *existence* of content through timing or quota differences. Scope the lookup to the user unless you have decided otherwise.
  - A cache lookup that costs more round trips than it saves (batch the lookup: one `WHERE content_hash = ANY(:hashes)`).

**Round trips, not query time.** Over a 63 ms link, a 0.05 ms query costs 63 ms. What multiplies round trips in SQLAlchemy + psycopg:
- **Pool pre-ping:** one extra round trip per checkout. It guards against connections the server dropped while idle. `pool_recycle` (retire a connection older than N seconds) covers the common idle-timeout case for free.
- **Transaction boundaries:** psycopg sends `BEGIN` as its own round trip. After `COMMIT` the session gives the connection back, so the next statement pays checkout + ping + `BEGIN` again. Reads that never commit end in a `ROLLBACK` on return.
- **ORM refreshes:** `commit()` expires loaded objects (`expire_on_commit=True`), so reading `obj.id` after a commit triggers another `SELECT`. So does `db.refresh()`.
- **Autocommit reads:** with no transaction, a pure read is one round trip: no `BEGIN`, no `ROLLBACK`.

The fix is a *unit of work*: group a request step's reads and writes into one transaction and commit once. Writes that don't need to be visible early (a cosmetic topic tag, a failed-query log) ride along with the next commit.

Trade-off: a long transaction holds a pooled connection, and holding one open across a slow external call (an LLM request) is an anti-pattern ("idle in transaction"). So boundaries go *around* the LLM calls, never across them.

**Measuring it.** Count round trips with SQLAlchemy events (`before_cursor_execute`, plus the engine's `begin` / `commit` / `rollback` events and pool checkouts) in a test. A count is deterministic, so it can be a regression guard in CI. Latency over the real link depends on the network and is measured separately on the deployed system (Day 17 release).

**Reindexing / backfills.** A batch job that rebuilds derived data (chunks, vectors) from the source of truth (stored files).
- Good ones are idempotent (safe to re-run), resumable (per-document commits), dry-run by default, report what they skipped, and bump cache versions so readers don't serve stale results.
- They read the same code path as the online writer (`IndexingService`), so the backfill can't diverge from an upload.

**Measure before enabling a detector.** A detector with better recall (borderless tables) also raises false positives: pictures and diagrams read as tables would index junk text. Measure recall *and* precision on real data first. Also check that the output is actually consumed (today it isn't).

## Decisions

### 1. Batching: concurrency
- **A — Sequential batches of ≤ 100 + retry:** one request per 100 texts, one at a time, with up to 3 attempts per batch (backoff 1 s → 2 s, jittered) on 429 / 5xx / network errors. It is simple, and a 300-chunk PDF becomes 3 calls, but large uploads don't overlap batches.
- **B — Bounded concurrency (2–4 workers) over batches:** `ThreadPoolExecutor` over the batches, same retry. Faster on paid tiers, but on the free tier (30K TPM) parallel batches mostly turn into 429s and backoff, and there are more moving parts in a sync upload handler.
- **Recommendation: A**, with the batch size and the worker count as named constants. A shows nearly all of the gain (calls ÷ 100). Concurrency can come back as a one-line change once there is a paid tier to measure it on. A live probe in Checkpoint 1 confirms the batch limit and whether a batch counts as 1 or N requests against RPM.

### 2. CO3: lookup scope and index
- **A — Per user, plus a `(user_id, content_hash)` index:** reuse only the same user's vectors (any document, any version), with one batched `SELECT content_hash, embedding … WHERE user_id = :u AND content_hash = ANY(:hashes)`, and a new Alembic revision adding a btree index. This keeps the "scope all user data by user_id" rule, and covers the real cases (changed re-uploads, the same file under two names, reindex).
- **B — Across all users:** more hits when students share course material, but the lookup touches other users' rows. Whether a text was already embedded becomes observable (upload speed, quota), and a bug in the lookup could hand one user another user's row.
- **Recommendation: A.** To make reuse work for a *changed* upload, the old versions' chunks must still exist when indexing runs. So `register_upload` stops deleting them, and `IndexingService` reads the hashes, then deletes every version's chunks and inserts the new ones in the upload's one commit. If indexing fails, the old inactive chunks stay (search already skips inactive versions) until the next upload of that name, or the reindex, clears them.

### 3. CO6: `pool_pre_ping`
- **A — Drop it:** `pool_recycle = 300 s` already retires connections before the pooler's idle timeout, and it saves one round trip on every checkout (6 per chat turn, 1 per `/me`). If Supabase restarts the pooler, the first request on each dead pooled connection fails once (500); the next one reconnects.
- **B — Keep it:** no failed request after a pooler restart, but every checkout keeps paying ~63 ms. Fewer checkouts (the transaction merge below) already shrinks that cost.
- **Recommendation: A**, as planned in `improvements.md` CO6. The other CO6 changes don't need a decision:
  - The chat's writes merge into two transactions: before retrieval (session + history + user message) and after streaming (topic + failed query + assistant message). No transaction stays open across an LLM call.
  - The `count(*)` goes: "no history" ⇔ count 0.
  - The topic `UPDATE` is by id, with no reload.
  - Retrieval's two SELECTs run on an autocommit connection (no BEGIN / ROLLBACK).

### 4. Reindex script: shape
- **A — A dry-run-by-default maintenance module, `backend/scripts/reindex_all.py`** (`python -m scripts.reindex_all` from `backend/`).
  - It walks active documents. The default selects the ones with no chunks, `--all` selects every one, and `--user <id>` narrows it.
  - For each document: skip and report it if its stored file is missing; otherwise run the same `IndexingService`, reusing embeddings by hash (`--re-embed` bypasses the reuse, for a model change). Commit per document and bump that user's `doc_version` once.
  - Nothing is written without `--apply`, and it prints a summary table.
  - Runs anywhere `.env` / a shell sets `DATABASE_URL` (+ `STORAGE_BACKEND=supabase` for staging / production). Render's free plan has no shell, so production runs from the owner's machine.
- **B — Drop it:** nothing needs it today, since production's files are gone and every Day-15+ upload is indexed. The next chunker or model change (Phase 10) would then have no way to rebuild.
- **Recommendation: A.** It is small, it reuses `IndexingService`, and it makes "Not searchable yet" rows that still have a file fixable without the user re-uploading. On Day 17 it will report v0.2.2's rows as "file missing", which is the honest answer.

### 5. B7: what to do with the result
- **A — Measure and record only:** run img2table on every picture in `HPC Lecture.pptx` with and without `borderless_tables`, count tables and judge false positives by eye, and record both numbers in the tracker. Record the "tables are extracted but never indexed" finding as a new tracker item, without enabling anything or wiring tables into chunks.
- **B — Measure, then wire tables into chunks today** (CSV text appended per slide). Tables would become searchable, but it changes the HPC deck's chunks, so it needs an E4 re-run and widens a day that is already full.
- **Recommendation: A.** Enabling the flag can't change answers until tables are indexed. I'll also time `extract_tables_from_pptx_slides` on the deck. If it is a large share of the PPTX upload time, I'll report it so you can decide (separately) whether to skip table extraction until it is consumed.

## Plan

**Checkpoint 1 — I3 batch embeddings (≈ 5 file ops)**
- `backend/app/retrieval/embeddings.py`: `EMBED_BATCH_SIZE = 100`, `EMBED_MAX_ATTEMPTS = 3`. Batches are sent in order, with retry on 429 / 5xx / `httpx` errors (not other 4xx), and a count check per batch. The sleep function is injectable, so tests don't wait.
- `backend/tests/test_embeddings.py` (new): 0 texts → no call; 250 texts → 3 calls, order preserved; a 429 on the first try → retried, success; a 400 → no retry, `EmbeddingError`; still failing after 3 attempts → `EmbeddingError`.
- `backend/tests/` (existing): adjust the tests that use `fail_embedding_at=1` to force a 502 or keyword fallback. With retry that now succeeds, so they switch to `embeddings_down`.
- Live probe (eval key, one shell): one batch of 100 short texts. Does it succeed, does the vector of text *i* match a single-text call (cosine ≈ 1), and how is it counted against RPM? Results go in the Outcome.
- Upload-time measurement, before and after, on `BCT mod2,3,6.pdf` (63 pages) with the **eval** key. A scratchpad script calls `IndexingService.index_document` against `rag_eval`, once with a one-per-text embedder (the old loop) and once with the new one. It records wall time, the API call count and the chunk count. *Before* costs one call per chunk of the eval key's 1K/day.

**Checkpoint 2 — CO3 reuse by content hash (≈ 7 file ops)**
- `alembic/versions/<rev>_document_chunks_user_content_hash.py`: btree `ix_document_chunks_user_id_content_hash` (autogenerated from the model, reviewed by hand); `backend/app/db/models/document_chunk.py`: the `Index`.
- `backend/app/db/repositories/chunks.py`: `embeddings_by_hash(db, user_id, hashes) -> Dict[str, np.ndarray]`, one query.
- `backend/app/services/indexing_service.py`: hash → reuse lookup → embed only the misses (deduplicated) → delete the chunks of the document *and its earlier versions* → insert. `IndexingResult` gains `embeddings_reused` (logged; not in the API response).
- `backend/app/services/document_service.py`: `register_upload` no longer deletes old versions' chunks. The list of ids moves to the indexing call.
- `backend/app/api/routes/documents.py`: pass the version ids to `index_document`.
- Tests:
  - `test_chunk_store.py`: re-indexing identical text makes 0 embed calls; a changed file with 1 new chunk makes 1 call; another user's identical text is not reused.
  - `test_document_service.py`: a changed upload leaves no old chunks after the commit.
  - `test_migrations.py` covers the new head.
- `alembic upgrade head` + `alembic check` on the local `rag`; staging (`rag_staging`) is your step, as on Day 15.

**Checkpoint 3 — CO6 round trips (≈ 7 file ops)**
- `backend/tests/test_round_trips.py` (new, written first so it gives the *before* number): counts cursor executes + BEGIN / COMMIT / ROLLBACK + pre-pings for `GET /me` and one chat turn (fake Gemini), on the suite's Postgres. It asserts the *after* budget.
- `backend/app/db/session.py`: drop `pool_pre_ping` (Decision 3A); the comment says why.
- `backend/app/services/session_service.py`: `get_or_create_session` / `add_message` flush instead of commit (the caller commits), and the separate refresh goes.
- `backend/app/db/repositories/sessions.py`: `set_topic(db, session_id, topic)`, an UPDATE by id.
- `backend/app/services/chat_pipeline.py`:
  - **T1:** session, history, user message → one commit, with the topic decision captured before the commit.
  - The topic is classified after T1 (no transaction open).
  - **T3:** the topic UPDATE, the failed query and the assistant message → one commit. The error paths still commit the failed query.
  - The `count(*)` goes. The cached-replay path gets the same shape.
- `backend/app/services/container.py`: `PgChunkSearch` gets a sessionmaker on `engine.execution_options(isolation_level="AUTOCOMMIT")`.
- Other callers of `session_service` (`api/routes/sessions.py`, if it uses `create_session`) keep committing themselves. Checked when editing.
- Run the whole suite: `test_api_smoke.py` guards the SSE contract and the stored messages.

**Checkpoint 4 — Reindex script (≈ 4 file ops)**
- `backend/scripts/__init__.py`, `backend/scripts/reindex_all.py`: Decision 4A. It builds `EmbeddingService` / `IndexingService` / `FileStorage` from `app.core` / `services.container` builders (no `app.main`), uses `logging`, and prints a summary table via `logging`.
- `backend/tests/test_reindex.py`: dry run writes nothing; `--apply` indexes a row without chunks; a missing file is reported and skipped; `doc_version` is bumped once per user; reuse means 0 API calls on a second `--all` run.
- `.dockerignore`: keep `backend/scripts/` out of the image, like `eval/` (it is run from a dev shell).
- Live: on the Docker / venv stack, upload a doc, delete its chunks by running the script on a row made chunkless in the test database only. Then run `--apply` on the local `rag` → the "Not searchable yet" badge disappears on refresh.

**Checkpoint 5 — B7 measurement, outcome, docs (≈ 5 file ops)**
- A scratchpad script (not committed): img2table on each picture of `HPC Lecture.pptx`, default vs `borderless_tables=True`. It records tables found and per-table judgement (real / false positive, the crops viewed by me), and times `extract_tables_from_pptx_slides` and `process_pptx` overall.
- No change to `tables.py` under Decision 5A.
- Brief Outcome, post material log (posts per the mapping + post 9), `docs/learning/ai-concepts.md`.
- `docs/improvements.md`: the new finding (tables discarded) as an entry. Tracker rows stay yours.

**New dependencies:** none.

## UI integration
- **I3, CO3:** backend-only, no user-visible change except a faster upload. `POST /upload`'s response keeps its fields (no new field: `embeddings_reused` is logged only). The Documents page's existing upload notice and spinner apply unchanged.
- **CO6:** backend-only. Same endpoints, same SSE frames (the order is guarded by `test_api_smoke.py`); only the round trips change.
- **Reindex script:** backend-only (an operator tool). Its user-visible effect goes through the existing UI: a reindexed row's "Not searchable yet" badge (`DocumentsPage.js`, Day 15) disappears, because `GET /documents` reports its chunk count. No frontend change needed. Checked live in Checkpoint 4.
- **B7:** measurement only, no code change.

## Verification
- **I3:**
  - unit tests (batch split, order, retry / no retry)
  - the live probe (batch of 100 accepted; per-text vectors match single calls, cosine ≥ 0.999)
  - **upload time** of `BCT mod2,3,6.pdf` before vs after: wall time, API calls, chunks (eval key, `rag_eval`)
- **CO3:**
  - tests above
  - a live re-upload on the Docker stack of a *changed* small PDF: the log shows `embeddings_reused` = unchanged chunks, and the API calls equal the new chunks only
- **CO6:**
  - `test_round_trips.py`: before (expected 33 / 4, re-measured with the new test) → after (target: chat ≤ 13, `/me` = 3), as an assertion in CI
  - Render latency (n = 30 `/me`, n ≥ 15 chat turns) can't be measured until v0.3.0 is deployed: it goes into the Day 17 release runbook, with the Day 14 script re-created then
- **Retrieval quality:** batching must not change vectors. The E4 baseline re-run uses the eval cache (0 API calls) and should be identical: Hit@5 50/55, MRR@5 0.806. Run it once after Checkpoint 2, since indexing changed.
- **Whole suite** (`python -m pytest -q` on `rag_test`), `ruff check .`, the frontend unchanged (no build needed), `alembic check` on local `rag`.

## Risks & open questions
1. **Retry changes test semantics.** `fail_embedding_at=1` used to mean "the upload fails". With 3 attempts it now recovers. Those tests move to `embeddings_down`, and new tests cover the recovery.
2. **Retry on the chat path.** In an outage, the query embedding now waits ~3 s (1 + 2 s backoff) before the keyword-only fallback. Acceptable? The alternative is `max_attempts=1` for single-text query calls.
3. **Free-tier accounting of batches.** If a batch of 100 counts as 100 requests against the 100 RPM / 1K RPD limits, batching saves latency but not quota. The live probe will tell. CO3 saves quota either way.
4. **Model / dimension changes and CO3.** Reused vectors are only valid for the same `EMBEDDING_MODEL` + `EMBEDDING_DIM`. Today both are constants and the column is fixed at halfvec(3072). A future change must reindex with `--re-embed`. I'll put that in the constant's comment.
5. **Old versions' chunks after a failed changed upload** (Decision 2A) stay inactive until the next upload or the reindex. They are never searchable (`d.is_active` in both queries), but they count toward the user's chunk rows.
6. **No pre-ping after a pooler restart:** one 500 per dead pooled connection (≤ 10). Watch Render logs after v0.3.0.
7. **Topic tag moves to the end of the turn.** If the client disconnects mid-stream, the tag isn't saved. The next turn re-tags, since the topic is still "General". The sessions sidebar already refreshes after `[DONE]`, but I'll confirm in `ChatWindow.js`.
8. **Staging migration:** the new index revision needs `alembic upgrade head` on `rag_staging` (your shell, as on Day 15) before Day 17's release; production gets it through the image CMD.
9. **The B7 finding** (tables never indexed) is new and not in the tracker. I'll add the evidence to `improvements.md`; the ID and priority are yours.
10. **Day 14's latency script** lived in a scratchpad and is gone. Day 17 needs it re-created for CO6's Render after-numbers.

## Outcome

### Checkpoint 1 — I3 batch embeddings (2026-11-14/15)
- **Files:**
  - `backend/app/retrieval/embeddings.py`: batches of ≤ `EMBED_BATCH_SIZE` (100), sent in order. Retry on 429 / 5xx / `httpx` errors. A 429 waits the server's `retryDelay`, capped at `MAX_RETRY_DELAY_SECONDS` (60 s; owner's change); otherwise 1 s → 2 s with jitter. No retry on other 4xx. A vector-count check per batch. The model / dimension comment (Risk 4).
  - `backend/app/services/container.py`: `embedding_service` (uploads, `INDEXING_MAX_ATTEMPTS = 3`) and `query_embedding_service` (retrieval + semantic cache, `QUERY_MAX_ATTEMPTS = 1`; owner's change to Risk 2), both on the one Gemini client.
  - `backend/tests/test_embeddings.py` (new, 11 tests). `conftest.py`: an autouse fixture records backoff waits instead of sleeping.
  - `test_app_factory.py`: both embedders and their attempts. `test_chunk_store.py`, `test_api_smoke.py`: the two "failure → 502 / nothing written" tests use `embeddings_down`, since one 429 is now retried.
  - `docs/improvements.md`: the triple query embedding recorded under CO5 (not fixed; owner's call).
- **Checks:** suite 325 → **336 passed** on `rag_test`; `ruff check .` clean.
- **Measured** (eval key, `rag_eval`, the real `IndexingService` incl. parse + insert, a throwaway user deleted afterwards; 65 s pause between runs). The "before" loop was paced by eval's `RateLimiter` (90 RPM / 27K TPM):

  | File | Chunks | Before: calls / time | After: calls / time | 429s after |
  |---|---|---|---|---|
  | `BCT mod2,3,6.pdf` (63 pages) | 45 | 45 / **24.1 s** | 1 / **3.7 s** | none |
  | `DL_Unit5_RNN.pdf` (107 pages) | 107 | 107 / **69.5 s** (19.9 s of it pacing) | 2 batches + 1 retry / **29.3 s** (22.0 s of it the retry wait) | batch 2 → 429, `retryDelay` 22 s honoured, then success |

  - Without the pacing the "before" DL run would have failed with a 429 at request ~101 (100 RPM), so its 69.5 s is the best a one-call loop can do on the free tier.
  - **Vectors are unchanged:** batch vs single call, cosine min 1.000000 over 45 + 107 chunks.
- **Risk 3 answered — a batch counts as one request per text against RPM.**
  - Batch 1 had 100 texts, and batch 2 (7 texts), sent right after it with the window clear, got a 429.
  - So batching cuts **latency** (24.1 → 3.7 s; 107 serial calls → 2), not **quota**. RPD presumably counts the same way (not measured).
  - On the free tier any upload over 100 chunks waits for the minute window. The retry with `retryDelay` turns that into a wait instead of a 502. CO3 is the lever that saves quota.
  - The token limit (30K TPM) was not the trigger here: these PDFs are one short chunk per page (~6–8K estimated tokens each).
- **Production's budget (owner, 2026-11-15):** production's Gemini key is on the same free tier, and requests count per text.
  - So production can embed **about 1,000 texts per day across all users**: upload chunks and chat queries draw on the same budget. One 107-chunk lecture PDF is ~11% of a day.
  - Each chat turn currently embeds its question up to 3 times (the CO5 Day 16 finding in `docs/improvements.md`), so a turn costs up to 3 of those 1,000.
  - Not fixed today. CO3 (Checkpoint 2) cuts the upload side for re-uploads.
