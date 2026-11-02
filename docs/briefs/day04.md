# Day 4 — Docker-first local development
Date: 2026-11-03 · Phase 2 — Dev foundation: Docker, tests & CI · Items: T3 (Docker sub-items only)
Branch: feature/day04-docker-dev (current branch; only `CLAUDE.md` is modified — the Current
Status block from the v0.1.1 release, not today's work)

## Scope
1. **Compose split.** `docker-compose.yml` becomes the shared, prod-like definition;
   a new `docker-compose.override.yml` (auto-loaded by `docker compose up`) adds dev behaviour:
   - backend: `./src` bind-mounted, `uvicorn --reload`, waits for Redis
   - frontend: CRA dev server (`npm start`) with hot reload; polling for Windows bind mounts
   - redis:7-alpine with a named volume (already there — keep)
   - named volumes for `src/data`, `src/uploads`, `src/logs`
2. **T3 Docker items.** (a) The semantic cache gets its own Redis DB in Docker via a new
   `SEMANTIC_CACHE_REDIS_URL` setting (CLAUDE.md already promises "a separate setting on Day 4").
   (b) Drop the unused `DATABASE_URL` from compose. The rest of T3 (dead code, requirements,
   unused deps) stays for Day 10 — T3 remains *In Progress*, not Done.
3. **Backend Dockerfile.** Multi-stage build, non-root user, `HEALTHCHECK` on `/health`;
   tighten `.dockerignore` (venv, node_modules, data, logs, uploads — plus `.env` and `*.db`).
4. **`.env.example`** covering every variable in CLAUDE.md's environment table (backend +
   frontend), placeholders only. `.gitignore` already whitelists it (`!.env.example`).
5. **`scripts/dev.ps1`** — `up`, `down`, `logs`, `test`, `shell`.
6. **Added to scope — the Docker frontend talks to production.** See "Current behavior" 6.
   One `ARG` in `frontend/Dockerfile` fixes it.
7. **Docs.** CLAUDE.md Key Commands, environment table, Redis key schema and Data & State rows
   updated to match (not the Current Status block).
8. **Verify** — fresh clone → copy `.env.example` → `docker compose up` → upload a PDF and chat;
   a backend edit reloads in a few seconds.

Not needed / out of scope: `--no-access-log` in the CMD — Day 2's `StripQueryStringFilter`
(`src/logger.py:52`) already strips query strings from uvicorn's access log in any process.

## Current behavior
1. `docker-compose.yml:11` runs the backend with `--reload` but **without** a source bind mount,
   so reload never sees host edits — every change needs `docker compose up --build`. The
   frontend (`:37-50`) is the nginx production build on port 3000: no hot reload at all.
   `src/data` and `src/logs` are bind-mounted from the host (`:14-15`); `uploads` is a named
   volume (`:17`, Day 3). `depends_on: redis` (`:30`) waits only for the container to *start*,
   not for Redis to accept connections.
2. (a) Compose sets `REDIS_URL=redis://redis:6379/0` (`:19`); `semantic_cache.py:13` reads the
   same `REDIS_URL`, so in Docker (and on Render, and locally via `.env`) the semantic cache
   shares DB 0 with `query_cache:*` and `websearch:*`. Only the code default is DB 1.
   (b) `DATABASE_URL` (`:21`) is read by nothing — `db.py:82-86` hardcodes `sqlite:///data/app.db`.
3. `Dockerfile`: single stage; `gcc` and `libpq-dev` (nothing needs `libpq` — no psycopg in
   `requirements.txt`) ship in the final image; runs as **root**; no `HEALTHCHECK`; creates
   `src/data/uploads` (`:28`), a path nothing uses (uploads live in `src/uploads`). The comment
   on line 2 says Python 3.9; the image is 3.11.
   `.dockerignore` does not exclude `src/data/`, `src/uploads/`, `src/logs/` or `*.db`, so
   `COPY src/ ./src/` (`:24`) **bakes the local `app.db` (users, password hashes), uploaded PDFs
   (~15 MB of coursework today) and `app.log` into every locally built image.** Render builds
   from git, where those paths are gitignored, so production images are not affected.
4. No `.env.example`. A new clone has no list of required variables; CLAUDE.md is the only
   source. The local `.env` holds `TESSERACT_PATH` (a Windows path) and
   `REDIS_URL=redis://localhost:6380/0`; `env_file: .env` (`:28-29`) passes both into the
   container — `REDIS_URL` is overridden by `environment`, `TESSERACT_PATH` is harmless only
   because `ocr_utils.py:14` ignores it (see Risks).
5. No helper scripts; `scripts/` does not exist.
6. `frontend/Dockerfile:18` runs `npm run build`. CRA loads `frontend/.env.production` during a
   build, which sets `REACT_APP_API_URL` to the **Render** URL. Compose passes
   `REACT_APP_API_URL=http://localhost:8000` (`docker-compose.yml:45`) as a *runtime* variable to
   nginx, where it has no effect. So the Docker frontend on :3000 logs in and chats against
   production, not the local backend. The image is also `node:18-alpine` (Node 18 is end-of-life).

## Why it matters
1. Edit `main.py` → nothing happens until a 3–5 minute image rebuild. Frontend edits need a full
   `npm run build`. Nobody uses Docker for development, so "works on my machine" (Python 3.12 venv
   on Windows) and "works in prod" (Python 3.11 on Linux) drift. On first start, the backend can
   race Redis and fail its first cache call.
2. (a) Flushing one cache (`FLUSHDB` on DB 0 to clear stale web results) silently wipes every
   user's semantic cache too; the key spaces are also harder to reason about on Render. (b) A
   reader sees `DATABASE_URL` and assumes it switches databases; setting it to Postgres does
   nothing — and Day 13 needs that name to mean something real.
3. A container running as root that is compromised (e.g. via a malicious PDF hitting a parser
   bug in pdfplumber/camelot) owns the whole container filesystem. Without a healthcheck,
   `docker ps` shows "Up" while startup is stuck on the Gemini call. And `docker push` of a
   locally built image would publish the user database.
4. A teammate (or CI on Day 6, or you on a new laptop) can't start the stack without reading
   source code to find out which variables are required; startup then fails on the first
   missing one (`GEMINI_API_KEY`, then the OAuth settings).
5. Long `docker compose …` incantations get mistyped; Day 5's tests need one way to run in the
   same Linux/Python 3.11 environment as CI.
6. Testing a backend change locally through the Docker frontend actually hits prod: local
   changes look broken, and test data (uploads, deleted accounts) lands in the production DB.

## The concept

**Images, containers, layers.** An image is a stack of read-only filesystem layers, one per
Dockerfile instruction; a container is a running process with a thin writable layer on top.
Docker caches each layer and reuses it if the instruction *and its inputs* are unchanged — which
is why `requirements.txt` is copied and installed *before* `COPY src/`: code edits then reuse
the expensive pip layer. Pitfall: anything in the build context that changes (logs, the SQLite
file) invalidates every layer after the `COPY` that includes it.

**Build context and `.dockerignore`.** `docker build .` uploads the whole directory to the
builder; `.dockerignore` decides what is sent. It is a security control, not just a speed-up:
whatever is in the context can end up in a layer, and layers are permanent — deleting a file in a
later `RUN rm` does not remove it from the earlier layer. Secrets and user data must never enter
the context.

**Multi-stage builds.** One `FROM` builds (compilers, headers, pip caches), a second `FROM`
copies only the result (a virtualenv) into a clean base. The runtime image loses the toolchain:
smaller, faster to pull, and fewer binaries an attacker can use. The usual trick for Python is
`python -m venv /opt/venv` in the builder and `COPY --from=builder /opt/venv /opt/venv` plus
`PATH=/opt/venv/bin:$PATH` at runtime. Pitfall: system libraries a wheel links against at
*runtime* (tesseract, poppler, libGL for OpenCV) must still be installed in the final stage.

**Least privilege: non-root containers.** By default a container's process is root (uid 0).
Container isolation is good but not a security boundary on its own; a process escape from root is
far worse than from an unprivileged user. Production images create a dedicated user and switch
with `USER`. Pitfall: that user must own every directory it writes to (`data/`, `uploads/`,
`logs/`), and named volumes inherit ownership from the image directory *the first time* they are
mounted — so the directories must exist and be `chown`ed in the image.

**Healthchecks and readiness.** "Container is running" ≠ "service is ready". A `HEALTHCHECK`
probes the app (here `GET /health`) and Docker marks the container `healthy`/`unhealthy`.
Compose's `depends_on: condition: service_healthy` uses it to order startup — the fix for
"backend starts before Redis accepts connections". `start_period` gives slow startups (this app
makes a Gemini embedding call at import) a grace window. Orchestrators (Kubernetes liveness and
readiness probes, Render's health check path) apply the same idea. Pitfall: slim images have no
`curl`; use the language runtime to probe.

**Compose override files.** `docker compose up` merges `docker-compose.yml` with
`docker-compose.override.yml` automatically. The base file describes the app as it really runs
(what CI and a prod-like smoke test use, via `-f docker-compose.yml`); the override adds dev-only
behaviour — source mounts, reload flags, dev servers. Merge rules: scalars (`command`, `image`)
are replaced; lists like `ports` and `volumes` are merged. Pitfall: a value in the base you
didn't mean to inherit in dev (or vice versa).

**Bind mounts vs named volumes.** A bind mount maps a host path into the container — ideal for
source code you edit. A named volume is storage managed by Docker — ideal for state (databases,
uploads) that should survive container recreation but doesn't belong in your working tree. A
named volume mounted *inside* a bind mount (`./src` → `/app/src`, volume → `/app/src/data`)
shadows that subdirectory, keeping runtime state out of the host checkout. Pitfall on Windows:
bind mounts from NTFS into the Linux VM do not deliver filesystem change events (inotify), so
file watchers (uvicorn's `watchfiles`, webpack's `watchpack`) need polling:
`WATCHFILES_FORCE_POLLING`, `CHOKIDAR_USEPOLLING`, `WATCHPACK_POLLING`. Another: a bind-mounted
`frontend/` would hide the image's `node_modules`, so `node_modules` gets its own anonymous volume.

**Twelve-factor config.** Config that varies between environments (URLs, keys, DB numbers) comes
from environment variables, never from code. `.env.example` is the contract: every variable,
which are required, safe placeholders. Build-time vs run-time matters: CRA inlines
`REACT_APP_*` into the JavaScript bundle at **build** time, so setting it on the running nginx
container does nothing — it must be a build `ARG`. Real environment variables override `.env*`
files in CRA, which is how the build arg beats `.env.production`.

**Redis logical databases.** One Redis server has numbered DBs (0–15) with separate key spaces;
`FLUSHDB` clears one. Separating caches by DB keeps their lifecycles independent. They share
memory and eviction policy, so this is organisation, not isolation (and Redis Cluster supports
only DB 0 — managed providers sometimes limit DBs, which is why the URL is a setting, not a
hardcoded number).

## Decisions

### 1. Local data in Docker
- **A — Named volumes (timeline):** `data`, `uploads`, `logs` become Docker-managed volumes
  shadowing those folders inside the `./src` bind mount; Docker starts with an empty database.
  Clean separation from the host checkout, but your current local `app.db` and its accounts are
  not visible inside Docker (the venv workflow still uses them).
- **B — Bind-mount the host folders (today's setup for data/logs):** the container reads and
  writes `src/data`, `src/uploads`, `src/logs` on the host, sharing state with the venv backend.
  Familiar, but SQLite files on a Windows bind mount are slow and lock-prone, and runtime writes
  land in the working tree.
- **Recommendation: A.** It matches the timeline and Day 13's Postgres volume; the in-memory FAISS
  index means old documents aren't searchable after any restart anyway (I4), so carrying the
  old DB over gains little. Register a fresh demo account in Docker.

### 2. Frontend dev container
- **A — `dev` stage in `frontend/Dockerfile`:** `FROM node:20-alpine AS dev`, `npm ci`,
  `CMD npm start`; the override uses `build.target: dev`. Dependencies are baked once and cached;
  the build stage reuses it.
- **B — Plain `node` image in the override:** `image: node:20-alpine`, `command: sh -c "npm ci &&
  npm start"`. No Dockerfile change, but `npm ci` runs on every container start (~1–2 min).
- **Recommendation: A.**

### 3. Node version for the frontend image
- **A — Bump to `node:20-alpine` (both stages):** Node 18 is end-of-life; react-scripts 5 and
  React 19 run on 20. Vercel builds independently, so production is untouched.
- **B — Keep `node:18-alpine`:** zero risk today, revisit on Day 6 when CI picks a "Node LTS".
- **Recommendation: A** — Day 6 CI uses Node LTS; matching it now avoids a second change.

### 4. Where `dev.ps1 test` runs
- **A — Inside the backend container:** `docker compose run --rm backend python -m pytest
  /app/tests` with `./tests` mounted read-only. Same Python 3.11/Linux as CI and Render; tesseract
  present.
- **B — On the host venv:** fast and no Docker needed, but Python 3.12 on Windows ≠ CI.
- **Recommendation: A** (and the plain `python -m pytest tests` still works for B).

`SEMANTIC_CACHE_REDIS_URL` is not a fork: CLAUDE.md already committed to a separate setting.
Precedence: `SEMANTIC_CACHE_REDIS_URL` → `REDIS_URL` → `redis://localhost:6379/1`. Render sets
only `REDIS_URL`, so **production behaviour is unchanged** until you choose to set it there.

## Plan

**Checkpoint 1 — backend image + semantic-cache setting (5 files)**
- `src/semantic_cache.py` — `semantic_cache_redis_url() -> str` with the precedence above,
  read when the cache is constructed (not at import, so tests can set env); `__init__` uses it
- `tests/test_semantic_cache.py` — 3 cases: dedicated var wins, falls back to `REDIS_URL`,
  falls back to the DB 1 default (monkeypatched env, no Redis needed)
- `Dockerfile` — builder stage (`python:3.11-slim`, gcc, venv, pip install); runtime stage
  (tesseract-ocr, tesseract-ocr-eng, poppler-utils; no gcc/libpq-dev), `useradd` uid 1000
  `app`, `mkdir` + `chown` `src/data src/uploads src/logs`, `USER app`, `HEALTHCHECK` via
  `python -c "urllib.request.urlopen('http://127.0.0.1:${PORT:-8000}/health')"`
  (interval 30s, timeout 5s, start-period 60s, retries 3); CMD unchanged (`${PORT:-8000}` for
  Render); fix the stale "Python 3.9" comment and the `src/data/uploads` path
- `.dockerignore` — add `.env`, `.env.*` (keep none), `src/data/`, `src/uploads/`, `src/logs/`,
  `*.db`, `*.sqlite*`, `node_modules/`, `docs/`, `.claude/`, `tests/`, `scripts/`, `*.exe`;
  remove the stale `src/data/uploads/*` lines
- Checks: `py_compile`, `pytest tests/test_semantic_cache.py`, `docker build .`, confirm with
  `docker run … ls /app/src` that no `app.db`/uploads are inside, `whoami` = app, image size
  before/after

**Checkpoint 2 — compose + frontend + env (5 files)**
- `docker-compose.yml` (base, prod-like) — backend: no `--reload` (uses the Dockerfile CMD),
  `env_file: .env` plus only container-specific `environment`: `REDIS_URL=redis://redis:6379/0`,
  `SEMANTIC_CACHE_REDIS_URL=redis://redis:6379/1`, `TESSERACT_PATH=/usr/bin/tesseract`; drop
  `DATABASE_URL` and the `${…}` duplicates already supplied by `env_file`; named volumes
  `data`, `uploads`, `logs`; `depends_on: redis: condition: service_healthy`. Redis gets a
  `redis-cli ping` healthcheck. Frontend: `build.args.REACT_APP_API_URL=http://localhost:8000`
- `docker-compose.override.yml` (new, dev) — backend: `./src:/app/src` bind mount (named volumes
  still shadow data/uploads/logs), `./tests:/app/tests:ro`, command `uvicorn … --reload
  --reload-dir /app/src`, `WATCHFILES_FORCE_POLLING=true`; frontend: `build.target: dev`,
  `ports: 3000:3000`, `./frontend:/app` + anonymous `/app/node_modules`,
  `CHOKIDAR_USEPOLLING=true`, `WATCHPACK_POLLING=true`, `WDS_SOCKET_PORT=3000`
- `frontend/Dockerfile` — `node:20-alpine`; `deps` stage (`npm ci`), `dev` stage (`CMD npm
  start`, port 3000), `build` stage with `ARG REACT_APP_API_URL` → `ENV` before `npm run build`,
  nginx stage unchanged
- `.env.example` (new) — every backend + frontend variable from the CLAUDE.md table, grouped,
  required/optional marked, placeholders only; host-run values (`localhost:6380/0` and `/1`)
  with a comment that compose overrides them
- Checks: `docker compose config` (dev) and `docker compose -f docker-compose.yml config` (base),
  `docker compose up --build`, `docker ps` shows `healthy`, :3000 loads, the browser's network tab
  shows calls going to `localhost:8000`

Note: the base file's `ports: "3000:80"` and the override's `"3000:3000"` are *merged*, so the
override must use `!override` (Compose ≥ 2.24; you have v5.1.4) for the frontend `ports`.

**Checkpoint 3 — helper, docs, end-to-end verify (3 files)**
- `scripts/dev.ps1` (new) — `param([ValidateSet('up','down','logs','test','shell')] $Command,
  [string] $Service = 'backend')`; `up` = `docker compose up --build -d` then status, `down`,
  `logs -f <service>`, `test` = `docker compose run --rm --no-deps backend python -m pytest
  /app/tests -q`, `shell` = `docker compose exec <service> sh`; fails with a clear message if
  `.env` is missing
- `CLAUDE.md` — Key Commands (Docker-first block + `scripts/dev.ps1`), env table
  (`SEMANTIC_CACHE_REDIS_URL`; remove the "separate setting on Day 4" note), Redis key schema
  row for `semantic_cache:*`, Data & State (named volumes in Docker). Not Current Status.
- Verify (below), then Outcome, post 9 line, learning-notes check

New dependencies: **none** (Python or npm). New base images: `node:20-alpine` (decision 3).

## UI integration
Backend-only — no user-visible change. Today is developer infrastructure: Dockerfiles, compose,
an env template, a helper script and one internal config setting (`SEMANTIC_CACHE_REDIS_URL`,
which only chooses a Redis DB). No endpoint, response field, status or flag is added or changed.
The frontend fix (deliverable 6) changes which backend the *Docker* frontend calls; the screens
are identical.

## Verification
- `python -m pytest tests -q` on the host and `scripts/dev.ps1 test` in the container — same
  result (all tests that pass today; numbers recorded in the Outcome).
- `docker build .` succeeds; `docker run --rm --entrypoint sh <img> -c "whoami; ls src/data
  src/uploads"` → `app`, both empty; image size before vs after.
- `docker compose config` and `docker compose -f docker-compose.yml config` both validate;
  no `DATABASE_URL` in either.
- **Fresh clone:** `git clone` the branch into the scratchpad, copy `.env.example` → `.env`
  and fill in the real keys, `docker compose up --build`, wait for `healthy`.
- End-to-end at http://localhost:3000: register a demo account, upload a demo PDF, ask a
  question, see the streamed answer with a citation showing the real filename.
- `docker exec rag-redis redis-cli -n 1 KEYS "semantic_cache:*"` shows the entry in DB 1 and
  `-n 0` shows none.
- Reload: edit a comment in `src/main.py`, time from save to "Application startup complete" in
  `scripts/dev.ps1 logs` (target: a few seconds plus the startup embedding call). Same for a
  frontend edit → browser refresh.
- `docker compose down` + `up` → the demo account and upload still exist (volumes), the document
  is listed but not searchable until re-uploaded (I4, expected).

## Risks & open questions
- **Production Dockerfile.** Render builds this Dockerfile on the next release. Non-root +
  multi-stage are standard, but the runtime stage must keep every system library the app loads.
  `opencv-python` (non-headless) is installed next to the headless build and may need `libGL`;
  today's image has none and prod works, so the current imports don't load it — I'll confirm by
  importing `main` inside the new image. Render ignores Docker's `HEALTHCHECK` (it uses its own
  health check path setting); worth setting that to `/health` on release day.
- **Render's disk.** With `USER app`, writes to `src/data` and `src/logs` work because the image
  `chown`s them; if a Render persistent disk is ever mounted there, it must be writable by uid 1000.
- **Startup needs real keys.** `IndexBuilder` makes a Gemini call at import, so `.env.example`
  placeholders alone won't start the backend; the fresh-clone check uses real keys. Day 5 adds the
  seam that removes this.
- **OCR is Windows-only.** `ocr_utils.py:14` hardcodes `C:\Program Files\Tesseract-OCR\…` and
  ignores `TESSERACT_PATH` (the env code is commented out). Not reachable from `/upload`, so not
  fixed today — recorded for Day 10 (T3 dead code) or whenever OCR is wired in.
- **Cold semantic cache locally.** Moving Docker's semantic cache to DB 1 orphans any
  `semantic_cache:*` keys in DB 0 of the local Redis volume — harmless; `FLUSHDB` on DB 0 if wanted.
- **Port clash.** Docker backend (8000) and the venv backend (8000) can't run together; the
  frontend dev server (3000) likewise. `dev.ps1 up` will say which port is busy.
- **Dangling volumes.** `docker volume ls` shows ~180 anonymous volumes from other projects; not
  touched. The `node_modules` anonymous volume adds one per frontend container recreation —
  `dev.ps1 down` will pass `--remove-orphans` but not `-v` (that would delete the data volumes).
- **Found in Checkpoint 2 — backend reload is ~14 s, not "a few seconds".** Change detection
  takes 1.2 s; the rest is re-importing the app (12.3 s whether the code is baked in or
  bind-mounted). `python -X importtime`: 9.9 s of it is `indexing_pipeline → chunk_builder →
  pptx_pipeline → table_utils → img2table` (img2table alone ~4 s), loaded eagerly even when only
  PDFs are indexed. Fix belongs to the Phase 3 refactor (lazy-import the PPTX table/OCR path).
- **Found in Checkpoint 2 — stale DB 0 entry.** The existing `redis-data` volume (created
  2025-12-20) holds `semantic_cache:1` in DB 0 from an earlier local session (pre-Day 4
  entries at doc_version 5). Deleted in Checkpoint 3 at the owner's request.
- **Open question (answered):** no `-Reset` switch on `dev.ps1 down` — owner's decision.
- **Found in Checkpoint 3 — fresh clone has no `frontend/.env`.** It is gitignored, so the dev
  frontend in a new clone has no `REACT_APP_GOOGLE_CLIENT_ID`; email login works, Google login
  needs that file (documented in `.env.example`). Not tested live today.
- **Found in Checkpoint 3 — container tests take 73 s** (host: 21 s), mostly the same heavy
  imports plus real OCR now running. Day 5's target is "under a minute" — on the host it is met;
  in the container it will be once the lazy-load bullet (Day 8) lands, or Day 5 can decide.

## Outcome

Approved decisions: 1A named volumes · 2A frontend `dev` stage · 3A Node 20 · 4A tests in the
container · no `-Reset`. Owner additions: base-file-only run, fresh-clone check via an unread
`.env` copy, concept map + quiz + permission-error scan in the base run, DEL of the stale DB 0
key, lazy-load bullet on the timeline. Two fixes added mid-way with the owner's approval: test
sample paths (container test run) and the hardcoded tesseract path.

### Files changed
- `Dockerfile` — two stages (gcc only in the builder, `libpq-dev` dropped); non-root `app` (uid 1000) owning only `src/data`, `src/uploads`, `src/logs`; `HEALTHCHECK` on `/health` (30 s / 5 s / start 60 s / 3 retries); exec-form CMD (`sh -c "exec uvicorn …${PORT:-8000}"`) so uvicorn is PID 1 and gets SIGTERM
- `.dockerignore` — excludes `.env*`, `src/data/`, `src/uploads/`, `src/logs/`, `*.db`, `*.log`, frontend, tests, docs, scripts, `.claude/`, `*.exe`
- `docker-compose.yml` — base/prod-like: `env_file` + container-only overrides (`REDIS_URL` DB 0, `SEMANTIC_CACHE_REDIS_URL` DB 1, `TESSERACT_PATH`, `FRONTEND_URL`); `DATABASE_URL` removed; named volumes `data`/`uploads`/`logs`; Redis healthcheck + `depends_on: service_healthy`; frontend `REACT_APP_API_URL` build arg
- `docker-compose.override.yml` (new) — dev: `./src` bind mount + `--reload` with WatchFiles polling; `./tests` and `./frontend/src:ro` mounted for the container test run; frontend `dev` target on 3000:3000 (`!override`), polling env, anonymous `node_modules`
- `frontend/Dockerfile` — `node:20-alpine`; stages `deps → dev / build → nginx`; `ARG REACT_APP_API_URL` with no `ENV`, so an unset arg keeps `.env.production`
- `.env.example` (new) — every backend variable with placeholders, required ones marked; frontend env explained
- `scripts/dev.ps1` (new) — `up` (checks `.env` and busy ports 8000/3000/6380), `down` (`--remove-orphans`, volumes kept), `logs [service]`, `test [pytest args]`, `shell [service]`; ASCII-only, judged by exit code
- `src/semantic_cache.py` — `semantic_cache_redis_url()`: `SEMANTIC_CACHE_REDIS_URL` → `REDIS_URL` → `redis://localhost:6379/1`, read at construction
- `src/ocr_utils.py` — honours `TESSERACT_PATH` when set, else tesseract on `PATH`; the hardcoded Windows path is gone (was OCR-breaking on Linux/Render)
- `tests/test_semantic_cache.py` — 3 tests for the URL fallback order
- `tests/test_pdf_utils.py`, `tests/test_pptx_utils.py` — sample paths built from `__file__` instead of the CWD
- `CLAUDE.md` — Key Commands (Docker-first block, `dev.ps1`, base-only command), env table (`SEMANTIC_CACHE_REDIS_URL`, `.env.example`, `DATABASE_URL` note, CRA build-time note, `TESSERACT_PATH`), Data & State (Docker volumes), Redis key schema. Current Status untouched
- `docs/timeline.md` — Day 8: lazy-load OCR/table libraries bullet with today's numbers
- `docs/briefs/day04.md` — this brief and Outcome

### Checks
| Check | Result |
|---|---|
| `py_compile` + ruff (E9, F63, F7, F82) on every changed `.py` | pass |
| `pytest tests` on the host (Python 3.12, Windows) | 84 passed (81 before + 3 new), 21–42 s |
| `scripts/dev.ps1 test` in the container (Python 3.11, Linux) | 78/84 → 83/84 (paths) → **84/84** (OCR fix), 73 s |
| `docker compose config` / `-f docker-compose.yml config` | both valid; no `DATABASE_URL`; dev frontend publishes only 3000:3000 |
| Import check in the new image as `app`: 26 backend modules + cv2, camelot, pdfplumber, faiss, pytesseract | 0 failures; tesseract 5.5.0, pdftoppm 25.03.0 present; `libGL` not needed |
| **Base-only run** (`docker compose -f docker-compose.yml up --build`) | backend healthy; register/login/upload 200; chat events `metadata → token… → message_id → [DONE]`, confidence 75, strict, citation `samples.pdf`; concept map 200 (6 nodes); quiz 200; files written as `app`; **0** PermissionError / Read-only / Errno 13/30 / Traceback; nginx bundle calls `localhost:8000`, 0 `onrender.com` |
| **Dev run** | all 3 healthy; CRA compiled; dev bundle calls `localhost:8000` |
| **Fresh clone** (working tree minus every `git status --ignored` path, `.env` copied unread) | own volumes `day04clone_*`; healthy; same register/upload/chat/concept map/quiz results; citation `samples.pdf`; semantic key in DB 1 only; 0 permission errors; then `down -v` in the clone (4 volumes removed) and folder deleted; main volumes untouched |
| `dev.ps1 up` / `down` / `test`; port guard with a dummy listener on 8000 | all work; guard: "Port 8000 is already in use by python (pid …). Stop it first." |
| OCR in the container | `/usr/bin/tesseract` reads "HOW TO COMBINE TEXT AND IMAGE…" from `sampleimg1.png` |
| Frontend build | `npm run build` ran inside the nginx image build (base run) — compiled; frontend source unchanged today |

Fresh-clone method: `git clone` would have produced the last commit (`c15313d`) without today's
uncommitted work, and `/run-day` allows no git command beyond status/log/diff — so the "clone"
was a copy of the working tree excluding `.git` and every ignored path (22 directories, 9 files,
incl. `.env`, `frontend/.env`, `src/data`, `node_modules`). Docker's layer cache was shared with
the main checkout, so this proves the file set, not a cold image build (the cold build was
timed in Checkpoint 1: 256 s backend).

### Measured numbers (for the tracker's Notes)
| What | Before | After |
|---|---|---|
| Backend image (`docker images`) | 3.4 GB (`rag-backend:precommit`) | 3.05 GB |
| Backend image content size | 822 MB | 725 MB |
| `/app/src` in the image | 16 MB incl. `app.db` + 6 uploaded PDFs | 480 KB, no user data |
| Image user | root | app (uid 1000) |
| Backend reload, save → "Application startup complete" | n/a (no bind mount: rebuild needed) | 13.5 s, 15.1 s (detection 1.2 s; re-import ~12 s) |
| `import` of the app's modules (baked vs bind-mounted) | — | 12.3 s vs 12.4 s — the mount is not the cost |
| Of which `indexing_pipeline → … → img2table` (`-X importtime`) | — | 9.9 s (img2table ~4 s) |
| Frontend hot reload, save → "Compiled successfully" | n/a (nginx build only) | 6.8 s (detection 3.0 s, compile 3.8 s) |
| Docker frontend API target | Render production | `http://localhost:8000` |
| Container test suite | not runnable | 84/84 in 73 s |
| OCR in Linux containers | broken (Windows path) | works |

### UI integration
| Backend change | Frontend file | What the user sees |
|---|---|---|
| `SEMANTIC_CACHE_REDIS_URL` | — | backend-only: chooses a Redis DB; responses identical |
| Dockerfile / compose / `.env.example` / `dev.ps1` | — | backend-only: developer infrastructure |
| `ocr_utils.py` tesseract path | — | no new UI; PPTX image text that was silently empty on Linux can now reach chunks and answers |
| Frontend build arg | `frontend/Dockerfile` | same screens; the Docker frontend now talks to the local API instead of production |

No endpoint, response field, status or flag was added or changed.

### Timeline bullets
- All Day 4 bullets delivered. T3 stays **In Progress**: the Docker items (semantic-cache DB,
  `DATABASE_URL`) are done; dead code, requirements reconcile and unused deps remain for Day 10.
- Not achieved: "a backend code edit reloads in a few seconds" — 13.5–15.1 s measured. Cause
  found and scheduled (Day 8 lazy-load bullet, target < 5 s).

### Notes for the Day 10 release (v0.2.0)
- **Set Render's health check path to `/health`** (Render ignores the Dockerfile `HEALTHCHECK`).
- First Render deploy of the new Dockerfile: watch the deploy log for permission errors (now
  non-root) — the base-only run here found none.
- Optional: set `SEMANTIC_CACHE_REDIS_URL` on Render to DB 1 of the Key Value instance (the cache
  starts cold there; DB 0 then holds only query/web caches).
- OCR starts working on Render with this release (PPTX image text), so PPTX answers may change.

### Suggested tracker Notes for T3 (owner updates the tracker)
`2026-11-03 (Day 4): Docker items done — semantic cache on its own Redis DB via
SEMANTIC_CACHE_REDIS_URL (Docker DB 1; Render unchanged until set), DATABASE_URL removed from
compose. Also: image no longer bakes app.db/uploads (16 MB → 480 KB src), non-root, 3.4 → 3.05 GB.
Remaining: dead code, requirements reconcile, unused deps (Day 10).`
