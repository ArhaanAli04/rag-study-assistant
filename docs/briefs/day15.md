# Day 15 — Chunks table — vector + keyword search in Postgres (I4, I5, I6, I1, I2)
Date: 2026-11-14 · Phase 5 — Postgres + pgvector data layer · Items: I4, I5, I6, I1, I2 (plus the Day 14 FK follow-up)
Branch: feature/day15-pgvector-chunks

## Scope

1. **Alembic revision `document_chunks`.** Columns: id, user_id FK, document_id FK `ON DELETE CASCADE`, document_version, page, chunk_index, text, content_hash, embedding, tsv (generated tsvector), metadata jsonb. Indexes: HNSW on embedding (cosine), GIN on tsv, btree on (user_id, document_id).
2. **Same revision: foreign-key rules (Day 14 follow-up).**
   - `fk_failed_queries_session_id_sessions` gets `ON DELETE SET NULL`.
   - The `user_id` FKs of sessions, documents, messages, failed_queries and concept_maps get `ON DELETE CASCADE`.
   - Each is dropped and re-created by its naming-convention name.
   - Added here: `documents.file_size` (nullable). `GET /documents` reads the size from the local file today, and once files live in Storage there is no local file to read (deliverable 7).
3. **Embedding dimension (Decision 1).** The timeline says 3072 → 1536 because HNSW on `vector` stops at 2000 dimensions. pgvector 0.8's `halfvec` type allows HNSW up to 4000 dimensions, so 3072 can stay.
4. **Indexing moves into `services/`.** `ingestion/indexing_pipeline.py` writes into retrieval's indexes, a sideways import that `layout.md` lists as an exception. It becomes a use case in `services/indexing_service.py`. `DocumentChunk` stays in ingestion as the parser output, and retrieval stops importing it (this closes layout exception 2).
5. **`PgVectorStore` + `PgKeywordIndex` (I1, I2, I4).** They sit behind the interfaces `RetrievalService` already uses. The user filter goes in the `WHERE` clause, so there is no over-fetch and post-filter (I1). Everything persists in Postgres (I4), and there is no rebuild on add (I2).
6. **Postgres full-text search (`ts_rank_cd`) replaces BM25Okapi.** Measured on E4 before rank-bm25 is deleted (Decision 4). E4 needs a database now (Decision 3).
7. **Uploaded files move to Supabase Storage** (Decisions 5 and 6). Private buckets `rag-prod` and `rag-staging`, object key `uploads/{user_id}/{uuid}{ext}`. Upload writes to Storage, indexing reads from it, and `Document.file_path` holds the object key.
   - **The copy script isn't needed, and I'll leave it out.** Production has no files to copy: Render has no disk, and every file was wiped at the latest by the v0.2.2 deploy. Local dev keeps a local-disk storage backend, so it has nothing to copy either.
   - v0.2.2 production rows with no file are handled by the re-upload path (deliverable 9) and by Day 16's reindex, which skips and reports rows without an object.
8. **I5: deleting a document** cascades to its chunks and removes the file from Storage. All versions of that file name go (see Plan).
9. **I6: `register_document` reports `new` / `changed` / `unchanged`.**
   - `unchanged` skips indexing and the `doc_version` bump.
   - `changed` deletes the old version's chunks.
   - One addition beyond the timeline: "unchanged" means the same hash **and** chunks exist for that row. Rows created on v0.2.2 have no chunks, and treating them as unchanged would make them impossible to index.
10. **UI changes:**
    - Deleted documents disappear from the list and from citations immediately.
    - Re-uploading an unchanged file shows "already indexed".
    - Added: a "not searchable yet" badge on rows with 0 chunks (deliverable 9's v0.2.2 rows).
11. **Not required by the timeline, forced by deliverable 1: the suite can't stay on SQLite** (Decision 2).
12. **Verify:** restart the backend → documents are still retrieved (I4); a deleted document is never cited again.

Already done or out of scope: R5 (concept maps on documents) is Day 17 (the tracker shows it In Progress, but no work has started). The batch embeddings, CO3, CO6 and the reindex are Day 16.

## Current behavior

- **Indexes live in memory.** `services/container.py:56-57` builds one `IndexBuilder` (FAISS `IndexFlatL2`, `retrieval/vector_store.py:11`) and one `BM25KeywordIndex` per process, so a restart empties both (I4).
- **The user filter runs after the search.** `FaissVectorStore.search` over-fetches `top_k * 5` and filters `user_id` in Python (`vector_store.py:66-86`, I1). A user whose chunks are outnumbered gets fewer than `top_k` results.
- **BM25 rebuilds everything on every add.** `BM25KeywordIndex.add_documents` rebuilds `BM25Okapi` over the whole corpus (`keyword_index.py:27-35`, I2). Its tokenizer is `lower().split()`, so "RNN?" ≠ "rnn" and nothing is stemmed.
- **Deleting a document leaves its chunks.** `DELETE /documents/{id}` deletes the row and bumps `doc_version` (`api/routes/documents.py:88-106`). Chunks stay in FAISS and BM25 and the file stays on disk (I5); the old `mark_delete_by_document_id` is never called.
- **Re-uploads always re-index.** `register_document` returns the existing row on an identical hash (`services/document_service.py:35-36`), but `/upload` indexes unconditionally and bumps `doc_version` (`documents.py:70-79`). A changed version never removes the old version's chunks (I6).
- **Indexing is a sideways import.** `IndexingPipeline` (`ingestion/indexing_pipeline.py:11-12`) imports retrieval's `IndexBuilder` and `BM25KeywordIndex` (`layout.md` exception, deferred to today). `IndexBuilder` and `FaissVectorStore` import `ingestion.models.DocumentChunk` (exception 2).
- **The embedding dimension is 3072.** `retrieval/embeddings.py:14` sets `EMBEDDING_DIM = 3072` and sends it as `output_dimensionality`. One call per text (I3, Day 16). On an API error it stores a zero vector (`embeddings.py:45-47`).
- **Files go to local disk.** `/upload` writes `uploads/{user_id}/{uuid}{ext}` there (`documents.py:57-64`, `ingestion/upload_storage.py`). On Render that disk is wiped by every restart. `GET /documents` reads `os.path.getsize(doc.file_path)` (`documents.py:120-121`), so on Render the size is `None` after a restart.
- **Account deletion deletes children first and tombstones the indexes.** `delete_user_account` deletes children explicitly, then tombstones FAISS/BM25 (`services/account_service.py:72-101`). `/user/delete` passes `services.index_builder.get_index()` and `services.bm25_index` (`api/routes/users.py:80`).
- **The baseline schema has no `ON DELETE` rules** (`alembic/versions/7cb8829683ab_baseline_schema.py:62,76,86,111-112,125-126`).
- **The default test run is SQLite.** A plain `pytest` uses a temp SQLite file (`tests/conftest.py:99-101`). `test_migrations.py` uses its own SQLite files on purpose. `alembic/env.py:47` has a batch mode for SQLite.
- **E4 builds in-memory indexes.** `eval/retrieval/corpus.py:93-105` runs `IndexingPipeline` into fresh in-memory indexes with `user_id="eval"` (a string, no user row). Its embedding cache key includes the dimension (`embedding_cache.py:39`), so 3072-dim vectors are cached for the whole corpus.
- **The frontend ignores the upload response.** `DocumentsPage.js:45-72` uploads, ignores the response body and refetches. It has an error banner, but no success or notice state.

## Why it matters

1. **I4:** Render restarts or spins down → the document is still listed, but the chat never cites it. It falls back to web results and general knowledge until the user re-uploads, and since Day 14 the rows outlive the vectors on every restart.
2. **I5:** a user deletes a lecture PDF → its chunks keep winning top-5, and answers cite a file that is no longer in their list.
3. **I6:** a student re-uploads the same slides twice → every chunk is in the index three times. The near-duplicates fill top-5 and crowd out other pages, each upload re-embeds every chunk (Gemini quota), and the `doc_version` bump throws away the user's caches.
4. **I1:** with many users, a small user's query can return fewer than 5 chunks, because the ×5 over-fetch is spent on other users' vectors. The cost is also a linear scan of everyone's vectors.
5. **I2:** each upload rebuilds BM25 over every user's corpus, so upload time grows with total users rather than with the file.
6. **Storage:** Render deletes the files on every restart. Day 16's reindex, Day 50's PDF viewer and the connectors all need the original file after a restart.
7. **FK rules:** a future delete path that forgets one child type gets a 500 (`ForeignKeyViolation`), as `DELETE /sessions/{id}` did on Day 14. With `CASCADE` / `SET NULL` the database enforces the rule whatever the code path.

## The concept

### Where search indexes should live

A search index is **derived data**: it can be rebuilt from the source documents, but rebuilding costs time and money (an embedding call per chunk). Keeping it only in process memory couples its lifetime to the process. That works for a notebook, but not for a server that restarts on every deploy.

There are three production patterns:

1. **A dedicated vector database** (Qdrant, Pinecone, Weaviate). Fast and feature-rich, but a second system to keep consistent with the relational rows, which leaves the dual-write problem: a crash between "insert document row" and "upsert vectors".
2. **The vector index inside the primary database** (pgvector). The chunk rows sit beside the document rows, so an upload's chunks are committed in the same transaction as the bookkeeping, and `ON DELETE CASCADE` makes a delete atomic across both. This is the "one database until it hurts" choice. It fits until tens of millions of vectors or very high QPS.
3. **Index files on object storage** (FAISS / LanceDB files saved to S3). Cheap, but writes are awkward (rewrite the file, lock it), and multi-process consistency is on you.

We picked (2) on 2026-11-04. Its main payoff is **transactional consistency**: no state exists where the row says "deleted" but the vectors still answer.

### Exact vs. approximate nearest neighbours

**Exact search.** `IndexFlatL2` compares the query with every vector: O(N), perfect recall.

**HNSW (Hierarchical Navigable Small World)** builds a multi-layer proximity graph and greedily walks it from a coarse top layer down to the dense bottom layer. The cost is O(log N)-ish, and recall is below 100%, tuned by:
- `m`: edges per node (default 16)
- `ef_construction`: candidate list width while building (default 64)
- `hnsw.ef_search`: candidate list width while querying (default 40). More means better recall and slower queries.

An HNSW index costs memory (it should fit in RAM), and a large build is slow. Its alternative, IVFFlat, needs training data at build time, which is wrong for an empty table that grows.

### Filtered vector search: the pitfall I1 is about

"Top-k nearest **among this user's chunks**" is the hard case for every ANN index:
- **Post-filtering** (search top-k·5, then drop other users' rows) silently returns fewer than k results when the user is a minority of the index. That is exactly today's FAISS code.
- **pgvector before 0.8** had the same behaviour: the HNSW scan returned `ef_search` candidates and the `WHERE` clause then removed most of them.
- **pgvector 0.8 adds iterative index scans** (`hnsw.iterative_scan = relaxed_order`): the scan keeps going until enough rows pass the filter.
- **The planner can also skip HNSW.** With a selective btree on `user_id`, it can read that user's few thousand rows and sort them exactly, which is fast at our scale and has perfect recall.

Either way the filter belongs **inside** the query, not after it, and `EXPLAIN ANALYZE` shows which plan you get. Very large multi-tenant systems partition by tenant (per-tenant indexes or partial indexes).

### vector vs. halfvec, and Matryoshka embeddings

- **`vector(n)`** stores float32. Its HNSW index supports n ≤ 2000, because an index tuple must fit in an 8 KB page.
- **`halfvec(n)`** stores float16 (half the bytes) and allows HNSW up to 4000 dimensions. For L2-normalized embeddings, float16's ~3 significant digits move cosine similarities by about 1e-3, far below the gaps between relevant and irrelevant chunks.
- **Matryoshka training.** `gemini-embedding-001` was trained so that a vector's leading dimensions are themselves a usable embedding (Matryoshka Representation Learning). Requesting `output_dimensionality=1536` is therefore cheap in quality. It is not free, and the vector must be re-normalized (our `EmbeddingService` already does).
- **The two options compared.** `vector(1536)` and `halfvec(3072)` take the **same storage** (6 KB per vector). Truncation removes information; halving precision removes almost none.

### Full-text search vs. BM25

Postgres full-text search turns text into a `tsvector` with `to_tsvector('english', text)`: it lower-cases, drops stop words, stems ("networks" → "network"), and records positions. A GIN index maps each lexeme to the rows containing it.

- **Ranking.** `ts_rank` / `ts_rank_cd` score by term frequency and proximity (cover density). Unlike BM25 they have **no IDF**: a rare term like "LSTM" counts no more than a common one like "network". This is the main quality risk, and why E4 measures it before rank-bm25 goes. True BM25 inside Postgres needs an extension (ParadeDB `pg_search`, VectorChord-bm25), and Supabase doesn't offer one.
- **Query construction is the classic pitfall.** `plainto_tsquery('english', 'what is a recurrent network')` ANDs every term (`recurr & network`). A natural-language question then matches almost nothing, and the keyword half of hybrid search goes silent. Hybrid retrieval wants **OR** semantics: any term matches, and the rank orders the rows. One way: `replace(plainto_tsquery(...)::text, ' & ', ' | ')::tsquery`. `websearch_to_tsquery` supports `or`, but only when the user types it.
- **The generated column.** `tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED` keeps the index consistent with the text automatically. The text-search configuration must be named explicitly (`'english'`), because a generated column requires an immutable expression and the one-argument form depends on a session setting.

### Hybrid fusion when one side changes scale

BM25 scores are unbounded, `ts_rank_cd` values are small floats, and cosine similarity lies in [-1, 1]. Our fusion min-max-normalizes each list, so a scale change doesn't break it, but the **shape** of the distribution changes and the 0.6 / 0.4 weights were never tuned. Reciprocal Rank Fusion (R4) avoids scale questions altogether. Today we only measure.

### Object storage for user files

Servers on platforms like Render, Heroku or Cloud Run have **ephemeral filesystems**. Durable bytes go to object storage (S3 or compatible: Supabase Storage, R2, GCS).

- **Store the key in the database, not the URL.** URLs change with buckets, CDNs and signed-URL expiry; the key is the stable identity.
- **Credentials should be least-privilege.** A key that can read every bucket, or that bypasses row-level security on every table, turns a leaked server env var into a breach of everything that key reaches.
- **Ordering and failure.** Write the object first, then commit the row. A crash leaves an orphan object, which is cheap and sweepable, rather than a row pointing at nothing. Delete in the reverse order: commit the row deletion, then delete the object, and log a failure rather than fail the request (the same "database is the source of truth" rule `delete_user_account` already follows).

### Referential actions

`ON DELETE CASCADE` deletes children with the parent, and `ON DELETE SET NULL` detaches them. They move a rule from "every code path must remember" into the schema.

Pitfalls:
- A cascade can delete far more than intended. Cascade only from true ownership (a user owns their sessions), never from a lookup.
- An ORM's own cascade settings are separate from the database's.
- SQLite ignores foreign keys unless `PRAGMA foreign_keys=ON`. That is why SQLite-tested code broke on Postgres on Day 14.

## Decisions

**Approved 2026-11-14:** 1B, 2A, 3A, 4A, 5B, 6A. `pgvector` and `boto3` approved. Deleting a document removes all its versions. Storage stays in Day 15 and moves to Day 16 only if the day runs long. The owner's changes to the plan:

1. **Parity rule (replaces Decision 4's CI test), paired per question against `2026-11-09-*-after-b8`:**
   - `vector_only` must match within 1 question. It uses the same cached vectors, so a bigger gap is a bug: the halfvec cast, HNSW recall or the filter.
   - Hybrid Hit@5 may lose at most 1 question, and MRR@5 at most 0.03.
   - Every question that flipped, either way, is listed.
   - `keyword_only` may drop (`ts_rank_cd` has no IDF): recorded, but the judgement is on hybrid.
2. **Order:** E4 on Postgres runs right after Checkpoint 2, before Checkpoints 3–4.
3. **No zero vectors in `document_chunks`, ever:**
   - empty-text chunks are skipped (B10);
   - a failed embedding call fails the upload instead of storing zeros;
   - a database CHECK, plus a test.
4. **CO6:**
   - one DB session per `hybrid_retrieve` (vector + keyword in the same session);
   - `GET /documents` counts chunks with one grouped query;
   - the round-trip count of a chat turn after the change is recorded for Day 16.
5. **HNSW recall@10:** measured on the eval corpus against an exact search (index scan off) for the same queries, alongside the EXPLAIN check.

### 1. Embedding storage: dimension and type
- **A — `vector(1536)`, as the timeline says:** request 1536 dimensions (Matryoshka truncation) and store float32, which fits HNSW's 2000 limit. This loses some quality to truncation (Google's MTEB numbers show a small drop). Every cached eval vector (keyed on 3072) becomes invalid, so E4 needs ~390 corpus re-embeddings plus query embeddings. The E4 comparison would also mix two changes, the dimension and the store.
- **B — `halfvec(3072)`:** keep 3072 dimensions and store float16. pgvector 0.8 builds HNSW on halfvec up to 4000 dimensions. Storage is identical to A (6 KB per vector) and precision loss is ~1e-3 on cosine. The eval cache stays valid, so E4 isolates the store change. The query is cast to `halfvec`, and the HNSW operator class is `halfvec_cosine_ops`.
- **Recommendation: B.** It is the same size as A without the truncation loss, and E4 then measures exactly one change. The timeline's note ("confirm the quality cost with E4") becomes moot. It also needs no re-embedding on Day 16 beyond what the reindex does anyway.

### 2. The test suite without SQLite
`document_chunks` uses `halfvec`, `tsvector`, a generated column, GIN and HNSW, none of which exist in SQLite.
- **A — Postgres only:** drop SQLite from the app and the suite. `DATABASE_URL` gets no SQLite default, `build_engine`'s SQLite branch and env.py's batch mode go, and conftest requires `TEST_DATABASE_URL` (a clear `UsageError` otherwise). `test_migrations.py` runs on the suite's `*_test` database and always leaves it at head. One schema everywhere, as T2 intended, at the cost of needing `docker compose up -d postgres` for every local `pytest` (CI and `dev.ps1 test` already have Postgres).
- **B — keep SQLite for a plain local run:** the revision creates `document_chunks` only on Postgres, the model's types get SQLite variants, and DB-retrieval tests skip on SQLite. That keeps the zero-setup local run, but the two dialects get different schemas, `alembic check` and the "no diff" test need dialect exceptions, and the skipped tests are exactly the ones that matter today.
- **Recommendation: A.** No environment runs SQLite since Day 14. B rebuilds the dual-schema drift T2 removed and quietly skips the important tests. CLAUDE.md's Key Commands get the one-time local setup (already documented for `rag_test`).

### 3. Where E4 gets its database
E4 used in-memory indexes. It now needs Postgres, and a real user row (`document_chunks.user_id` is an FK, so `"eval"` can't stay a string).
- **A — a dedicated local database `rag_eval`:** `EVAL_DATABASE_URL` / `EVAL_DATABASE_SCHEMA`, refused unless the name ends in `_eval`. Each run wipes it, migrates it, creates one eval user and indexes the corpus through the real indexing service (vectors from the embedding cache, 0 API calls). This uses the same guard pattern as conftest's `_test`, so a typo can never wipe dev data.
- **B — reuse `rag_test`:** no new database, but an eval run and a test run would wipe each other's data, and the eval's corpus would sit in a database the suite resets.
- **Recommendation: A.** It costs one `createdb` (same command as `rag_test`).

### 4. rank-bm25 and the FAISS code
- **A — delete them today if E4 shows parity:** parity means Hit@5 / MRR@5 on pgvector + FTS within the 2026-11-09 baseline's 95% CI. Delete `vector_store.py`, `index_builder.py`, `keyword_index.py`, `faiss-cpu`, `rank-bm25`, `tqdm`, and regenerate the lock. This pulls one Day 16 bullet forward, and the owner's dead-code rule says unused code goes.
- **B — leave them unused until Day 16, as the timeline says.** Smaller diff today, but dead modules sit in `develop` for a day.
- **Recommendation: A if parity holds; otherwise keep them, record the gap, and decide on Day 16** (for example, keyword weight or RRF before deletion).

### 5. Supabase Storage credential (the project is shared with another app)
- **A — `service_role` (or `sb_secret_…`) key + Storage REST over `httpx`:** no new dependency (httpx is already a direct dependency). But that key bypasses RLS for the **whole project**: every bucket, plus every table the Data API exposes, including the other app's. A leaked Render env var would undo Day 13's per-schema isolation.
- **B — Supabase S3 access keys + `boto3`:** the key reaches Storage only (all buckets in the project, including the other app's, but no database and no Auth admin). It needs `boto3` (new dependency, ~15 MB with botocore; **needs approval**).
- **Recommendation: B.** It keeps the database out of the credential's reach, matching Day 13's isolation decision. S3 keys can be revoked independently of the project's API keys. If you'd rather not add boto3, A is workable, but the brief would record the wider blast radius under Risks.

### 6. Local dev and tests: storage backend
- **A — a `FileStorage` protocol with two backends:** `local` (a directory, the default for dev and tests) and `supabase`, selected by `STORAGE_BACKEND`. Render (and staging) set `supabase`. Tests stay offline, and local dev needs no cloud credential.
- **B — Supabase everywhere** (local dev on `rag-staging`): one code path, but every local upload hits the network, tests still need a fake, and a dev machine holds a Storage key.
- **Recommendation: A.**

## Plan

New dependencies (**need approval**):
- `pgvector==0.4.x` (the official pgvector-python; SQLAlchemy `HALFVEC` type, bind/result processing, reflection for Alembic). Small, no transitive dependencies beyond numpy.
- `boto3` (Decision 5B only).
- Removed if Decision 4A holds: `faiss-cpu`, `rank-bm25`, `tqdm`.

### Checkpoint 1 — schema and Postgres-only suite (Decision 2A), ~10 files
- `backend/app/db/models/document_chunk.py` (new): `DocumentChunkRow` with `HALFVEC(3072)`, `tsv` `Computed(... persisted=True)`, `JSONB` metadata, and the three indexes in `__table_args__`.
- `backend/app/db/models/{document,chat_session,message,failed_query,concept_map}.py`: add `ondelete="CASCADE"` / `"SET NULL"`; `Document.file_size`.
- `backend/app/db/models/__init__.py`: import the new model.
- `alembic/versions/<rev>_document_chunks_and_fk_rules.py`: autogenerated against the local Postgres, then reviewed by hand. It contains `SET LOCAL statement_timeout` before the HNSW build, drop + create of each FK by its convention name, and a downgrade that restores the baseline FKs.
- `alembic/env.py`: register `halfvec` for reflection, and drop the SQLite batch mode.
- `backend/app/core/config.py`, `backend/app/db/session.py`: Postgres only (no SQLite default or branch).
- `backend/tests/conftest.py`: require `TEST_DATABASE_URL`.
- `backend/tests/test_migrations.py`: run on the suite database and leave it at head. Add a check of the new FK rules (`confdeltype`) and that the HNSW / GIN indexes exist.
- `requirements.in` / `requirements.txt` (`pgvector`).

### Checkpoint 2 — stores, indexing service, retrieval wiring, ~10 files
- `backend/app/db/repositories/chunks.py` (new): `insert_many`, `delete_for_documents`, `count_by_document`, `vector_search` (`1 - (embedding <=> :q)` as score, user in `WHERE`), `keyword_search` (OR-ed tsquery, `ts_rank_cd`). They return plain dicts in today's metadata shape (`id`, `text`, `file_name`, `page_num`, `chunk_index`, `doc_type`, `extra_metadata.document_id`, `user_id` as a string).
- `backend/app/retrieval/pg_stores.py` (new): `PgVectorStore` (embed the query, then `chunks.vector_search`) and `PgKeywordIndex`, each opening a short session from an injected `sessionmaker`.
- `backend/app/retrieval/retrieval_service.py`: take `embedding_service`, `vector_index`, `keyword_index` (Protocols) instead of `IndexBuilder` / `BM25KeywordIndex`. The fusion logic is unchanged.
- `backend/app/services/indexing_service.py` (new): `IndexingService.index_document(doc, file_bytes_or_path)`, which builds chunks (ingestion), embeds them (retrieval `EmbeddingService`), and inserts them in one transaction. It skips empty-text chunks (B10, already Day 16's item; a one-line filter, or I'll leave it if you prefer).
- Delete `backend/app/ingestion/indexing_pipeline.py`.
- `backend/app/services/container.py`, `services/caches/semantic_cache.py` (takes the `EmbeddingService`).
- Tests: `test_confidence.py`, `test_retrieval_switches.py`, `test_semantic_cache.py`, `test_app_factory.py` (constructor names). `test_vector_score_direction.py` is rewritten for pgvector, so it checks real cosine order on Postgres. New `test_chunk_store.py`: user isolation in `WHERE`, k results for a minority user (I1), keyword OR-semantics, document-delete cascade.

### Checkpoint 3 — I5, I6, account deletion, UI, ~10 files
- `backend/app/services/document_service.py`: `register_upload` returns `(doc, status)` with `status ∈ {new, changed, unchanged}`. Unchanged requires the same hash and chunk count > 0. Changed deletes the previous version's chunks.
- `backend/app/api/routes/documents.py`:
  - `/upload` skips indexing and the bump when unchanged, and returns `status`, `version`, `chunks_indexed`.
  - `DELETE` removes every version of that file name (rows → chunks cascade), then bumps `doc_version`.
  - `GET /documents` returns `file_size` from the row, plus `chunks`.
- `backend/app/services/account_service.py`, `api/routes/users.py`: no index tombstones. Chunks are counted and deleted with the user's rows (the cascade is the safety net), and `index_entries_removed` → `chunks`.
- Frontend `pages/DocumentsPage.js`, `components/DocumentList.js`: an upload notice (`new` → "Indexed N chunks", `changed` → "New version vN indexed", `unchanged` → "Already indexed — nothing to do"), and a "Not searchable yet — re-upload" badge when `chunks === 0`.
- Tests: `test_document_service.py` (three statuses, v0.2.2 row with no chunks → reindexed), `test_account_service.py`, `test_api_smoke.py` (upload → delete → chat never cites it). Frontend test for the notice states.

### Checkpoint 4 — Supabase Storage (Decisions 5, 6), ~8 files
- `backend/app/ingestion/upload_storage.py` → `FileStorage` protocol:
  - `LocalFileStorage` (today's directory, containment check kept).
  - `SupabaseS3Storage` (put, get to a temp file, delete, delete prefix).
  - Object key `uploads/{user_id}/{uuid}{ext}`.
- `backend/app/core/config.py` + `.env.example`: `STORAGE_BACKEND`, `STORAGE_BUCKET`, `SUPABASE_S3_ENDPOINT`, `SUPABASE_S3_REGION`, `SUPABASE_S3_ACCESS_KEY_ID`, `SUPABASE_S3_SECRET_ACCESS_KEY` (SecretStr). Validation: `supabase` requires all of them.
- `/upload`: the hash comes from the bytes first; the object is uploaded only for new / changed (or when the existing row's object is missing), and the row is committed after the object.
- Delete paths remove objects after the commit; failures are logged.
- `container.py` builds the storage.
- Tests: a fake S3 at the boto3 boundary (no network), plus the local backend's containment tests (existing `test_upload_storage.py`).
- Owner actions (no code): create private buckets `rag-prod` and `rag-staging`, generate an S3 access key, and set Render env vars at the next release (Day 17).

### Checkpoint 5 — E4 on Postgres, verification, docs
- `backend/eval/retrieval/{corpus,runner,__main__}.py`: the `rag_eval` guard (Decision 3), an eval user row, and indexing through `IndexingService` with `CachedEmbeddingService` (0 API calls expected under 1B).
- Run `baseline`, `vector_only`, `keyword_only` with `--label pgvector`, and compare with the 2026-11-09 `after-b8` files.
- Decision 4: delete the FAISS / BM25 modules and dependencies, and regenerate the lock (in `python:3.11-slim`, as its header says).
- `docs/architecture/layout.md` (the two exceptions closed), CLAUDE.md Key Commands for `rag_eval` (only with your OK, since CLAUDE.md edits are yours), `.env.example`.
- Manual checks (Verification), brief Outcome, post material, learning notes.

## UI integration

| Backend change | Frontend | What the user sees | States |
|---|---|---|---|
| `/upload` returns `status` (`new` / `changed` / `unchanged`), `version`, `chunks_indexed` | `pages/DocumentsPage.js` (`handleUpload`), new notice banner next to the error banner | "Indexed 42 chunks from notes.pdf", "New version v2 of notes.pdf indexed", "notes.pdf is already indexed — nothing changed" | loading: existing `uploading` spinner; error: existing banner; empty: n/a |
| `GET /documents` gains `chunks`; `file_size` now from the row | `components/DocumentList.js` | size shown again on Render; amber "Not searchable yet — re-upload" badge when `chunks === 0` | loading / empty already exist |
| `DELETE /documents/{id}` removes chunks + file (I5) | `DocumentsPage.js` (already refetches) | the row disappears (as today), and answers stop citing it from the next message (`doc_version` bump invalidates L1 / query / semantic caches) | error: existing banner |
| `/user/delete` summary field renamed (`index_entries_removed` → `chunks`) | `components/AccountSettingsModal.js` — check whether it renders the summary; update if so | unchanged wording | — |

Backend-only, with no user-visible change:
- the Alembic revision and FK rules (schema);
- the `services/` indexing move (refactor);
- the Postgres-only suite (tests);
- the Storage backend (file location; the user sees only that files survive restarts);
- E4 (eval).

## Verification

- **Tests (on Postgres, `rag_test`):**
  - `test_migrations` (head, no diff, FK `confdeltype` = `c` / `n`, HNSW + GIN exist, downgrade base);
  - `test_chunk_store` (isolation, minority user still gets k (I1), OR keyword semantics, cascade on document delete and on user delete);
  - `test_document_service` (new / changed / unchanged, v0.2.2 row without chunks);
  - `test_api_smoke` (upload → chat cites it; delete → never cited; unchanged re-upload → no `doc_version` bump);
  - `test_account_service`;
  - the whole suite: `python -m pytest -q` with `TEST_DATABASE_URL`;
  - frontend `npm test -- --watchAll=false` and `npm run build`.
- **`EXPLAIN ANALYZE`** of the vector query for a small user and a large user (locally, with the eval corpus): record which plan (btree + sort, or HNSW + iterative scan). Set `hnsw.iterative_scan` only if HNSW is chosen and returns fewer than k.
- **E4 before / after.** Before: `2026-11-09-*-after-b8.md` (Hit@5 0.909, MRR@5 0.801 hybrid). After: the same three configs on pgvector + FTS. Recorded in the tracker's Notes for I4 / I2, with the keyword-only delta called out (BM25 → `ts_rank_cd`).
- **Manual, local Docker stack:**
  - upload a demo PDF and ask a question → it is cited;
  - `docker compose restart backend`, ask again → still cited (I4);
  - delete it, ask again → not cited, and the object or file is gone (I5);
  - re-upload the same file twice → "already indexed", and the chunk count is unchanged (I6).
- **Staging Storage:** one manual run with `STORAGE_BACKEND=supabase` against `rag-staging` (upload, restart, retrieve, delete), with the venv pointed at `rag_staging` for that session.
- **`alembic upgrade head` + `alembic check`** on local `rag` and on Supabase `rag_staging`. Production gets it at the Day 17 release.

## Risks & open questions

1. **Day size.** This is the largest day so far (~45 file operations over 5 checkpoints). If it runs long, Checkpoint 4 (Storage) is the natural cut to Day 16. Say if you'd rather plan that split now.
2. **Production between Day 15 and the Day 17 release.** Nothing changes in production until v0.3.0, so the Render env vars (Storage, `STORAGE_BACKEND`) are set during that release. v0.2.2 rows will show "Not searchable yet" until re-upload or Day 16's reindex. The reindex can only use files that exist, and Render has none, so those users must re-upload. Day 16/17 should say so in a UI notice or the release notes.
3. **`ts_rank_cd` has no IDF.** Keyword-only quality may drop, so the parity rule in Decision 4 decides deletion. If keyword-only drops but hybrid holds, I'll record both and still treat it as parity (hybrid is what ships).
4. **HNSW + filter plan.** Covered in Verification. `hnsw.iterative_scan` as a role setting would need one owner-run `ALTER ROLE` on Supabase. `SET LOCAL` per query costs a round trip (CO6), so the role setting is preferred if needed.
5. **Alembic and `halfvec` reflection.** Without registering the type, `alembic check` may report a type diff on every run. Registering it in env.py is in Checkpoint 1, and `alembic check` must say no diff.
6. **`statement_timeout` 60 s on the roles.** The HNSW build in the migration is on an empty table everywhere today, but `SET LOCAL statement_timeout = '10min'` goes in the revision anyway.
7. **Never edit the baseline revision** (it ran on Supabase). The FK changes are drop + create in the new revision.
8. **Storage key scope (Decision 5).** S3 access keys reach every bucket in the project. Today that is only `rag-prod` and `rag-staging`: the owner confirmed (2026-11-14) that the other app doesn't use Supabase Storage and the project has no buckets yet. **This changes if the other app ever adds buckets:** the key would then reach them too, so revisit the credential then. Never log the key or the endpoint.
9. **`DELETE /documents/{id}` removing all versions** is a behaviour change. Today only the active row goes, and older versions silently linger with their files. If you prefer "delete this version only, re-activate the previous one", say so.
10. **Semantic-cache replay (CO5 finding).** A hit replays stored `sources`, but entries are matched on the exact `doc_version` (`semantic_cache.py:84`), so the bump on delete is enough. No change needed.
11. **`dev.ps1 test`** must point the container's test run at the compose Postgres (`rag_test`) after Decision 2A. It is in Checkpoint 1's scope (one line in the override or script).
12. **Found in Checkpoint 2: `concept_map_nodes.map_id` had no ON DELETE rule.**
    - With every `user_id` FK cascading, a user delete cascades to `concept_maps`, whose nodes then blocked it (`ForeignKeyViolation`, found by `test_account_service`'s new schema-cascade test).
    - The timeline's goal ("deleting a user can't leave or block on child rows whatever the code path") needs it, and Day 14's list missed it.
    - Fixed by its own revision `500c410270f5`: `9e72706d7449` had already run on `rag_staging` and is never edited.
13. **`DELETE /user/delete`'s `index_entries_removed` keeps its name** (in the account-deletion summary). It now counts `document_chunks` rows. The frontend doesn't render it (only the test fixtures name it), so renaming it to `chunks` would be churn for no user-visible gain. This replaces the brief's UI-table row.
14. **`PgChunkSearch` is one class, not `PgVectorStore` + `PgKeywordIndex`.** The owner's CO6 change requires one session per `hybrid_retrieve`, so one object runs both queries in one session behind a `ChunkSearch` protocol.
15. **`POST /search` (`semantic_search`) now returns cosine similarity**, which ends B8's residual. `subject` / `file_type` filters are applied in SQL (jsonb `@>`), not after the search. The endpoint still has no frontend caller (unchanged since Day 11).
16. **A failed query embedding now fails the request** instead of searching with a zero vector. For chat that is a 500 before streaming starts (steps 1–6), like any retrieval failure. *Superseded in Checkpoint 3:* the owner chose to degrade to keyword-only search instead.
17. **Found in Checkpoint 4's live check: Supabase's S3 endpoint rejects `DeleteObjects` from boto3 1.44.3 with `InvalidRequest`.**
    - It failed even for one key, and also with `request_checksum_calculation="when_required"`.
    - Put, HeadObject, GetObject, DeleteObject and ListObjectsV2 all work.
    - **Suspected cause, unconfirmed:** boto3 ≥ 1.36 sends a CRC32 checksum on `DeleteObjects` where older clients sent `Content-MD5`, and Supabase's S3 layer expects the latter (or doesn't implement batch delete).
    - **Decision (owner, option A):** `delete_prefix` lists the keys and deletes them one at a time with `DeleteObject`. The untested checksum settings were reverted. The fake S3 client has no `delete_objects`, so reintroducing batch delete fails a test.
    - **Cost:** one request per file, on account deletion only.
    - **Revisit** if a boto3 or Supabase release fixes it, or if a user's file count makes account deletion slow.

## Outcome

_Written during the day; completed at the end._

### Checkpoint 1 — schema, Postgres-only suite (commit `de45311`, PR #21, CI green)

- **`rag_staging` migrated** (owner's request, 2026-11-14): `7cb8829683ab` → `9e72706d7449` → `500c410270f5`, and `alembic check` reports no diff.
  - MCP catalog check: `document_chunks.embedding` is `extensions.halfvec(3072)`; there are HNSW (`extensions.halfvec_cosine_ops`), GIN (`tsv`) and btree `(user_id, document_id)` indexes, plus both CHECKs.
  - FK rules: every `user_id` is `c`, `failed_queries.session_id` is `n`, `messages.session_id` is `a`.
  - pgvector 0.8.2 is in `extensions`, and no permission or extension-schema issue came up.

### Checkpoint 2 + E4 parity (2026-11-14)

**E4 on pgvector + Postgres full-text vs the FAISS + BM25 baseline (`2026-11-09-*-after-b8`).**
- Same dataset (`retrieval_v1`, 55 answerable questions) and same cached vectors: halfvec(3072) keeps the cache key, so the runs made 0 embedding API calls.
- Corpus: 419 chunks. The HPC deck's 3 blank chunks are now skipped (B10).

| Config | Hit@5 | MRR@5 | Questions that flipped (Hit@5) |
|---|---|---|---|
| vector_only | 52/55 → 52/55 (0.945) | 0.833 → 0.830 (−0.003) | none; one rank move (g-029 2→3) |
| **baseline (hybrid)** | **50/55 → 50/55 (0.909)** | **0.801 → 0.806 (+0.005)** | lost g-012, gained g-021 |
| keyword_only | 47/55 → 49/55 (0.855 → 0.891) | 0.602 → 0.559 (−0.043) | lost g-012; gained g-015, g-040, g-042 |

- **Parity rule (owner): met.**
  - vector_only is within 1 question (0 flips).
  - Hybrid lost 1 question, the most allowed, and gained 1. MRR is +0.005, so no loss.
  - keyword_only finds more pages but ranks them lower (`ts_rank_cd` has no IDF); recorded, and the judgement is on hybrid.
- **Decision 4A carried out:** `vector_store.py`, `index_builder.py` and `keyword_index.py` are deleted, and `faiss-cpu` and `rank-bm25` are out of `requirements.in`. The regenerated lock drops exactly those two. `tqdm` stays in the lock as another package's dependency, but is no longer a direct one.
- **Query plans, `rag_eval` (419 chunks, one user):**
  - The planner's default is a **Seq Scan + exact sort**; at this size HNSW isn't chosen.
  - With seq scan, bitmap scan *and* sort turned off, it uses `Index Scan using ix_document_chunks_embedding_hnsw` (10 rows read). Seq and bitmap off alone still picked the `(user_id, document_id)` btree plus a sort.
- **HNSW recall@10 vs exact search** (index scans off): **1.000** (61/61 queries identical, none short). The default plan is also 1.000, since it *is* exact.
- **`hnsw.iterative_scan` was not set.** With one user, the filter never discards anything, and nothing measured today needs it. Revisit when a large user's filtered query returns fewer than k rows.
- **CO6, round trips per request after today** (local, fake Gemini; counts statements + BEGIN + COMMIT/ROLLBACK + pool pre-pings):
  - `/me` = **4**: ping, BEGIN, SELECT, ROLLBACK. Day 14 counted 3, without the ping.
  - **A chat turn = 33**: 6 pings, 6 BEGIN, 15 statements, 4 COMMIT, 2 ROLLBACK.
  - Retrieval's share is 5: one session holding both search queries.
  - At ~63 ms each (Render Singapore → Supabase Mumbai), that is ≈ 2.1 s of network per turn. This is Day 16's before number. Its targets are the 6 pings (`pool_pre_ping`) and the 6 separate transactions.
  - Recorded in the tracker's CO6 notes and the Day 16 timeline bullet (owner, replacing "10–15").

### Checkpoint 3 — I5, I6, query-embedding degradation, UI (2026-11-14)

- **A failed query embedding degrades instead of failing the chat** (owner's change; replaces Risk 16).
  - `hybrid_retrieve` logs the error and runs keyword-only search for that query (`ChunkSearch.search(None, …)` skips the vector half). Web search runs as usual, though it embeds too, so in a full outage it adds nothing.
  - A degraded result is not written to the L1 cache.
  - `SemanticCache.lookup` treats the failure as a miss. `store` skips it too: it runs after the answer has streamed, and raising there would break the stream's end.
  - A failed embedding during **upload** still returns 502.
- **I6 — `register_upload` returns a `RegisteredUpload(document, status)`.**
  - `new` and `changed` index the file. `changed` makes the previous version inactive and deletes its chunks in the same transaction.
  - `unchanged` (same hash, chunks exist) skips indexing and the `doc_version` bump.
  - **`reindexed`**, a fourth status beyond the brief: same hash but no chunks (a v0.2.2 row, or a failed earlier indexing). It indexes again, so those files can always be made searchable.
  - The upload stores `file_size`.
- **I5 — `document_service.delete_document`** deletes every version of the file name for that user, their chunks (ON DELETE CASCADE, counted for the response) and the user's own stored files, after the commit. A failure there is logged, never surfaced. The route then bumps `doc_version`.
  - The response adds `versions_deleted` and `chunks_deleted`.
  - Pre-G7 flat paths are left alone, because another user's row may share them.
- **`GET /documents`:**
  - `chunks` comes from one grouped query (`count_by_document`).
  - `file_size` comes from the row, falling back to the local file for older rows.
  - `created_at` is now returned. It was hard-coded to `None` with a stale "no timestamp field" comment, although the column has always existed, so the list showed "Recently uploaded" for every file.

### Checkpoint 4 — uploaded files in Supabase Storage (2026-11-14)

- **`ingestion/upload_storage.py`:** a `FileStorage` protocol (`put`, `exists`, `local_copy`, `delete`, `delete_prefix`) with two implementations:
  - `LocalFileStorage`: keys are paths under the working directory, as before.
  - `S3FileStorage`: a boto3 client against Supabase's S3 endpoint, path-style addressing, SigV4.
  - `Document.file_path` holds the key `uploads/{user_id}/{uuid}{ext}`.
  - `check_key` refuses anything outside `uploads/` by component (traversal, absolute, `uploads2/`, drive letters). Keys written on Windows (backslashes) are normalized.
  - `local_copy` yields a file the parsers can read: the stored file itself, or a temporary download that keeps the extension.
  - Backend failures become `StorageError`, whose message names the error type only, never credentials.
- **Settings:** `STORAGE_BACKEND` (`local` by default, or `supabase`), `STORAGE_BUCKET`, `SUPABASE_S3_ENDPOINT`, `SUPABASE_S3_REGION`, `SUPABASE_S3_ACCESS_KEY_ID`, `SUPABASE_S3_SECRET_ACCESS_KEY` (SecretStr). `supabase` requires all five; documented in `.env.example`. The tests pin `STORAGE_BACKEND=local`, so `.env` can never point them at a real bucket.
- **Upload order:**
  1. The hash comes from the bytes before anything is stored.
  2. A new or changed file: the object is written, then the row is committed. If the commit fails, the object is deleted.
  3. An identical re-upload stores nothing, unless the row's file is gone or is a legacy flat key; then a fresh copy is stored and the row re-linked.
  4. Indexing reads through `local_copy`. A storage failure on write is a 503 ("Could not store the file right now"); on read it's the existing 502.
- **Delete paths:** `delete_document` and `delete_user_account` remove objects through the storage after the commit (`delete_prefix` for the user's whole prefix, plus unshared legacy keys). Failures are logged. On S3, `delete_prefix` lists the keys and deletes them one by one (Risk 17: Supabase rejects `DeleteObjects`).
- **Not done, as decided:** the copy script for existing local files (Scope 7).
- **Deleted as dead code:** `ingestion/file_hash.py`, since the hash now comes from the bytes.
- **Dependencies:** `boto3==1.44.3` (approved). The lock adds `boto3`, `botocore`, `jmespath` and `s3transfer`, and no other version moved.
- **Tests:** 325 pass (299 before).
  - Both backends run one shared contract test against a fake S3 client that raises real botocore errors: keys, put / read / delete, prefix delete, errors.
  - The document-service flow also runs end to end on the fake bucket.
  - The config tests check that `supabase` needs every S3 setting and that the secret is masked.
- **Live check on `rag-staging`:**
  - **Setup:** the owner created private buckets `rag-staging` and `rag-prod` and an S3 access key, and put the five values in `.env` without `STORAGE_BACKEND`. The check ran through the app's own `build_file_storage()`, with `STORAGE_BACKEND=supabase` set for that one process.
  - **First run:** exists (False before, True after), put, a `local_copy` round trip (`.pdf` suffix, identical bytes) and delete (True, then False) passed. `delete_prefix` failed (Risk 17).
  - **After option A:** the same steps plus `delete_prefix` on a 2-object test prefix passed (2 deleted, **0 left**).
  - Test objects lived only under `uploads/0/`, a user id that never exists; the earlier run's two leftovers were removed. No configuration value was printed.
