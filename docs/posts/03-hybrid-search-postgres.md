# Post 3 — "Hybrid search on Postgres: pgvector + full-text"

Publish after: Day 17 (v0.3.0) · Fed by days: 13–17 · Format: text + 2–3 images

## Hook
Every deploy wiped my app's search index — users still saw their documents, but retrieval
returned nothing. Moving vector + keyword search into Postgres fixed persistence, deletion and
per-user filtering in one move.

## Concepts to explain (plain words)
- Embeddings and cosine similarity
- Brute-force vs. ANN search; how HNSW works at a high level
- Keyword search: BM25 vs. Postgres full-text ranking
- Hybrid search — why you want both
- Pre-filtering vs. post-filtering for multi-tenant search
- Embedding dimensions (3072 → 1536) and the quality trade-off
- Batch embedding and a content-hash embedding cache

## Outline
1. Hook: the vanishing index
2. Before: in-memory FAISS + BM25, filter after search
3. After: one `document_chunks` table (vector + tsvector + user_id)
4. HNSW in one picture
5. Hybrid query: vector + full-text in SQL
6. Results: recall before/after, upload time before/after
7. Deletes and re-uploads now just work (cascade, content hash)
8. Lesson + repo link

## Visuals needed
- [ ] Architecture diagram: before vs. after
- [ ] Table/ERD: `document_chunks` columns and indexes
- [ ] Chart: Recall@5 FAISS vs. pgvector; upload time per 50-page PDF before/after
- [ ] Code card: the hybrid SQL query

## Material log
<!-- /run-day appends one entry per day below, newest last. -->

### Day 13 — 2026-11-11 — Postgres provisioning and Alembic as the real migration path
- Takeaway: before moving search into Postgres, the database itself had to move — and the code that "worked" on SQLite had bugs that only Postgres's stricter rules expose.
- Numbers:
  - old ownership filter `Document.user_id == '1'` on Postgres → `operator does not exist: integer = character varying` (5 such filters + 3 string-id inserts fixed)
  - a raw INSERT returned no row id on Postgres, so the chat's `message_id` would have been null (fixed)
  - schema from code: an empty Postgres → `alembic upgrade head` → 7 tables, `alembic check` = no diff, on local, CI and Supabase staging
  - tests 244 → 269; repository tests 11/11 on SQLite and Postgres
  - a setup script sent through Supabase's SQL editor logged 2 of 2 test passwords in plain text (proved in a throwaway container) → 0 after switching to SCRAM verifiers
- Capture now (only what depends on today's app state and can't be recreated later):
  - [ ] nothing today (no user-visible change; everything below is recreatable)
- Make when writing the post (recreatable any time from git, the brief or this log):
  - [ ] Code card: the old `Document.user_id == str(current_user.id)` vs. the repository's `user_id: int`, with the Postgres error under it
  - [ ] Diagram: one Supabase project → schemas `rag` / `rag_staging`, each owned by its own role, `search_path` on the role, API roles locked out
  - [ ] Terminal card: `alembic upgrade head` + `alembic check` → "No new upgrade operations detected."
  - [ ] Table card: SQLite vs. Postgres differences (brief, "Day 14 notes")
- Lesson / quote: "My database layer had five tenant filters that compared a number with a string — SQLite shrugged, Postgres refused. The bug was invisible until the database got stricter than my code."
- Concept source: docs/briefs/day13.md#the-concept

### Day 14 — 2026-11-13 — Production moves to Postgres (release v0.2.2)
- Takeaway: production used to forget every account whenever the free server went idle, because its database was a file on a disk that gets wiped. Now accounts, chats and feedback live in a real hosted database and survive restarts. Moving cost about 0.2 seconds per request, because the server and the database sit in different countries.
- Numbers:
  - Render has no persistent disk, so there was nothing to migrate: production started empty. The migration-on-start created 7 tables, 7 sequences and 12 indexes in `rag`, at Alembic `7cb8829683ab`, with nothing new in `public`.
  - Persistence, live: register, upload, chat, thumbs-down, restart Render → the account, its session (2 messages), 2 concept maps and the document row all still there. Before: all gone on every restart.
  - The whole test suite on Postgres in CI: 270–271 passed. Its first run found a 500: deleting a chat session that has a logged failed query (the foreign key SQLite never enforced).
  - Latency, Render Singapore → Supabase Mumbai (p50, v0.2.1 SQLite → v0.2.2 Postgres): `/me` − `/health` 0.2 → 190.3 ms (3 round trips × ~63 ms; n = 30); chat to first frame 7720 → 9170 ms, to done 8621 → 11019 ms (n = 5, noisy). Server-side statement time ≤ 0.05 ms: the cost is all round trips (CO6, fixed on Day 16).
  - Ids: the last SQLite-era test account got id 1 (wiped database); the first two Postgres accounts got ids 1 and 2, and Postgres never hands an id out twice.
- Capture now (only what depends on today's app state and can't be recreated later):
  - [ ] Render Logs at the v0.2.2 deploy: `Running upgrade -> 7cb8829683ab, baseline schema` → "Database schema is at head" → "Application startup complete" (the first migration of production `rag` happens only once)
  - [ ] The app after the 17:34 UTC restart: the session and concept maps still listed, using demo data only
- Make when writing the post (recreatable any time from git, the brief or this log):
  - [ ] Table card: the latency before/after table above, with the "3 round trips × 63 ms" breakdown
  - [ ] Diagram: Render (Singapore) ↔ Supabase (Mumbai), one arrow per round trip of a `/me` request (BEGIN, SELECT, ROLLBACK)
  - [ ] Code card: `DELETE FROM sessions` → `ForeignKeyViolation … fk_failed_queries_session_id_sessions`, and the detach fix
  - [ ] Diagram: what survives a restart now (rows: Postgres) vs. what doesn't yet (files, vectors: Days 15–16)
- Lesson / quote: "Moving to a real database made the app keep its memory and cost 190 ms a request. The database work itself takes under a tenth of a millisecond; the rest is three trips between Singapore and Mumbai."
- Concept source: docs/briefs/day14.md#the-concept

### Day 15 — 2026-11-14 — Search moves into Postgres (pgvector + full-text), files into Supabase Storage
- Takeaway: until today the app's search index lived in the server's memory, so every restart made uploaded notes unsearchable, and deleting a file didn't stop it from being quoted. Now the searchable pieces of every document live in the database next to the document itself, and the original files live in cloud storage. A restart forgets nothing, and a delete is final.
- Numbers:
  - E4 retrieval eval, FAISS + BM25 (2026-11-09) → pgvector + Postgres full-text, the same 55 answerable questions and the same cached vectors (0 embedding calls):
    - hybrid Hit@5 50/55 → 50/55 (one question lost, one gained), MRR@5 0.801 → 0.806;
    - vector-only 52/55 → 52/55, with no question flipped;
    - keyword-only Hit@5 47 → 49/55 but MRR@5 0.602 → 0.559 (Postgres ranking has no rare-word weighting).
  - HNSW recall@10 vs exact search on the 419-chunk eval corpus: 1.000 (61/61 queries). At that size the planner chooses an exact scan anyway.
  - Embedding storage: halfvec(3072), the same 6 KB per vector as vector(1536), without truncating dimensions.
  - Database round trips per chat turn, counted after the move: 33 (6 pool pings, 6 BEGIN, 15 statements, 6 COMMIT/ROLLBACK), ≈ 2.1 s at ~63 ms each on Render → Supabase. Retrieval's share is 5. Day 16 cuts it.
  - Restart checks: Docker stack, and `rag_staging` + the `rag-staging` bucket. After a restart a new question still cites the PDF; an identical re-upload returns `unchanged` with 3 chunks either way; a delete leaves 0 files.
  - Tests: 271 → 325 (backend), 11 → 19 (frontend).
- Capture now (only what depends on today's app state and can't be recreated later):
  - nothing today. The live checks ran on demo data that was deleted afterwards, and production gets this at the Day 17 release, where the screenshots belong (the "already indexed" notice and the "Not searchable yet" badge on a real v0.2.2 row).
- Make when writing the post (recreatable any time from git, the brief or this log):
  - [ ] Table card: the E4 FAISS + BM25 vs pgvector + full-text table above, with flipped questions
  - [ ] Diagram: before (vectors in RAM, files on a wiped disk, rows in Postgres) vs after (all three durable; chunks deleted with their document by ON DELETE CASCADE)
  - [ ] Code card: `plainto_tsquery` ANDs every word → `replace(... ' & ', ' | ')` gives OR semantics, with the "How do neural networks in the brain learn?" example
  - [ ] Code card: the two CHECKs that make a zero vector or blank chunk impossible to store
  - [ ] Terminal card: the HNSW-forced EXPLAIN (`Index Scan using ix_document_chunks_embedding_hnsw`) next to recall@10 = 1.000
  - [ ] Table card: the four upload statuses (new / changed / unchanged / reindexed) and what each one does
- Lesson / quote: "The parity test I feared was the vector search; it matched to the question. The surprise was elsewhere: Supabase's S3 refuses boto3's batch delete, so deleting a user's files is now one request per file, and a test makes sure nobody 'optimizes' it back."
- Concept source: docs/briefs/day15.md#the-concept
### Day 16 — 2026-11-15 — Faster ingestion: batched embeddings, reuse by content hash, fewer database round trips, reindex
- Takeaway: uploading a lecture deck used to make one call to the AI provider per slide. Now slides go in batches, unchanged slides of a re-uploaded file reuse the work already stored, and the app paces itself under the free tier's limit instead of failing. Each chat message also waits on a third as many database trips.
- Numbers:
  - Upload time, real indexing path (eval key, the same PDFs):
    - `BCT mod2,3,6.pdf` (63 pages, 45 chunks): 45 calls / 24.1 s → 1 call / 3.7 s.
    - `DL_Unit5_RNN.pdf` (107 pages, 107 chunks): 107 calls / 69.5 s → 2 batches / 29.3 s (22 s of it a 429 wait).
    - Batched vectors identical to single-call ones: cosine 1.000000 over 152 chunks.
  - **The free-tier limit counts texts, not requests:** a 100-text batch used the whole 100-per-minute window.
    - First retry design (wait the server's `retryDelay`): the HPC deck (217 texts) failed with hints of 27 s, 0 s, 59 s.
    - With pacing + 60 s on a 429: 143.3 s, **0 rejected batches** (two 60 s waits).
  - Quota: one 217-text deck ≈ 22% of the free tier's ~1,000 embedded texts per day.
  - Re-upload of a changed PDF (2 of 7 chunks changed): 5 vectors reused, 2 texts embedded, 1 API call. Re-indexing everything again: 0 API calls.
  - Database round trips (counted by a test and matched against Postgres's own statement log): chat turn **33 → 11**, follow-up 23 → 11, `/me` 4 → 3. At ~63 ms each (Render → Supabase), ≈ 2.1 s → 0.7 s per turn — an estimate until it is measured on Render at the Day 17 release.
  - E4: Hit@5 50/55 unchanged. MRR@5 0.806 → 0.808, from an exact tie between identical slides, now ordered by id (two runs give identical numbers).
  - Slide-image table extraction, whose output never became searchable, is no longer run: the HPC deck's working time (without the free tier's pacing) 23.3 s → 12.3 s.
  - Tests 325 → 363 (backend), 19 → 20 (frontend).
- Capture now (only what depends on today's app state and can't be recreated later):
  - nothing today: every live check used throwaway accounts that were deleted, and production gets this with v0.3.0 (Day 17), where the "Large files can take a few minutes to index." spinner and the Render latency numbers belong.
- Make when writing the post (recreatable any time from git, the brief or this log):
  - [ ] Table card: upload time before/after (BCT, DL), calls per upload
  - [ ] Timeline diagram: HPC deck, 100 / 100 / 17 texts with the two 60 s pacing waits, vs the old retry (27 s → 0 s → 59 s → fail)
  - [ ] Table card: round trips per request, test count vs server log, before/after (4/33/23 → 3/11/11)
  - [ ] Diagram: a chat turn's six transactions → two (session + question | answer + topic + failed query), with retrieval's reads outside any transaction
  - [ ] Code card: the two-level vector query — top-k by the HNSW index inside, `(distance, id)` outside — with the EXPLAIN showing the index scan is unchanged
  - [ ] Terminal card: reindex dry run → `--apply` → `--all` with "0 embedding requests"
- Lesson / quote: "I trusted the API's own `retryDelay` and it told me 0 seconds. The limit counts every text in a batch, so the client has to pace itself — the server's hint only says when one request might get through."
- Concept source: docs/briefs/day16.md#the-concept
