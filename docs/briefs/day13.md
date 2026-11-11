# Day 13 — Postgres provisioning and Alembic as the real migration path (T2)
Date: 2026-11-11 · Phase 5 — Postgres + pgvector data layer · Items: T2
Branch: feature/day13-postgres

## Scope
1. **Local Postgres**: a `pgvector/pgvector` service in `docker-compose.yml` with a named volume (version: see Decision 5).
2. **Hosted Postgres**: *(changed 2026-11-11 on approval)* the owner's **existing** Supabase project, isolated by schema, with no new projects:
   - `rag` (production) and `rag_staging` (staging), each owned by its own login role (`rag_app`, `rag_staging_app`) with rights only on its own schema
   - neither schema exposed to the Data API
   - `search_path` set on the role, not in the URL, so it survives the Supavisor pooler
   - `CREATE EXTENSION vector` in Supabase's `extensions` schema for Day 15.

   Delivered as a reviewed SQL script, `scripts/supabase/setup_rag_schemas.sql`, which **the owner runs in the SQL editor and fills the passwords into**. Claude verifies the result read-only through MCP (Verification §4).
3. **Keep-alive**: `.github/workflows/supabase-keepalive.yml` runs every 3 days. It makes one cheap read **as `rag_app`** against that one project, through the session pooler. The URL is a GitHub secret.
   - 3a. **Local parity**: the compose Postgres gets the same `rag` schema, `rag_app` role and role-level `search_path`, through an init script.
   - 3b. **CI**: a Postgres service container in the **existing `backend` job** (no new job; branch protection requires exactly `backend` / `frontend` / `docker`). It runs `alembic upgrade head` on the empty database, then `alembic check` (no autogenerate diff).
4. **`DATABASE_URL` in `Settings`**, using the psycopg (v3) driver, which is a new dependency that needs approval. The sync `Session` stays.
5. **Alembic as the only migration path**:
   - the URL comes from `Settings`
   - `env.py` imports every model, `ConceptMap` and `ConceptMapNode` included
   - one baseline revision describes today's schema
   - `migrate_database()` / `migrate_concept_maps()` / `init_db()`'s `create_all` and `refresh_metadata()` are deleted.
6. **Split `db/database.py`** into `db/base.py` (Base + naming convention), `db/session.py` (engine, `SessionLocal`) and `db/models/` (`user`, `chat_session`, `message`, `document`, `failed_query`, plus the existing `concept_map`). `database.py` is then deleted.
7. **`db/repositories/`**: the CRUD SQL in the `sessions`, `documents`, `users` and `feedback` routers moves into repositories. I'm adding the `User` lookups from `auth.py` and `deps.py` to this scope, because they are the same kind of query and a `users` repository is created anyway.
8. **Verify**: `alembic upgrade head` on an empty database creates every table, and autogenerate reports no diff.

**Not today**:
- the data copy and switching the app to Postgres (Day 14)
- the *pytest suite* running on Postgres (Day 14). Today CI only migrates and diff-checks there.
- the chunks table (Day 15)
- Supabase Storage (Day 15: buckets `rag-prod` and `rag-staging` in the same project).

## Supabase catalog check (2026-11-11, read-only through MCP, metadata only)
- **Version**: Postgres **17.11**, so the local image is `pgvector/pgvector:pg17` (Decision 5 resolved).
- **No collisions**: no `rag` / `rag_staging` schemas and no `rag*` roles exist. The existing schemas are Supabase's own (`auth`, `extensions`, `graphql`, `graphql_public`, `public`, `realtime`, `storage`, `supabase_migrations`, `vault`).
- **Extensions**: `vector` 0.8.2 is available but not installed. `pg_stat_statements`, `pgcrypto` and `uuid-ossp` are already in `extensions`.
- **Default privileges** (`pg_default_acl`) grant `anon` / `authenticated` / `service_role` access only in `public`, `storage`, `graphql*`, and to `postgres` in `extensions`. **Nothing applies to new schemas**, so `rag` / `rag_staging` start with no grants for the API roles.
- **Event trigger `ensure_rls` → `public.rls_auto_enable()`** turns on RLS for new tables **only in `public`** (it checks `schema_name IN ('public')`). Our schemas are skipped, so the app role's tables stay RLS-free, which they need: the app does its own `user_id` scoping.
- **`PUBLIC` pseudo-role**: on `public` it has `USAGE` (the Postgres default), no `CREATE`, 0 tables or sequences granted, and 1 function executable (`rls_auto_enable`, an event-trigger function, which can't be called directly). On `extensions` it has no `USAGE`, so the app roles need an explicit `GRANT USAGE ON SCHEMA extensions` to use `vector` on Day 15.
- **Security advisors**: 3 existing warnings, all outside our scope (`public.rls_auto_enable` executable by anon/authenticated ×2, leaked-password protection off in Auth). Not touched; they belong to the other app's setup.

## Current behavior
- **Engine**: `backend/app/db/database.py:82-87` hardcodes `sqlite:///data/app.db`, which is **relative to the CWD**. It also creates `data/` at import time. `DATABASE_URL` is read by nothing.
- **Schema changes** happen in three places:
  - `init_db()` (`database.py:175`) runs `create_all` followed by hand-written `ALTER TABLE`s (`database.py:89-173`, which use `print` and catch bare `Exception`)
  - `init_db()` is called from the lifespan (`main.py:30`)
  - Alembic runs on the side.
- **Alembic**:
  - `alembic.ini:87` → `sqlite:///data/app.db` is CWD-relative. From the repo root it creates and migrates `./data/app.db`, not `backend/data/app.db`.
  - `alembic/env.py:13` imports only `app.db.database`, so the concept-map tables are missing from `target_metadata`, and autogenerate against the real database would emit `drop_table` for them.
  - The one revision, `1e5877c62358`, only adds the two feedback columns and has no root that creates the tables.
- **Local data**: `backend/data/app.db` (checked read-only today) has all 7 tables. Their columns match the models exactly, and there is no `alembic_version` table. The Docker `data` volume holds a second SQLite database of the same shape.
- **Docker image**: `alembic/` is in `.dockerignore`, and the `CMD` runs only uvicorn.
- **CRUD SQL inside routers**:
  - `api/routes/sessions.py:21-40` (latest-message subquery), `:63-75`, `:99-112`, `:134-145`
  - `documents.py:94-107`, `:119-127`
  - `users.py:38-39`, `:56-59`
  - `feedback.py:24-66`: a raw `text()` `UPDATE`, plus the "previous user message" lookup
  - `auth.py:22-29`, `:136-160`
  - `deps.py:38`
- **Type mismatches**:
  - Several queries compare an `Integer` FK with `str(current_user.id)`: `documents.py:96,122`, `users.py:57`, `feedback.py:26,79`.
  - `FailedQuery(user_id=str(...))` inserts a string into an integer column (`feedback.py:55`).
  - SQLite coerces both silently. Postgres compares types strictly.
- **Who uses `SessionLocal` / `database.py`**:
  - the four modules in `services/`, `api/deps.py`, every router
  - `eval/cache_tuner.py` and `eval/retrieval/mine_feedback.py`
  - `tests/test_account_service.py` and `tests/test_document_service.py`
  - `conftest.py:129` (disposes the engine).

## Why it matters
- **Alembic config**: today `alembic upgrade head` from the repo root creates an empty `./data/app.db` and reports success. If someone points it at the real DB, `revision --autogenerate` proposes dropping `concept_maps` and `concept_map_nodes`, and that data is lost if anyone applies it. Day 14's data copy needs a schema that Alembic created on Postgres, and Day 15's chunks table needs a revision chain to sit on.
- **Startup `ALTER`s**: they only run against SQLite (`sqlite3.connect`) and swallow every error with a `print`. On Postgres they would do nothing while the app started anyway, so a missing column would first show up as a 500 in a user's request.
- **CWD-relative SQLite path**: the same app can open different databases depending on where it was started. That is exactly how T2's side database came to exist.
- **The `str(user_id)` filters**: on Postgres, `documents.user_id = '5'` relies on implicit casts that may or may not happen depending on the driver. These are the queries that scope a user's data (convention: *scope all user data by `user_id`*), so they must be type-correct before the Day 14 switch.
- **CRUD in routers**: Days 15–20 add the chunks table, projects and project scoping. Each of those would otherwise be scattered across four routers again. Repositories give each query one home and one place to add `project_id`.
- **Supabase pausing**: a free project pauses after ~7 days without activity, and a paused production database is a full outage.

## The concept

### 1. Schema migrations as versioned history
A migration tool turns "the schema" into an ordered chain of revisions:
- each revision has an `upgrade()` and a `downgrade()` and points at its parent (`down_revision`)
- the database records the revision it is at, in the `alembic_version` table
- `alembic upgrade head` applies whatever is missing, in order.

This makes every environment (dev, CI, staging, production) reproducible from code: an empty database plus `upgrade head` gives exactly the production schema. Competing mechanisms, like today's `create_all` + `ALTER`s + Alembic, mean no single place knows what production looks like.

### 2. Autogenerate is a diff, not a decision
`alembic revision --autogenerate` compares `target_metadata` (the models that were *imported*) with the live database and writes the difference as code. Pitfalls:
- **Models that aren't imported look deleted.** This is T2's `drop_table` trap. `env.py` must import every model module; one `app.db.models` package that imports them all is the standard fix.
- **Renames come out as drop + add.** Autogenerate can't see intent.
- **Some changes are invisible to it**: server defaults, some type changes (`compare_type` helps), constraints without names, and data migrations.
- **Every generated file is reviewed by a human.** Alembic ≥ 1.9 adds `alembic check`, which fails if models and database differ. That is the "no diff" check in CI form.

### 3. Baseline and stamp
When a schema already exists without migration history, you write one **baseline revision** that creates the current schema from nothing:
- on empty databases (Postgres, CI, tests), `upgrade head` runs it
- on databases that already have the tables (the two local SQLite files), `alembic stamp head` records "already at baseline" without executing anything.

Stamping a database whose schema *doesn't* match the baseline hides drift forever. So before stamping, compare the schemas (here: `compare_metadata` against the real file).

### 4. Constraint naming conventions
Postgres auto-names constraints (`users_email_key`), SQLite often leaves them unnamed, and Alembic can only drop or alter a constraint by name. Setting `MetaData(naming_convention=...)` on `Base` *before* the baseline gives every index, unique, FK and PK a deterministic name (`uq_users_email`, `fk_messages_session_id_sessions`). Future migrations can then refer to them on every backend. Retrofitting names later costs a migration of its own.

### 5. When migrations run
There are three common choices:
- **In the app's startup.** Simple, but with several workers or instances, two processes race to migrate. A slow migration also blocks the health check, and the platform may kill the boot.
- **As a separate deploy step**: a release phase, Render's pre-deploy command, a Kubernetes Job, or the container command `alembic upgrade head && exec uvicorn`. One run per deploy, and a failed migration means the new version never starts.
- **Manually.** Fine for dev, a source of incidents in production.

Production systems use a separate step. The app itself may *check* that it is at head and refuse to start if not (fail fast), but it doesn't migrate.

Related: **expand/contract** (backward-compatible migrations). Add the new column first, deploy code that writes both, then remove the old one. During a rolling deploy, old and new code briefly share one schema.

### 6. SQLite vs Postgres: what breaks when you switch
- **Types**: SQLite stores almost anything in any column. Postgres refuses `integer = text`, which is today's `str(user_id)` filters.
- **ALTER TABLE**: SQLite can't drop or alter columns, so Alembic needs `render_as_batch=True` there (copy-and-rename tables).
- **Concurrency**: SQLite has one writer. That is why the engine needs `check_same_thread=False`. Postgres has real MVCC and needs neither.
- **Sequences**: Postgres `SERIAL`/identity sequences don't advance when rows are inserted with explicit ids (Day 14 resets them).
- **Time zones**: `DateTime` without `timezone=True` is `timestamp without time zone`. Fine as long as everything is UTC, which `utcnow` is today.

### 7. Connection management with a hosted Postgres
- **Supabase's direct connection is IPv6-only** on the free plan. Render and GitHub-hosted runners have no outbound IPv6, so both must use the **Supavisor pooler**, which is IPv4.
- The pooler has two modes:
  - **Session mode** (port 5432 on the pooler host): one server connection per client connection. Prepared statements and `SET` work.
  - **Transaction mode** (port 6543): connections are shared between transactions. psycopg 3's automatic prepared statements (`prepare_threshold`, default 5) then fail with "prepared statement does not exist", so they must be disabled.

  For a single long-running app with its own SQLAlchemy pool, session mode is the safer default.
- **Engine settings that matter**:
  - `pool_pre_ping=True`: poolers and the free tier drop idle connections, and the first query after an idle hour would otherwise fail.
  - A small `pool_size` / `max_overflow`: the free tier's pooler has a client limit.
  - `pool_recycle` below the server's idle timeout.

### 8. Repository pattern and unit of work
A repository is the one module that knows how to query a table:
- routers handle HTTP (validation, status codes, response shape)
- repositories handle SQL
- services orchestrate.

The **unit of work**, meaning who calls `commit()`, belongs to the caller, not the repository. Several repository calls in one request then commit or roll back together, as `delete_user_account` already does across 7 tables. Pitfalls:
- repositories that commit internally, which makes multi-step operations non-atomic
- repositories that return HTTP errors
- "generic repository" base classes that hide the SQL they were meant to make explicit.

### 9. Free-tier keep-alive
Free hosted databases pause when idle. Something cheap must touch each project before the idle window closes. Three details matter:
- **Scheduled GitHub workflows run only from the default branch.** The file does nothing until it reaches `master`.
- GitHub disables a schedule after 60 days without repository activity.
- The ping must hit the database itself, not just the dashboard.

### 10. One database, isolated by schema and role
A Postgres *schema* is a namespace inside one database. Putting each environment in its own schema, owned by its own login role, gives isolation without a second server:
- **Privileges**: a role with no `USAGE` on a schema can't touch anything in it.
- **Name resolution**: `search_path` decides where unqualified names resolve *and* where new tables are created.

Three details make it work in practice:
1. **Set `search_path` on the role** (`ALTER ROLE … SET search_path`). That applies at every login, even through a pooler. URL `options=-csearch_path=…` parameters are dropped by transaction-mode poolers.
2. **Put the migration tool's version table inside the schema** (`version_table_schema`). Then each environment's history travels with its tables.
3. **Guard against the fallback.** If the role setting is lost, unqualified DDL silently lands in `public`. A check that `current_schema()` is what you expect turns that into a loud failure.

Limits compared with separate projects:
- shared CPU, memory and connection limits (a load test on staging slows production)
- one backup and restore unit
- extensions installed once for every schema
- the same Postgres major version.

That's acceptable for a free-tier solo project. Real production systems usually separate environments at the project or server level.

## Decisions
**Approved 2026-11-11: recommended options 1–6, and `psycopg[binary]` v3 as a new dependency.** v0.2.1 had already been released (PR #16, tagged), so Risk 3 below is closed. Decision 5 was settled by the catalog check: `pg17`.

### 1. Postgres driver (new dependency: needs approval)
- **A — `psycopg[binary]` (psycopg 3):** this is the maintained driver and SQLAlchemy 2's recommended Postgres dialect (`postgresql+psycopg://`). It ships prebuilt wheels for Windows/3.12 and Linux/3.11, and it supports pipeline mode and async if needed later. Adds `psycopg` + `psycopg-binary` (+ `tzdata` on Windows only). The trade-off: its automatic prepared statements must be turned off if we ever use Supabase's transaction-mode pooler.
- **B — `psycopg2-binary`:** older and in maintenance mode, with the most tutorials and Stack Overflow answers. It has no prepared-statement pitfall, but it is a dead end for async, and its binary wheel is officially "not for production".
- **Recommendation: A.** It is what the timeline names, and we use the session pooler anyway (§7). The exact version is the newest psycopg 3 release with wheels for both Python 3.11 and 3.12, chosen when regenerating the lock and shown to you before committing.

### 2. When the app itself switches to Postgres
- **A — Not today:** `DATABASE_URL` defaults to the SQLite file (now an absolute path). Postgres is provisioned, migrated to head (empty) and smoke-tested by hand. Day 14 copies the data and flips `DATABASE_URL` everywhere. The trade-off: the app keeps running on SQLite for one more day.
- **B — Flip local Docker dev today:** the Docker backend points at the compose Postgres right away and starts with an empty database, since your current Docker data stays in the old SQLite volume until Day 14 copies it. It exercises Postgres a day earlier, but your local app loses its accounts and sessions in the meantime.
- **Recommendation: A.** That is how the timeline splits Days 13 and 14. Today's Postgres check is a manual end-to-end run against the local container (Verification §3).

### 3. Where `alembic upgrade head` runs
- **A — In the lifespan:** `init_db()` becomes `command.upgrade(cfg, "head")`, so every way of starting the app migrates automatically (venv, Docker, Render, tests). The trade-offs: concurrent workers race, a slow migration delays the health check, and a broken migration crash-loops the service.
- **B — As an explicit step, with a fail-fast check in the lifespan:**
  - The Docker `CMD` and compose dev command run `alembic upgrade head && exec uvicorn …`.
  - Venv users run `alembic upgrade head` themselves.
  - The lifespan compares the DB's revision with the script head and refuses to start with a one-line instruction if they differ.
  - Tests migrate a temporary database in `conftest`.
  - The trade-off: one more command to know on the host.
- **Recommendation: B.** It is the production pattern (§5), and it keeps Render's single-instance deploy just as simple, because the migration is still part of the container start. The image must now include `alembic/` and `alembic.ini` (removed from `.dockerignore`).

### 4. Repository shape and who commits
- **A — Module-level functions that take the `Session`; the caller commits.** For example, `repositories.sessions.get_owned(db, session_id, user_id)` and `list_with_last_message(db, user_id)`. Routers call `db.commit()`. It is explicit, there are no extra `Depends`, and it matches the existing `account_service` / `document_service` style. The trade-off: there is no object to swap in tests (the tests use a real SQLite or Postgres session instead, which is better anyway).
- **B — Repository classes injected with `Depends`**, for example `SessionRepository(db)`, with methods that commit. They mock easily, but each router gains a dependency per table, and repositories that commit make multi-table operations non-atomic (§8).
- **Recommendation: A**, with `user_id: int` in every signature. That also fixes the `str(user_id)` comparisons as the queries move.

### 5. Local Postgres version
- **A — `pgvector/pgvector:pg16`, as the timeline says.** Widely used and stable, but it may differ from Supabase's major version.
- **B — Match the Supabase projects' major version.** New Supabase projects currently get Postgres 17, so this is most likely `pg17`. Dev then equals production for planner behaviour and `pg_dump` / restore compatibility, which Day 14 relies on.
- **Recommendation: B.** Once you've created the projects, read the version in the Supabase dashboard (Settings → Infrastructure) and I'll pin the image tag to that major version. If the projects aren't created yet when we reach Checkpoint 1, I'll use `pg17` and adjust later.

### 6. `postgresql://` URLs (what Supabase hands you)
- **A — Reject with a clear error:** a `Settings` validator fails startup with "use postgresql+psycopg://…" if the URL names no driver. It is explicit, at the cost of one manual edit when pasting from Supabase.
- **B — Rewrite silently:** the validator turns `postgresql://` and `postgres://` into `postgresql+psycopg://`. Copy and paste just works, but the effective URL differs from the configured one.
- **Recommendation: A.** That follows your "explicit over implicit" rule. The error message includes the corrected prefix.

## Plan

### Checkpoint 1 — Driver, setting, local Postgres (≈ 8 operations)
- `requirements.in`: `psycopg[binary]==<ver>`, with the reason "Postgres driver (T2, Day 13)". **Needs approval (Decision 1).**
- `requirements.txt`: regenerated in `python:3.11-slim` with the command in its header. I'll show you the diff before going on.
- `backend/app/core/config.py`:
  - `DATABASE_URL: SecretStr`, defaulting to `sqlite:///<backend>/data/app.db` as an **absolute** path (resolved like `ENV_FILE`), which ends T2's CWD dependence
  - the scheme validator (Decision 6).
- `backend/app/core/config.py`: a `DATABASE_SCHEMA: str | None` field.
  - It is the schema the role's `search_path` must resolve to (`rag` / `rag_staging`). It is required for Postgres URLs and unused for SQLite.
  - Models stay schema-agnostic. The setting exists **only as a guard**: Alembic and the app refuse to run if `current_schema()` differs, so a misconfigured role can never migrate into `public` (Checkpoint 4).
- `.env.example`: documents
  - `DATABASE_URL`: the SQLite default, the local Postgres URL, and the Supabase session-pooler shape `postgresql+psycopg://rag_app.<project-ref>:<pw>@aws-0-<region>.pooler.supabase.com:5432/postgres`, where the pooler username is `role.projectref`
  - `DATABASE_SCHEMA`
  - `POSTGRES_*` / `RAG_APP_PASSWORD` for compose.
- `docker-compose.yml`:
  - a `postgres` service (`pgvector/pgvector:pg17`), container `rag-postgres`
  - host port **5433** (the 6380 reasoning: room for another project's Postgres)
  - named volume `pgdata`, `pg_isready` healthcheck, credentials from `.env` with dev defaults
  - mounts the init script read-only
  - the backend does **not** depend on it yet (Decision 2).
- `scripts/postgres/init-rag-schema.sh`: **local parity (3a)**, run once by the image's `/docker-entrypoint-initdb.d` on an empty volume.
  - It creates `rag_app` with `RAG_APP_PASSWORD`, `CREATE SCHEMA rag AUTHORIZATION rag_app`, and `ALTER ROLE rag_app SET search_path = rag, extensions` (see Risk 9).
  - It creates `extensions` and `vector` in it, mirroring Supabase's layout, and revokes `CREATE` on `public`.
  - CI reuses this same script (Checkpoint 6), so local, CI and Supabase share one shape.
- `backend/tests/test_config.py`: tests for the default (absolute path), for the validator rejecting `postgresql://`, and for a Postgres URL without `DATABASE_SCHEMA` being refused.
- Venv: `pip install` the new pin.

**Commits**: the owner commits after every checkpoint (with `/ship commit`; `/run-day` forbids Claude's own git writes). Checkpoint 2 ends with its own commit, so the model split is recorded before Checkpoint 3 rewrites the importers.

### Checkpoint 2 — New `db` package modules, nothing switched over yet (≈ 9 operations)
*(Adjusted: to stay green on its own, `database.py` keeps working for one checkpoint.)*
- The model classes **move** out of `database.py` into the new modules.
- `database.py` shrinks to a re-export of `Base`, the models, `engine` and `SessionLocal`. Defining the classes twice on one `Base` would fail ("Table already defined").
- Checkpoint 3 deletes that shim.
- About git and renames: a file split into five is recorded as content moves, not renames. Rename detection needs ≥ 50 % similarity per file. `git log --follow` works for the file that keeps most of the text, and `git blame -C -C` traces the lines across all of them.
- `backend/app/db/base.py`: `Base` with a constraint naming convention (§4).
- `backend/app/db/session.py`:
  - `build_engine(url)` branches explicitly by dialect: SQLite gets `check_same_thread=False` and creates the parent directory; Postgres gets `pool_pre_ping`, a small pool and `pool_recycle`
  - plus `engine` and `SessionLocal`.
  - Building an engine opens no connection, so importing `app.main` stays network-free (`test_app_factory.py`).
- `backend/app/db/models/user.py`, `chat_session.py` (class still `Session`, so `Session as ChatSession` keeps working everywhere), `message.py`, `document.py`, `failed_query.py`. These are moved **unchanged**, so columns and types stay identical to the current schema.
- `backend/app/db/models/__init__.py` imports and re-exports all 7 models. This is the one module `env.py` imports.
- `backend/app/db/models/concept_map.py`: imports `Base` from `app.db.base`.

### Checkpoint 3 — Switch every importer, delete `database.py` (≈ 18 small edits; one mechanical commit)
- Imports updated in:
  - `api/deps.py` and `api/routes/{auth,users,feedback,sessions,documents,quiz,concepts,chat}.py`
  - `services/{session_service,document_service,chat_pipeline,account_service}.py`
  - `eval/cache_tuner.py`, `eval/retrieval/mine_feedback.py`
  - `tests/{test_account_service,test_document_service}.py`, `tests/conftest.py` (dispose `app.db.session.engine`).
- `backend/app/db/database.py`: **deleted**, including `migrate_database`, `migrate_concept_maps` and `refresh_metadata` (no callers).
- `main.py`: the lifespan temporarily calls `Base.metadata.create_all` through a small `db/session.py` helper, so this checkpoint stays green on its own. Checkpoint 4 replaces it.
- Check: the full suite passes unchanged, which proves the split didn't change behaviour.

### Checkpoint 4 — Alembic for real (≈ 10 operations)
- `alembic.ini`:
  - the `sqlalchemy.url` line is removed (the URL comes from `Settings` only)
  - `prepend_sys_path = backend` replaces `env.py`'s `sys.path.append`
  - the comments say why.
- `alembic/env.py`:
  - imports `app.db.models` (everything) and `settings`
  - builds the engine with the same `build_engine`
  - turns on `compare_type=True`, and `render_as_batch=True` when the dialect is SQLite
  - offline mode uses the same URL
  - the URL never goes through configparser, so a `%` in a Supabase password can't break it.
  - **On Postgres**:
    - `version_table_schema = settings.DATABASE_SCHEMA`, so `alembic_version` lives inside `rag` / `rag_staging`
    - before migrating it checks `select current_schema()` against `DATABASE_SCHEMA` and **refuses** on a mismatch (e.g. a role without the `search_path`, which would otherwise create the tables in `public`)
    - `include_schemas` stays off, so autogenerate only compares the role's own schema.
- `alembic/versions/1e5877c62358_…py`: **deleted**. It has no root and was only ever applied to the side database.
- `alembic/versions/<rev>_baseline_schema.py`: autogenerated against the **empty local Postgres**, then reviewed by hand. It contains the 7 tables and their indexes, and a `downgrade` that drops them.
- `backend/app/db/migrations.py`:
  - `current_revision(engine)` / `head_revision()`
  - `assert_schema_at_head()`, which raises a clear `RuntimeError` naming `alembic upgrade head`.
- `main.py`: the lifespan calls `assert_schema_at_head()` instead of `create_all` (Decision 3).
- `Dockerfile`:
  - `COPY alembic.ini alembic/` into `/app`
  - `CMD ["sh","-c","alembic -c /app/alembic.ini upgrade head && exec uvicorn …"]`
  - `exec` stays, so uvicorn is still PID 1.
- `.dockerignore`: drop the `alembic/` line.
- `docker-compose.override.yml`: the dev `command` runs the same `upgrade head &&` first.
- `backend/tests/conftest.py`: `DATABASE_URL` is added to `TEST_ENV` (a temporary SQLite file). Without it, a real `DATABASE_URL` in `.env` would leak into the tests. The suite then runs `command.upgrade(cfg, "head")` once in `pytest_configure`.
- `backend/tests/test_migrations.py`:
  - `upgrade head` on an empty SQLite database → `compare_metadata` reports nothing, and all 7 tables exist
  - `downgrade base` → only `alembic_version` is left
  - `assert_schema_at_head` raises on an unmigrated database
  - all offline, in CI.
- **One-off, with your OK, run by me:** check each existing local SQLite database's schema against the models with `compare_metadata` (read-only), then run `alembic stamp head` on:
  - `backend/data/app.db`
  - the Docker `data` volume's copy, through `docker compose run`.

  Without the stamp, both would try to re-create existing tables.

### Checkpoint 5 — Repositories (≈ 10 operations)
- `backend/app/db/repositories/users.py`: `get_by_email`, `create`, `count_active_documents`.
- `backend/app/db/repositories/sessions.py`: `list_with_last_message`, `get_owned`, `delete_with_messages`, `rename`.
- `backend/app/db/repositories/documents.py`: `get_owned`, `list_active`.
- `backend/app/db/repositories/messages.py`: `get_owned`, `set_feedback` (ORM assignment replaces the raw `text()` `UPDATE`), `previous_user_message`.
- `backend/app/db/repositories/failed_queries.py`: `add_negative_feedback`, `list_recent`.
- Routers `sessions.py`, `documents.py`, `users.py`, `feedback.py` and `auth.py`, plus `api/deps.py`: they call the repositories and keep the HTTP checks, response shapes and `db.commit()`. Every `str(current_user.id)` comparison against a DB column becomes the int. FAISS metadata keeps its strings, as the convention says.
- `backend/tests/test_repositories.py`: one focused test per repository module on an in-memory SQLite session. Ownership scoping is the key case: user B can't fetch user A's session, document or message.
- Check: `test_api_smoke.py` passes **unchanged**. Response shapes are identical.

### Checkpoint 6 — Supabase script, CI, keep-alive, docs, wrap-up (≈ 10 operations)
- `scripts/supabase/setup_rag_schemas.sql`: **the owner reviews it and runs it in the SQL editor as `postgres`.** One transaction, idempotent where Postgres allows (`IF NOT EXISTS`). Contents:
  - `CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions`
  - per environment:
    - `CREATE ROLE rag_app LOGIN PASSWORD '<RAG_APP_PASSWORD>' CONNECTION LIMIT 10`
    - `CREATE SCHEMA rag AUTHORIZATION rag_app`
    - `ALTER ROLE rag_app SET search_path = rag, extensions` (Risk 9)
    - `GRANT USAGE ON SCHEMA extensions TO rag_app`
    - a `statement_timeout`
    - `REVOKE ALL ON SCHEMA rag FROM PUBLIC`
    - the same for `rag_staging` / `rag_staging_app`
  - a `DO` block first that **aborts** if either password placeholder is still unreplaced
  - no grants to `anon` / `authenticated` / `service_role`, and no Data API exposure. The script's header says to leave both schemas out of *API → Exposed schemas*.
- `.github/workflows/ci.yml`, **`backend` job only**. The job name is unchanged, so branch protection is untouched.
  - `services: postgres` (`pgvector/pgvector:pg17`)
  - a step that applies `scripts/postgres/init-rag-schema.sh`
  - then `alembic upgrade head` and `alembic check` as `rag_app` (`DATABASE_SCHEMA=rag`)
  - then **`pytest backend/tests/test_repositories.py` with `TEST_POSTGRES_URL`** pointing at the service (added on approval of Checkpoint 5). An int-vs-text comparison then fails CI, not production; on Day 13 the old `Document.user_id == str(id)` filter raised `operator does not exist: integer = character varying` on Postgres.
  - all before the full pytest run, which stays on SQLite until Day 14.
- `.github/workflows/supabase-keepalive.yml`:
  - `schedule: "0 6 */3 * *"` + `workflow_dispatch`, `permissions: contents: read`
  - installs `postgresql-client`
  - runs `psql "$SUPABASE_RAG_DB_URL" -tAc "select current_schema()"` **as `rag_app` through the session pooler**, and fails unless the answer is `rag`. The read keeps the project active and also catches a lost `search_path`.
  - fails clearly if the secret is empty
  - comments cover the default-branch and 60-day caveats.
- `.claude/hooks/edit_reminders.py`: the stale T2 reminder becomes "review autogenerated revisions for drop_table / renames; never edit an applied revision".
- `CLAUDE.md`. Not Current Status; the sections changed are:
  - Repo Structure / module map (db rows)
  - Tech Stack (Database)
  - Key Commands (Postgres, alembic upgrade/check/stamp, revision)
  - Env Vars (`DATABASE_URL`, `POSTGRES_*`)
  - Data & State
  - Known Issues (T2 → Done)
  - Open Decisions (Migrations → decided)
  - Conventions (repositories; the caller commits; schema changes only through Alembic revisions).
- `docs/timeline.md`, Days 13 and 15: the hosting text now reads one existing project, schemas `rag` / `rag_staging`, buckets `rag-prod` / `rag-staging`.
- `docs/architecture/layout.md`: the `db/` rows and the routers-hold-CRUD exception marked as removed. I'll also fix line 59's "Day 13 replaces `DocumentChunk`", which is Day 15.
- Brief `## Outcome`, post material log, learning notes (per `/run-day`).

### Dependencies
- `psycopg[binary]`, **needs approval** (Decision 1). Nothing else. `pgvector` (Python) is Day 15.

## UI integration
**Backend-only, no user-visible change today.**
- Every endpoint keeps its path, request and response shape.
- `test_api_smoke.py` and the frontend's 11 tests must pass unchanged, which is the proof.
- The app keeps running on SQLite until Day 14 (Decision 2), so a user can't tell anything changed.
- The keep-alive is infrastructure.
- No new endpoint, field, status or flag means there is nothing for the frontend to call.

## Verification
1. **Offline suite**:
   - `python -m pytest` on the host and in the container (`.\scripts\dev.ps1 test`); expect today's 244 plus the new tests
   - `ruff check .`
   - `cd frontend; npm test -- --watchAll=false` (untouched, as a sanity check).
2. **Alembic on an empty Postgres**, against the compose container:
   ```powershell
   docker compose up -d postgres
   $env:DATABASE_URL = "postgresql+psycopg://rag:<pw>@localhost:5433/rag"
   alembic upgrade head          # creates 7 tables + alembic_version
   alembic check                 # "No new upgrade operations detected." ← the timeline's "no diff"
   alembic downgrade base; alembic upgrade head   # the round trip works
   ```
   Then `psql \dt` lists the tables, and `\d messages` shows the named constraints.
3. **The app end-to-end on Postgres**, manually, against the throwaway local database:
   - uvicorn with `$env:DATABASE_URL` pointing at the container
   - register → login → upload a demo PDF → chat (stream) → thumbs down (writes `failed_queries`) → rename and delete a session → delete the document → `/user/stats` → concept map → delete the account
   - check `app.log` for errors.

   This is the run that would catch any remaining `integer = text` mismatch. Afterwards `alembic downgrade base` empties the database again.
4. **Supabase**:
   - After the owner runs the setup script, Claude verifies **read-only through MCP, catalog only**:
     - both roles exist and can log in
     - each owns only its own schema and has no privileges on the other
     - neither has `CREATE` on `public` nor any table or sequence privilege there (`USAGE` comes only from `PUBLIC`; see Risk 10)
     - `rolconfig` holds the `search_path`
     - `vector` is installed in `extensions`
     - `anon` / `authenticated` / `service_role` have no `USAGE` on either schema
     - the security advisors show no new findings.
   - Data API exposure is a dashboard setting MCP can't read. The owner confirms *API → Exposed schemas*, and the no-`USAGE` check makes the schemas unreachable through the API even if exposed by mistake.
   - Then `alembic upgrade head` + `alembic check` against **`rag_staging`** through the session pooler, using `rag_staging_app`'s URL from `.env`, which Claude never prints.
   - `rag` (production) stays empty until Day 14.
   - CI does the same on its service container on every PR.
5. **Stamped local databases**: the app starts on `backend/data/app.db` (venv) and in Docker. Existing accounts log in and see their sessions, and the lifespan check passes.
6. **Keep-alive**:
   - `actionlint`-style review of the YAML
   - it can't be run with `workflow_dispatch` until it is on `master`. Before then, the same `psql` command run locally against each pooler URL proves the secrets work.
7. **No retrieval, prompt or cache change**, so there is no E4 or E1 re-run.

## Risks & open questions
1. *Superseded 2026-11-11: one existing project with two schemas; setup through `scripts/supabase/setup_rag_schemas.sql` (Checkpoint 6). The original text is kept for the record.* **Supabase provisioning**:
   - create two projects, `rag-study-prod` and `rag-study-staging`, in the region nearest Render's (Render's region is in its dashboard; Oregon → `us-west-1`)
   - for each, copy the **Session pooler** connection string (Connect → Session pooler, port 5432, user `postgres.<ref>`), not the direct one
   - add them as GitHub secrets `SUPABASE_PROD_DB_URL` and `SUPABASE_STAGING_DB_URL`, keeping the `postgresql://` prefix that `psql` needs
   - give me the Postgres major version (Decision 5).

   **Never paste the passwords in chat.** They go in `.env` and GitHub secrets only.
2. **Pause timing**: *(still relevant: the project is shared, but if the other app's traffic stops, nothing of ours touches it until the keep-alive reaches `master` on Day 17)* the keep-alive only runs once it is on `master`, which happens with the v0.3.0 release on Day 17. A project created today that sees no activity for 7 days pauses before then. Either create the projects only when Day 14 needs them, or run the local `psql` ping by hand every few days until the release. Restoring a paused project takes ~2 minutes from the dashboard, and no data is lost.
3. *Closed: v0.2.1 was released before today.* **Release v0.2.1 has to come first.** Current Status says v0.2.1 (`develop` → `master`, B8 + B9) is released *before* Day 13. **Has it shipped?** If Day 13 merged into `develop` first, the release would carry Alembic-at-container-start to Render. If Render has a persistent disk with an un-stamped SQLite database, `upgrade head` would fail with "table users already exists" and the deploy would crash-loop. If v0.2.1 hasn't gone out, release it from `develop` before merging today's PR.
4. **Stamping hides drift if the check is skipped.** That's why the read-only `compare_metadata` runs before each stamp. If a local database differs (old columns, etc.), I'll stop and show you.
5. **Naming convention vs existing SQLite databases**: the stamped databases keep their unnamed constraints. That doesn't matter, because they are abandoned on Day 14, but no future migration should be run against them.
6. **`str(user_id)` remnants**: I'll grep for `str(current_user.id)` / `str(user.id)` used against DB columns outside the routers (`services/`, `chat_pipeline`) and fix only the DB comparisons. Index metadata keeps strings.
7. **`datetime.utcnow`** (deprecated in 3.12) and naive timestamps stay as they are; the baseline mirrors today's schema. Moving to `timestamptz` is a later migration.
9. *Decided 2026-11-11: `rag, extensions`. Risk 10 decided the same day: leave `PUBLIC` as is.* **`search_path = rag, extensions`, not just `rag`.** Your instruction was `search_path = <schema>`. I'm proposing to add `extensions` after it, because pgvector's type (`vector`) and its operators (`<=>`, `<#>`) live in Supabase's `extensions` schema. With `rag` alone, Day 15's `VECTOR(1536)` columns and `ORDER BY embedding <=> :q` would fail to resolve. The alternative is qualifying every use as `extensions.vector` / `OPERATOR(extensions.<=>)` in code. Unqualified objects are still *created* in the first schema (`rag`), so isolation is unchanged, and `extensions` holds no data. **Please confirm or overrule.**
10. **"No rights on `public`"**: the new roles get `USAGE` on `public` through the `PUBLIC` pseudo-role (a Postgres default the catalog check shows). It can't be revoked per role, only from `PUBLIC` as a whole, which could affect the other app. What it actually allows today: seeing object names (the catalogs are readable anyway) and calling the 1 `PUBLIC`-executable function, `rls_auto_enable`, an event-trigger function that can't be called directly. No `CREATE`, no tables, no sequences. The verification reports exactly this. I'd leave `PUBLIC` alone; say if you want the project-wide revoke instead.
8. **Doc drift found**: `docs/architecture/layout.md:59` puts the chunk model on Day 13 (it is Day 15). The fix is included in Checkpoint 6. `docs/posts/README.md` has no Day 13 row, so only post 9 gets a line unless you add one.

## Day 14 notes — SQLite → Postgres copy
Measured on Day 13 (2026-11-11), Checkpoint 4. The baseline `7cb8829683ab` applies cleanly on both dialects:
- SQLite: `test_migrations.py`, plus the two stamped files.
- Postgres 17: the local `rag` schema, where `alembic check` reports no diff.

These are the differences Day 14's copy script has to handle:

| Model type | SQLite (source) | Postgres (target) | What the copy must do |
|---|---|---|---|
| `Integer` primary key | `INTEGER PRIMARY KEY` (rowid alias; freed ids are reused, the B1 residual) | `integer` + `nextval('<table>_id_seq')`, the **only** server defaults in the schema | Insert the ids as they are (foreign keys depend on them), then **reset every sequence**: `select setval('<table>_id_seq', coalesce(max(id), 1), max(id) is not null) from <table>` for all 7 tables. Otherwise the next insert collides with a copied id. |
| `DateTime` | `DATETIME`, stored as **text** (`2026-11-08 10:06:12.345678`) | `timestamp without time zone` | **Parse the text** into `datetime` (reading through SQLAlchemy models does it; raw `sqlite3` doesn't). Values are naive UTC on both sides; keep them naive. |
| `Boolean` | `BOOLEAN`, stored **0/1**, no CHECK | `boolean` | **Convert 0/1 → false/true** (`users.is_active`, `documents.is_active`). Postgres rejects an integer for a boolean. |
| `Float` | `FLOAT` (REAL, 8 bytes) | `double precision` | Nothing; same precision (`concept_maps.confidence_score`). |
| `String` / `Text` | `VARCHAR` / `TEXT` | `character varying` (no length) / `text` | Nothing. |
| Defaults: `is_active`, `doc_version`, `version`, `topic`, `node_count`…, every `created_at` / `timestamp` | **Python-side only** (`Column(default=…)`); no server defaults (both SQLite files checked) | Python-side only | **Carry every column explicitly.** A raw `INSERT` that omits one gets `NULL`, not the ORM default. Count NULLs per column before and after. |
| Type strictness | stores `'5'` in an integer column silently | `integer = text` is an error | Cast ids to `int`. The `str(user_id)` filters are fixed in Checkpoint 5. |

Also for Day 14:
- **Production data lives on Render, not in either local database.** The first step of Day 14 is to check whether the Render backend service has a **persistent disk** mounted at `/app/backend/data` (Render dashboard → the service → Disks). CLAUDE.md lists this as not verified.
  - **No disk:** production's SQLite file is recreated empty on every deploy and restart. There may be nothing durable to migrate; only what accumulated since the last deploy exists, and it disappears at the next one. Day 14's copy then targets the local databases (or nothing), and "users log in after the move" means re-registering.
  - **A disk:** production's `app.db` is the real source. It must be backed up (Render shell or a one-off download) before anything else, and it is **not stamped**. Do **not** merge Day 13's migrate-before-uvicorn `CMD` to `master` before it is either stamped or replaced by the Postgres copy: `upgrade head` on an unstamped, populated SQLite would fail with "table users already exists" and the deploy would crash-loop.
- **Copy order follows the foreign keys:**
  1. `users`
  2. `sessions`, `documents`, `concept_maps`
  3. `messages`, `failed_queries`, `concept_map_nodes`

  Otherwise defer the constraints in one transaction.
- **Sources:** two SQLite files, each stamped at `7cb8829683ab`, with backups:
  - host `backend/data/app.db`: 2 users / 2 sessions / 16 messages / 2 documents / 1 failed query / 1 concept map / 20 nodes. Backup: `backend/data/app.backup-2026-11-11.db`.
  - Docker `data` volume: 3 / 3 / 10 / 3 / 0 / 2 / 12. Backup: `backend/data/app.docker-backup-2026-11-11.db`.

  They are **separate user populations whose ids overlap** (both start at 1). Decide which one is the source of truth before copying; merging them needs id remapping.
- **The target schema is created by Alembic**, never by the copy script: `alembic upgrade head` first, then copy data only. The copy must leave `alembic_version` alone.

## Outcome
Done 2026-11-11 → 2026-11-12. Six checkpoints and six commits on `feature/day13-postgres` (PR #17, draft): `e95ef81`, `c02b5e6`, `52ca646`, `ac795d6`, `cd188ff`, `16584fe`, plus this docs commit. 59 files changed against `develop` before the docs commit.

### What changed against the plan
- **Hosting (owner, on approval):** no new Supabase projects. The existing project holds schemas `rag` / `rag_staging`, each owned by its own login role, with `search_path = <schema>, extensions` (Risk 9: `extensions` added so pgvector resolves) and no Data API exposure. `PUBLIC` was left as is (Risk 10). Decision 5 was settled by the catalog: Postgres 17.11, so the local image is `pgvector/pgvector:0.8.2-pg17`, the exact pgvector version.
- **Added on request:**
  - local parity: `scripts/postgres/init-rag-schema.sh`, shared by compose and CI
  - CI Postgres service: `alembic upgrade head` + `alembic check`, then `test_repositories.py` on Postgres
  - SQLite backups before stamping, and the "Day 14 notes" (types, sequences, Render disk)
  - a narrowed `alembic downgrade` guard instead of the blanket block
  - a commit after every checkpoint
- **Found during implementation, fixed the same day:**
  - **`lastrowid` (Checkpoint 5):** `session_service.add_message` used a raw INSERT + `lastrowid`, which gives no row id on Postgres. The SSE `message_id` would have been null and feedback broken. It now goes through `messages_repo.add`.
  - **`str(user_id)` (Checkpoint 5):** 5 filters + 3 inserts compared or stored `str(user_id)` in integer columns. Measured on Postgres 17: `operator does not exist: integer = character varying`.
  - **Autogenerate (Checkpoint 4):** with `version_table_schema`, autogenerate wrote `op.drop_table('alembic_version')`. Fixed with an `include_name` filter.
  - **Silent rollback (Checkpoint 4):** `env.py`'s schema-guard SELECT auto-began a transaction, so `upgrade` ran and was rolled back silently. Fixed with `engine.begin()`.
  - **Conftest (Checkpoint 2):** with the absolute SQLite default, the test suite would have written to the real `backend/data/app.db`. `conftest` now sets its own `DATABASE_URL`.
  - **GitGuardian (Checkpoints 1–3):** it flagged dev-default passwords, then the `${VAR:?message}` form. Now the bare `${VAR:?}` form is used, with no password in any tracked file. The 6 old incidents stay in history (`e95ef81`, `c02b5e6`); the owner resolves them as false positives.
  - **Supabase setup script (Checkpoint 6), three iterations caught by dry runs:**
    - the result grid echoed the passwords
    - an owner-only `REVOKE` failed
    - the error context quoted the password
    - then the owner spotted that the SQL editor sends the script as **one** query, so `log_statement = ddl` logs it whole. Proved: 2 of 2 test passwords in the server log. Final version: SCRAM verifiers only (`scripts/supabase/scram_verifier.py`), with 0 passwords in the log or `pg_stat_statements`.
- **Not done / deferred:** the app still runs on SQLite (Decision 2, Day 14). `rag` (production) is empty (Day 14). The keep-alive can't run before it reaches `master` (Day 17). The Postgres CLI downgrade round trip was skipped on request: `test_migrations` covers downgrade on SQLite, CI covers upgrade + check on Postgres.
- **Correction to Risk 8:** `docs/posts/README.md` maps Day 13 to post 3 (days 13–17). The brief wrongly said there was no row; post 3 got today's material entry.

### Files (against `develop`)
- **Settings and driver:**
  - `requirements.in`, `requirements.txt`: `psycopg[binary]==3.3.8`; the lock gains only psycopg + psycopg-binary, 136 → 138
  - `backend/app/core/config.py`: `DATABASE_URL` (`SecretStr`, absolute SQLite default), `DATABASE_SCHEMA`, scheme validator
  - `.env.example`
- **Database package:**
  - new `backend/app/db/{base,session,migrations}.py`
  - new `db/models/{user,chat_session,message,document,failed_query}.py`; `db/models/__init__.py`, `concept_map.py` updated
  - new `db/repositories/{__init__,users,sessions,documents,messages,failed_queries}.py`
  - `db/database.py` deleted
- **Callers:** `api/deps.py`; `api/routes/{auth,chat,concepts,documents,feedback,quiz,sessions,users}.py`; `services/{account_service,chat_pipeline,document_service,session_service}.py`; `main.py` (lifespan head check); `eval/cache_tuner.py`, `eval/retrieval/mine_feedback.py`.
- **Alembic:** `alembic.ini`, `alembic/env.py`; `versions/1e5877c62358_…` deleted; `versions/7cb8829683ab_baseline_schema.py` new.
- **Docker:** `Dockerfile` (ships `alembic/`, `CMD` migrates first), `.dockerignore`, `docker-compose.yml` (postgres service, required passwords), `docker-compose.override.yml`.
- **Scripts:** `.gitattributes` (`*.sh` LF), `scripts/postgres/init-rag-schema.sh`, `scripts/supabase/{setup_rag_schemas.sql,scram_verifier.py}`.
- **CI:** `.github/workflows/ci.yml` (`backend` job), `.github/workflows/supabase-keepalive.yml` (new).
- **Tests:** `backend/tests/{conftest,test_config,test_account_service,test_document_service}.py`; new `test_migrations.py`, `test_repositories.py`.
- **Hooks:** `.claude/hooks/guard_commands.py` (target-aware downgrade guard), `.claude/hooks/edit_reminders.py` (the new `alembic/versions/` reminder).
- **Docs:** `CLAUDE.md` (sections plus Current Status), `docs/architecture/layout.md`, `docs/timeline.md` (Days 13, 14, 15, 21), `docs/improvement-tracker.md` (T2 Done), this brief, `docs/posts/03-hybrid-search-postgres.md`, `docs/posts/09-launch-recap.md`.

### Checks
| Check | Result |
|---|---|
| Offline suite, host (3.12) | 244 → **269 passed** (+7 config, +7 migrations, +11 repositories) |
| Offline suite, container (Linux / 3.11) | 258 passed after Checkpoint 4 (the last container run) |
| ruff 0.15.18 | clean |
| CI on `16584fe` | `backend` 1m55s (Postgres steps: baseline ran, **no new upgrade operations**, repositories **11/11**, suite 269), `frontend` 39s, `docker` 17s |
| Alembic, local Postgres (`rag`) | `upgrade head` → 7 tables + `rag.alembic_version`, nothing in `public`; `alembic check` = no diff |
| Alembic, Supabase `rag_staging` | `upgrade head` → 8 tables, 12 indexes, 7 sequences, all in `rag_staging` and owned by `rag_staging_app`; `check` = no diff; `public` unchanged (2 tables) |
| SQLite stamp | both files: `compare_metadata` differs only in the `uq_users_email` name and has no server defaults; stamped at `7cb8829683ab`; row counts unchanged (host 2/2/16/2/1/1/20, Docker 3/3/10/3/0/2/12); dev container healthy, "Database schema is at head" |
| Supabase verification (MCP, catalog only) | roles LOGIN-only with SCRAM secrets; schemas owner-only; no cross-schema access; API roles have no USAGE on either schema; in `public`: USAGE via `PUBLIC` only, 0 tables / 0 sequences, 1 EXECUTE (`rls_auto_enable`, an event-trigger function that can't be called directly); `vector` 0.8.2 in `extensions`; advisors: no new findings |
| Guard hook | **29/29** cases as expected (JSON-payload harness) |
| Docker image | builds; `alembic -c /app/alembic.ini heads` → `7cb8829683ab` |

### UI integration
| Backend change | Frontend file | What the user sees |
|---|---|---|
| Settings, model split, Alembic, startup head check | — | backend-only: schema and startup mechanics; no endpoint, field or status changed |
| Repositories, int `user_id` filters, ORM message insert | — | backend-only: every response shape unchanged (`test_api_smoke.py` passes unmodified); same `message_id` frame |
| Postgres (local, CI, Supabase), keep-alive | — | backend-only: infrastructure; the app stays on SQLite until Day 14 |

### Numbers for the tracker
T2: suite 244 → 269; `alembic check` no diff on local / CI / staging; 5 `str(user_id)` filters + 3 string-id inserts + 1 `lastrowid` fixed; Supabase setup logs 0 passwords (single-query dry run: 2 of 2 before the verifier change).
