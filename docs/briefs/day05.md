# Day 5 — Offline test safety net (T1 + API smoke tests)
Date: 2026-11-05 · Phase 2 — Dev foundation: Docker, tests & CI · Items: T1
Branch: feature/day05-tests

## Scope
1. **T1** — `pytest.ini` header `[tool:pytest]` → `[pytest]`; move the 11 manual `src/test_*.py`
   scripts to `scripts/manual/` so pytest can never collect them.
2. **`tests/conftest.py`** — FastAPI `TestClient` on a temporary database; fake Gemini client
   (deterministic embeddings, scripted text and streams); in-memory Redis stub; the smallest seam
   that lets `import main` run with no API key and no network.
3. **API smoke tests** — register / login / me, upload `samples.pdf`, list / delete documents,
   `/chat/stream` event order (`metadata → token… → message_id → [DONE]`), sessions list /
   rename / delete, feedback, concept-map generate with a mocked LLM, `/health`.
4. **Frontend** — render tests for the login page and the chat window. The default CRA
   `App.test.js` is already gone (deleted earlier; CLAUDE.md), so "replace" becomes "add".
   `ChatWindow.test.js` exists but only covers refusals — today adds the normal answer path.
5. **Fix `test_table_extraction_on_image`** — outputs to `tmp_path`, no double-cleaning,
   existence check first, assert real table output; remove the `*_cleaned*.jpg` ignore line.
   **Blocked as written:** image table extraction is broken in this environment (see Current
   behavior → 5), so "assert real table output" cannot pass without a dependency change →
   Decision 2.
6. **Verify** — `python -m pytest tests` green with no API keys and no network, in under a minute.

## Current behavior
1. `pytest.ini:1` is `[tool:pytest]`, which pytest only honours in `setup.cfg`; `testpaths`,
   `pythonpath` and `addopts` are all ignored. A bare `pytest` from the root therefore also
   collects `src/test_*.py` (e.g. `src/test_full_pipeline.py:17 def test_full_pipeline()`),
   which build real Gemini clients. Today everyone runs `python -m pytest tests` to dodge this
   (CLAUDE.md Key Commands; `scripts/dev.ps1:93`). Nothing else references the 11 scripts
   (grep: only CLAUDE.md and docs/improvements.md mention them).
2. There is no `conftest.py`. Importing `main` from a test is impossible offline:
   - `src/main.py:80` `IndexBuilder()` → `src/index_builder.py:16` embeds `"hello world"` through
     `src/embedding_service.py:19` `genai.Client(...)` — a live Gemini call at import time, and
     `RuntimeError("GEMINI_API_KEY not set")` without a key.
   - `main.py:84` `LLMClient()`, `src/topic_classifier.py:125` module singleton,
     `src/concept_extractor.py:41` — all `genai.Client(api_key=...)`.
   - `src/cache.py:8` builds a Redis client at import; `get_cached_response` (`cache.py:15`) does
     not catch connection errors, so the first retrieval needs a live Redis.
     `src/web_cache.py:11` and `src/semantic_cache.py:62` also call `redis.from_url`.
   - Relative paths resolved against the CWD at import: `src/db.py:82-86` (`data/app.db`),
     `src/upload_storage.py:12` (`uploads/`), `src/logger.py` (`logs/app.log`). Imported from the
     repo root, they would create `./data/app.db` etc. in the repo.
   - `load_dotenv()` (e.g. `embedding_service.py:14`) walks up to the real root `.env`, so a test
     run silently picks up the real `GEMINI_API_KEY` / `TAVILY_API_KEY` unless they are already
     set in the environment (load_dotenv never overrides).
   - `src/config/oauth_config.py:5` requires `GOOGLE_*` and `JWT_SECRET_KEY`;
     `src/services/oauth_service.py:3` imports `src.config…`, so the repo root must be on
     `sys.path` (it will be, once `pythonpath = .` is honoured).
   - The singletons are module globals, not FastAPI dependencies; only `get_db` / `get_current_user`
     (`src/auth.py:22,67`) go through `Depends`. `register_upload` binds `SessionLocal` as a default
     argument (`src/document_service.py:64`), so overriding `get_db` would not reach it.
3. No API-level tests exist. The 84 current tests (all green: **84 passed in 42.6 s**, 51 s wall,
   measured today) are unit tests of parsers, guards, logger, semantic cache, upload storage,
   document service and account service.
4. Frontend: `components/ChatWindow.test.js:49` tests only a refused stream; `AccountDeletionFlow.test.js`
   shows the working router setup (MemoryRouter + AuthProvider + `AppRoutes`, TextEncoder
   polyfill). No test renders `pages/LoginPage.js` / `components/LoginForm.js`.
5. `tests/test_pptx_utils.py:104-120`: calls `preprocess_image_for_table` (writes
   `tableimage2_cleaned.jpg` into `tests/samples/`), then `extract_tables_from_image` on that
   output — which preprocesses again (`src/table_utils.py:23`) → `_cleaned_cleaned.jpg`. The
   existence check comes after the first use; the test asserts only `isinstance(tables, list)`
   and prints. Both cleaned files are sitting in `tests/samples/` now, hidden by `.gitignore:44`;
   `docker-compose.override.yml:15` mounts `tests/` read-write only because of this.
   **Run today on a copy:** `extract_tables_from_image` returns `[]` and prints
   `module 'cv2.ximgproc' has no attribute 'niBlackThreshold'`. Cause: three OpenCV wheels are
   pinned (`opencv-python`, `opencv-python-headless`, `opencv-contrib-python-headless`, all
   4.12.0.88) and all write the same `cv2` package; whichever pip installs last wins, and here a
   non-contrib build won. `camelot-py` requires `opencv-python-headless`, `img2table` requires the
   contrib build, `opencv-python` is required by nothing. This also silently disables table
   extraction from PPTX slide images (`extract_tables_from_pptx_slides`), which *is* reachable
   from `/upload`.

## Why it matters
1. T1: someone runs `pytest` → 11 scripts collected → live Gemini calls, cost, failures without
   keys → people stop running tests. On Day 6 CI the same command would fail outright.
2/3. Phase 3 (Days 7–10) moves every module and splits `main.py`. Without API-level tests, a
   wrong import in a route or a changed SSE event shape is found by the user in production, not
   by `pytest`. Example: Day 9 extracts a `ChatPipeline`; if `message_id` is emitted after
   `[DONE]`, `ChatWindow.js` closes the stream first and thumbs feedback silently stops working —
   today nothing would catch that.
4. A login form or chat-render regression from the Phase 16 restyle (or a dependency bump) is
   currently invisible until a manual click-through.
5. A test that writes into `tests/samples/` dirties the repo and forces a read-write mount; a test
   that only asserts `isinstance(list)` passed for months while the feature returned `[]`. That is
   exactly how the OpenCV breakage went unnoticed.

## The concept

### Hermetic tests and the test pyramid
A *hermetic* test depends only on what is in the repo: no network, no API keys, no shared
database, no wall-clock or randomness it doesn't control. It gives the same answer on a laptop, in
Docker and in CI, and it's fast enough to run on every change. The classic pyramid: many fast
unit tests, fewer integration/API tests, very few end-to-end tests. Today fills the middle layer:
**API smoke tests** — one or two happy-path requests per endpoint through the real FastAPI app,
real routing, real SQLAlchemy, real auth — with only the *external* systems faked. They don't
prove answers are good (that's the eval harness, Days 11–12); they prove the wiring works.

### Test doubles, and where to put the seam
- **Stub:** returns canned data (the Redis stub). **Fake:** a working lightweight implementation
  (an in-memory dict that behaves like Redis; a deterministic embedder). **Mock:** records calls so
  you can assert on them. **Spy:** wraps the real thing.
- A **seam** is a place where you can swap behaviour without editing the code under test. The best
  seams are at the *process boundary*: the HTTP/SDK client to Gemini, the Redis client, the clock.
  Fake there and every line of *your* code above it still runs — prompt building, JSON parsing,
  SSE framing, DB writes.
- Common pitfall: mocking your own functions (`retrieval_service.hybrid_retrieve = Mock()`). The
  test then checks that the mock returns what you told it — it stops covering the code that
  actually breaks during a refactor.
- **Deterministic embeddings**: hash the text into a seed and generate a fixed unit vector. Same
  text → same vector across runs, so similarity-based behaviour (semantic-cache hits, FAISS
  ranking) is reproducible. Real semantic quality is irrelevant for smoke tests.

### Import-time side effects
`main.py` does network I/O *while being imported* (`IndexBuilder()` embeds a dummy string). That
is the main reason it can't be tested: you can't even get a reference to `app` without a key.
Production FastAPI apps build expensive clients in a **lifespan** handler (startup) and expose
them through `Depends`, so tests swap them with `app.dependency_overrides[get_llm] = lambda:
FakeLLM()`. That is Day 9's job. Until then the seam has to sit *below* `main` — at the SDK
constructor — and be installed *before* the import. Same for relative paths: `db.py` resolves
`data/` against the CWD at import time, so the test must choose the CWD first.

### Contract tests for streaming
SSE is a contract between backend and frontend: event names, order and payload shape.
`ChatWindow.js` depends on `metadata` arriving first (session id, sources), tokens next, then
`message_id` (enables thumbs feedback), then `[DONE]` (closes the stream). A contract test parses
the raw `text/event-stream` body and asserts that sequence. Pitfalls: asserting on exact token
text from a real LLM (non-deterministic), and forgetting the cached-replay path, which emits the
same contract from a different code branch (`main.py:880-910`).

### Isolation between tests
- Each test creates its own user (unique email), so state that can't easily be reset (the
  in-memory FAISS index, class-level L1 cache) never leaks between tests — the app already scopes
  everything by `user_id`, so per-user isolation *is* the product's isolation model.
- Process-global changes (CWD, env vars, patched SDK classes) are made once per test session,
  before `main` is imported, and undone at the end.
- A **network guard** (refuse every non-loopback socket connect) turns "no network" from a hope
  into a checked property: any accidental live call fails loudly instead of quietly costing money.
  Loopback stays allowed because asyncio on Windows uses a loopback socket pair internally.

### Silent failures in tests
`assert isinstance(tables, list)` is a *tautology test*: the function returns `[]` on every
exception, so the test passes when the feature is dead. Good tests assert on the *outcome*
(at least one table, with rows and columns). `pytest.mark.xfail(strict=True)` records a known
bug honestly: the suite stays green, and the moment someone fixes the bug the test *fails* with
"XPASS(strict)", forcing the marker's removal.

### Frontend component tests
React Testing Library renders a component in jsdom and queries it the way a user would (by role,
label, placeholder, visible text). `fetch` and `EventSource` are replaced by fakes, so tests stay
offline. The test proves: the login form submits credentials to `/login`, stores the token and
navigates; a wrong password shows the server's error; a normal stream renders the answer and its
sources and enables feedback.

## Decisions

### 1. The offline seam for importing `main`
- **A — Fake at the SDK boundary, from `conftest.py` only:** before importing `main`, set dummy
  env vars, replace `google.genai.Client` and `redis.from_url` with in-memory fakes, block
  non-loopback sockets, and `chdir` into a session temp dir so `data/`, `uploads/`, `logs/` land
  there. Zero production lines change and every line of our code still runs; the cost is coupling
  to the SDK call shapes (`models.embed_content`, `generate_content`, `generate_content_stream`)
  and a process-wide `chdir`.
- **B — Provider functions + `app.dependency_overrides` now:** wrap each singleton in a
  `get_llm()` / `get_retrieval()` / … provider, change ~15 route signatures to `Depends` them, and
  let `IndexBuilder` accept an injected embedding service. Matches the timeline's wording
  ("dependency overrides"), but it is Day 9's refactor done early in a 1,400-line file two days
  before that file is split, with no tests yet to protect the change.
- **Recommendation: A.** It is the smallest seam (none in production code), it protects the
  Phase 3 refactor instead of being part of it, and on Day 9 the fakes move unchanged behind
  `dependency_overrides`. The timeline's "dependency overrides" wording is still honoured for
  `get_db`-style deps where they already exist — but with A they aren't needed, since the module
  engine itself points at the temp database.

### 2. The broken image-table test (OpenCV wheel clash)
- **A — Fix the dependency now:** drop the unused `opencv-python` pin and make sure
  `opencv-contrib-python-headless` is installed *after* camelot's `opencv-python-headless`
  (force-reinstall step in the Dockerfile and locally), then assert real tables. Restores PPTX
  image-table extraction in production, but it is a dependency change (needs your approval), needs
  an image rebuild and a camelot re-check, and the install-order trick is fragile.
- **B — Fix the test, record the bug, mark it `xfail(strict=True)`:** the test is rewritten
  exactly as the timeline asks (tmp_path, single clean, check first, real assertion) and marked as
  an expected failure that names the cause; a new tracker item records the OpenCV clash and the
  silent PPTX impact for a later day (Day 8 lazy-loads these same libraries; Day 10 cleans deps).
- **Recommendation: B.** Today is about a trustworthy safety net, not about changing dependencies
  under it; strict xfail keeps the bug visible and turns into a failure the moment it is fixed.
  If you'd rather fix it today, A fits in checkpoint 1.

### Approved 2026-11-05
1A, 2B. B3 added to the tracker and to Day 10 of the timeline (ask before touching requirements).
Owner additions: (1) the socket guard also refuses loopback ports 6379 and 6380, and
`redis.Redis` / `redis.StrictRedis` are patched as well as `redis.from_url`; (2) find the cause of
Jest's "A worker process has failed to exit gracefully" warning and fix it or record it; (3) API
smoke test for account deletion: register → upload → chat → `DELETE /user/delete` → login fails,
and a new registration sees no old documents or sessions; (4) API smoke test for upload
rejection: `.exe` → 400, and a client name `../evil.pdf` is stored under `uploads/<user_id>/`
with display name `evil.pdf`.

## Plan

### Checkpoint 1 — T1 and the table test (≈ 6 file operations + one move command)
- `pytest.ini` — `[pytest]`; `testpaths = tests`; `pythonpath = . src` (adds `src` so the new
  conftest and tests don't need `sys.path.insert`; existing tests keep theirs — untouched);
  keep `addopts = -v`.
- `src/test_*.py` (11 files) → `scripts/manual/` with `Move-Item` (git sees the rename at commit;
  no `git mv` per the run-day rules). Scripts unchanged.
- `scripts/manual/README.md` — what these are (manual, live-API, never collected) and how to run
  one (`$env:PYTHONPATH="src"; python scripts/manual/<name>.py`).
- `tests/test_pptx_utils.py` — rewrite `test_table_extraction_on_image` (tmp_path copy, one call
  to `extract_tables_from_image`, existence check first, assert ≥ 1 table with ≥ 2 rows and ≥ 2
  columns; per Decision 2 B: `xfail(strict=True, reason=...)`). Prints in this test become
  assertions (no `print`, global rule). Other tests in that file untouched.
- Delete `tests/samples/tableimage2_cleaned.jpg`, `tableimage2_cleaned_cleaned.jpg` (untracked
  outputs); remove `.gitignore:44`.
- `docker-compose.override.yml` — mount `./tests` read-only again (the reason for `rw` is gone).
- Check: `python -m pytest tests -q`; bare `python -m pytest` from the root collects only `tests/`.

### Checkpoint 2 — conftest, fakes, first smoke tests (≈ 4 files)
- `tests/fakes.py` — `FakeRedis` (get / set / setex / delete / scan_iter as the app uses them),
  `FakeGenaiClient` (`models.embed_content` → hash-seeded 768-d vector; `generate_content` /
  `generate_content_stream` → scripted text, default per caller; queue for per-test overrides).
- `tests/conftest.py` — session setup *before* `import main`: dummy `GEMINI_API_KEY`,
  `JWT_SECRET_KEY`, `GOOGLE_*`, `TAVILY_API_KEY=""` (blocks the real `.env` value), patch
  `google.genai.Client` and `redis.from_url`, socket guard, `chdir` to a session tmp dir. Fixtures:
  `client` (TestClient), `fake_llm` (scripting handle), `auth` (registers a unique user, returns
  token + headers).
- `tests/test_semantic_cache.py` — import `FakeRedis` from `tests/fakes.py` instead of its own copy
  (one small edit; delete the duplicate class).
- `tests/test_api_smoke.py` — `/health`; register → login → `/me`; duplicate registration and
  wrong password rejected.
- Check: those tests + full suite; run once with the real `.env` renamed away is *not* needed —
  the env vars set in conftest win over `load_dotenv`; verified by the socket guard.

### Checkpoint 3 — the rest of the API smoke tests (1–2 files)
- `tests/test_api_smoke.py` — upload `samples.pdf` (chunks > 0, `doc_version` bumped) → list →
  delete → list empty; `/chat/stream` after an upload: parse SSE, assert
  `metadata → token+ → message_id → [DONE]`, sources include `samples.pdf`, answer = scripted text;
  same question again → cached replay with the same event order; sessions list / rename / delete;
  feedback up on the `message_id`; concept map generate with scripted JSON → nodes/edges saved,
  listed, deleted; a second user can't see the first user's documents or sessions.
- If the concept-map path needs more than the fake client (e.g. it swallows the Tavily
  `RuntimeError` differently), I report it rather than patch production code.
- Check: full suite twice in a row (no state leaks), timing recorded.

### Checkpoint 4 — frontend tests, outcome, posts, notes (≈ 5 files)
- `frontend/src/pages/LoginPage.test.js` — render `AppRoutes` at `/login`: form renders; submit
  posts to `/login` and stores the token and lands on `/chat`; 401 shows the error message.
  Doubles as the App smoke test CLAUDE.md promised for Day 5.
- `frontend/src/components/ChatWindow.test.js` — add: a normal stream renders the answer and a
  source, enables the feedback buttons, and reports the new session id.
- Check: `npm test -- --watchAll=false`, `npm run build` (CI=true-safe: no unused imports).
- Brief `## Outcome`; post 9 material-log line (Day 5 isn't mapped to posts 1–8/10); concept
  notes in `docs/learning/ai-concepts.md` if any heading matches (likely none — testing isn't an
  AI concept; I'll say so).

New dependencies: **none** (no `fakeredis`, no `pytest-socket`, no `httpx` beyond what FastAPI's
TestClient already uses — I'll confirm `httpx` is installed in checkpoint 2 and stop if not).

## UI integration
Backend-only — no user-visible change: every deliverable is tests, test config, or moving manual
scripts. No endpoint, field, status or flag changes. Frontend work today is tests of existing
screens (login, chat), not new UI.

## Verification
- `python -m pytest tests` from the repo root, with `GEMINI_API_KEY` and `TAVILY_API_KEY` unset in
  the shell: all pass; the socket guard proves no non-loopback connection was attempted.
- Bare `python -m pytest` collects nothing from `src/` or `scripts/`.
- No files appear in the repo after a run (`git status` clean apart from today's changes; no
  `data/`, `uploads/`, `logs/` at the root or in `tests/`).
- Time: baseline **84 passed in 42.6 s** (51 s wall). Target < 60 s; measured at checkpoint 3.
- `.\scripts\dev.ps1 test` in the container with `tests/` mounted read-only.
- Frontend: `npm test -- --watchAll=false` and `npm run build`.
- No retrieval/prompt/cache behaviour changes, so no eval numbers.

## Risks & open questions
- **Time budget:** importing `main` costs ~12 s (img2table chain, measured Day 4), on top of 42.6 s.
  The < 60 s target may be missed until Day 8's lazy loading. I'll report the real number, not
  trim tests to hit it.
- **Process-wide `chdir`:** existing tests use `__file__`-relative paths (checked:
  `test_pptx_utils.py:12`, `test_llm_modes.py`), so they're unaffected; any new test must do the same.
- **SDK coupling:** if `google-genai` changes call shapes, the fake breaks loudly — acceptable,
  and Day 9 narrows it to our own interfaces.
- **Day 8 note:** these tests import bare module names; Day 8's moves will update their imports
  (expected — the timeline says the smoke tests must pass "unchanged" in behaviour).
- **Found, not fixed (out of scope):** OpenCV wheel clash silently disables PPTX/image table
  extraction (Decision 2) — proposes a new tracker item; `chat_stream` swallows token errors with a
  bare `except:` (`main.py:819`) — Day 9; `DELETE /documents/{id}` leaves chunks searchable (I5,
  Day 15) — today's delete test asserts only the API contract, not index removal.
- **Question:** OK to add a tracker row for the OpenCV clash (e.g. `B3`), or fold it into T3?
  Answered: B3 added (P1, Day 10).

## Outcome

Date: 2026-11-05. All four checkpoints done. Decisions as approved: 1A (fakes at the SDK boundary,
no production seam), 2B (table test rewritten and `xfail(strict=True)`, B3 recorded).

### Files changed
**T1 and the table test (checkpoint 1)**
- `pytest.ini` — `[pytest]` header; `pythonpath = . src`
- `src/test_*.py` → `scripts/manual/` — 11 manual scripts moved unchanged (stage both sides so git records renames)
- `scripts/manual/README.md` — new: what the scripts are and how to run one
- `tests/test_pptx_utils.py` — `test_table_extraction_on_image` rewritten (tmp_path copy, one clean, existence check first, asserts ≥ 1 table with ≥ 2 rows × 2 columns) and `xfail(strict=True)` → B3; unused import and duplicate `import os` removed
- `tests/samples/tableimage2_cleaned*.jpg` — 2 untracked outputs deleted; `.gitignore` — their ignore line removed
- `docker-compose.override.yml` — `./tests` mounted read-only again

**Offline harness (checkpoint 2)**
- `tests/fakes.py` — new: `FakeRedis` + `FakeRedisServer`, `FakeGenaiClient` / `FakeGemini` (deterministic embeddings, scripted replies and streams, call counters), `FakeTavilyClient`
- `tests/conftest.py` — new: `pytest_configure` sets dummy env (empty `TAVILY_API_KEY` blocks the real `.env`); patches `redis.from_url` / `Redis` / `StrictRedis`, `google.genai.Client`, `tavily.TavilyClient`; installs the socket guard (non-loopback connects and DNS refused, loopback 6379/6380 refused); chdirs into a temp dir. `pytest_unconfigure` releases SQLite + log handles and removes it. Fixtures `app`, `client`, `account`, `gemini`, `web_search`
- `tests/test_network_guard.py` — new: 6 tests proving the guard and the patches hold
- `tests/test_semantic_cache.py` — uses the shared `FakeRedis`; duplicate class and unused import deleted

**API smoke tests (checkpoint 3)**
- `tests/test_api_smoke.py` — new, 18 tests: health; register/login/me; duplicate email 400; wrong password 401; missing/bad token 401; upload → list → delete; `.exe` 400; `../evil.pdf` stored in `uploads/<id>/` under a server name, shown as `evil.pdf`; `/chat/stream` contract (`metadata → token… → message_id → [DONE]`, sources include `samples.pdf`, messages stored); semantic-cache replay (0 LLM stream calls, same contract); injection refusal over SSE (not stored); `/chat/stream` bad token 401; sessions list/rename/delete; feedback up/down → failed-queries log; cross-user isolation (documents, sessions, messages, feedback, chat sources); account deletion (login fails, re-registration with the same email sees nothing, chat sources clean); concept map generate/list/get/statistics/delete; concept map with no context (empty, no LLM call)
- `tests/test_docx_pdf_utils.py` — unused `preprocess_image` import removed (Day 6 ruff)
- `src/concept_extractor.py` — **B4 fix (deviation from the plan, approved)**: `_add_source_attribution` assigned `[web_sources]` / `[doc_sources]` (a list inside a list) instead of the first source, so any node with empty `sources` made `POST /api/concepts/generate` return 500. Now `[web_sources[0]]` / `[doc_sources[0]]`
- `tests/test_concept_extractor.py` — new, 4 unit tests: web fallback, document fallback, kept sources, no source of that type

**Frontend (checkpoint 4)**
- `frontend/src/pages/LoginPage.test.js` — new, 3 tests (also the App smoke test): anonymous `/chat` → login form; sign-in posts form-encoded credentials, stores the token, opens the chat; wrong password shows "Invalid credentials" and stays on the form
- `frontend/src/components/ChatWindow.test.js` — new test: a normal stream renders answer + source, reports session 42, and thumbs-up posts to `/messages/7/feedback` (the streamed `message_id`)

**Docs**
- `docs/improvement-tracker.md`, `docs/improvements.md` — B3 (P1, Not Started, Day 10; production impact confirmed in the backend image) and B4 (Done Day 5)
- `docs/timeline.md` — B3 bullet on Day 10
- `docs/posts/09-launch-recap.md` — Day 5 line; `docs/learning/ai-concepts.md` — §9 Structured output (first fill), §14 Semantic caching (Day 5 update)

**Housekeeping (owner-approved, outside git)**
- Deleted repo-root `data/` (`app.db` = Alembic's empty side DB, only `alembic_version` with 0 rows; `faiss_index.bin`; `faiss_metadata.json`) and `uploads/` (4 old files), then the empty folders. Checked first: the app resolves `src/data/` and `src/uploads/`, and 0 of the 2 `documents` rows point at the root. `src/data/` and `src/uploads/` untouched. The root `logs/` (written by pre-Day-5 test runs) is still there.

### Checks
| Check | Result |
|---|---|
| Baseline before Day 5 (host) | 84 passed in 42.6 s (51 s wall) |
| Checkpoint 1 — host | 83 passed, 1 xfailed in **21.4 s** (28 s wall) |
| Checkpoint 1 — container (`dev.ps1 test`, tests `:ro`) | 83 passed, 1 xfailed in **73.9 s** |
| Final — host, `GEMINI_API_KEY` / `TAVILY_API_KEY` unset | **111 passed, 1 xfailed in 23.3 s** (34.9 s wall); 26.1 / 24.6 / 21.5 s on earlier runs |
| Final — container | **111 passed, 1 xfailed in 77.7 s** |
| Bare `python -m pytest` from the root | collects 112 items, all from `tests/` |
| Repo stays clean after a run | no `data/`, `uploads/`, `logs/` written in the repo; 0 `rag-tests-*` temp dirs left |
| ruff (`E9,F63,F7,F82,F401`) on `tests/` | clean |
| `python -m py_compile src/concept_extractor.py` | ok |
| Frontend `npm test -- --watchAll=false` (CI=true) | 5 suites, **11 passed** (was 7); 19.1 s |
| Frontend `npm run build` (CI=true) | compiled, no warnings |
| `docker compose config` | valid |

**Against the < 60 s target:** the host run meets it (23 s). The container run doesn't (74–78 s).
That's expected until Day 8 lazy-loads the OCR/table import chain: the container loads it on a
slower bind-mounted filesystem.

**Jest "A worker process has failed to exit gracefully" (owner addition 2):** not reproduced in 5
runs (parallel ×3, `--runInBand --detectOpenHandles`, parallel `--detectOpenHandles`), before and
after today's new tests. `--detectOpenHandles` reports nothing. The timers in the app
(`AccountSettingsModal.js:95` 3 s success reset, `MessageList.js:65` 2 s copy reset,
`AuthCallback.js` 3 s redirects) aren't reached by any test, and the 50 ms delay in
`useAuth.login` is awaited and finishes inside the test. Day 4's output wasn't saved, so the
original trigger can't be checked. Most likely cause: worker shutdown timing under load, not a
leak. Today's first, cold run (no Babel cache) took 30–44 s per suite vs 7–12 s warm, and Day 4
ran with the Docker stack up. If it comes back in CI (Day 6), rerun with `--detectOpenHandles` and
fake the timers in the test that triggers it.

### UI integration
| Backend change | Frontend | What the user sees |
|---|---|---|
| B4 fix in `concept_extractor.py` | none needed — `ConceptMapPage` / `CreateMapForm` already call `POST /api/concepts/generate` | concept maps whose LLM reply had a node without sources now render instead of the "Failed to generate concept map" error |
| Tests, pytest config, moved scripts | — | backend-only: no endpoint, field, status or flag changed |

### Deviations from the plan
- **B4 fixed in production code** (`src/concept_extractor.py`, 2 lines): found by the concept-map smoke test, approved by the owner. Unit tests and tracker/improvements entries added.
- **`FakeTavilyClient` added** (not in the brief): the default concept-map path is web-only, so without a Tavily fake it never reaches the LLM and the JSON parsing can't be tested. Same seam as Gemini; web search stays off unless a test turns it on.
- **`tests/test_network_guard.py`** added to prove the guard (owner addition 1).
- Owner additions 3 and 4 (account deletion, upload rejection) are in `test_api_smoke.py`.

### Deferred / not done
- B3 (OpenCV clash) → Day 10, as approved.
- Done afterwards at the owner's request: removed the 3 pre-existing unused imports (`re`, `List`, `Any`) from `src/concept_extractor.py` (Day 6 CI runs ruff); deleted the repo-root `logs/` (one `app.log`, written by pre-Day-5 test runs; `src/logs/` untouched); updated CLAUDE.md (Current Status, module map, Known Issues T1/B3/B4, frontend tests, Key Commands) and marked T1 Done in the tracker.

### Numbers for the tracker
- T1 Notes: "Day 5: `[pytest]` header; 11 `src/test_*.py` → `scripts/manual/`; bare `pytest` collects only `tests/` (112 items). Suite 84 → 111 tests (+1 strict xfail), 42.6 s → 23.3 s on the host with no keys or network; container 77.7 s (Day 8 lazy loading)."
