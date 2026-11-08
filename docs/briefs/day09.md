# Day 9 — Split main.py into routers, add dependency injection, one chat pipeline
Date: 2026-11-08 · Phase 3 — Codebase refactor — proper package structure · Items: B2, G3 (prep only)
Branch: feature/day09-routers-di

## Scope
1. **Routers.** One `APIRouter` per area under `app/api/routes/`: `auth` (Google OAuth + logout,
   joined by `/register`, `/login`, `/change-password`, `/me`), `users`, `documents`, `chat`,
   `sessions`, `feedback` (new name: `/messages/{id}/feedback` + `/analytics/failed-queries` — the
   layout's list had no home for them), `quiz`, `concepts`, `health`. `routes/auth_routes.py` moves
   to `api/routes/auth.py`.
2. **App factory + lifespan + `Depends`.** `main.py` becomes `create_app()`; a lifespan builds the
   LLM client, embedding service, indexes, retrieval service, caches and Redis clients once and puts
   them on `app.state`; routes reach them only through `app/api/deps.py`. `get_db` and
   `get_current_user*` move from `core/security.py` to `api/deps.py` (removes the
   `core → db` layering exception). The deprecated `@app.on_event("startup")` goes into the lifespan.
3. **One chat pipeline.** `services/chat_pipeline.py` (`ChatPipeline`) holds what `/chat/stream`
   does today; `GET /chat/stream` calls it. `POST /chat` is deleted — **needs the owner's
   confirmation** (Decision 1). Quiz prompt logic moves to `services/quiz_service.py` (layout row, Day 9).
4. **B2.** The `/chat` 0.7 / 0.3 thresholds disappear with `/chat`. Fix the forced-web cap
   (`min(confidence, 0.3)` on a 0–100 scale) and define the confidence scale and every threshold
   once, as named constants (Decision 3).
5. **One keyword safety list** in `services/chat_guards.py` (prep for G3, Day 35) — Decision 2.
   G3 itself (real moderation) stays Not Started.
6. **Startup cost.** One shared `google.genai.Client` built in the lifespan and passed to every
   consumer; drop `IndexBuilder`'s startup embedding call (known dimension, Decision 4). Measure
   `import app.main` against Day 8's 23–25 s, plus lifespan startup time.
7. **Verify:** SSE contract unchanged; the frontend works with zero edits.

Not in scope, though the layout lists them for Day 9 — see Decisions 6–8: the `db/` split into
`db/session.py` + `db/models/`, thinning the CRUD routers (SQL into services), and the
`ingestion → retrieval` indexing edge.

## Current behavior
- **Everything lives in `main.py` (1353 lines).** 27 route handlers (`main.py:86-1343`) plus
  `include_router(auth_router)` (`:74`). Module-level singletons at import (`:76-83`):
  `IndexBuilder()`, `BM25KeywordIndex()`, `IndexingPipeline`, `RetrievalService`, `LLMClient()`,
  `QueryDecomposer`, `SemanticCache`, `SimpleContextCompressor`. Imports are scattered and
  repeated mid-file (`:240-251`, `:414`, `:1066-1068`); `HTTPException` and `desc` are used before
  their import line and only work because they're resolved at call time.
- **Seven `genai.Client` constructions, five at import of `app.main`:** `EmbeddingService`
  (`retrieval/embeddings.py:17`), `LLMClient` (`generation/llm_client.py:18`), `TopicClassifier`
  (module-level singleton, `generation/topic_classifier.py:23,123`), `CrossEncoderReranker`
  (`retrieval/reranker.py:17` — builds a client and never uses it), and on first concept-map call
  `ConceptMapService` → `ConceptMapRetriever()` builds its *own* `IndexBuilder` + `BM25KeywordIndex`
  + `RetrievalService` (`retrieval/concept_map_retriever.py:36-53`, i.e. two more clients, a second
  startup embedding call, and R5's empty index) and `ConceptExtractor` (`generation/concept_extractor.py:38`).
  Day 8 measured ~3 s per client on this host; `app.main` import 23–25 s.
- **Startup embedding call:** `IndexBuilder.__init__` embeds `"hello world"` only to learn the
  dimension (`retrieval/index_builder.py:15-17`). `gemini-embedding-001` defaults to 3072
  dimensions; the failure fallback in `embeddings.py:39-41` appends a 768-long zero vector, which
  can't be stacked with 3072-long ones.
- **Two chat pipelines.** `POST /chat` (`main.py:557-740`) and `GET /chat/stream` (`:742-988`)
  repeat the same 12 steps with drift: `/chat` grounds on 0.7 / 0.3 (`:670-675`) — always "strict"
  on a 0–100 score — and calls `generate_followups`; `/chat/stream` uses 70 / 30 (`:902`). The
  frontend calls only `/chat/stream` (`frontend/src/components/ChatWindow.js:126`); no test or
  frontend file calls `POST /chat` (grep).
- **`/chat/stream` auth by hand** (`main.py:751-765`): decodes `?token=` itself and swallows every
  error with a bare `except: pass`.
- **Two keyword safety lists.** `/chat`: `suicide, kill myself, nuke, die, self harm, explosives,
  terrorist, make a bomb` (`:582`) — `"die"` as a substring blocks *"I studied…"*, *"diet"*,
  *"diesel"*. `/chat/stream`: `explosive, bomb, suicide, self harm` (`:782`) — `"bomb"` blocks
  *"electron bombardment"*. Different refusal texts too.
- **B2 forced-web cap.** `retrieval/retrieval_service.py:352-353`: when the keyword/example
  heuristic fires, `confidence = min(confidence, 0.3)` — effectively 0 on the 0–100 scale. Only the
  web-result bump at `:399-411` raises it again, and only if a web chunk makes the top 5 (never when
  Tavily is off or fails). Thresholds 60 (`:357`), 40 (`:403`), 70 / 30 (`main.py:902`), 30
  (`main.py:927`) are bare literals.
- **Upward edge:** `RetrievalService` imports the Redis helpers in `services/caches/` (`:13,15`);
  `query_cache.py:7` builds a Redis client at import, `web_cache.py:11` one per call.
- **L1 cache is class-level:** `_manual_l1_cache` (`retrieval_service.py:64`) is shared by every
  `RetrievalService` instance in the process.
- **Duplicate `get_db`** in `routes/auth_routes.py:15-20`.
- **Tests** build the app by `from app import main` once per session (`backend/tests/conftest.py:173-176`)
  and fake Gemini / Redis / Tavily at the SDK constructors; the fake embedder returns 768-dim
  vectors whatever is requested (`backend/tests/fakes.py:11,120-123`).
- **Eval scripts** `rag_metrics.py`, `rag_eval_runner.py`, `manual_eval.py`, `cache_tuner.py`
  import `llm_client` / `retrieval_service` / `index_builder` / `semantic_cache` from `app.main`.

## Why it matters
- **Routers:** a 1353-line file with 27 handlers is where every later day (Projects, connectors,
  study features) would add more — every change touches the same file, and nothing enforces
  "routers are thin".
- **DI / lifespan:** import-time singletons mean *importing* the app costs 23–25 s and makes network
  calls; `uvicorn --reload` pays that on every save; tests can only fake at the SDK level; and the
  eval code has to `import main` to get a retrieval service.
- **One pipeline:** a fix applied to one endpoint silently misses the other — B2's 0.7 / 0.3 is
  exactly that. Same question → "strict" grounding on `/chat`, "loose" or "none" on `/chat/stream`.
- **B2:** a query about a topic the user's documents don't cover, with Tavily down → confidence
  0.3 → grounding "none" and logged as a failed query, regardless of how close the retrieval was.
- **Safety list:** a student typing *"I studied the diet of…"* gets a self-harm refusal on `/chat`;
  *"electron bombardment"* gets one on the stream.
- **Shared client / no startup call:** ~3 s per client × 5 at import; plus the startup embedding
  call fails the whole boot if Gemini is unreachable for a moment.

## The concept

### 1. Composition root and dependency injection
A *composition root* is the one place where the object graph is built: which LLM client, which
index, which cache, wired together. Everything else **receives** its collaborators instead of
constructing them (`RetrievalService(index_builder, bm25, query_cache, web_cache)` rather than
`RetrievalService()` reaching for module globals). Benefits:
- **Lifetimes are explicit.** One process-wide `genai.Client`, one FAISS index — not "whatever
  each module happened to build". R5 is a textbook lifetime bug: two `IndexBuilder`s, one of them
  never written to.
- **Tests swap implementations** without monkeypatching import paths.
- **Layers stay honest.** `retrieval` no longer needs to import `services.caches`; it takes
  whatever object has `get` / `set`.
Pitfall: DI frameworks and service locators. Here the "container" is a plain dataclass built in
one function; no magic (owner rule).

### 2. FastAPI app factory and lifespan
`create_app()` returns a configured `FastAPI` — middleware, routers, exception handlers — without
doing I/O. The **lifespan** is an async context manager FastAPI runs around the server's life:
code before `yield` runs at startup (build clients, `init_db()`), code after runs at shutdown
(close Redis pools). It replaces `@app.on_event("startup")`, which is deprecated. Why it matters:
- **Import is cheap and side-effect free.** `uvicorn --reload`, pytest collection, `ruff`, and
  scripts can import modules without network calls.
- **Startup failures are startup failures**, reported once, not import errors in random modules.
- **Several apps per process** (tests) each get their own state.
Pitfalls: building things in `create_app()` instead of the lifespan (back to import cost when
`app = create_app()` runs at module level); forgetting that `TestClient` runs the lifespan only
inside `with TestClient(app)`; and middleware order — the *last* middleware added is the outermost,
so `RequestIdMiddleware` must still be added last.

### 3. `app.state` + `Depends` — request-scoped access to app-scoped objects
`Depends(fn)` makes FastAPI call `fn` per request and pass the result in. Three lifetimes coexist:
- **App-scoped** (built once in the lifespan, on `app.state`): genai client, indexes, caches,
  `ChatPipeline`. A dependency like `get_services(request) -> Services` just reads `request.app.state`.
- **Request-scoped** (`yield` dependencies): the SQLAlchemy `Session` from `get_db`, opened per
  request and closed after.
- **Derived per request:** `get_current_user` depends on `get_db` and the token.
Tests override any of these with `app.dependency_overrides[get_services] = lambda: fake`.
**Streaming pitfall:** a `StreamingResponse` body runs *after* the endpoint function returns. In
FastAPI ≥ 0.118 (this repo: 0.122) a `yield` dependency's exit code runs after the response has
been sent, so the DB session stays open while tokens stream; FastAPI 0.106–0.117 closed it before
the body ran. 0.121 added `Depends(..., scope="function")` for the early-exit behaviour. The SSE
generator writes the assistant message through that session at the end of the stream, so this
ordering is load-bearing; a smoke test covers it.

### 4. One pipeline, thin transports
The chat pipeline (guard → cache → session → history → retrieve → compress → ground → prompt →
generate → store) is *domain logic*; SSE vs JSON is *transport*. Production systems keep one
pipeline and put adapters on top, because two copies drift (B2). Here the frontend only streams, so
the cheapest correct move is one pipeline and one transport. If a JSON endpoint is needed later
(an API client, the eval harness), it should consume the same pipeline, not a copy.

### 5. Scales, thresholds and magic numbers (B2)
A score is only meaningful with its scale. `0.3` and `30` look alike in a diff and mean opposite
things on a 0–100 scale. The fix is to name the scale and every threshold once
(`CONFIDENCE_MAX = 100.0`, `GROUNDING_STRICT_MIN = 70.0`, …) and compare only against the names.
Thresholds on an unvalidated heuristic are still guesses — E4 (Day 11) measures whether 70 / 30
separate good from bad retrievals; named constants make that tuning a one-line change.

### 6. Blocklists vs moderation (G3 prep)
Substring keyword lists have two failure modes at once: false positives (*"studied"* contains
*"die"*) and trivial bypasses (typos, other languages). They're a tripwire, not a defence. Real
moderation (Gemini safety settings or a classifier, Day 35) needs **one** call site to replace —
which is what consolidating the list buys today.

### 7. Embedding dimension as a contract
A vector index has a fixed dimension; every vector added or queried must match. Probing the model
at startup ("embed 'hello world' and read the shape") makes boot depend on the network and hides
the contract. Matryoshka-trained models such as `gemini-embedding-001` (3072 by default, also 1536
or 768) let you *request* the size via `output_dimensionality` — so the request states the
contract and the index is built to match. Pitfall: changing the dimension invalidates every stored
vector (relevant on Day 13–16 with pgvector), and truncated Matryoshka vectors must be
re-normalized (the code already L2-normalizes).

## Decisions

### 1. `POST /chat` (open decision in CLAUDE.md)
- **A — Delete it; one `ChatPipeline` behind `/chat/stream`:** the frontend, the tests and the docs'
  request flow use only the stream, so deleting removes the drift and ~185 lines. Trade-off: no JSON
  chat endpoint for scripts or the eval harness until one is rebuilt on the pipeline (Day 11–12 can
  call `ChatPipeline` directly in Python).
- **B — Keep both on a shared pipeline:** `/chat` becomes a thin adapter that collects the stream.
  Trade-off: an untested, unused endpoint (and its `generate_followups` call, an extra LLM call per
  request) to keep correct.
- **Recommendation: A.** Nothing calls it; the eval harness needs Python access, not HTTP.
  **Owner confirmation required.**

### 2. The one keyword safety list
- **A — The stream's list plus the two safe multi-word entries from `/chat`:** `explosive, bomb,
  suicide, self harm, kill myself, terrorist`, substring match, the stream's refusal text. Drops
  `die` and `nuke` (false positives on "studied", "diet", "nuked"); `explosives` and `make a bomb`
  are already covered. Trade-off: still flags "electron bombardment" — left for G3.
- **B — The stream's list unchanged:** zero behaviour change for the only live endpoint. Trade-off:
  `/chat`'s self-harm phrase "kill myself" is lost with `/chat`.
- **Recommendation: A** — keeps every self-harm phrase either list had without importing `die`'s
  false positives; refusals stay unstored and SSE-shaped, as today.

### 3. B2 — value of the forced-web cap
- **A — Cap at 30 (`FORCED_WEB_CONFIDENCE_CAP = 30.0`):** the literal 0–100 reading of `0.3`; the
  comment's intent ("below the 60 fallback threshold") holds. Effect: when the heuristic fires and no
  web chunk lands, the score is ≤ 30 → grounding "loose" at exactly 30, "none" below.
- **B — Cap just below the loose threshold (e.g. 29):** forced-web queries without web support always
  get "none" grounding and are logged as failed queries, as the 0.3 cap effectively did. Trade-off:
  ties the retrieval cap to a generation threshold.
- **Recommendation: A** — it's what the code meant; the heuristic already multiplies the score by
  0.5 / 0.6, so most forced-web scores end below 30 anyway. E4 (Day 11) validates the numbers.
  Constants live in `retrieval/confidence.py` (grounding thresholds too, since they're on this scale).

### 4. Embedding dimension without the startup call
- **A — Request it explicitly:** `EMBEDDING_DIM = 3072` in `retrieval/embeddings.py`, passed as
  `output_dimensionality` on every `embed_content` call; FAISS is built with it; the zero-vector
  fallback uses it; the test fake honours `output_dimensionality`. Trade-off: one constant to change
  deliberately later (pgvector, Day 13).
- **B — Lazy: build the FAISS store on the first embedding:** no constant. Trade-off: `search` before
  any upload must special-case "no index yet", and the dimension contract stays implicit.
- **Recommendation: A.** I'll confirm 3072 with one live embedding call before relying on it (needs
  your OK — it uses the real key).

### 5. Concept maps share the app's retrieval service
- **A — Inject the shared `RetrievalService` and `ConceptExtractor` from the lifespan** (removes the
  second `IndexBuilder`, two `genai.Client`s and `get_concept_map_service()`'s global). Side effect:
  `use_documents=True` would now search the real index — but the UI hard-codes
  `useDocuments = false` (`CreateMapForm.js:8`), so nothing user-visible changes; R5 (test + UI
  toggle) stays on Day 17.
- **B — Keep the concept-map service's own private retrieval stack**, just built in the lifespan.
  Trade-off: keeps R5's empty index and two extra clients alive for 8 more days.
- **Recommendation: A** — it is R5's own "direction"; I'll note it in the tracker Notes as
  "half-done Day 9" rather than marking R5 Done.

### 6. Upward edge `retrieval → services/caches`
- **A — Inject cache objects:** `query_cache.py` / `web_cache.py` become small classes holding a
  Redis client built in the lifespan; `RetrievalService` takes them in its constructor and imports
  nothing from `services`. Also gives one Redis client per URL instead of one per call.
- **B — Move the two helpers down into `retrieval/`:** simplest, but Redis-backed caches then live in
  two layers (the semantic cache stays in `services/caches`).
- **Recommendation: A** (the layout's proposed fix).

### 7. How thin the routers get today
- **A — Thin only chat and quiz** (into `ChatPipeline` / `quiz_service`); the small CRUD handlers
  (sessions, documents list, stats, feedback, register) move into routers **body-for-body** with
  their SQL, listed as a known exception to layout rule 3 until Day 13's repositories.
- **B — Move all SQL into services now.** Trade-off: ~15 more functions and a much larger diff on the
  day the routing changes, and Day 13 rewrites these queries for Postgres anyway.
- **Recommendation: A.**

### 8. Layout rows deferred
- `db/` split into `db/session.py` + `db/models/` → **Day 13** (Postgres rewrites the engine and
  session; split once). Recommended over doing it today.
- `ingestion/indexing_pipeline → retrieval` edge → **Day 15** (indexing into pgvector is rewritten
  then). Recommended over a new `services/indexing_service.py` today.

### 9. How services reach routes
- **A — One typed `Services` dataclass on `app.state.services`** and one `get_services` dependency
  (plus narrow ones like `get_chat_pipeline` built on it). Explicit and easy to override in tests.
- **B — One attribute + one dependency per service** (`app.state.llm_client`, `get_llm_client`, …).
  More boilerplate, same behaviour.
- **Recommendation: A.**

## Plan
Python files are new modules unless marked "edit". Each checkpoint ends with
`python -m py_compile`, `ruff check .`, and `python -m pytest` (all must be 134 passed + 2 xfailed,
minus/plus tests named below).

**Checkpoint 0 — baseline (no edits).** `python -m pytest`; time `import app.main` ×3 (fresh
process, real `.env` — makes one real embedding call, as every start does today); one live
`embed_content` call to confirm the 3072 dimension (Decision 4). **Needs your OK for the live calls.**

**Checkpoint 1 — injectable clients (8 files).**
- edit `generation/llm_client.py`, `generation/topic_classifier.py` (drop the module-level
  `topic_classifier` singleton), `generation/concept_extractor.py`, `retrieval/embeddings.py`:
  constructors take a `genai.Client`; `EMBEDDING_DIM` + `output_dimensionality`; fallback vector
  sized by it (its `print` → `logger.warning`, since I'm editing that block)
- edit `retrieval/reranker.py`: drop the unused client
- edit `retrieval/index_builder.py`: takes an `EmbeddingService`, no startup call
- edit `backend/tests/fakes.py`: honour `output_dimensionality`
- edit `main.py`: build one client at module level for now (temporary until Checkpoint 4, so the
  suite stays green between checkpoints)

**Checkpoint 2 — retrieval wiring + B2 (7 files).**
- add `retrieval/confidence.py`: scale + thresholds (Decision 3)
- edit `retrieval/retrieval_service.py`: injected caches, instance-level L1 cache, constants, cap fix
- edit `services/caches/query_cache.py`, `services/caches/web_cache.py`: classes over an injected client
- edit `retrieval/concept_map_retriever.py`, `services/concept_map_service.py`: injected
  retrieval service + extractor; delete `get_concept_map_service`
- add `backend/tests/test_confidence.py`: forced-web path caps at 30 not 0.3; grounding thresholds

**Checkpoint 3 — services (5 files).**
- add `services/chat_pipeline.py`: `ChatPipeline` (guards → cache replay → session/history/topic →
  retrieve → compress → ground → stream → store), yielding the same SSE strings as today
- add `services/quiz_service.py`: prompt building + `LLMClient` call from `main.py:992-1064`
- edit `services/chat_guards.py`: `UNSAFE_KEYWORDS`, `find_unsafe_keyword`, `UNSAFE_REFUSAL` (Decision 2)
- edit `backend/tests/test_chat_guards.py`: the unified list, incl. "I studied the diet of…" allowed
- edit `main.py`: `/chat/stream` delegates to `ChatPipeline`; `POST /chat` deleted (if Decision 1 = A)

**Checkpoint 4 — routers + deps (11 files).**
- add `api/__init__.py`, `api/routes/__init__.py`, `api/deps.py` (`get_db`, `get_current_user`,
  `get_current_user_optional`, `get_user_from_query_token`, `get_services`, `Services` dataclass)
- move `routes/auth_routes.py` → `api/routes/auth.py` (+ register/login/change-password/me);
  delete `routes/`
- add `api/routes/{health,users,documents,chat,sessions,feedback,quiz,concepts}.py`
- edit `core/security.py`: keep hashing + JWT only
- Callers of `get_db` / `get_current_user` outside main (grep) switch to `app.api.deps`

**Checkpoint 5 — factory, lifespan, tests (3–4 files).**
- edit `main.py`: `create_app()` + `lifespan` (build `Services`, `init_db()`, close Redis on
  shutdown); `app = create_app()` for uvicorn; middleware order preserved
- edit `backend/tests/conftest.py`: docstring + `app` fixture via the factory (fakes stay at the SDK
  boundary — they still apply)
- add one smoke test: the app imports without constructing any `genai.Client` (counts constructions
  until the lifespan runs)
- Run: full suite host + `.\scripts\dev.ps1 test`; `uvicorn app.main:app` → `/docs` lists the 27
  remaining routes (28 − `POST /chat`); import time ×3; lifespan startup time; reload time.

**Checkpoint 6 — docs + verification.**
- `docs/architecture/layout.md`: status, exceptions table (2 removed, 1 rescheduled to Day 15,
  1 new: CRUD SQL in routers until Day 13), module-map rows
- `CLAUDE.md` (non-Status sections): module map, request flow, API list, conventions (drop "mirror
  `/chat` and `/chat/stream`"), Open Decisions (chat endpoints resolved)
- `docs/improvements.md`: B2 note; brief `## Outcome`; post material; learning notes
- Manual: frontend + backend running locally, one upload + chat + cached repeat + refusal (you, or me
  if you want me to drive it)

New dependencies: **none.**

## UI integration
- **Routers, factory, lifespan, deps, shared client, no startup call** — backend-only, no
  user-visible change: the same 27 paths, same request/response shapes. Proof: smoke tests unchanged.
- **`POST /chat` deleted** — no frontend caller (`grep "/chat"` in `frontend/src`: only
  `ChatWindow.js:126` → `/chat/stream`, the rest are router paths). Nothing to wire.
- **ChatPipeline** — same SSE events in the same order (`metadata → token… → message_id → [DONE]`,
  refusals `metadata(refused) → token → [DONE]`, errors `{"type":"error"}`), consumed unchanged by
  `ChatWindow.js`. Loading / empty / error states already exist there.
- **B2 cap** — changes the `confidence` value in the `metadata` event on the forced-web path
  (≤ 30 instead of ≤ 0.3) and possibly the grounding level of the answer. `ChatWindow.js:151` stores
  `confidence` but nothing renders it; grounding only changes the answer's wording. No UI change needed.
- **Safety list** — refusal text for unsafe topics stays the stream's existing message, rendered by
  the existing refusal path (`ChatWindow.js:145`).

## Verification
- Before / after: `python -m pytest` (134 passed + 2 xfailed → same + new tests); `test_api_smoke.py`
  **unchanged** — it is the SSE-contract proof.
- New tests: `test_confidence.py` (B2), unified keyword list in `test_chat_guards.py`, "importing
  `app.main` builds no Gemini client".
- `.\scripts\dev.ps1 test` (Linux / Python 3.11 container); `ruff check .`; CI on the PR.
- `uvicorn app.main:app`: starts, `/health` ok, `/openapi.json` path count 27, `POST /chat` absent.
- Timing (host venv, real `.env`, fresh process ×3): `import app.main` vs 23–25 s; lifespan startup
  (server start → "Application startup complete"); `--reload` restart after a file edit.
- Manual frontend check with zero frontend edits: login, upload, chat streams with sources, repeat
  question is served from the semantic cache, an injection phrase and an unsafe keyword are refused,
  thumbs feedback, a concept map (web) generates.
- No retrieval-quality measurement possible yet (E4 is Day 11); the B2 change is covered by unit tests.

## Risks & open questions
- **Lifespan per `TestClient`:** each test's `with TestClient(app)` now runs the lifespan, so FAISS /
  BM25 / L1 state is fresh per test instead of per session. Tests that implicitly relied on
  carry-over would fail — none expected (each test uses a fresh account), but it's the likeliest
  breakage. The SQLite file is still shared across tests.
- **Streaming + DB session lifetime** (The concept §3): correct on FastAPI 0.122; a future FastAPI
  downgrade or `scope="function"` would close the session before the stream writes the message.
- **Eval scripts break today:** `rag_metrics.py`, `rag_eval_runner.py`, `manual_eval.py`,
  `cache_tuner.py` import globals from `app.main` that will no longer exist. They're already
  non-functional, untested and rewritten on Days 10–12; I won't patch them. OK?
- **Day 10 / later effects:** Day 10's eval move gets simpler (build `Services` directly). Day 13 now
  owns the `db/` split and the CRUD-SQL-in-routers exception; Day 15 owns the indexing edge.
- **Not fixing (recorded only):** blocking sync calls (SQLAlchemy, Gemini, Tavily) inside `async def`
  routes and the SSE generator stall the event loop under concurrency (Day 38 area);
  `logging.basicConfig` in `concept_map_service.py` / `concept_map_retriever.py`; `print()` and broad
  `except Exception` in `embeddings.py` beyond the fallback line I touch; mojibake emoji in
  `concept_map_retriever.py` log lines; `delete_document`'s commented-out file removal (dropped when
  the handler moves — dead code — the real delete is Day 15).
- **Rename detection:** `routes/auth_routes.py` → `api/routes/auth.py` gains four routes; if git
  doesn't detect the rename, commit the move alone first (layout rule 6). I'll do the move as the
  first step of Checkpoint 4 so you can commit it separately if you want.
- **Live calls in Checkpoint 0** need your OK (one embedding call ×4, real key, no data sent but
  "hello world").
- **Found during implementation (recorded, not fixed):**
  - `import app.main` is still 9.5–10.4 s with nothing built at import: library imports — the
    `google.genai` SDK 2.75 s, the ingestion parser chain 2.44 s, FastAPI 1.9 s, SQLAlchemy 1.0 s
    (`-X importtime`). Further cuts mean lazy imports of the SDK / parsers — not planned for any day yet.
  - Docker dev reload is 18.6 s (was 20.8 s), almost all of it before the new worker starts: file
    reads through the Windows bind mount, not app code. The lifespan itself takes 0.27 s in the container.
  - The live concept map asked for `max_concepts=6` returned 8 nodes — the extractor doesn't
    enforce the limit (pre-existing; S1 territory, Day 44).
  - `AsyncGenerator` unused in `generation/llm_client.py`, `User` unused in
    `services/concept_map_service.py` (pre-existing; the bug-only ruff rules don't flag F401 — Day 10).

## Outcome
Date: 2026-11-08. Six commits on `feature/day09-routers-di` → draft PR #11 into `develop`; CI
(`backend`, `frontend`, `docker`) green after each of the first five. All nine decisions taken as
recommended (owner, 2026-11-08); `POST /chat` deletion confirmed by the owner.

### Commits and files
- **`c533056` — Checkpoint 1, injectable clients (14 files incl. this brief)**
  - new `core/gemini.py` (`build_gemini_client()`); `LLMClient`, `TopicClassifier`, `ConceptExtractor`, `EmbeddingService` take a `genai.Client`; `TopicClassifier`'s module singleton and no-key branch deleted
  - `retrieval/embeddings.py`: `EMBEDDING_DIM = 3072` sent as `output_dimensionality`; fallback vector sized by it; `print` → `logger.warning`
  - `retrieval/index_builder.py`: takes an `EmbeddingService`, no startup embedding call; `retrieval/reranker.py`: unused client removed
  - `retrieval/concept_map_retriever.py` + `services/concept_map_service.py`: injected collaborators, `get_concept_map_service()` and both demo `__main__` blocks / `create_*` factories deleted (moved here from Checkpoint 2 to keep the suite green between checkpoints)
  - tests: `fakes.py` honours `output_dimensionality`; `test_config.py` targets `build_gemini_client`; `test_concept_extractor.py` passes a fake client
- **`67c3eb2` — Checkpoint 2, B2 + retrieval wiring (6 files)**
  - new `retrieval/confidence.py`; `retrieval_service.py`: cap 30, named thresholds, injected caches typed by `Protocol`s, per-instance L1 cache, dead `lru_cache` stub removed
  - `services/caches/{query_cache,web_cache}.py` → `QueryCache` / `WebCache` classes (keys and TTLs unchanged; `except Exception` → `JSONDecodeError`)
  - new `tests/test_confidence.py` (9 tests)
- **`f499a76` — Checkpoint 3, one pipeline (6 files)**
  - new `services/chat_pipeline.py` (`ChatPipeline`, `ChatStream`), new `services/quiz_service.py`
  - `services/chat_guards.py`: `UNSAFE_KEYWORDS`, `UNSAFE_REFUSAL`, `find_unsafe_keyword`; `POST /chat` deleted from `main.py`; `schemas/chat.py` deleted (only `/chat` used it)
  - `tests/test_chat_guards.py`: +11 tests
- **`00e9bea` — Checkpoint 4a, the move (9 files)**: `routes/auth_routes.py` → `api/routes/auth.py` byte-identical (**R100**); new `api/deps.py`, `services/container.py`; `core/security.py` hashing + JWT only (`decode_access_token` added, `get_current_user_optional` deleted); `authenticate_user` → `services/account_service.py`; `FakeRedis.close()`. The rewrite measured ~56 % similar, too close to git's 50 % rename threshold, so the move went alone.
- **`51f4a43` — Checkpoint 4b, routers (10 files)**: `api/routes/auth.py` gains `/register`, `/login`, `/change-password`, `/me` (prefix → full paths, duplicate `get_db` gone); new `api/routes/{health,users,documents,chat,sessions,feedback,quiz,concepts}.py`; `main.py` 918 → 66 lines
- **Checkpoints 5 + 6 (this commit)**
  - `main.py`: `create_app()` + lifespan (`init_db()`, `build_services()`, Redis closed on shutdown; `@app.on_event` gone), middleware order unchanged
  - tests: `conftest.py` builds the app through `create_app()`; `fakes.py` counts `FakeGenaiClient` constructions; new `test_app_factory.py` (3 tests)
  - docs: `docs/timeline.md` (Day 13: `db/` split + repositories for the router SQL; Day 15: "EMBEDDING_DIM changes 3072 → 1536 (pgvector HNSW limit); re-embed on Day 16" + the indexing edge), `docs/architecture/layout.md` (status, exceptions: 2 removed, 1 → Day 15, 1 new → Day 13; module map), `CLAUDE.md` (structure, module map, chat flow, conventions, commands, API list, Known Issues B2, Open Decisions — not Current Status), `docs/improvements.md` (B2 and R5 status lines), post 9 line, this Outcome
  - **outside the plan:** `.claude/hooks/edit_reminders.py` — the `main.py` "mirror POST /chat" reminder (now false; it fired 5× today) retargeted to `services/chat_pipeline.py` with the SSE-contract reminder

### Checks run
| Check | Result |
|---|---|
| Baseline (Checkpoint 0) | 134 passed, 2 xfailed (54.8 s) |
| `python -m pytest` after each checkpoint | 134 → 143 → 154 → 154 → 154 → **157 passed, 2 xfailed** (29–34 s; one 52.5 s run, rerun 29.2 s) |
| `test_api_smoke.py` | **unchanged all day** and green — the SSE-contract proof |
| `.\scripts\dev.ps1 test` (Linux, Python 3.11) | 157 passed, 2 xfailed (90.6 s) |
| `ruff check .` | clean after every checkpoint |
| Route table | 29 operations on 27 paths = Day 8's 28 paths minus `/chat`; every other method/path identical |
| Host `uvicorn app.main:app` | `/health` ok; `/openapi.json` 27 paths, no `/chat` |
| CI on PR #11 | green: `c533056` (backend 2m6s), `67c3eb2` (1m58s), `f499a76` (1m50s), `00e9bea` (1m42s), `51f4a43` (2m0s) |
| Live API checks vs the Docker stack (real Gemini, Tavily, Redis; throwaway account, demo PDF) | **17/17**: upload (3 chunks); stream `metadata → token → message_id → [DONE]` (confidence 55.7, loose, 4 local sources, 2.8 s); cached repeat, same answer in 0.57 s; injection + "how do I make a bomb" refused (no `message_id`); "I studied the diet of early humans…" answered; thumbs down → failed query; sessions; concept map (web) 8 nodes in 8.8 s; maps list; quiz; `POST /chat` 404/405; stream without / with a bad token → 401; account delete (`documents 1, sessions 2, messages 6, concept_maps 1, failed_queries 1, files 1, index entries 6`) then login 401 |
| Browser check (zero frontend edits) | owner, after this commit |

### Measured (host venv, Python 3.12, real `.env`, fresh process per run)
| What | Before (Checkpoint 0 / Day 8) | After |
|---|---|---|
| `import app.main` | 25.83 s, 23.75 s, 24.62 s | **10.37 s, 9.47 s, 9.47 s** (after Checkpoint 1 only: 17.40 s, 15.17 s) |
| `genai.Client` constructions at import / at startup | 5 / +2 on the first concept map | **0 / 1** |
| Embedding calls at startup | 1 | **0** |
| Host server start → "Application startup complete" | ~24 s (Day 8) | **14.07 s**; lifespan `build_services()` 2.55 s |
| Docker dev reload (file change → startup complete) | 20.8 s (first reload today) | 18.6 s; lifespan 0.27 s |
| `main.py` | 1353 lines | 66 lines |
| Live embedding dimension | — | default 3072, requested 3072 → 3072 |

### UI integration
| Backend change | Frontend file | What the user sees |
|---|---|---|
| Routers, factory, lifespan, `Depends`, shared client, no startup call | — | backend-only: same 27 paths, same request/response shapes (route table + unchanged smoke tests) |
| `POST /chat` deleted | none calls it (`ChatWindow.js:126` uses `/chat/stream`; grep) | nothing |
| `ChatPipeline` | `ChatWindow.js` (unchanged) | same SSE frames in the same order; live check above |
| B2 cap 30 | `ChatWindow.js:151` stores `confidence`, nothing renders it | on the forced-web path the answer may be "loose" instead of "none" grounded — wording only |
| One safety list | `ChatWindow.js:145` refusal path (unchanged) | "die"/"nuke" questions answered; "kill myself", "terrorist" refused on the stream (were `/chat`-only) |
| `get_user_from_query_token` | `ChatWindow.js` `?token=` (unchanged) | same 401 for a missing or bad token |

### User-visible behaviour changes reaching production with the Day 10 release (v0.2.0)
1. **`POST /chat` removed** — any external caller gets 404/405 (no known caller; the frontend never used it).
2. **B2 forced-web cap 0.3 → 30** — when the documents don't cover a question and no web chunk makes
   the top 5 (e.g. Tavily down), the answer is grounded "loose" at 30 instead of always "none",
   the `metadata.confidence` value is ≤ 30 instead of ≤ 0.3, and it is logged to `failed_queries`
   only when below 30.
3. **Merged safety list** — questions containing "die" or "nuke" (e.g. "studied", "diet", "diesel")
   are no longer refused; "kill myself" and "terrorist" are now refused on `/chat/stream`; spacing
   variants like "self   harm" now match.

### Deferred or dropped
- `db/` split → Day 13; CRUD SQL in four routers → Day 13 repositories; indexing edge → Day 15 (all in `docs/timeline.md` and the layout exceptions table).
- R5 half done (shared service); its retrieval test and the UI toggle stay on Day 17.
- Eval scripts (`rag_metrics.py`, `rag_eval_runner.py`, `manual_eval.py`, `cache_tuner.py`) now fail at import — left broken by owner decision for Days 10–12.

### Tracker Notes (for the owner)
- **B2:** Done — cap 30, named thresholds in `retrieval/confidence.py`, `POST /chat` gone; `test_confidence.py`. E4 validation open.
- **G3:** still Not Started; prep done (one list, one call site in `ChatPipeline`).
- **R5:** In Progress — shared `RetrievalService` since Day 9; test + UI on Day 17.
