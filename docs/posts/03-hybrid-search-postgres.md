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
