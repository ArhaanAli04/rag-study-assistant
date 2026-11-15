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

### Checkpoint 2 — CO3 embedding reuse by content hash (2026-11-15)
- **Files:**
  - `alembic/versions/21f0595f83d5_document_chunks_user_content_hash_index.py`: one `create_index` (reviewed by hand: no drops). `backend/app/db/models/document_chunk.py`: the `Index`.
  - `backend/app/db/repositories/chunks.py`: `embeddings_by_hash(db, user_id, hashes)`, one query, this user only, active and inactive versions alike.
  - `backend/app/services/indexing_service.py`:
    - hash → look up the stored vectors (before the delete, so re-indexing reuses the document's own vectors) → embed only the missing texts, each distinct text once → delete the chunks of the document *and its superseded versions* → insert
    - `reuse_embeddings=False` forces a full re-embed (model change, reindex `--re-embed`)
    - `IndexingResult` gains `embeddings_reused` and `texts_embedded` (logged, not in the API response)
  - `backend/app/services/document_service.py`:
    - `register_upload` no longer deletes old versions' chunks. `RegisteredUpload.superseded_document_ids` carries them to indexing.
    - A `reindexed` re-upload also carries the earlier versions, so a failed changed upload's leftovers are cleared then.
  - `backend/app/api/routes/documents.py`: passes `superseded_document_ids`.
  - **Tests:**
    - `test_embedding_reuse.py` (new, 7 tests):
      - re-index identical → 0 calls
      - `reuse=False` → all embedded
      - duplicate text within a document embedded once
      - **another user's identical text is not reused**
      - **a changed upload embeds only its changed chunks and leaves no old chunks**
      - **a changed upload whose embedding fails keeps the old chunks, unsearchable** (vector and keyword halves both empty)
      - a re-upload after that failure clears the old chunks
    - `test_document_service.py`: the changed-version test now expects superseded ids and v1's chunks kept until indexing.
    - `test_chunk_store.py`: the failed-embedding test forces `reuse_embeddings=False` (the same file would otherwise make no call).
    - `test_migrations.py`: the new index exists.
- **Checks:**
  - suite 336 → **343 passed**; `ruff check .` clean
  - local `rag`: `alembic upgrade head` → `21f0595f83d5`, `alembic check` "No new upgrade operations detected"
  - `rag_staging`: not touched (owner runs it)
- **E4 baseline after CO3** (eval cache: 588 hits, **0 API calls**; `2026-11-15-baseline-after-co3.md`): Hit@5 **0.909 = 50/55** (unchanged), **MRR@5 0.808, not 0.806** (MRR@10 0.824 → 0.821, nDCG@10 0.853 → 0.851).
  - **Cause: the order of exact ties.** 7 questions changed order (g-012, g-029, g-034, h-07, h-09, n-01, n-04). Every pair that swapped has **identical chunk text** (same `content_hash`, so the same vector and score; confidence equal to every decimal):
    - HPC slides 88/89, 98/99, 86/87, 4/6, 110/111
    - BCT pages 30/34/40/46
  - `_VECTOR_SEARCH` orders by distance only. Postgres's sort is not stable, and the eval re-creates its user each run, so the physical row layout differs. Tied rows can then come back in either order.
  - Only g-029 changes a metric: its relevant slide 98 swapped with its duplicate 99 (rank 4 → 3 served; rank 2 → 3 deep).
  - 616 → 588 cache hits: the corpus has 28 chunks whose text repeats an earlier chunk's, and they are now embedded once per document.
  - Not caused by a vector change. A deterministic fix would be `ORDER BY c.embedding <=> :q, c.id` (keyword search already breaks ties on `c.id`). **Not done: owner's call.**
- **Live check** (venv backend on :8001, eval key, local `rag`; a throwaway account deleted afterwards). `co3-notes.pdf`: v1 = NLP Exp4 pages 1–3, v2 = the same with page 3 replaced by BDA Exp10's page 1 (built with pypdf):

  | Upload | Status | Chunks | Reused | Texts embedded | Gemini requests | Time |
  |---|---|---|---|---|---|---|
  | v1 | new | 6 | 0 | 6 | 1 | 3.9 s |
  | v2 (2 of 7 chunks changed) | changed | 7 | **5** | **2** | **1** | 3.0 s |
  | v2 again | unchanged | 0 (skipped, I6) | — | 0 | 0 | 2.1 s |

  - Requests counted as batches: one batch per upload, and no retry warning in the log.
  - `GET /documents` listed only version 2, with 7 chunks.
  - The account delete removed 2 document rows, 2 files and 7 chunks: v1's 6 chunks were already gone.
- **Found:** the Docker backend (`rag-backend`) fails startup after the local migration: `SchemaNotAtHead: Database schema is at 21f0595f83d5, the code expects 500c410270f5`. Its `alembic/` directory is baked into the image (only `backend/app/` is bind-mounted). `docker compose build backend` fixes it; it is needed before Checkpoint 4's badge check.
- **`rag_staging` commands for the owner** (repo root, PowerShell; nothing is printed but revisions):
  ```powershell
  $env:DATABASE_URL = ((Get-Content .env | Where-Object { $_ -match '^RAG_STAGING_DATABASE_URL=' }) -replace '^RAG_STAGING_DATABASE_URL=', '').Trim('"')
  $env:DATABASE_SCHEMA = "rag_staging"
  .\venv\Scripts\alembic.exe current        # expect 500c410270f5
  .\venv\Scripts\alembic.exe upgrade head   # 500c410270f5 -> 21f0595f83d5
  .\venv\Scripts\alembic.exe check          # expect "No new upgrade operations detected."
  .\venv\Scripts\alembic.exe current        # expect 21f0595f83d5 (head)
  Remove-Item Env:DATABASE_URL, Env:DATABASE_SCHEMA
  ```
- **Deterministic tie order (owner's Decision 1, 2026-11-15).**
  - **Why not `ORDER BY distance, id` in one query:** pgvector's HNSW index serves only `ORDER BY <distance> LIMIT k`, so a second sort key would turn it into a full scan at scale (owner).
  - **What changed:**
    - `_VECTOR_SEARCH` (`db/repositories/chunks.py`) is now two levels. The inner query is unchanged in shape (top-k by distance, served by the index). The outer one orders those k rows by `(distance, id)`.
    - Test: `test_exact_ties_in_vector_search_come_back_in_id_order` (`test_chunk_store.py`).
    - Suite **344 passed**, ruff clean.
  - **EXPLAIN** (`rag_eval`, 419 chunks, k = 10, a stored chunk's vector as the query, planner settings `SET LOCAL` in a rolled-back transaction):
    - `enable_seqscan=off` alone: **neither** version uses HNSW. Before and after both pick a user_id btree (bitmap scan) + exact sort. Adding `enable_bitmapscan=off` gives the `(user_id, document_id)` btree + sort, again in both. At this size the planner prefers exact search, as on Day 15.
    - With Day 15's settings (`enable_seqscan`, `enable_bitmapscan`, `enable_sort` off), both use the HNSW index under the `Limit`:
      ```
      BEFORE                                          AFTER
      Limit                                           Incremental Sort
        ->  Nested Loop                                 Sort Key: top.distance, top.id
              ->  Index Scan using                      Presorted Key: top.distance
                  ix_document_chunks_embedding_hnsw     ->  Subquery Scan on top
                  Order By: (embedding <=> q)                 ->  Limit
                  Filter: metadata @> {} AND user_id                ->  Nested Loop
              ->  Memoize -> Index Scan pk_documents                    ->  Index Scan using ix_document_chunks_embedding_hnsw
                                                                            Order By: (embedding <=> q)
                                                                        ->  Memoize -> Index Scan pk_documents
      ```
      The inner plan is the same index scan; the outer `Incremental Sort` touches only the k rows, already sorted by distance.
  - **E4 baseline, run twice after the change** (`2026-11-15-baseline-tiebreak-run1/2`; each 588 cache hits, **0 API calls**):
    - **Every summary number is identical between the two runs:** Hit@5 **0.909 (50/55)**, **MRR@5 0.808**, Recall@5 0.897, Recall@10 0.964, MRR@10 0.824, nDCG@10 0.853.
    - **MRR@5 0.808 is the recorded value.** It differs from Day 15's 0.806 only through g-029's tie: slide 98 and its identical slide 99 now come back in id order, so the relevant one ranks 3rd instead of 4th.
    - **One per-question difference remains:** n-05 (out-of-corpus, no metric). Its 5th served chunk is BCT page 40 in run 1 and page 34 in run 2, two of the four identical BCT chunks (30/34/40/46). This is a tie **straddling the k-th place**: which tied rows the inner `LIMIT` admits is still up to the scan, and the outer sort can only order what it gets. It affects no metric today. Over-fetching (inner `LIMIT k + m`, outer `LIMIT k`) would cover up to m extra ties; not done.

### Checkpoint 3 — CO6 database round trips (2026-11-15)
- **Files:**
  - `backend/tests/test_round_trips.py` (new): counts wire round trips for `GET /me`, a first chat turn (new session) and a follow-up turn.
    - What it counts: statements, `BEGIN` (psycopg sends it before a transaction's first statement), `COMMIT` / `ROLLBACK` (only when a transaction is open, including the pool's reset-on-return) and pre-pings (via `dialect.do_ping`, which no cursor event sees).
    - It asserts exact budgets.
  - `backend/app/db/session.py`: no `pool_pre_ping` (Decision 3A; the trade-off is in the comment). `ReadOnlyAutocommitSession` shares the pool, in autocommit.
  - `backend/app/services/container.py`: `PgChunkSearch(ReadOnlyAutocommitSession)`: retrieval's two searches run with no BEGIN / ROLLBACK.
  - `backend/app/services/session_service.py`: nothing commits.
    - `get_or_create_session` returns `(session, created)` and skips the lookup for `session_id` 0 (the frontend's "new chat").
    - `add_message` flushes and returns the id read back by `RETURNING`.
    - The unused `create_session` is folded in.
  - `backend/app/db/repositories/sessions.py`: `set_topic`, an UPDATE by id (scoped to the user), with no load.
  - `backend/app/services/chat_pipeline.py`:
    - `_open_turn`: session + history (skipped for a new session) + user message, one commit, returning plain values (`_Turn`), so nothing reloads an expired object.
    - `_classify_topic`: an LLM call with no transaction open; the `count(*)` is gone, since "topic is still General" covers it.
    - `_close_turn`: topic UPDATE + the low-confidence failed query (only `add`-ed before streaming, so no transaction stays open while the answer streams) + the assistant message, one commit.
    - On a stream error, `_commit_failed_query` keeps the failed query (`SQLAlchemyError` → rollback + log).
    - The cached-replay path has the same shape. The SSE frame order is unchanged.
  - `backend/tests/test_chat_writes.py` (new, 3 tests):
    - the first turn tags the topic
    - a low-confidence turn stores the failed query with the answer
    - a stream error keeps the question and the failed query, and stores no assistant message
- **Checks:** suite 344 → **349 passed** (+2 round-trip tests, +3 chat-write tests); `ruff check .` clean.
- **Round trips, counted by the test and checked against the compose Postgres's own log** (owner's change 3):
  - Method:
    - `ALTER SYSTEM SET log_statement = 'all'` + `pg_reload_conf()`, reverted afterwards with `RESET` (verified `none`).
    - "Before" ran from a scratchpad copy of the repo with today's `backend/app` diff reverse-applied (`patch -R`; no git write).
    - A scratchpad pytest plugin bracketed each measured request with marker queries from a separate connection, whose pid was excluded.

  | Request | Test, before | Server log, before | Test, after | Server log, after |
  |---|---|---|---|---|
  | `GET /me` | 4 | 4 | **3** | 3 |
  | chat, first turn (new session) | 33 | 33 | **11** | 11 |
  | chat, follow-up turn | 23 | 23 | **11** | 11 |

  - **They match exactly; no fix to the test was needed.** The pre-ping appears in the server log as `;` (psycopg's ping statement). The pool's reset `ROLLBACK` and psycopg's `BEGIN` are both visible there and counted by the test.
  - Before = 6 pings + 6 BEGIN + 15 statements + 4 COMMIT + 2 ROLLBACK (Day 15's 33, reproduced). The reloads after each commit (`SELECT sessions…`, `SELECT messages…` to read ids and the topic) made up 5 of the 15 statements.
  - After, first turn:
    - `BEGIN, user, INSERT session, INSERT message, COMMIT`
    - `vector search, keyword search` (autocommit)
    - `BEGIN, UPDATE topic, INSERT message, COMMIT`
  - After, follow-up turn: session lookup + history instead of the INSERT session, and no topic UPDATE.
  - At ~63 ms per round trip (Day 14), that is about 2.1 s → 0.7 s of network per turn on Render. **Estimate only: measure on Render after v0.3.0 (Day 17), n = 30 `/me`, n ≥ 15 chat turns.**
- **Risk 7 checked:** `ChatWindow.js:157` calls `onSessionCreated` at `[DONE]`, and `ChatPage.js:55` re-fetches the sessions then. The topic commit happens before the `message_id` frame, so the sidebar sees it.
- **Not done:** a live chat on the Docker stack (it would use production's Gemini key). The SSE contract and the stored messages are covered by `test_api_smoke.py` and `test_chat_writes.py`.

### Checkpoint 4 — reindex script + live chat check (2026-11-15)
- **Files:**
  - `backend/scripts/__init__.py`, `backend/scripts/reindex_all.py` (new; `backend/scripts/` was already in `.dockerignore`):
    - Decision 4A, run as `python -m scripts.reindex_all [--all] [--user N] [--re-embed] [--apply]` from `backend/`.
    - Dry run by default. Logs the database name / schema / storage backend (never the URL), a per-document table and a summary with the number of embedding requests.
    - Exit code 1 if any document failed.
  - `backend/app/db/repositories/documents.py`: `list_active_for_reindex(db, user_id | None)`.
  - `backend/app/services/document_service.py`: `_stored_copy_is_usable` → `stored_copy_is_usable` (now also used by the script).
  - `backend/tests/test_reindex.py` (new, 7 tests):
    - dry run writes nothing
    - `--apply` indexes and bumps `doc_version`
    - a missing file is reported and skipped
    - documents with chunks are left alone unless `--all`
    - `--all` again → every embedding reused, 0 calls
    - `--re-embed` bypasses reuse
    - an embedding outage fails only that document and writes nothing
- **Deviation from the plan (told to the owner): `doc_version` is bumped in each document's own commit, not once per user.** With a single bump at the end, a run stopped after the first commit would leave new chunks behind an unchanged `doc_version`. A later default run would skip those documents (they have chunks now), so the bump would never come. Per-document bumps match `/upload`.
- **Checks:** suite 349 → **356 passed**; `ruff check .` clean.
- **Bug found in the live run, fixed:** the script wrapped the Gemini client to count requests, but kept only `client.models`. The unreferenced `genai.Client` was garbage-collected and closed its HTTP client, so `--apply` failed with `RuntimeError: Cannot send a request, as the client has been closed`. Nothing was written. `_CountingClient` now holds the client. The unit tests use a fake client that never closes, so they couldn't catch this.
- **Live chat check** (venv backend on :8001, eval key, local `rag`, web search off, throwaway accounts deleted afterwards):
  - **First attempt invalid: web search was on, Claude's mistake.** In Windows PowerShell `$env:TAVILY_API_KEY = ""` *deletes* the variable, so `.env`'s real Tavily key was read. The three turns made up to 3 real Tavily searches on that key (answer 1 cited a web URL).
  - Re-run through a launcher that sets the empty value inside the Python process (`serve_no_web.py`; pydantic-settings keeps an empty env value), asserting it took effect. The three questions were reworded, because `websearch:{query}` in Redis (1 h) would otherwise have replayed the first run's web results. **0 web sources on every turn.**

  | Step | Result | Evidence |
  |---|---|---|
  | 1. Upload a small PDF, new chat about it | **PASS** | frames metadata → 5 tokens → message_id → [DONE]; cites the PDF; confidence 57.5 (loose); the session is in `GET /sessions` (what the sidebar fetches) with topic **"Linguistics"** |
  | 2. Follow-up in the same chat | **PASS** | same `session_id`, 1 session on the account. Judged by hand: "give one example of each of the two kinds you just explained" got a free-morpheme example ("book") and bound-morpheme examples ("un-", "-ed"), so it used the first turn |
  | 3. Reload, thumbs-down | **PASS** | `GET /sessions/{id}/messages` → user, assistant, user, assistant in order; the assistant ids equal the two `message_id` frames; `POST /messages/{id}/feedback` → `{"status": "ok"}` |
  | 4. Question the PDF can't answer → `failed_queries` | **FAIL, not a CO6 bug** | "Which team won the 1998 football World Cup final…" scored **confidence 72.0 (strict)** against a morphology-only PDF, so no row (0 → 0). This is the B2 / E4 finding: the heuristic doesn't predict relevance (Day 11: 2 of 6 out-of-corpus questions got strict; replaced Day 26) |
  | 4b. Same question, account with **no documents** | **PASS** | confidence 0.0 (none); `failed_queries` rows for it 0 → **1** (`low_confidence`, same session), stored in the turn's last commit with the assistant message |

  - The step 1 check of "after [DONE]" was done through the API the sidebar calls, not in a browser: the browser's frontend talks to the Docker backend, which has production's key.
- **Reindex live check** (local `rag` only; the script ran with `--user` for the throwaway account, so no other local data was touched; eval key). The badge was checked through `GET /documents` on the Docker backend (:8000), the call `DocumentList.js` renders the badge from (`chunks === 0`):

  | Step | Result |
  |---|---|
  | Upload `reindex-notes.pdf` through :8001 | `new`, 6 chunks; `GET /documents` → `chunks 6`, no badge |
  | Delete that document's chunks (`drop_chunks.py`: refuses anything but database `rag` on localhost) | 6 deleted; `GET /documents` → `chunks 0`, **badge shown** |
  | Dry run | lists document 11 "would index"; nothing written; 0 embedding requests; exit 0 |
  | `--apply` | indexed: 6 chunks, 0 reused, 6 embedded in **1** request; `GET /documents` → `chunks 6`, **badge gone** |
  | `--all --apply` | indexed: **6 reused, 0 embedded, 0 embedding requests** |

  - `doc_version` 1 → 3 (one bump per applied run).
  - The reindex account (user 26) was then **deleted** (owner's request) through the venv backend, so its host-stored file went too. Response: 1 document, 1 file, 6 index entries removed. Afterwards: login → 401; `backend/uploads/26` gone; 0 user / document / chunk rows for id 26.
- **Owner's follow-ups (2026-11-15):**
  - Accepted the per-document `doc_version` bump.
  - Regression test for the closed-client bug: `test_the_request_counter_keeps_the_whole_client_alive` (`test_reindex.py`). Its fake client closes its `.models` when garbage-collected, like `genai.Client`, and the test asserts that a call through the counter still works after `gc.collect()`. Checked against the pre-fix wrapper (models only): the same fake fails with the live run's exact error. Suite **357 passed**.
  - Step 4 recorded as new B2 evidence for Day 26 in `docs/improvements.md` (B2, "Day 16 evidence").
- `rag_staging` and production: not touched. Day 17: production gets a dry run only (owner).

### Checkpoint 5 — B7 measurement (2026-11-15; measure only, Decision 5A; `tables.py` unchanged)
- **Account check first:** the reindex throwaway account is gone from local `rag` (0 rows for user 26; `backend/uploads/26` doesn't exist).
- **Tables in `HPC Lecture.pptx`** (242 slides, **11 pictures**). Same preprocessing as `extract_tables_from_image`, then img2table `extract_tables()` with the default vs `borderless_tables=True`. Each detection was outlined and viewed:

  | Picture (slide) | What it is | Default | Borderless | Verdict |
  |---|---|---|---|---|
  | 1 (4) | `do_payroll()` → instruction stream → processor diagram | 0 | 1 (5×14) | false positive |
  | 2 (6) | parallel payroll diagram (4 rows of instruction blocks) | 0 | 1 (8×6) | false positive: a grid-like diagram, not data |
  | 3 (9) | photo collage (galaxy, planets, hurricane) | 0 | 1 (3×5) | false positive |
  | 4 (9) | photo collage (traffic, plate tectonics, tornado) | 0 | 1 (2×5) | false positive |
  | 5 (71) | SISD diagram + instruction stack | 0 | 1 (8×4) | false positive |
  | 6 (72) | SIMD diagram + per-processor instruction stacks + vector add | 0 | 1 (9×9) | false positive |
  | 7 (73) | MISD diagram + instruction stacks | 0 | 1 (7×5) | false positive |
  | 8 (74) | MIMD diagram + instruction stacks | 0 | 1 (8×6) | false positive |
  | 9 (167) | mesh network diagram | 0 | 0 | correct |
  | 10 (169) | hypercube diagram | 0 | 0 | correct |
  | 11 (171) | tree network diagram | 0 | 1 (2×5) | false positive |

  - **No picture in the deck is a real table**, so recall can't be measured on this corpus.
  - Default: 0 detections, all correct.
  - Borderless: **9 detections, 9 false positives, 0 true positives.** Enabling it would index junk "tables" from diagrams and photos, if tables were indexed at all (they aren't; Scope 5).
  - Day 10's samples still stand: `tableimage2.jpg` 0 → 1 real table.
  - **Recommendation: keep the default.** Revisit with real borderless-table slides, together with the decision to index tables at all.
- **Time spent on table extraction** (`extract_tables_from_pptx_slides`, whose output is discarded):

  | Run | Parse (`build_chunks_for_file`) | Of which table extraction | Share |
  |---|---|---|---|
  | first in a fresh process (includes img2table's slow first import) | 10.80 s | **10.16 s** | **94.1%** |
  | warm | 3.42 s | **2.85 s** | **83.2%** |

  - The deck parses to 245 chunks: 242 non-blank, 217 distinct texts (25 repeats, embedded once per document since CO3).
  - **Share of the total upload: not measured.** The full-upload timing run failed at embedding (next finding), so there is no successful upload to divide by. It needs re-running after the retry decision.
- **Finding: Checkpoint 1's retry doesn't survive a full-size second batch on the free tier.**
  - Log, embedding 217 texts in batches of 100: batch 2 → 429 with `retryDelay` **27 s** (waited) → 429 again with `retryDelay` **0 s** (retried at once) → 429 with `retryDelay` **59 s**, after 3 attempts → `EmbeddingError`. `/upload` would answer 502.
  - The quota is per text (`embed_content_free_tier_requests`, limit 100 per minute).
  - `retryDelay` says when *a* request may succeed, not when 100 slots are free for a 100-text batch. Checkpoint 1's DL run passed only because its second batch had 7 texts.
  - The throwaway `rag_eval` user was deleted (in `finally`). Fix decision pending with the owner.
- **Owner's fix (2026-11-15), replacing both options offered:**
  - `backend/app/retrieval/embeddings.py`:
    - `EMBED_TEXTS_PER_MINUTE = 100` (the free tier's limit, counted per text) and `RATE_WINDOW_SECONDS = 60`.
    - `EmbeddingService(texts_per_minute=…)` paces each `embed_texts` call: before a batch, if the texts sent in the last 60 s plus this batch exceed 100, it sleeps until the oldest batch is 60 s old. The window is local to the call (no state shared across requests, no new setting). Sleep and clock are module functions the suite replaces.
    - A 429 now waits `min(max(retryDelay, 60 s), 60 s)` = 60 s, with 3 attempts.
    - The chat-path embedder has no pacing and 1 attempt (unchanged).
  - `backend/app/services/container.py`: the upload embedder gets `texts_per_minute=EMBED_TEXTS_PER_MINUTE`.
  - `backend/scripts/reindex_all.py`: the same pacing, per document. Between documents the 429 safety net covers it.
  - `backend/tests/conftest.py`: the autouse fixture now also patches the clock, and each recorded wait advances it.
  - `backend/tests/test_embeddings.py`:
    - 217 texts → batches 100/100/17 with recorded waits [60, 60] and no 429
    - a 429 waits 60 s even with `retryDelay` 27 s and then 0 s
    - a 429 with no hint waits 60 s; a 3600 s hint is capped at 60 s
    - two 45-text uploads don't wait
    - the chat path isn't paced
  - `test_app_factory.py`: only the upload embedder is paced.
  - **UI:** `frontend/src/components/DocumentUpload.js` shows a spinner and "Large files can take a few minutes to index." (`role="note"`) under the buttons while an upload runs. `frontend/src/pages/DocumentsPage.test.js`: shown while the upload is pending, gone after it finishes.
- **HPC deck re-timed live** (eval key, `rag_eval`, throwaway user deleted; the app's paced upload embedder):

  | | Seconds | Share |
  |---|---|---|
  | **Total upload** (242 chunks, 3 blank skipped, 217 texts embedded) | **143.3** | 100% |
  | parse (`build_chunks_for_file`, fresh process) | 12.1 | 8.4% |
  | of which **table extraction** (output discarded) | **11.4** | **8.0%** of the total; **49.1%** of the 23.3 s left once the 120 s of pacing is excluded |
  | embedding | 128.7 | of which **120.0 s pacing** (two 60 s waits before batches 2 and 3) |
  | database writes etc. | 2.5 | |

  - **Rejected batches (429): 0.**
  - A warm parse rerun: 3.6 s, of which tables 2.8 s (76.3%).
  - **Quota:** this one deck used 217 of the free tier's ~1,000 embedded texts a day, **about 22%**. That is an argument for the CO5 fix (the question embedded up to 3 times per chat turn) and for checking a paid tier before real usage.
- **B7 recommendation, for the owner to decide (not acted on):** table extraction is about half of an HPC upload's working time when the free-tier waits are excluded (11.4 of 23.3 s in a fresh process; 2.8 s warm). Its output is never indexed (Scope 5), and on this deck it finds no real tables. **Skip `extract_tables_from_pptx_slides` in `process_pptx` until tables are indexed.** That would also skip img2table's ~4 s import on the first PPTX upload after each start. Keep `borderless_tables` off either way (9/9 false positives).
- **Suite:** 357 → **361 passed** (backend); `DocumentsPage.test.js` 8 → **9 passed**; `ruff check .` clean; frontend `CI=true npm run build` passes (as Vercel builds it).

## Day 16 summary

### Files changed (whole day)
- **I3, embeddings:** `backend/app/retrieval/embeddings.py`; `backend/app/services/container.py`; tests `test_embeddings.py` (new), `conftest.py`, `test_app_factory.py`, `test_chunk_store.py`, `test_api_smoke.py`
- **CO3, reuse:** `alembic/versions/21f0595f83d5_document_chunks_user_content_hash_index.py`; `backend/app/db/models/document_chunk.py`; `backend/app/db/repositories/chunks.py` (also the two-level vector query); `backend/app/services/indexing_service.py`; `backend/app/services/document_service.py`; `backend/app/api/routes/documents.py`; tests `test_embedding_reuse.py` (new), `test_document_service.py`, `test_migrations.py`, `test_chunk_store.py`; E4 summaries `backend/eval/results/2026-11-15-baseline-{after-co3,tiebreak-run1,tiebreak-run2}.md`
- **CO6, round trips:** `backend/app/db/session.py`; `backend/app/db/repositories/sessions.py`; `backend/app/services/session_service.py`; `backend/app/services/chat_pipeline.py`; `backend/app/services/container.py`; tests `test_round_trips.py` (new), `test_chat_writes.py` (new)
- **Reindex:** `backend/scripts/__init__.py`, `backend/scripts/reindex_all.py` (new); `backend/app/db/repositories/documents.py`; tests `test_reindex.py` (new)
- **UI:** `frontend/src/components/DocumentUpload.js`; `frontend/src/pages/DocumentsPage.test.js`
- **Docs:** this brief; `docs/improvements.md` (CO5 triple-embedding finding + quota note; B2 Day 16 evidence); `docs/posts/03-hybrid-search-postgres.md`, `docs/posts/09-launch-recap.md` (material logs); `docs/learning/ai-concepts.md` (gitignored; concepts 1, 4, 11)

### UI integration
| Backend change | Frontend file | What the user sees |
|---|---|---|
| Upload embeddings paced under 100 texts per minute (a large file can take minutes) | `components/DocumentUpload.js` | While an upload runs: a spinner and "Large files can take a few minutes to index." (tested in `DocumentsPage.test.js`) |
| I3 batching, CO3 reuse (`IndexingResult.embeddings_reused` / `texts_embedded`) | — | backend-only: logged, not in the API response. Uploads are faster; the existing notice and statuses are unchanged |
| CO6 transactions, no pre-ping, autocommit reads | — | backend-only: same endpoints and SSE frames (order guarded by `test_api_smoke.py`); the topic tag is committed before `message_id`, so the sidebar refresh at `[DONE]` sees it |
| Deterministic tie order in vector search | — | backend-only: the same results, in a stable order |
| Reindex script | `components/DocumentList.js` (existing) | an operator tool; its effect goes through the existing "Not searchable yet" badge (`chunks === 0`), which disappears after `--apply` (checked live) |
| Index `(user_id, content_hash)` | — | backend-only: a migration |

### Timeline bullets deferred or dropped
- "Remove FAISS / BM25 + their dependencies" and "E4 re-run vs the FAISS baseline": done on Day 15.
- "Upload time for a 50-page PDF before vs after": done with `BCT mod2,3,6.pdf` (63 pages) and `DL_Unit5_RNN.pdf` (107 pages), plus the HPC deck after the pacing fix.
- CO6 "re-measure n = 30 `/me`, n ≥ 15 chat turns": on Render only after v0.3.0 (Day 17). Today's numbers are local round-trip counts.
- B7: measured only (Decision 5A). Not enabled: 9/9 false positives.
- `reindex_all.py` against production: not run (Day 17, dry run only).

### Numbers for the tracker's Notes column
- **I3:**
  - BCT 45 calls / 24.1 s → 1 / 3.7 s; DL 107 / 69.5 s → 2 batches / 29.3 s.
  - HPC deck (217 texts) 143.3 s with 0 rejected batches (pacing 100 texts / 60 s; a 429 waits 60 s).
  - Batch vs single cosine 1.000000.
  - The free tier counts per text.
- **CO3:** changed re-upload with 2 of 7 chunks changed: 5 reused, 2 embedded, 1 call. Reindex `--all`: 0 calls. Index `21f0595f83d5`.
- **CO6:** chat turn 33 → 11, follow-up 23 → 11, `/me` 4 → 3 round trips (test = server log). Render latency pending (Day 17).
- **B7:** HPC deck 11 pictures, 0 real tables; default 0 detections, borderless 9 (9 false positives). Not enabled. Table extraction is 11.4 s of a 143.3 s upload (8.0%; 49.1% without free-tier waits).
- **E4:** Hit@5 50/55, MRR@5 0.808 (deterministic; was 0.806 through unstable tie order).

### Day 17 release checklist (Day 16's part)
`rag_staging` is already at `21f0595f83d5` (the owner ran it); production gets the migration through the image's CMD (`alembic upgrade head`); measure CO6 on Render with n = 30 `/me` and n ≥ 15 chat turns after re-creating the latency script (the Day 14 one was a scratchpad file); run `python -m scripts.reindex_all` against production as a **dry run only**, and expect v0.2.2's rows to be reported "skipped: file missing".

### Owner's decision: B13 (2026-11-15)
- **Skip PPTX table extraction until tables are indexed.** `backend/app/ingestion/parsers/pptx_pipeline.py`:
  - `process_pptx` no longer calls `extract_tables_from_pptx_slides` or returns `"tables"`. Nothing else read the key, apart from one test asserting it existed.
  - Dropped rather than returned empty: an empty list would claim "no tables found".
  - The docstring says why (11.4 s / 49%, 0 real tables) and when to re-enable.
  - Type hints added; the docstring's old "OCR" step, which never ran here, removed.
  - `tables.py` and `extract_tables_from_pptx_slides` unchanged.
- **Tests (`backend/tests/test_pptx_utils.py`):**
  - A fixture records img2table's `Image.extract_tables` calls, where every path to slide-image tables ends. The callers swallow exceptions, so a raising fake would go unnoticed.
  - A deck built in the test with a picture (`sampleimg1.png`). `sample2.pptx` has **no pictures**, so a test on it would have passed with or without extraction (checked: 0 calls either way).
  - Control: called directly, the old extraction reaches img2table once on that deck.
  - `process_pptx` returns only `metadata` + `slides` and makes 0 detection calls.
  - `POST /upload` of the deck returns 200 with chunks and makes 0 detection calls.
  - The old `"tables"`-key test was replaced.
- **Re-timed live** (eval key, `rag_eval`, throwaway user deleted): HPC deck working time without pacing **23.3 s → 12.3 s**. Total 132.3 s, of which 120.0 s pacing; parse 12.1 s → 0.7 s; table timer 0.0 s; 0 rejected batches.
- **Recorded:**
  - `docs/improvements.md` B13 (P2), plus a B7 Day 16 status note.
  - Tracker: B13 new (Not Started: "extraction skipped since Day 16, re-enable when tables become chunks"); I3, CO3, CO6, B7 → Done with today's numbers.
  - CLAUDE.md: Current Status, the Embeddings row, the Ingestion row, the partial / not-present lists (CO3 gone), Known Issues B7 / B13 / CO6, the reindex commands, `backend/scripts/` in the repo structure.
- **Checks:** suite **363 passed**, ruff clean.
- **More files changed today:** `backend/app/ingestion/parsers/pptx_pipeline.py`, `backend/tests/test_pptx_utils.py`, `docs/improvement-tracker.md`, `CLAUDE.md`.
