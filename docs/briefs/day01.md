# Day 1 — Git workflow, semantic-cache isolation (G6), CORS (G4), debug prints (O2)
Date: 2026-10-30 · Phase 1 — Security fixes & git workflow · Items: G6, G4, O2
Branch: feature/day01-g6-g4-o2 (current branch; `develop` exists locally, nothing pushed since 73d8bae)

## Scope
1. **Branching model** — document the develop / feature / release flow in CLAUDE.md's
   "Git history" convention. `develop` already exists locally (verified with `git branch -a`).
   The timeline also asks for a Current Status update; the /run-day skill forbids that unless
   you ask, so it is a question below rather than part of the plan.
2. **G6** — scope the semantic cache by user: `store()` writes `user_id`; `lookup()` filters on
   `user_id` + `doc_version` + `mode`; `is not None` replaces the falsy version check; both
   `/chat` and `/chat/stream` pass `user.id`.
3. **G6 deploy flush** — document the one-off flush of `semantic_cache_entries` (it runs on the
   Day 3 release, per the timeline).
4. **G6 docs** — update the Redis key schema table in CLAUDE.md.
5. **G6 test** — `tests/test_semantic_cache.py`: user A's cached query misses for user B; two
   users at `doc_version` 0 stay isolated. Uses an in-memory Redis stub and a fake embedder, so
   no new dependency and no Gemini or Redis needed.
6. **G4** — feed `ALLOWED_ORIGINS` into `CORSMiddleware` instead of `["*"]`. Setting the env var
   on Render is **your** step (dashboard). It only matters once the Day 3 release deploys this code.
7. **O2** — remove or convert the three `print("DEBUG ...")` calls.

## Current behavior
- **G6** — `src/semantic_cache.py:62-87`: `lookup()` keeps entries where
  `not user_doc_version or e["doc_version"] == user_doc_version`. When the version is `0` this is
  `True` for every entry, so the filter is off. Entries hold no `user_id`
  (`semantic_cache.py:98-104`). The whole cache is one Redis string (`SEM_CACHE_KEY`, line 14)
  holding a JSON list capped at 64 entries **shared by all users** (lines 105-106).
  Callers: `src/main.py:661` (`/chat` lookup) and `:790` (store), `src/main.py:837`
  (`/chat/stream` lookup) and `:1016` (store). On a hit, `/chat/stream` sends
  `cached["sources"]` in the metadata event (`main.py:860-868`). Those sources are chunk metadata
  that include the original user's chunk `text` and `file_name`.
- **G4** — `src/main.py:58-61` builds `ALLOWED_ORIGINS` from the env (default: localhost:3000,
  localhost:8000, the Vercel URL). `main.py:63-69` then passes `allow_origins=["*"]` with
  `allow_credentials=True`. The installed Starlette (`venv/.../starlette/middleware/cors.py:155-163`)
  **echoes back any request Origin when the request carries a cookie** and `*` is configured.
  `SessionMiddleware` (`main.py:52-55`) sets such a cookie during Google OAuth. So in practice
  this is "any origin, with credentials", not just a messy config.
  The frontend sends no cookies or credentials. It uses `Authorization` headers and an
  `EventSource` with `?token=` (`frontend/src/components/ChatWindow.js:126-133`), so an
  explicit allowlist costs it nothing.
- **O2** — `src/main.py:883` and `:886` (`print(f"DEBUG: ...")` in the cached-stream generator);
  `src/retrieval_service.py:401` (web-fallback confidence). `retrieval_service.py` has no logger
  today.

## Why it matters
- **G6** — User A uploads `thesis.pdf` and asks "summarize chapter 2". User B, a new account at
  `doc_version` 0, asks the same thing. B gets A's answer streamed back, and the metadata event
  carries A's chunk text and file name. This is a cross-tenant data leak in production. Separately,
  one heavy user can push everyone else out of the 64-entry list.
- **G4** — any website a logged-in user visits can make credentialed requests to the API, and
  the browser lets it read the responses, as long as a session cookie exists. The allowlist that
  should block this is written but never used.
- **O2** — `print` skips the log format, level, and file handler. In production these lines are
  noise on stdout that can't be filtered or switched off.

## The concept
**Multi-tenant cache isolation.** Any cache shared between tenants needs the tenant in its
*key*, not only in its value. The safe pattern is "the cache key is everything the answer depends
on": `tenant + data version + request params + the input`. Here the answer depends on the user's
documents (user + `doc_version`), the answer mode, and the query. A semantic cache makes this
harder than an exact-match cache. The lookup is a *nearest-neighbour search*, so the scope has to
be a hard pre-filter on the candidate set. You can't rely on the similarity score to keep tenants
apart: two users asking "what is backprop?" score about 0.99. Production systems (GPTCache,
Redis vector search, LangChain's `RedisSemanticCache`) do this with a namespace per tenant or a
metadata filter applied *before* the similarity ranking.
Common pitfalls:
- **Truthiness bugs on scope values.** `if not version` treats `0`, `""` and `None` alike, and
  silently turns the filter off. That is exactly G6's second bug. Use `is not None`, or make the
  argument required.
- **Optional scope parameters.** If `user_id` defaults to `None`, a future caller that forgets it
  quietly reads across tenants. Make the parameter required so forgetting it fails loudly.
- **Cached payloads carrying foreign state.** Here the cached value also holds the original
  `session_id`.
- **Stale entries written before the fix.** They have no scope field, so they must be flushed or
  made unreachable.
- **Shared eviction budgets.** One tenant evicting another is a fairness problem, and also a side
  channel.

**CORS.** CORS is a *browser* rule that relaxes the same-origin policy. It never stops a server
from receiving a request. It only decides whether the browser lets the page's JavaScript *read*
the response. `Access-Control-Allow-Origin: *` is fine for public, credential-less APIs. With
credentials, the spec forbids `*`, so frameworks "helpfully" echo back the caller's Origin, which
grants every site full access. The production pattern is an explicit allowlist from configuration
(per environment), credentials only if cookies are really used, and `allow_origin_regex` only
when it is tightly anchored (such as Vercel preview URLs, for Day 19). Pitfalls:
- whitespace or trailing slashes in env values (`"https://x.app "` ≠ `"https://x.app"`)
- forgetting the deployed frontend's exact origin, so prod breaks while local still works
- treating CORS as authentication (curl ignores it completely)

**Logging over print.** Logging gives you levels (silence `DEBUG` in prod, turn it on while
debugging), one format with timestamps and module names, handlers (file rotation, later shipping
to Langfuse/O1), and filters (Day 2 uses one to strip tokens). Pitfall in this repo:
`setup_logging()` adds new handlers on every call, so calling it from more modules duplicates
every line. New modules should use a child of the existing logger:
`logging.getLogger("rag_assistant.retrieval")`. It propagates to the parent's handlers and level.

## Decisions
### Cache storage layout
- **A — one shared list + `user_id` filter (timeline as written):** keep the single
  `semantic_cache_entries` key, add `user_id` to each entry, and pre-filter on it. Smallest diff,
  but every lookup still loads every user's embeddings, and users still evict each other from the
  shared 64-entry cap.
- **B — one list per user, `semantic_cache:{user_id}`, plus the `user_id` filter:** the key
  itself is scoped, so cross-user reads are impossible by construction. Each user gets their own
  64-entry cap, lookups load only that user's entries, and the old key becomes orphaned (the
  flush is a single `DEL`). The diff is slightly bigger, and the CLAUDE.md schema row changes
  shape.
- **Recommendation: B.** The isolation is structural rather than a filter someone can get wrong.
  It also fixes cross-user eviction, and the `user_id` check on each entry stays as defence in
  depth. CO1/CO5 (Day 29) will redesign the store anyway.

### How the test gets a fake Redis
- **A — constructor injection:** `SemanticCache(index_builder, redis_client=None)`, falling back
  to `redis.from_url(REDIS_URL)`. Explicit, and it costs one optional parameter.
- **B — monkeypatch `redis.from_url` in the test:** no production signature change, but the test
  reaches into module internals.
- **Recommendation: A.** It matches your "explicit over implicit" rule, and Day 5's offline test
  suite will reuse the seam.

## Plan
**Checkpoint 1 — G6 code + test (4 files)**
- `src/semantic_cache.py`:
  - per-user key helper
  - required `user_id: int` on `lookup()` / `store()`
  - `doc_version` filter with `is not None` (required int, so version 0 is filtered)
  - `user_id` in each entry
  - optional `redis_client` parameter
  - full type hints
  - narrow `except Exception` to `json.JSONDecodeError` (global rule; same function)
  - delete the dead `# TEMP` comment
- `src/main.py`: pass `user_id=user_id_int` at the 2 lookups and 2 stores (`/chat`, `/chat/stream`).
- `tests/test_semantic_cache.py`:
  - in-memory `get`/`set` stub
  - deterministic fake embedder
  - tests: A-cached → B-miss; both at version 0 → isolated; same user hits; a different mode misses
- Checks: `py_compile` on both files, `python -m pytest tests/test_semantic_cache.py -q`, then the full `python -m pytest tests -q`.

**Checkpoint 2 — G4 + O2 (2 files)**
- `src/main.py`:
  - CORS: `allow_origins=[o.strip() for o in ALLOWED_ORIGINS if o.strip()]`, with the list cleaned once where it's built
  - methods and headers stay `*`
  - `allow_credentials` stays `True` for now: the OAuth session cookie flow uses it, and a narrowed allowlist makes it safe. Revisit with refresh tokens on Day 35.
  - O2: delete the two `DEBUG` prints at :883/:886 (a message id is not worth keeping)
- `src/retrieval_service.py`: add `logger = logging.getLogger("rag_assistant.retrieval")`; turn line 401 into `logger.debug(...)` (useful when tuning confidence on Day 24)
- Checks: `py_compile`; `grep "print(" src/main.py src/retrieval_service.py` → 0; if a local server is running, a preflight `OPTIONS` from `Origin: http://evil.example` gets no `Access-Control-Allow-Origin`, and from `http://localhost:3000` it is allowed

**Checkpoint 3 — docs (1–2 files)**
- `CLAUDE.md`:
  - "Git history" convention → the develop / feature / release flow
  - Redis key schema row → `semantic_cache:{user_id}`, with the legacy-key flush note
  - Env var table: `ALLOWED_ORIGINS` → "comma-separated CORS allowlist"
  - Current Status only if you say so
- Flush instruction for the Day 3 release: `redis-cli -n 1 DEL semantic_cache_entries` (and the same on Render's Redis) — written into the Redis schema note and this brief's Outcome

**Dependencies:** none.

## UI integration
- **G6** — backend-only, no user-visible change. It is a security fix: no new endpoint, field or
  status. The SSE event shape is unchanged, so `ChatWindow.js` works as-is. The only visible
  effect is that users stop seeing each other's answers.
- **G4** — backend-only. The frontend sends no credentials and its origins are on the allowlist.
  Verified by the frontend still connecting (see Verification).
- **O2** — backend-only. These are log lines.

## Verification
- `tests/test_semantic_cache.py` passes offline (no Gemini key, no Redis); the existing parser tests still pass.
- Manual, needs the local stack (Redis on host port 6380 plus Gemini):
  - Account A asks a question, then account B asks the same question.
  - B's backend log shows `CACHE MISS`, and B's metadata event sources contain none of A's file names.
  - A asking again shows `CACHE HIT`.
- CORS: the frontend at localhost:3000 logs in, lists documents and streams chat. A `curl -X OPTIONS` with a foreign Origin gets no allow-origin header.
- No retrieval or prompt change, so there is no before/after metric. The cache hit rate for one user stays the same.

## Risks & open questions
- **Render env var:** if `ALLOWED_ORIGINS` is set on Render without the exact Vercel origin, prod
  chat breaks. The default list already includes `https://rag-study-assistant-chi.vercel.app`,
  so leaving it unset is also safe. Vercel preview URLs won't be allowed until Day 19.
  Decision (owner): production allows only `https://rag-study-assistant-chi.vercel.app`, with no localhost.
- **Orphaned legacy key:** with option B, `semantic_cache_entries` is never read again, so the
  leak stops even before the flush. The flush is still on the Day 3 release checklist, to delete
  the leaked data.
- `/chat` cache hits return the cached `session_id` and skip message logging (`main.py:661-663`).
  With per-user scope this is the same user's own session, so it's not a leak, but it's still
  wrong. Out of scope, since Day 9 consolidates `/chat`.
- The cache ignores the conversation (CO5): a follow-up like "explain more" can hit an unrelated
  cached answer. Not changed today.
- `setup_logging()` stacks duplicate handlers when called more than once. Noted; I'm not fixing it.
- `tests/test_pptx_utils.py::test_table_extraction_on_image` writes `tableimage2_cleaned.jpg` and
  `tableimage2_cleaned_cleaned.jpg` into `tests/samples/` on every full run:
  - `preprocess_image_for_table()` (`src/table_utils.py:7-19`) saves next to its input.
  - The test cleans the image, then passes the cleaned image to `extract_tables_from_image()`, which cleans it again.
  - The existence check runs after the first write, and the only assertion is `isinstance(list)`.
  - Decision (owner, Day 1): delete the files, gitignore `tests/samples/*_cleaned*.jpg`, and fix the test on Day 5 (bullet added to `docs/timeline.md`).
- **Leftover test accounts:** `DELETE /user/delete` still returns 500 (B1: `got <class 'sqlalchemy.orm.session.Session'>`), so the four `g6-*@example.com` accounts from the live G6 check stay in the local DB, along with their uploads and index rows. Their JWTs are also in `src/logs/app.log` (G8). Decision (owner): leave them until Day 3. A bullet was added to Day 3 to delete them via `DELETE /user/delete` after the B1 fix and confirm their uploads and rows are gone.
- **Gemini key:** the first live run failed with `403 PERMISSION_DENIED: Your API key was reported as leaked`. No key pattern exists anywhere in this repo's git history. The owner rotated the key locally and on Render on Day 1.
- **Current Status:** answered. The owner updates CLAUDE.md's Current Status at the end of the day and will ask Claude if needed.
- **Misses on an empty per-user list aren't logged.** `lookup()` returns before logging when a user has no entries, so a first-time miss leaves no `CACHE MISS` line. It was found in the live check. Worth fixing when the cache is reworked (CO1/CO5, Day 29) or when tracing lands (O1, Day 20).
- **A cache hit wasn't faster end to end** in the live check: 3.69 s against 3.64 s for the fresh answer. The cached path still runs topic classification for a new session, and it replays the answer one character per SSE event. Not investigated today, and no claim of a speed-up is made.

## Outcome

### Files changed
- `src/semantic_cache.py`:
  - one key per user, `semantic_cache:{user_id}`
  - `user_id`, `user_doc_version` and `mode` are now required
  - an exact `doc_version` comparison, so version 0 filters too
  - a `user_id` check on every entry, as a backstop
  - an optional `redis_client` parameter for tests
  - type hints
  - `except json.JSONDecodeError` with a warning, instead of `except Exception`
  - the dead `# TEMP` comment is gone
- `src/main.py`:
  - `/chat` (lookup and store) and `/chat/stream` (lookup and store) now pass `user_id`
  - CORS reads the trimmed `ALLOWED_ORIGINS` list instead of `["*"]`
  - the two `DEBUG` prints are deleted
- `src/retrieval_service.py`: adds the `rag_assistant.retrieval` child logger; the web-fallback print becomes `logger.debug`.
- `tests/test_semantic_cache.py` (new): 7 offline tests with a fake Redis and a fake embedder.
- `CLAUDE.md`:
  - the git flow convention
  - the `REDIS_URL` row: host port 6380, and the semantic cache shares DB 0 when `REDIS_URL` is set
  - the `ALLOWED_ORIGINS` row (Render: Vercel URL only)
  - the Redis key table: the new per-user key, and the legacy-key flush on DB 0 and DB 1
  - Feature Status: the G6 line is corrected and the G4/O2 line removed
  - the user-scoping convention
- `docs/timeline.md`:
  - Day 3 gets a bullet to delete the `g6-*` test accounts after the B1 fix
  - Day 5 gets a bullet to fix `test_table_extraction_on_image`
- `.gitignore`: ignores `tests/samples/*_cleaned*.jpg` until Day 5.
- Deleted (generated by a test, untracked): `tests/samples/tableimage2_cleaned.jpg` and `tableimage2_cleaned_cleaned.jpg`.
- Local Redis, not a file: ran `DEL semantic_cache_entries` on DB 0 (it returned 1) and DB 1 (it returned 0). `EXISTS` now gives 0 on both.

### Checks run
| Check | Result |
|---|---|
| `py_compile` on `semantic_cache.py`, `main.py`, `retrieval_service.py`, `test_semantic_cache.py` | pass |
| `pytest tests/test_semantic_cache.py -q` | 7 passed |
| `pytest tests -q` (full suite) | 26 passed in 183 s |
| `print(` in `main.py` and `retrieval_service.py` | 0 |
| CORS: old vs. new middleware config on the installed Starlette, run as a throwaway app | see table below |
| Live G6 check, two accounts, local backend and Redis | see below |
| `/docs` route check | not applicable: no routes added or changed |
| `npm run build` | not run: no frontend change |

**CORS, before and after** (`OPTIONS /me` preflight, and a `GET` with a cookie; the value is the `Access-Control-Allow-Origin` the server returned):

| Config | Origin | Preflight | GET with cookie |
|---|---|---|---|
| old `["*"]` + credentials | `http://localhost:3000` | 200 · echoed | echoed |
| old `["*"]` + credentials | `https://rag-study-assistant-chi.vercel.app` | 200 · echoed | echoed |
| old `["*"]` + credentials | `http://evil.example` | **200 · echoed** | **echoed** |
| new allowlist | `http://localhost:3000` | 200 · echoed | echoed |
| new allowlist | `https://rag-study-assistant-chi.vercel.app` | 200 · echoed | echoed |
| new allowlist | `http://evil.example` | **400 · none** | **none** |

**Live G6 check.** One `/chat/stream` query, mode `quick`. User A (id 5) has uploaded one PDF and is at `doc_version` 1. User B (id 6) has no documents and is at `doc_version` 0.

| Request | Events | Sources | Cache |
|---|---|---|---|
| A, first | metadata → token… → message_id → [DONE] · 3.64 s | `g6_userA_private_8e49ad.pdf` | stored under `semantic_cache:5` |
| B, same query | metadata → token… → message_id → [DONE] · 4.99 s | none | miss: no HIT line for user 6, a fresh answer ("Please upload your document…"), stored under `semantic_cache:6` |
| A, repeat | metadata → token… → message_id → [DONE] · 3.69 s | `g6_userA_private_8e49ad.pdf` | `CACHE HIT: user_id=5 … score=1.000`, answer identical |

A's file in B's sources: **none**. Under the old code, B (version 0, filter off) would have received A's cached answer and A's file name and chunk text.

The first attempt, with accounts `g6-*-751103`, failed: every generation returned `403 … API key was reported as leaked`. The owner rotated the key and the rerun above succeeded.

`DELETE /user/delete` returned 500 for all four accounts (B1). They stay until Day 3.

### UI integration
| Backend change | Frontend file | What the user sees |
|---|---|---|
| G6: per-user semantic cache | none | backend-only. SSE events and fields are unchanged; users stop getting other users' answers and sources |
| G4: CORS allowlist | none | backend-only. The frontend sends no cookies and its origins are on the list; the new config allowed `localhost:3000` and the Vercel origin |
| O2: prints → logging | none | backend-only. Log output only |

### Deferred or dropped timeline bullets
- **Set `ALLOWED_ORIGINS` on Render:** the owner's step, at the Day 3 release. Value: the Vercel URL only.
- **Flush the legacy key on Render's Redis, DB 0 and DB 1:** Day 3 release checklist. The local flush is done.
- **Two-account check against the deployed app** (Verify bullet): done locally only. The prod deploy is Day 3.
- **"The frontend still connects":** checked through the CORS config with the frontend's origins, not by running the React app.

### Tracker Notes (for the owner to copy)
- **G6:** per-user key `semantic_cache:{user_id}` plus a `user_id` check per entry; exact `doc_version` match. 7/7 offline tests. Live: user B got 0 of A's sources; A's repeat was a HIT (score 1.000). Legacy key flushed locally; Render flush on Day 3.
- **G4:** with the allowlist, a foreign origin's preflight returns 400 and no allow-origin header (before: 200 and its origin echoed back). Render: Vercel URL only.
- **O2:** 3 prints removed: 2 deleted, 1 now `logger.debug`.
