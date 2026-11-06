# Day 7 — Target layout and the core package
Date: 2026-11-06 · Phase 3 — Codebase refactor: proper package structure · Items: none
Branch: feature/day07-refactor-core

## Scope
1. **`docs/architecture/layout.md`.** The target tree (`backend/app/{api/routes, core, db, ingestion, retrieval, generation, services, schemas}`, plus `backend/tests`, `backend/eval`, `backend/scripts`; `frontend/` unchanged). It maps every current module to its target package and to the day that moves it. **Approved before anything moves** (Checkpoint 1 is only this file).
2. **One pydantic-settings `Settings` class** for every environment variable the backend reads. It replaces `config/oauth_config.py` and removes every `os.getenv` / `load_dotenv` from the app code.
3. **`core/logging.py`.** The rotating file and console handlers that already exist (`logger.py`), plus a request-ID filter ready for Langfuse.
4. **Package imports** (`from app.core.config import settings`) replace bare-name imports, and **file history follows the moves**.
   - **As written, `git mv` isn't possible for Claude:** `/run-day` forbids git writes. The result is identical with plain moves — see The concept → *git and renames* and Decision 2.
5. **Verify:** CI green after each move, and `uvicorn app.main:app` starts.

**Not in the timeline but forced by item 5** (see Decision 1):
- `uvicorn app.main:app` can only start if `main.py` and everything it imports are importable as `app.*`. So today the whole `src/` tree becomes `backend/app/`, flat, and `tests/` becomes `backend/tests/`.
- The deploy files follow it today: Dockerfile, compose files, `dev.ps1`, `pytest.ini`, `.dockerignore`, `alembic/env.py` and the hook paths. Day 8's bullet "Update Dockerfile WORKDIR/CMD, docker-compose…" moves up to today, and Day 8 becomes pure regrouping inside the package.

**Also in `core/` today:** `security` (`auth.py`) and `errors` (`error_handler.py`), so the timeline's four `core/` modules all exist. These are pure moves with no logic change.

## Current behavior
1. **No layout doc.** The backend is 62 flat modules in `src/`, plus three small sub-packages: `config/`, `routes/` and `services/`.
   - **Bare-name imports** work only because the CWD is `src/`:
     - `uvicorn main:app` runs from `src/` (`Dockerfile:47,58`, `docker-compose.override.yml:6`).
     - Tests insert `src` into `sys.path` (`pytest.ini:3`, `tests/conftest.py:25-27`, and again in 11 test files, e.g. `tests/test_chat_guards.py:9`).
   - **Measured:** 150 bare local-import lines in 46 files. 6 of them are lazy imports inside functions (`main.py:813,985,1135,1192`, `chunking.py:42`, `chunk_builder.py:136`).
2. **Configuration is scattered.**
   - **One partial settings class:** `config/oauth_config.py:5-20` covers only Google OAuth and JWT. It reads `.env` relative to the CWD (`:18`), so it works only because `load_dotenv()` has already populated `os.environ`.
   - **Direct env reads:**
     - `load_dotenv()` + `os.getenv("GEMINI_API_KEY")` is repeated in `llm_client.py:16-17`, `embedding_service.py:14-15`, `reranker.py:14-15`, `topic_classifier.py:16-17` and `concept_extractor.py:33-34`.
     - `load_dotenv()` also runs at import time in `web_search_client.py:7` and `ocr_utils.py:7`.
     - `REDIS_URL`: `cache.py:7`, `web_cache.py:6`. `SEMANTIC_CACHE_REDIS_URL` → `REDIS_URL` → default fallback: `semantic_cache.py:17-25`. `TAVILY_API_KEY`: `web_search_client.py:38`. `TESSERACT_PATH`: `ocr_utils.py:11`. `BASE_URL`, `FRONTEND_URL`: `routes/auth_routes.py:34,106,117`.
     - `JWT_SECRET_KEY` with a random fallback is unreachable, because `auth.py` already requires the key: `main.py:58`. `ALLOWED_ORIGINS`: `main.py:62-69`.
   - **Two import paths for one file:**
     - `services/oauth_service.py:3` imports `src.config.oauth_config`.
     - `auth.py:10` and `routes/auth_routes.py:7` import `config.oauth_config`.
     - Python loads that file twice, as two modules with two settings objects.
     - The same `src.` style appears in `update_existing_sessions.py:6` and `alembic/env.py:13`.
3. **Logging** (`logger.py:82-113`):
   - **Handlers:** `setup_logging()` adds a rotating `logs/app.log` (5 MB × 3) and a console handler to the `rag_assistant` logger. Both are idempotent and carry G8 redaction (`:15-76`).
   - **No request correlation:** the format is `asctime - level - name - message` (`:102-104`). Two concurrent chats interleave their lines with nothing to tell them apart.
   - **Root handlers:** three modules still call `logging.basicConfig` (`concept_extractor.py:15`, `hybrid_retriever.py:19`, `concept_map_service.py:17`).
4. **Paths depend on the CWD:**
   - The DB, uploads and logs: `db.py:82-86` (`data/app.db`), `upload_storage.py:12` (`uploads`), `logger.py:100` (`logs/app.log`).
   - These folders are **gitignored**, so moving the tracked files leaves them behind in `src/`. In Docker, named volumes mount at `/app/src/{data,uploads,logs}` (`docker-compose.yml:26-28`).
5. **CI** (`.github/workflows/ci.yml`) runs `ruff check .` and `python -m pytest -q` from the repo root and builds the `Dockerfile`. None of it names `src/` directly; `pytest.ini` and the Dockerfile do.
   - **Baseline, measured today:** `python -m pytest` → **111 passed, 1 xfailed in 36.8 s**. `ruff check .` → all checks passed.

## Why it matters
1. **No agreed layout.** Days 8–9 move ~60 files. Without a written map, each move is decided ad hoc, and "where does `semantic_cache.py` go?" gets answered three different ways. The doc makes the moves mechanical and reviewable.
2. **Scattered config:**
   - **Delayed failures:** a typo in `.env` (`GEMINI_APIKEY`) surfaces only when the first object that needs the key is built, deep inside an import chain. A wrong type (`JWT_EXPIRATION_MINUTES=7d`) surfaces only at first use.
   - **Double-loaded module:** `config.oauth_config` and `src.config.oauth_config` are two separate module objects. A test or Day 9 dependency override that patches one silently misses the other.
   - **Implicit loading:** `load_dotenv()` only works if it happens to run first, so import order decides whether the config exists.
3. **No request ID.** When a Day 23 Langfuse trace shows a slow chat, there's no way to find that request's lines in `app.log` among a dozen concurrent requests. That's the same gap O1 tracks, on the logging side.
4. **Bare imports:**
   - **Name clashes:** `models.py`, `db.py`, `cache.py`, `logger.py` and `config` are generic names. Any installed package or new top-level module with the same name shadows them, depending on `sys.path` order.
   - **No real packages:** `ingestion/`, `retrieval/` and so on can't exist as packages while every module imports its siblings by bare name.
   - **Lost history:** moving files with large rewrites in the same commit drops `git log --follow` history. Rename detection is a similarity heuristic (see The concept).
5. **Verification:** each step must stay green on CI's clean checkout. A stale `src/__pycache__` on the host can hide a broken import.

## The concept

### Package layout: why `backend/app/` and layered packages
A Python *package* is a directory with `__init__.py` that you import by its dotted path.
- **The timeline's layout is layered:**
  - `api` (HTTP) → `services` (use cases) → `retrieval` / `generation` / `ingestion` (domain capabilities) → `db` (persistence)
  - `core` sits underneath everything: config, logging, security, errors.
- **The rule that makes layering worth it:** dependencies point **downward only**.
  - `core` imports nothing from the app.
  - `retrieval` never imports `api`.
  - Routers are thin: they parse the request, call a service and shape the response.
- **Why it pays off:**
  - **Circular imports become rare.** Today `main.py` is both the router and the place every singleton lives, and the eval scripts must `import main` (CLAUDE.md: "Eval and experiment code must not `import main`").
  - **Each layer can be tested by replacing the one below it** (Day 9's `Depends`).
- **Alternative: feature-based packages** (`chat/`, `documents/`, each with its own routes, service and models). These scale better in big teams, but they duplicate retrieval plumbing that chat, concept maps and quizzes all share. Layered fits this app's one shared retrieval core.

The extra `backend/` level separates the *deployable Python project* (app, tests, eval, scripts) from the repo's other projects (`frontend/`, `docs/`, `.github/`). The package is still called `app`. This is the convention in FastAPI's full-stack template.

### How Python finds modules: `sys.path`, the CWD and `-m`
`import x` searches `sys.path` in order.
- **What `sys.path[0]` is:**
  - `python script.py` → the script's directory
  - `python -m pkg.mod` → the CWD
  - `uvicorn main:app` → the CWD, which uvicorn adds itself
- **Why the bare imports work today:** the CWD is `src/`, so `db.py` is the top-level module `db`.
- **The pitfalls:**
  - **The same file under two names** (`config.oauth_config` vs `src.config.oauth_config`): two module objects with two copies of module-level state.
  - **Shadowing:** a local `logging.py` placed on `sys.path` hides the standard library's `logging` (hence `core/logging.py` must only ever be imported as `app.core.logging`).
  - **`sys.path.insert` hacks** in scripts and tests, which hide the real import path from tools.
- **The fix:** one root on `sys.path` (`backend/`) and absolute imports from the package name (`from app.db import User`). Python 3 has no implicit relative imports, so inside `app/core/logging.py`, `import logging` still means the standard library.

### Twelve-factor config with pydantic-settings
Twelve-factor rule III: *configuration lives in the environment*, separate from code, so one build runs in dev, CI, staging and prod. A typed settings object adds:
- **Validation at startup (fail fast):** missing or malformed config stops the process at boot, with every problem listed at once, instead of failing on the first request that needs it.
- **One source of truth:** every variable, its type and its default in one file. `.env.example` can be checked against it.
- **Precedence**, highest wins: init kwargs → **environment variables** → the `.env` file → field defaults. So CI and Render (real env vars) override any `.env`, and tests override everything by setting env vars before the first import (what `conftest.py` already does).

Pitfalls:
- **Relative `env_file`:** resolved against the CWD, which changes between uvicorn, pytest and Docker. Use an absolute path computed from `__file__`. A missing file is silently skipped, which is right for Docker and CI.
- **Lists from env vars:** pydantic-settings parses `list[str]` fields as **JSON**. `ALLOWED_ORIGINS=https://a,https://b` would fail to parse. Keep it a `str` and split it in a property.
- **"Unset" vs "default":** today `SEMANTIC_CACHE_REDIS_URL` → `REDIS_URL` → `redis://localhost:6379/1`. A *default* on `REDIS_URL` would erase the difference between "unset" and "set to the default", and change which DB the semantic cache uses. Keep both optional and resolve the fallback in one property. The existing test `test_defaults_to_db_1_when_nothing_is_set` guards this.
- **Secrets in reprs:** `print(settings)` or an exception that includes it would dump keys into logs. `SecretStr` renders as `**********` and needs an explicit `.get_secret_value()`. That's a deliberate, greppable act (Decision 4, ties to G8).
- **Singleton vs fresh read:** today `WebSearchClient` reads `TAVILY_API_KEY` at construction, so a test's `monkeypatch.setenv` takes effect. A cached settings object doesn't see later env changes; tests must patch the object instead.

### Request IDs and `contextvars`
A **correlation ID** is a short random ID assigned when a request arrives. Every log line, outbound call and trace span for that request carries it, so you can filter one request out of interleaved logs and join logs to traces (Langfuse on Day 23) and to the client's error report.

**How it works in Python:**
- A `contextvars.ContextVar` holds the current ID. asyncio gives each task its own copy of the context, so concurrent requests on one event loop never see each other's ID.
- Starlette runs sync endpoints in a thread pool through anyio, which carries the context into the worker thread. Today's test checks this with a sync route instead of assuming it.

**Where the pieces go:**
- **A middleware sets the ID** at the start of each request and echoes it in an `X-Request-ID` response header.
  - **Use a pure ASGI middleware, not `BaseHTTPMiddleware`.** The latter wraps streaming responses and has a history of contextvar and streaming bugs. This app's main endpoint is SSE.
- **A `logging.Filter` reads it** and stamps `record.request_id`, so the formatter can print `%(request_id)s`. Lines logged outside a request (startup) get `-`.
- **Never trust an incoming ID blindly:** an attacker-chosen `X-Request-ID` containing newlines would forge log lines (log injection). Accept a client's ID only if it matches a strict pattern (`[A-Za-z0-9._-]{1,64}`); otherwise generate one.

### git and renames: why `git mv` isn't magic
Git stores snapshots, not renames. `git mv a b` is exactly `mv a b; git rm --cached a; git add b`.
- **How renames are detected:** at diff or log time, by **content similarity** (default ≥ 50%). `git log --follow app/core/config.py` finds the old history only if some commit shows the old and new paths similar enough.
- **The practical rule:** **commit moves separately from rewrites.**
  - A commit that moves a file *and* rewrites most of it shows as delete + add, and the history chain breaks.
  - Changing a few import lines keeps similarity high, so moves plus import fixes in one commit are fine.
  - Turning a 25-line `oauth_config.py` into an ~90-line `Settings` module is not. It goes in a later commit than its move.

### Common pitfalls of a big-bang move
- **Stale `__pycache__` or leftover files** make broken imports pass locally. CI's fresh checkout is the real test, which is why the timeline says "CI green after each move".
- **String references** to module paths break silently: `uvicorn main:app` in Dockerfile and compose, `sys.modules.get("db")` (`conftest.py:129`), patch targets, hook regexes like `^src/main\.py$`, and `.dockerignore` entries.
- **CWD-relative runtime state** silently moves with the CWD. The app starts fine with an *empty* database, which looks like data loss.

## Decisions

### 1. How much moves today
- **A — The whole tree today, flat:**
  - `src/*` → `backend/app/` and `tests/` → `backend/tests/` in one move, all imports rewritten to `app.*`, and the deploy files (Dockerfile, compose, `dev.ps1`, `pytest.ini`, `.dockerignore`, alembic, hooks) updated today.
  - **Trade-off:** today's diff is large (~150 import lines in 46 files, done mechanically). But every path changes exactly once, `uvicorn app.main:app` works today as the timeline's Verify demands, and Day 8 becomes pure moves inside one package.
- **B — Only `core/` today, inside `src/`:**
  - Create `src/core/` with bare imports and keep `uvicorn main:app`. Day 8 does the `src` → `backend/app` move and the `app.*` rewrite.
  - **Trade-off:** today is smaller, but the timeline's Verify ("`uvicorn app.main:app` starts") can't be met, and every `core` import is written twice (bare today, `app.` tomorrow).
- **Recommendation: A.** It's the only option that satisfies today's Verify. Doing every path change once also means the deploy files are touched in one reviewed step instead of two.

### 2. How the moves are recorded
- **A — Claude moves the files on disk; you stage and commit at the checkpoint boundary:**
  - `git add -A` records exactly what `git mv` would, because `git mv` is mv + add (see The concept).
  - **Trade-off:** `git status` shows deletes and untracked files until you stage. That's cosmetic.
- **B — Claude writes a `git mv` script and you run it:**
  - The paths are staged immediately.
  - **Trade-off:** an extra hand-off for no difference in the resulting history.
- **Recommendation: A**, with checkpoints arranged so the pure-move commit lands before any file is heavily rewritten.

### 3. How code gets the settings
- **A — Module-level singleton `settings = Settings()`** in `app/core/config.py`, imported as `from app.core.config import settings` (the timeline's own example).
  - Tests override fields with `monkeypatch.setattr(settings, ...)`.
  - **Trade-off:** it's a global, but so is everything that reads it until Day 9's app factory, which can wrap it in `def get_settings() -> Settings`.
- **B — `@lru_cache get_settings()` everywhere:** the FastAPI-docs pattern, injectable with `Depends`.
  - **Trade-off:** module-level clients (`cache.py:8` builds Redis at import) can't use `Depends` yet, so most call sites would call `get_settings()` at import anyway, with cache-clearing needed in tests.
- **Recommendation: A** today. Day 9 adds the `Depends` wrapper when the singletons move into the lifespan.

### 4. `SecretStr` for secrets
- **A — Secrets as `SecretStr`:** `GEMINI_API_KEY`, `TAVILY_API_KEY`, `JWT_SECRET_KEY`, `GOOGLE_CLIENT_SECRET`.
  - Call sites use `.get_secret_value()` (about 9 places), and `repr(settings)` or a traceback never shows them.
  - **Trade-off:** slightly noisier call sites.
- **B — Plain `str`, as `oauth_config.py` has today:**
  - **Trade-off:** simpler, but one careless `logger.info(settings)` puts every key in `app.log` and Render's logs. The G8 redaction filter only knows JWT and `token=` patterns, not API keys.
- **Recommendation: A.** It extends G8's "secrets never reach logs" from tokens to keys at almost no cost.

### 5. Request ID: filter only, or filter + middleware
- **A — Filter + contextvar + pure ASGI middleware today:**
  - The middleware sets an ID per request: the client's `X-Request-ID` if it matches `[A-Za-z0-9._-]{1,64}`, otherwise a new `uuid4().hex`. It also returns the ID as the `X-Request-ID` response header.
  - **Trade-off:** ~40 more lines today, and they touch `main.py` (one `add_middleware` line).
- **B — Filter + contextvar only:** the middleware arrives with Day 9's app factory or Day 23's Langfuse.
  - **Trade-off:** less code today, but every line logs `request_id=-` until then, so "ready for Langfuse" can't be verified.
- **Recommendation: A.** Without something setting the ID, the filter is untestable, and that's the kind of silently-does-nothing code the global rules forbid.

## Approval (2026-11-06)
Decisions **1A, 2A, 3A, 4A, 5A** approved, with these conditions:
- **Checkpoints 2 and 3 are one commit point (one push).** After Checkpoint 2 alone, the Dockerfile still copies `src/`, so the required `docker` check would go red.
- **Moves and rewrites stay in separate commits.** The PR is merged with a merge commit, never squashed, so rename history survives.
- **Before each commit point,** Claude shows `git status` and confirms that nothing under `backend/data`, `backend/uploads` or `backend/logs` is listed.
- **At the end of today, Claude updates CLAUDE.md's "Run the backend from `src/`" line and Key Commands** (not Current Status).
- **Render** runs the Dockerfile's `CMD`: Root Directory empty, Dockerfile Path `./Dockerfile`, build context `.`, Docker Command empty. Today's Dockerfile change is all Day 10 needs, so there's no dashboard change. This is recorded in the Day 10 release bullet in `docs/timeline.md`.
- **CI runs through a draft PR into `develop`** (opened by the owner), so it runs on each push.

Commit points therefore:
1. Checkpoint 1 (layout doc + brief)
2. Checkpoints 2 + 3 (move, imports, deploy paths)
3. Checkpoint 4 (`core/` pure moves)
4. Checkpoint 5 (Settings + request-ID rewrites)
5. Checkpoint 6 (docs)

## Plan

`backend/app/` is the package. The CWD for running is `backend/`.

**Checkpoint 1 — layout doc (1 file). STOP for approval.**
- `docs/architecture/layout.md` (new):
  - the target tree
  - a table: every current module (CLAUDE.md module map) → target path → the day it moves (7, 8, 9 or 10, or deleted on Day 10)
  - the dependency rule (downward only)
  - where runtime state lives (`backend/data`, `backend/uploads`, `backend/logs`)

**Checkpoint 2 — the move (pure moves + import rewrite). Commit point "day 07 - move src/ to backend/app/ and tests/ to backend/tests/".**
- Move every tracked `src/**/*.py` → `backend/app/` (same relative paths; `src/__init__.py` becomes `backend/app/__init__.py`) and `tests/` → `backend/tests/` (including `samples/`, `fakes.py`, `__init__.py`).
  - `src/requirements.txt` stays where it is: Day 10 deletes it, and it doesn't belong inside a package.
- Rewrite imports with a one-off script in the scratchpad (not committed). It rewrites only `from|import <one of the 62 module names | config | routes | services>` to the `app.` form, including the 6 lazy imports, and the `src.` imports (`oauth_service.py:3`, `update_existing_sessions.py:6`). The script stays out of the repo; you get the `git diff --stat` and a sample.
- `sys.path.insert(... 'src')` lines: remove the 11 in tests and the one in `hybrid_retriever.py:12`; `run_migration.py:7` and `update_existing_sessions.py:4` are fixed to the new root. `tests/conftest.py`: `REPO_ROOT` and `SAMPLES_DIR`, the `sys.path` setup, `sys.modules.get("app.db")`, `import app.main`.
  - `test_llm_modes.py:13`: the `ChatInput.js` path gets one more `parents` level. `test_docx_pdf_utils.py`: its CWD-relative `tests/samples/...` paths are anchored to `__file__`.
- `pytest.ini`: `testpaths = backend/tests`, `pythonpath = backend`.
- Check: `python -m pytest` (same 111 + 1 xfail), `ruff check .`, `py_compile` on every moved file.

**Checkpoint 3 — deploy and tooling paths. Can share Checkpoint 2's commit, or have its own.**
- `Dockerfile`: `COPY backend/app/ ./backend/app/`, runtime dirs `backend/{data,uploads,logs}`, `WORKDIR /app/backend`, `CMD … uvicorn app.main:app …`.
- `docker-compose.yml`: volume mount points `/app/backend/{data,uploads,logs}`. The named volumes keep their data.
- `docker-compose.override.yml`: `uvicorn app.main:app … --reload-dir /app/backend/app`, bind mounts `./backend/app` and `./backend/tests:ro`, and the frontend mount path.
- `scripts/dev.ps1`: `pytest /app/backend/tests`.
- `.dockerignore`: `backend/data/`, `backend/uploads/`, `backend/logs/`, `backend/tests/`.
- `alembic/env.py`: `sys.path` → `backend/`, `from app.db import Base`. Behaviour otherwise untouched (T2, Day 13).
- `.claude/hooks/guard_commands.py` (the DB guard must protect `backend/data`, or it guards nothing during Days 7–10) and `.claude/hooks/edit_reminders.py` (path regexes).
- Check: `docker compose config` (both modes), `docker build` of the backend, `uvicorn app.main:app` from `backend/` → `/health` 200.

**Checkpoint 4 — `core/` package: pure moves. Commit point before Checkpoint 5.**
- Move `logger.py` → `core/logging.py`, `auth.py` → `core/security.py`, `error_handler.py` → `core/errors.py`, `config/oauth_config.py` → `core/config.py`, plus `core/__init__.py`. Delete the empty `config/` package.
- Update their importers (about 15 import lines). Check: pytest, ruff.

**Checkpoint 5 — Settings + request-ID logging (rewrites).**
- `app/core/config.py`: `Settings(BaseSettings)` with every variable:
  - **Secrets:** `GEMINI_API_KEY`, `TAVILY_API_KEY` (default empty), `JWT_SECRET_KEY`, `GOOGLE_CLIENT_SECRET` (`SecretStr` per Decision 4).
  - **Other values:** `GOOGLE_CLIENT_ID`, `GOOGLE_REDIRECT_URI`, `JWT_ALGORITHM`, `JWT_EXPIRATION_MINUTES`, `REDIS_URL` and `SEMANTIC_CACHE_REDIS_URL` (both optional), `BASE_URL`, `FRONTEND_URL`, `ALLOWED_ORIGINS` (str), `TESSERACT_PATH`.
  - **Properties:** `redis_url`, `semantic_cache_redis_url`, `allowed_origins`.
  - **`.env` lookup:** `env_file` = absolute repo-root `.env`, `extra="ignore"`.
  - **Left out:** `PORT` (read only by the Dockerfile's shell) and `DATABASE_URL` (unread until Day 13).
- Replace every env read and `load_dotenv` in:
  - `llm_client.py`, `embedding_service.py`, `reranker.py`, `topic_classifier.py`, `concept_extractor.py`
  - `web_search_client.py`, `ocr_utils.py`, `cache.py`, `web_cache.py`, `semantic_cache.py`
  - `main.py` (CORS + SessionMiddleware), `routes/auth_routes.py`, `services/oauth_service.py`, `core/security.py`
  - `scripts/manual/*` is left for Day 10.
- `app/core/request_id.py` (new): the `ContextVar`, `RequestIdMiddleware` (pure ASGI) and the header validation.
- `app/core/logging.py`: a `RequestIdFilter` on both handlers; the format gains `[%(request_id)s]`.
- `main.py`: `app.add_middleware(RequestIdMiddleware)`.
- Tests:
  - `backend/tests/test_config.py` (new): defaults, `ALLOWED_ORIGINS` split and trim, the semantic-cache URL fallback (the three Day 4 tests move here from `test_semantic_cache.py` and are rewritten against `Settings`), a missing required variable raising `ValidationError`, and `SecretStr` not leaking in `repr`.
  - `backend/tests/test_request_id.py` (new): an ID is generated and returned, a valid incoming ID is echoed, a malicious one is replaced, a log line from a sync route and from the SSE stream carries the ID, and concurrent requests get different IDs.
  - `conftest.py`'s `web_search` fixture patches `settings.TAVILY_API_KEY` instead of the env var.
- `.env.example`: check that it lists exactly the Settings fields. No new variables.
- Check: pytest, ruff, uvicorn from `backend/`, `docker compose up` → `/health` with an `X-Request-ID` header, and the ID visible in `docker compose logs backend`.

**Checkpoint 6 — wrap-up:** brief Outcome, the post 9 line, learning notes check.

**New dependencies:** none (`pydantic-settings` and `python-dotenv` are already pinned).

## UI integration
**All of today's work is backend-only — no user-visible change:**
- The layout move, Settings and logging are internal refactors.
- **`X-Request-ID` is a response header meant for log correlation, not something the UI shows.** The chat stream is consumed with `EventSource` (`ChatWindow.js`), which can't read response headers at all, and showing an "error reference" in the UI belongs with Langfuse (Day 23), where the ID becomes traceable. CORS `expose_headers` is therefore not changed.
- `frontend/` is untouched. Proof: the frontend CI job and Jest suite pass with zero frontend edits.

## Verification
- **Checkpoint 1:** you approve `layout.md`.
- **Checkpoints 2–4:**
  - `python -m pytest` must be **exactly 111 passed + 1 xfailed** (the measured baseline). Any difference is an import or path problem.
  - `ruff check .` must stay clean.
  - `rg "^\s*(from|import) (db|main|auth|…)\b" backend` returns nothing.
  - `git ls-files src` lists only `src/requirements.txt`.
- **Checkpoint 3:**
  - `docker compose config` passes for dev and as deployed.
  - `docker build .` succeeds.
  - `cd backend; uvicorn app.main:app` starts, `/health` returns 200, and `/docs` lists the same routes as before. Today: diff the route list from `app.routes` before and after the move.
- **Checkpoint 5:**
  - The suite plus the new `test_config.py` and `test_request_id.py` pass.
  - `rg "os\.getenv|os\.environ|load_dotenv" backend/app` returns only `rag_metrics.py` (an env *write* in the broken RAGAS file, Day 12).
  - A request to `/health` shows `X-Request-ID` and the same ID in `app.log`.
- **CI:** you push after each commit point (a draft PR into `develop` makes CI run on every push). All three jobs must be green before the next checkpoint starts.
- **No retrieval, prompt or cache behaviour changes today, so there's nothing to measure before and after.** The semantic-cache URL tests prove the cache's DB choice didn't change.

## Risks & open questions
- **Your local data (action needed after Checkpoint 2):**
  - `src/data/app.db`, `src/uploads/` and `src/logs/` are gitignored, so the move leaves them in `src/`, and the app run from `backend/` starts with an empty database.
  - **Move them yourself:** `Move-Item src\data, src\uploads, src\logs backend\`. The guard hook rightly blocks Claude from touching the database.
  - Stored `Document.file_path` values are CWD-relative (`uploads/...`, `upload_storage.py:63-64`), so they stay valid once `uploads/` sits next to the new CWD. Docker named volumes keep their data at the new mount points.
- **Render:** production deploys `master`, which doesn't change until the Day 10 release, so nothing breaks today.
  - **Question:** does the Render service use the Dockerfile's `CMD`, or a custom *Docker Command* / *Root Directory* in its settings? If it uses `CMD`, today's Dockerfile change is all Day 10 needs. If not, the override must be updated at release (timeline Day 10 already notes this).
- **CLAUDE.md is stale for Days 8–9:** "Run the backend from `src/`", the Key Commands and the paths. Day 10 rewrites it.
  - **Question:** shall I update only the convention line and the Key Commands block at the end of today (a few lines, not Current Status), so the next two sessions don't start from wrong instructions?
- **Behaviour change in `test_semantic_cache.py`:** three Day 4 tests move to `test_config.py` and are rewritten against `Settings`, because the function they test now reads the settings object. Same assertions, different setup. The Day 5 smoke tests stay unchanged apart from import lines.
- **Startup failure mode changes slightly.** A missing `GEMINI_API_KEY` now fails at `app.core.config` import with a pydantic `ValidationError` listing every missing variable, instead of `RuntimeError("GEMINI_API_KEY not set")` from `LLMClient`. It's still a failed boot, just a clearer one.
- **Tests still read the developer's real `.env`** for variables `TEST_ENV` doesn't set (`ALLOWED_ORIGINS`, `BASE_URL`, `TESSERACT_PATH`), exactly as `load_dotenv()` did. That's unchanged hermeticity, and CI has no `.env`.
- **Days 8–9 effects:**
  - Day 8's tests change import lines again as modules move into sub-packages. That's unavoidable in any order, and Day 8's "tests pass unchanged" means unchanged *assertions*.
  - Day 8's "Update Dockerfile/compose/alembic" bullet is done today.
- **Left broken until Day 10 deletes them:** the root scripts `recreate_db.py`, `fix_db.py`, `migrate_user_model.py` and `scripts/manual/*` still point at `src/`. They aren't run by CI or by anything else. `docs/claude-cheatsheet.md` paths likewise wait for Day 10.
- **Found during the work:**
  - **`backend/tests/test_docx_pdf_utils.py` checks nothing.** Its sample paths are CWD-relative, and conftest switches to a temp folder, so every `if os.path.exists(...)` is False. Scheduled on Day 8 in `docs/timeline.md`, as its own commit after the pure moves.
  - **Runtime state outside git:** `src/data`, `src/uploads` and `src/logs` stayed behind after the move, as predicted. The owner moved them to `backend/` by hand. Any other checkout from before Day 7 has to do the same.

## Outcome

Five commits on `feature/day07-refactor-core`, draft PR #8 into `develop`, CI green after each push. The first three:
- cbd20e9: layout doc + brief
- a467435: the move, 90 renames detected
- fbbea8d: `core/` pure moves, 5 renames, 4 of them at 100% similarity

The other two are ac99840 (Settings + request ID) and this docs commit.

### Files changed
**Checkpoint 1 — layout**
- `docs/architecture/layout.md` (new): the target tree, six rules, and a module map with every module's target path and day.
- `docs/briefs/day07.md` (new).
- `docs/timeline.md`: the Day 10 release bullet records that Render needs no dashboard change.

**Checkpoints 2 + 3 — the move and deploy paths**
- **The move:** 90 tracked files went `src/**` → `backend/app/**` and `tests/**` → `backend/tests/**`. `src/requirements.txt` stays until Day 10.
- **Imports:** 135 bare-name import lines in 41 files became `app.*`, via a one-off scratchpad script that keeps CRLF line endings. This included the double-loaded `src.config.oauth_config` import.
- **Path hacks removed:**
  - 10 test files: the `sys.path.insert(... 'src')` lines, plus the `os`/`sys` imports used only for them.
  - `hybrid_retriever.py`, `run_migration.py`, `update_existing_sessions.py`: their `sys.path` hacks.
- **Test path fixes:**
  - `backend/tests/conftest.py`: `backend/` on the path, `sys.modules.get("app.db")`, `from app import main`.
  - `backend/tests/test_llm_modes.py`: the `ChatInput.js` path.
  - `test_pdf_utils.py`, `test_pptx_utils.py`: comments.
- **Deploy and tooling paths:**
  - `pytest.ini`: `testpaths = backend/tests`, `pythonpath = backend`.
  - `Dockerfile`: `COPY backend/app/`, runtime dirs `backend/{data,uploads,logs}`, `WORKDIR /app/backend`, `CMD uvicorn app.main:app`.
  - `docker-compose.yml`: volume mount points `/app/backend/{data,uploads,logs}`.
  - `docker-compose.override.yml`: `app.main:app`, `--reload-dir /app/backend/app`, bind mounts for `backend/app` and `backend/tests`.
  - `scripts/dev.ps1`: `pytest /app/backend/tests`.
  - `.dockerignore`: `backend/{data,uploads,logs,tests,eval,scripts}` and the old `src/`.
  - `alembic/env.py`: imports `app.db` from `backend/`.
- **Hooks:**
  - `.claude/hooks/guard_commands.py`: `backend/data` protected, `src/data` kept, `backend*` dirs protected.
  - `.claude/hooks/edit_reminders.py`: path regexes now match `backend/app/` and Day 8's sub-packages.

**Checkpoint 4 — `core/` moves**
- `logger.py` → `core/logging.py`
- `auth.py` → `core/security.py`
- `error_handler.py` → `core/errors.py`
- `config/oauth_config.py` → `core/config.py`
- new empty `core/__init__.py`; the `config/` package is deleted
- 12 importer lines updated
- `docs/timeline.md`: Day 8 bullet for the `test_docx_pdf_utils.py` sample paths

**Checkpoint 5 — Settings and request ID**
- **`core/config.py`:** `Settings` with 14 fields, `SecretStr` secrets, an absolute repo-root `.env`, and the properties `redis_url`, `semantic_cache_redis_url` and `allowed_origins`.
- **Consumers:**
  - `llm_client.py`, `embedding_service.py`, `reranker.py`, `topic_classifier.py`, `concept_extractor.py`: `settings.GEMINI_API_KEY`; their `RuntimeError` on an empty key is kept.
  - `web_search_client.py`: `TAVILY_API_KEY`. `ocr_utils.py`: `TESSERACT_PATH`.
  - `cache.py`, `web_cache.py`: `settings.redis_url`. `semantic_cache.py`: its URL function became a `Settings` property.
  - `core/security.py`, `services/oauth_service.py`, `routes/auth_routes.py`: JWT, Google, `BASE_URL`, `FRONTEND_URL`.
  - `main.py`: SessionMiddleware and CORS read from `settings`, and `app.add_middleware(RequestIdMiddleware)` is registered last.
- **`core/request_id.py` (new):** a `ContextVar`, the pure ASGI `RequestIdMiddleware`, and header validation `[A-Za-z0-9._-]{1,64}`.
- **`core/logging.py`:** `RequestIdFilter` on the file and console handlers; the format gains `[%(request_id)s]`.
- **Tests:**
  - `backend/tests/test_config.py` (new, 13 tests): one per row of the before/after table, plus the 3 Day 4 tests moved from `test_semantic_cache.py`.
  - `backend/tests/test_request_id.py` (new, 13 tests).
  - `backend/tests/conftest.py`: the `web_search` fixture patches `settings`.

**Checkpoint 6 — docs**
- `CLAUDE.md`: Current Status, repo tree, module map (new Core row), Tech Stack DB path, the conventions for running from `backend/` and for config via `settings`, Key Commands, the Environment Variables intro and its "used by" cells, Data & State paths, and Open Decisions.
- This Outcome.
- `docs/posts/09-launch-recap.md`.
- `docs/learning/ai-concepts.md` (#13, gitignored).

### Checks run
| Check | Result |
|---|---|
| Baseline before any change | `pytest` 111 passed, 1 xfailed (36.8 s), 156 warnings; `ruff check .` clean |
| After Checkpoints 2 + 3 | 111 passed, 1 xfailed, 155 warnings; ruff clean; `compileall` OK; `docker compose config` OK in dev and deployed mode |
| `uvicorn app.main:app` | `/health` 200, **30 routes**, matching the 27 + 3 route decorators at the pre-move commit. Run from a scratch folder via `--app-dir`, so no runtime state landed in `backend/` |
| After Checkpoint 4 | 111 passed, 1 xfailed; ruff clean |
| After Checkpoint 5, host | **134 passed, 1 xfailed** (24.9 s), 154 warnings; ruff clean; the only env access in `backend/app/` is `rag_metrics.py`'s `os.environ[...] =` write (Day 12) |
| After Checkpoint 5, container (`dev.ps1 test`, Linux, Python 3.11) | **134 passed, 1 xfailed** (76.6 s) |
| `docker compose up --build backend` | `/health` 200 with `X-Request-ID`; `day07-check-1` echoed; `bad id;<x>` replaced; the same IDs in `docker compose logs` and `/app/backend/logs/app.log` |
| CI on PR #8 | green after each of the four pushes so far (backend job 2m44s on the last) |

**Warnings 156 → 154, explained.** The old `OAuthSettings` used a class-based `Config`, which pydantic flags as deprecated.
- Before Day 7, the same file was imported under two module names (`config.oauth_config` and `src.config.oauth_config`), so it was executed twice and warned twice.
- After the move it was loaded once (155), and Checkpoint 5 removed the class (154).

### UI integration
| Backend change | Frontend file | What the user sees |
|---|---|---|
| Package move, `core/`, `Settings` | — | Backend-only: internal refactor with identical routes (30) and an identical SSE contract (the Day 5 smoke tests pass) |
| `X-Request-ID` response header | — | Backend-only: for joining log lines and, from Day 23, Langfuse traces. The chat stream uses `EventSource`, which can't read response headers, so showing an error reference belongs with Day 23. `frontend/` is untouched, and CI's frontend job passed with zero edits |

### Timeline bullets deferred or changed
- **`git mv` → plain moves staged by the owner (Decision 2A).** The resulting history is identical: git detected 90 and 5 renames.
- **Day 8's "Update Dockerfile WORKDIR/CMD, docker-compose, alembic/env.py sys.path" is done today (Decision 1A).** Root scripts and `scripts/manual/*` still use the old paths until Day 10 deletes or moves them.
- **The brief planned to anchor `test_docx_pdf_utils.py`'s paths.** That was left out of the pure-move commit because it would make OCR and camelot actually run; it's scheduled on Day 8.

### Numbers for the tracker
No tracker items today. Measured:
- tests 111 → 134 (+13 config, +13 request ID, −3 moved), all passing on host and in the container
- 90 files moved with history
- 135 import lines rewritten
- 14 environment variables in one `Settings` class; 0 `os.getenv` / `load_dotenv` left in `backend/app/`
