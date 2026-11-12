# Day 14 — Migrate the data off SQLite → production on Postgres (release v0.2.2)
Date: 2026-11-13 · Phase 5 — Postgres + pgvector data layer · Items: none (T2 is Done since Day 13; today puts it in production)
Branch: feature/day14-sqlite-to-postgres

## Scope
Rewritten 2026-11-13 after the owner's answers. Render has **no persistent disk** (free plan: "Disks are not supported"), so production's SQLite is wiped on every deploy, restart and idle spin-down, and there is nothing to migrate. Production and local dev both **start empty on Postgres**.

1. **Copy script — dropped (owner).** No production data exists, and local data doesn't matter. The notes a copy would need are kept under "Reference — if a SQLite → Postgres copy is ever needed" at the end of this brief. Nothing is built for it.
2. **Render disk check — done (owner): none.**
3. **The whole pytest suite runs on Postgres in CI**, against a `_test` database. Local runs stay on SQLite by default and can opt into Postgres.
4. **Local dev switches to the compose Postgres** (Docker backend and venv), starting empty.
5. **Gap found while re-planning:** once rows persist but files don't, re-uploading an identical file fails on Render. The fix is a small `register_upload` change (Decision 2).
6. **Release v0.2.2 at the end of the day:**
   - `develop` → `master`, carrying Days 13–14 only
   - Render's `DATABASE_URL` / `DATABASE_SCHEMA` are set *before* the deploy
   - the image's CMD runs `alembic upgrade head` on `rag`
   - then a live check (register, chat, feedback, survive a restart), the latency Render → Supabase measured before and after, and a written rollback
7. **Verify:**
   - the suite passes on Postgres in CI
   - locally and on Render, an account survives a restart with its sessions
   - **Changed from the timeline:** "row counts match" is moot, since nothing is copied

## Current behavior
- **App database:** `settings.DATABASE_URL` defaults to `sqlite:///<repo>/backend/data/app.db` (`backend/app/core/config.py:18,67`).
  - A Postgres URL must be `postgresql+psycopg://` and needs `DATABASE_SCHEMA` (validator `config.py:74-85`).
  - The engine comes from `build_engine` (`db/session.py:21`), with `pool_pre_ping=True`: one extra round trip per connection checkout (`session.py:34`).
- **Startup:**
  - the image's CMD runs `alembic upgrade head && exec uvicorn` (`Dockerfile`, last line)
  - the lifespan refuses a database not at head and a role whose `current_schema()` isn't `DATABASE_SCHEMA` (`db/migrations.py:37-74`)
- **Production (v0.2.1 on `master`):**
  - SQLite with a hard-coded path. `master`'s `config.py` has no database setting, so setting `DATABASE_URL` on Render today changes nothing.
  - No disk: every deploy, restart or 15-minute idle spin-down starts from an empty database. Accounts disappear, and so do the uploaded files and the in-memory FAISS/BM25 indexes (I4).
  - Supabase `rag`: empty, no `alembic_version` (Day 13).
- **Local:**
  - `.env` sets no `DATABASE_URL`.
  - Compose's backend has no `DATABASE_URL` (`docker-compose.yml:15-28`), so it uses SQLite in the `data` volume.
  - The compose `postgres` service's `rag` is at head and empty (Day 13).
- **Tests:**
  - `conftest.py:96` forces a temporary SQLite `DATABASE_URL`, drops `DATABASE_SCHEMA` (`:100`) and runs `alembic upgrade head` (`:135`).
  - `test_repositories.py:33` switches to Postgres on `TEST_POSTGRES_URL`.
  - `test_account_service.py:53`, `test_document_service.py:26` and `test_migrations.py:24` build their own SQLite engines on purpose. In-memory engines, and Alembic downgrade on a temp file, stay SQLite.
- **CI** (`ci.yml:31-117`): service DB `rag` + init script, then `alembic upgrade head` + `alembic check`, then `test_repositories.py` on Postgres. The full `pytest -q` runs on SQLite.
- **Init script:** `scripts/postgres/init-rag-schema.sh` is not re-runnable. `CREATE ROLE rag_app` / `CREATE SCHEMA rag` fail the second time, so it can't set up a second database (`rag_test`) in a volume that already has the role.
- **Uploads:** `services/document_service.py:60-91` (`register_upload`). On an identical re-upload, the existing row wins. If that row's path is inside the user's directory, the **new copy is deleted** (`:79-81`) and indexing then runs on the row's old path.
- **Auth:** the JWT `sub` is the user's **email** (`api/routes/auth.py:38,153`), resolved with `users_repo.get_by_email` (`api/deps.py:35-40`).
- **Redis on Render:**
  - `REDIS_URL` only, so query, web and semantic caches share DB 0 (CLAUDE.md, Environment Variables)
  - `semantic_cache:{user_id}` has no TTL
  - `query_cache` keys hash `user_id::doc_version::query`

## Why it matters
- **Production loses every account on every idle spin-down.** On the free plan that happens after 15 minutes without traffic. "Users log in and see their sessions" is impossible today. With Postgres, accounts, sessions, messages, feedback and concept maps survive deploys and restarts.
- **Suite on SQLite only:** Postgres-only failures (strict types — `integer = text` was found Day 13 —, case-sensitive `LIKE`, `NULL` ordering, "current transaction is aborted" after an error, sequences that never reuse ids) reach production first. Today's repository tests cover 11 queries; the API smoke tests cover every route.
- **Re-upload after a restart (new with persistence)** — the order of events:
  1. On v0.2.2, a user uploads `notes.pdf`. The row is kept in Postgres; the file is written to `uploads/5/<uuid>.pdf` on Render's ephemeral disk.
  2. Render spins down. The file and the FAISS vectors are gone; the row isn't.
  3. The user sees `notes.pdf` in the list, but chat can't find it. They re-upload the same file.
  4. `register_document` matches the hash and returns the old row. Its path is inside `uploads/5/`, so the **new** copy is deleted, and indexing opens the old, missing path.
  5. The upload fails, every time, for that file.

  Before today this couldn't happen, because the row vanished together with the file.
- **Stale Redis caches at the cutover:** Postgres ids start at 1 again. `semantic_cache:1` written for a SQLite-era user 1 (no TTL) would be served to the first new Postgres user if the cache entry's `doc_version` matches, which is likely at 0 or 1. That is someone else's answers. Flushing the cache DBs at the cutover closes this. From then on Postgres never reuses ids, which also ends the B1 residual on production.
- **Latency:** Supabase is in `ap-south-1` (Mumbai). Every request that touches the database now pays network round trips instead of a local file read:
  - one round trip for `pool_pre_ping` on checkout, plus one per statement, plus one per `COMMIT`
  - a chat turn runs roughly 8–12 statements and commits

  If Render is in Oregon (~220–250 ms RTT to Mumbai), that could add 1–3 s per chat turn. From Singapore (~35–60 ms) it is small. It has to be measured, not guessed: the Render region is checked first, and the before/after numbers decide whether a follow-up is needed (Risks 3).

## The concept

### Environment-driven cutover (12-factor config)
- The code that talks to Postgres is identical in every environment. *Which* database is a deploy-time setting (`DATABASE_URL`, `DATABASE_SCHEMA`).
- The cutover is therefore a configuration change plus a deploy, not a code branch. The rollback is the reverse configuration change.
- **The ordering rule:** configuration that the new code needs must exist **before** the new code deploys. If v0.2.2 deployed without `DATABASE_URL`, it would silently start on the SQLite default: an empty database again, migrated and stamped, with nothing failing loudly.
- Setting the variables early is harmless here, because v0.2.1 doesn't read them.

### Migrate-on-start
- The container runs `alembic upgrade head` before the web server (`&&`).
- On a fresh schema, that creates every table and `alembic_version`. On later starts it is a no-op: one round trip to read the version.
- It is safe with **one** instance. With several replicas, two could migrate at once. Production systems then run migrations as a separate release step: a Render pre-deploy command, a Kubernetes Job, or a CI job (Days 21–22).
- If the migration fails, `&&` keeps uvicorn from starting. Render's health check fails, and the deploy is marked failed instead of serving a half-migrated schema.

### Connection cost across regions
- A query to a remote Postgres costs at least one network round trip (RTT). The application's latency is roughly *(round trips per request) × RTT* plus server time.
- **Levers, cheapest first:**
  1. **Co-locate** app and database (same region): usually the only lever that changes the order of magnitude.
  2. **Fewer round trips:**
     - drop `pool_pre_ping` (a ping per checkout) in favor of `pool_recycle` below the pooler's idle timeout, accepting a rare failed request on a dead connection
     - batch statements, and commit once per request instead of after each insert
     - eager-load instead of N+1
  3. **Persistent pooled connections:** already in place, so no TCP + TLS + auth handshake per request (that alone is 3–4 RTTs).
- **Pooler modes:**
  - Supabase's **session pooler** (port 5432) keeps one server connection per client connection, and supports prepared statements and `SET`, so psycopg works unchanged.
  - The **transaction pooler** (6543) multiplexes better, but breaks session state.
  - On a free Render instance (IPv4 only), the session pooler is the documented path; the direct connection is IPv6.

### Measuring a remote dependency without instrumenting it
- **Differential timing:** time an endpoint that does no I/O (`/health`) and one that does exactly one authenticated DB lookup (`/me`), from the same client, many times. Take medians: network jitter is long-tailed, and means lie.
- `median(/me) − median(/health)` approximates the server-side cost of auth + pre-ping + one query. The client-to-Render path cancels out.
- Before (SQLite, sub-millisecond reads) vs after (Postgres) isolates what the database move added. Warm the instance first: a free Render instance's cold start (~30–60 s) would swamp everything.
- A chat turn (`/chat/stream`, time to the `metadata` frame) shows the end-to-end effect, with Gemini noise.
- **Exact alternative:** a `Server-Timing` header from SQLAlchemy event hooks (Decision 3).

### Rollback paths
1. **Config rollback:** unset `DATABASE_URL` / `DATABASE_SCHEMA` → Render redeploys → the CMD migrates a fresh SQLite file → the app runs as before v0.2.2 (ephemeral, empty). Postgres data stays in Supabase, untouched, ready for a switch back.
2. **Code rollback:** Render's "Rollback" to the v0.2.1 deploy, which ignores the variables. Use it if v0.2.2's code itself misbehaves.

**Forward-only data:** rows written to Postgres during the incident don't follow a rollback to SQLite. With an empty production that costs nothing today, but it is the reason real systems prefer fixing forward once users exist.

### Persistence boundaries
- Moving one store to durable storage while others stay ephemeral creates **dangling references**: rows that point at files or vectors that no longer exist.
- The robust fix is to move them all (files to Supabase Storage on Day 15, chunks to pgvector on Day 15–16). Until then, code that follows a reference must tolerate it being gone (Decision 2).

### Test databases
- **Same engine as production:** "works on SQLite" is not evidence for Postgres.
- **Disposable:** reset at the start of every run (`downgrade base` + `upgrade head`), which also exercises the downgrade path.
- **Guarded:** refuse any database whose name doesn't end in `_test`, so a stray `TEST_DATABASE_URL` can never wipe dev or Supabase.

## Decisions

### Decided by the owner (2026-11-13)
- **Decision 2 → A** (re-link on re-upload) and **Decision 3 → A** (differential timing; `/health` is the network baseline, `/me` and chat turns are the DB-backed numbers). Approved 2026-11-13.
- **Copy script:** not built. Production and local start empty; reference notes kept at the end of this brief.
- **Production timing:** production switches to Postgres with release **v0.2.2 today**, not on Day 17.
- **Test suite (was Decision 3) — A:**
  - CI runs the full suite on Postgres (`rag_test`)
  - a local `pytest` stays on SQLite by default; `TEST_DATABASE_URL` opts in
  - conftest refuses a database not named `*_test` and resets it each run
- **Local app (was Decision 4) — A:** the Docker backend and the venv switch to the compose Postgres (`rag`, at head, empty).
- **Keep:** the re-runnable init script and the `_test` database for CI.

### 1. Render region vs Supabase Mumbai
**Settled: Render is in Singapore** (owner, 2026-11-13). Singapore ↔ Mumbai is expected at ~50–70 ms per round trip. A `/me` costs about 2 round trips (pre-ping + query); a chat turn about 8–12 statements and commits. So expect roughly +100–150 ms on `/me` and +0.4–0.8 s on a chat turn. The measured numbers are compared against this. If they are far worse, the options in Risks 3 go to you.

### 2. Re-upload when the row survives but its file doesn't
- **A — Re-link to the new copy:**
  - In `register_upload`, if the existing row's file **no longer exists on disk**, move the row to the freshly stored copy (the same branch the legacy flat-path case already takes) instead of deleting the new copy.
  - One condition plus one test in `test_document_service.py`. Re-uploading restores the document after a Render restart. The `doc_version` bump and re-indexing already happen on every upload.
- **B — A + mark rows whose file is missing:**
  - also flag them in `GET /documents` and show a "re-upload needed" badge in the documents list (backend + UI, per the owner's rule)
  - more work for a state that Day 15 (Supabase Storage) removes in two days
- **Recommendation: A.** It fixes the hard failure (an upload that can never succeed) with the smallest change. The "listed but not searchable after a restart" state is I4, already true for indexes today, and goes away on Day 15–16. The release notes say so.

### 3. How to measure DB latency Render → Supabase
- **A — Differential timing from the client, no code:**
  - a throwaway script in my scratchpad (not committed), standard library only
  - 5 warm-up calls, then 30 × `GET /health` and 30 × `GET /me` with a test account's token, plus 5 chat turns timed to the `metadata` frame
  - medians and p90; run once on v0.2.1 (SQLite) before the release and once on v0.2.2 after
  - Approximate, since client-to-Render jitter is in both legs, but it is the number users feel, and it needs no change to production code.
- **B — A `Server-Timing: db;dur=…` response header:**
  - SQLAlchemy `before/after_cursor_execute` events sum DB time and statement count per request; a middleware writes them out
  - exact, and also counts round trips per endpoint
  - but it is new production code (and arguably an observability feature for Days 23–25 / O1), added on a release day
- **Recommendation: A** today. If the numbers show a problem, B is the first tool for diagnosing it.

## Plan

### Checkpoint 1 — the suite on Postgres (4 files)
- `scripts/postgres/init-rag-schema.sh`: re-runnable.
  - `CREATE ROLE rag_app` only if it's missing (`DO` block, password still from the variable)
  - `CREATE SCHEMA IF NOT EXISTS rag AUTHORIZATION rag_app`
  - `CREATE EXTENSION IF NOT EXISTS` as today
  - Compose behavior on an empty volume is unchanged.
- `backend/tests/conftest.py`:
  - `TEST_DATABASE_URL` set → use it with `TEST_DATABASE_SCHEMA`, and refuse unless the database name ends in `_test` (and the backend is Postgres)
  - reset with `alembic downgrade base` + `upgrade head` before the run
  - unset → the temporary SQLite file, as today
  - Docstring updated.
- `backend/tests/test_repositories.py`: read `TEST_DATABASE_URL` (one variable for the suite) instead of `TEST_POSTGRES_URL`. The Postgres branch reuses the already-migrated database, as now.
- `.github/workflows/ci.yml` (`backend` job, **job names unchanged**, branch protection):
  - service `POSTGRES_DB: rag_test`
  - the init script for `rag_test`
  - `alembic upgrade head` + `alembic check` kept as the explicit Day 13 step
  - the separate repository step folded into one `pytest -q` with `TEST_DATABASE_URL` / `TEST_DATABASE_SCHEMA=rag`
- **Local run:**
  - `createdb rag_test` in the compose Postgres plus the init script, via `docker exec` as the superuser
  - the full suite with `TEST_DATABASE_URL` → all pass
  - the default SQLite run → still 269
  - If Postgres exposes a bug in app code, I stop and show the fix before making it.

### Checkpoint 2 — re-upload fix and local switch (4 files + commands)
- `backend/app/services/document_service.py`: Decision 2 A, the row moves to the new copy when its file is gone.
- `backend/tests/test_document_service.py`: a new test. Identical re-upload after the stored file was deleted → the row points at the new copy, which still exists.
- `docker-compose.yml` backend:
  - `DATABASE_URL=postgresql+psycopg://rag_app:${RAG_APP_PASSWORD}@postgres:5432/rag` (interpolated from `.env`; no password in the repo)
  - `DATABASE_SCHEMA=rag`
  - `depends_on: postgres: condition: service_healthy`
  - `docker compose config --quiet` to validate.
- `.env.example`: the venv's local-Postgres `DATABASE_URL` / `DATABASE_SCHEMA` lines with a placeholder password, plus a note on Render's values.
- **You:** add to `.env`:
  - `DATABASE_URL=postgresql+psycopg://rag_app:<RAG_APP_PASSWORD>@localhost:5433/rag`
  - `DATABASE_SCHEMA=rag`

  I don't read or write `.env`.
- **Commands:**
  1. `alembic current` / `alembic check` on local `rag`
  2. `docker compose up -d --build backend` → healthy and "Database schema is at head"
- **You:**
  1. register, upload, chat, thumbs-down
  2. `docker compose restart backend`, log in again, check that the session and feedback are still there
  3. Decision 2 can't be proven by a local restart, because the `uploads` volume keeps the file. Its test covers it locally; runbook step 7 proves it on Render.

### Checkpoint 3 — docs and the release runbook (no code)
- `CLAUDE.md` (not Current Status):
  - Tech Stack / Data & State / Environment Variables / Key Commands / Feature Status / Known Issues: the app on Postgres (local and production from v0.2.2), `TEST_DATABASE_URL`, Render's variables
  - Redis key schema note on the cutover flush
  - remove "don't set DATABASE_URL before Day 14"
- `docs/timeline.md`:
  - Day 14: no disk, no copy, release v0.2.2
  - Day 17: drop "the data migration" from its release bullet (v0.3.0 still carries Days 15–17)
- This brief: the runbook below, refined with anything Checkpoints 1–2 found.

### Then you: `/pre-commit`, `/ship commit`, `/ship merge` (Day 14 into `develop`), then the release runbook

### Release runbook — v0.2.2 (`develop` → `master`, Days 13–14)
Steps marked **(you)** need the dashboard, secrets or git, which stay yours. **(me)** are read-only checks I run when you ask.

0. **Pre-flight, before merging anything:**
   1. **Render region: Singapore** (owner, 2026-11-13). Supabase is `ap-south-1` (Mumbai), so expect ~50–70 ms per database round trip. The before/after medians are compared against that.
   2. **(me)** Baseline latency on v0.2.1 (Decision 3). The script warms the instance, registers a throwaway `latency-<random>@example.com` account and times:
      - `/health`: no database, so it is the **network baseline** to subtract
      - `/me`: one user query by email, plus `pool_pre_ping` on Postgres
      - chat turns, timed to the `metadata` frame: the DB-backed end-to-end number

      The database-attributable cost is `/me − /health` and `chat − /health`.

      The account lives in ephemeral SQLite, so it disappears by itself. After the release the script registers a new one, which stays in `rag` as a test account (it can be deleted with `DELETE /user/delete`, and the script does that at the end).
   3. **(me)** MCP, catalog only: `rag` has 0 tables and no `alembic_version`; `rag_app` still has its `search_path`.
   4. **(you)** From your shell, check the production URL once: `alembic current` with `$env:DATABASE_URL` = the `rag_app` session-pooler URL and `$env:DATABASE_SCHEMA = "rag"`. Expected: no revision, no error. This proves the password, the pooler host and the schema guard before Render depends on them. Then remove both variables.
1. **(you) Render env vars, before the release merges:**
   - `DATABASE_URL = postgresql+psycopg://rag_app.<project-ref>:<password>@aws-0-ap-south-1.pooler.supabase.com:5432/postgres` (session pooler, `+psycopg`)
   - `DATABASE_SCHEMA = rag`
   - Render redeploys v0.2.1, which ignores them. Harmless.
2. **(you) Clear Render's Redis (Key Value).** Only caches live there (query, web and semantic). This removes `semantic_cache:{id}` entries keyed by SQLite-era ids that Postgres will hand out again. Do it **after step 1's redeploy has finished and before step 3**, so v0.2.1 has as little time as possible to write new entries.
   1. Render dashboard → the Key Value instance → **Info / Connect**.
      - An **External** URL (`rediss://` + user and password + `@singapore-keyvalue.render.com:6379`) needs your IP on its allowlist: **Networking / Access Control → Add source → your IP**, `/32`.
      - The **Internal** URL (`redis://red-…:6379`) is reachable only from Render services, so it won't work from your machine.
   2. From PowerShell, with the external URL in a variable so it stays out of history. The image is already pulled for compose, and its `redis-cli` speaks TLS:
      ```powershell
      $env:RENDER_REDIS_URL = Read-Host "Render Key Value external URL"
      docker run --rm -e RENDER_REDIS_URL redis:7-alpine sh -c 'redis-cli -u "$RENDER_REDIS_URL" -n 0 DBSIZE; redis-cli -u "$RENDER_REDIS_URL" -n 1 DBSIZE'
      docker run --rm -e RENDER_REDIS_URL redis:7-alpine sh -c 'redis-cli -u "$RENDER_REDIS_URL" -n 0 FLUSHDB; redis-cli -u "$RENDER_REDIS_URL" -n 1 FLUSHDB'
      docker run --rm -e RENDER_REDIS_URL redis:7-alpine sh -c 'redis-cli -u "$RENDER_REDIS_URL" -n 0 DBSIZE; redis-cli -u "$RENDER_REDIS_URL" -n 1 DBSIZE'
      Remove-Item Env:RENDER_REDIS_URL
      ```
      Expect `OK` twice, then `0` and `0`.
      - If the first command reports `ERR DB index is out of range` for `-n 1`, the instance has a single database. That's fine; DB 0 is all there is.
      - An `-u` URL that already ends in `/0` is overridden by `-n`.
   3. Remove the IP rule you added in step 1.

   If the instance shows **no external URL at all** (some plans), use the dashboard's **Shell** tab on the Key Value instance if present: run `SELECT 0`, `FLUSHDB`, `SELECT 1`, `FLUSHDB`. Otherwise tell me and we'll pick another way. One option is to skip the flush, since the risk is only the first new user per id, and give the semantic cache keys a version prefix later.
3. **(you)** Release PR `develop` → `master`, merge commit (`gh pr merge <N> --merge`). Render auto-deploys `master`.
4. **(you, me reading the logs you paste):** the Render deploy log shows:
   - `Running upgrade  -> 7cb8829683ab`
   - then "Database schema is at head"
   - the service turns **Live**.

   If the deploy fails, Render keeps serving v0.2.1, and we read the error before going further.
5. **(me)** MCP, catalog + counts only: `rag.alembic_version` = `7cb8829683ab`, the 7 tables owned by `rag_app`, the 7 sequences, nothing new in `public`.
6. **(you) Live check on the Vercel app:**
   1. register a new account
   2. upload a small PDF
   3. ask a question that cites it
   4. thumbs-down an answer (feedback)
   5. generate a concept map

   **(me)** Row counts in `rag` match: 1 user, 1 session, 2 messages, 1 document, 1 failed query, 1 map.
7. **(you) Persistence proof:**
   1. Render → Manual Deploy → Restart (or wait out an idle spin-down)
   2. log in with the same account: the session, its messages and the feedback are still there
   3. **Expected after the restart, not a failure:**
      - **survive (Postgres):** the account, sessions, messages, feedback, concept maps and the document **row** (the document is still listed)
      - **gone:** the uploaded **file** (no disk), and the document's chunks in FAISS / BM25 (in memory, I4). Answers no longer cite the document, and chat falls back to web or model knowledge.

      Both are fixed by Day 15 (Supabase Storage + pgvector chunks) and Day 16 (reindex).
   4. Re-upload the same file. Since Decision 2 this succeeds (before, it failed every time), and the next answer cites it again.
8. **(me)** After-latency on v0.2.2: the same script and the same measurements, with the test account deleted at the end. Both columns go into the Outcome with the Render region (Singapore), compared against the expected ~50–70 ms per database round trip.
9. **(you)** Tag: `git checkout master; git pull origin master; git tag v0.2.2; git push origin v0.2.2`. Then the `master` → `develop` sync is not needed (a release merges `develop` into `master`).
10. **(you) Keep-alive (now on `master`).** The secret `SUPABASE_RAG_DB_URL` is **already set and verified** (owner: `rag_app` → `current_schema = rag`). Run the workflow once by hand from `master` and confirm it passes:
    ```powershell
    gh workflow run supabase-keepalive.yml --ref master
    gh run list --workflow supabase-keepalive.yml --limit 1
    gh run watch <run-id>
    ```
    After that, the schedule (every 3 days) takes over.
11. **(you)** Resolve GitGuardian's 6 old incidents as false positives (from Current Status), whenever convenient.

**Rollback:**
- **Config** (bad DB connection, latency unacceptable, Supabase down): on Render, **delete** `DATABASE_URL` and `DATABASE_SCHEMA` → redeploy → the CMD creates and stamps a fresh SQLite file → the app runs as it did before v0.2.2 (ephemeral). Supabase `rag` keeps its rows for the switch back. Flush Redis again when switching back, since ids diverge.
- **Code** (v0.2.2 itself broken): Render → Events → **Rollback** to the last v0.2.1 deploy. It ignores the variables. Then a hotfix branch from `master`.
- **Decision rule:** any 5xx on register, chat or feedback in step 6, or a failed deploy, triggers a rollback first and debugging afterwards. Latency alone does not: it goes to you with numbers (Risks 3).

**New dependencies:** none.

## UI integration
- **Suite on Postgres, CI, init script** → backend-only: tests and infrastructure.
- **Local switch, production cutover** → backend-only: no endpoint, field or status changes. The API smoke tests run unchanged on Postgres to prove the contract holds.
- **What users do notice:** accounts and chats now survive restarts. That is a behavior change with no new UI, so there is nothing to wire.
- **Re-upload fix (Decision 2 A)** → no response shape changes. The same `POST /upload` success that `DocumentUpload` already renders replaces an error. Decision 2 B would add a UI badge.

## Verification
- **Suite:**
  - default SQLite run on the host: 269 + 1 new test pass
  - `TEST_DATABASE_URL` run on the compose `rag_test`: all pass
  - CI green on `backend` / `frontend` / `docker`, the backend log showing `test_backend_under_test` on `postgresql`
- **Local:**
  - Docker backend healthy on Postgres, "schema at head"
  - `alembic check` on `rag`: no diff
  - your register → chat → feedback → restart → still there check, plus a re-upload after a restart
- **Production:** runbook steps 4–8. The Outcome gets the Render region and the latency table:

  | Metric | v0.2.1 (SQLite) | v0.2.2 (Postgres) |
  |---|---|---|
  | `/health` | p50 / p90 | p50 / p90 |
  | `/me` | p50 / p90 | p50 / p90 |
  | `/me` − `/health` | p50 | p50 |
  | chat, time to `metadata` frame | p50 | p50 |

- **No retrieval, prompt or cache-logic change:** no E4/E1 run.

## Risks & open questions
1. **The release carries Day 13 too.** It is all of Alembic, the repositories and migrate-on-start. CI ran it on Postgres since Day 13, and today's full-suite run on Postgres is the extra safety net before it reaches Render. Its first real run against Supabase `rag` is in production (staging `rag_staging` was migrated on Day 13 with the same baseline).
2. **Settings validation on Render:** v0.2.2 requires every `Settings` field Render already has. `DATABASE_URL` without `DATABASE_SCHEMA` fails startup by design. If the deploy fails on a `ValidationError`, Render keeps v0.2.1 running.
3. **Latency if Render isn't near Mumbai.** Possible follow-ups, for you to choose once numbers exist:
   - recreate the Render service in Singapore (new URL → Vercel's `REACT_APP_API_URL`, the Google OAuth redirect, `ALLOWED_ORIGINS`)
   - cut round trips (drop `pool_pre_ping` for `pool_recycle`, one commit per chat turn)
   - accept it

   None is built today.
4. **The documents list shows documents whose files and vectors are gone after a restart** (I4, now more visible because rows persist). It is mitigated by Decision 2's re-upload fix and removed by Day 15 (Storage + pgvector) and Day 16 (reindex). Worth one line in the v0.2.2 release notes.
5. **Supabase free tier:** the project pauses after 7 days without activity. Production traffic plus the keep-alive (step 10) prevent it. The other app sharing the project shares its connection and storage quotas: `rag_app`'s `CONNECTION LIMIT 10` vs the app's pool of 5 + 5 overflow is exactly at the limit. A deploy overlap, with the old instance draining while the new one starts, could briefly need more. If a deploy logs "too many connections" for `rag_app`, lower the pool or raise the limit.
6. **Guard hook:** a shell command containing a Supabase URL may be flagged by `guard_commands.py` (it matches `supabase.co` / `SUPABASE_*URL`). Pre-flight step 4 is yours to run anyway.
7. **Local Docker data:** the `data` volume's SQLite (3 accounts) is abandoned, not deleted. The backups in `backend/data/` stay.
9. **Found in Checkpoint 1 (2026-11-13): deleting a session that has a failed query returned 500 on Postgres.** The error was `ForeignKeyViolation` on `fk_failed_queries_session_id_sessions`, from `DELETE /sessions/{id}`; SQLite never enforced it.
   - **Fixed (owner: A):** `sessions_repo.delete_with_messages` sets the session's failed queries' `session_id` to `NULL` before deleting the session, with a new repository test.
   - **Tracked for Day 15 (owner: B):** the same revision that creates `document_chunks` recreates the foreign key with `ON DELETE SET NULL` (noted in `docs/timeline.md` Day 15).
8. **Day 17 changes:** its release (v0.3.0) no longer does a data migration or a first `upgrade` on `rag`. Its CLAUDE.md bullet ("indexes now persist in Postgres") stays.

## Reference — if a SQLite → Postgres copy is ever needed
Not built (owner, 2026-11-13). Measured today on the two local files (read-only) and on Day 13. It extends the Day 13 brief's "Day 14 notes".

- **Measured state of the local files:**

  | File | users | sessions | documents | concept_maps | messages | failed_queries | nodes |
  |---|---|---|---|---|---|---|---|
  | host `backend/data/app.db` (at `7cb8829683ab`) | 2 (max id 2) | 2 (max 9) | 2 (2) | 1 (1) | 16 (max 27) | 1 (max 4) | 20 (20) |
  | `app.docker-backup-2026-11-11.db` (pre-stamp) | 3 (3) | 3 (3) | 3 (3) | 2 (2) | 10 (10) | 0 | 12 (12) |

  - 0 orphaned foreign keys in either file (SQLite doesn't enforce them): messages→sessions, failed_queries→sessions, nodes→maps, every `user_id`→users
  - every `user_id` stored as an integer
  - booleans stored as `1`
  - every datetime is 26-character text, `YYYY-MM-DD HH:MM:SS.ffffff`
- **Ids have gaps** (sessions: 2 rows, max id 9; messages: 16 rows, max 27). Preserve ids, then set each sequence to **`max(id)`**, not the row count:

  ```sql
  select setval(pg_get_serial_sequence('<table>', 'id'), coalesce(max(id), 1), max(id) is not null) from <table>;
  ```

  Without this, the next insert collides with a copied id (`duplicate key … "pk_messages"`). `setval` is **non-transactional**, so a dry run must not call it.
- **Type differences:**
  - **datetime text → `timestamp`:** naive UTC on both sides
  - **0/1 → `boolean`:** `users.is_active`, `documents.is_active`; Postgres rejects an integer
  - **ids in integer columns must be integers**
  - **defaults are Python-side only:** carry every column explicitly, or `NULL`s appear (`doc_version` → `NULL`)

  Reading and writing through SQLAlchemy `Table` objects (the models' types) does every conversion. Raw `sqlite3` + raw `INSERT` does none.
- **Order:** `Base.metadata.sorted_tables` (users → sessions, documents, concept_maps → messages, failed_queries, concept_map_nodes), in **one transaction**. The constraints aren't `DEFERRABLE`, so the order is required.
- **Preconditions:**
  - source and target at the same Alembic head
  - the target created by `alembic upgrade head` (never by the copy), with every table empty
  - target `current_schema()` = the intended schema
  - no orphans in the source
- **Reconcile before commit:** per table, rows, `max(id)` and per-column `NULL` counts must match; otherwise roll back.
- **The two local files are separate user populations whose ids overlap.** Combining them needs id remapping (offset every id and foreign key, resolve duplicate emails).
- **Read the target URL from `Settings`/env, never as an argument** (shell history), and never print it.
