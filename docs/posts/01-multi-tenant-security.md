# Post 1 — "My RAG app was leaking users' notes to each other"

Publish after: Day 3 (v0.1.0 deployed) · Fed by days: 1–3 · Format: PDF carousel

## Hook
A semantic cache made my study assistant faster — and served one user's answers, built from
their private documents, to a different user. Here's how it happened and how multi-tenant RAG
should scope everything.

## Concepts to explain (plain words)
- Semantic caching — reuse an answer when a new question means the same as an old one
- Multi-tenant isolation — every cache key, search filter and file path carries the user
- Why `doc_version` alone isn't a tenant key (version 0 matched everyone)
- Secrets in logs — tokens in query strings end up in request and access logs
- Per-user file storage and path sanitization

## Slide outline
1. Hook + the symptom
2. What a semantic cache is (diagram)
3. The bug: entries keyed by version + mode, not user
4. Why it leaked document text too (sources in the cached payload)
5. The fix: user-scoped entries, `is not None` check, cache flush on deploy
6. Two more leaks found in the same audit: JWTs in logs, shared upload folder
7. The rule: scope every key, filter and path by user — plus the test that proves it
8. Lesson + repo link

## Visuals needed
- [ ] Diagram: request → semantic cache → hit/miss, before vs. after (user in the key)
- [ ] Code card: the before/after lookup filter
- [ ] Screenshot: the isolation test passing (user A cached, user B misses)

## Material log
<!-- /run-day appends one entry per day below, newest last. -->

### Day 1 — 2026-10-30 — Git workflow, semantic-cache isolation (G6), CORS (G4), debug prints (O2)
- Takeaway: the answer cache now has a separate drawer for each user. One user's question can no longer be answered with another user's answer or their private file content. And the API now only lets the app's own website read its responses.
- Numbers:
  - G6 offline tests (fake Redis + fake embedder, `tests/test_semantic_cache.py`): 7/7 pass. They cover user A cached → user B misses; two users at doc_version 0 stay isolated; the same user hits; a different version or mode misses; a per-user Redis key; a foreign entry under a user's key is ignored. Full suite: 26/26 pass.
  - G6 live check (local backend, the same `/chat/stream` question): user A (1 uploaded PDF) then user B (no documents). B received 0 of A's sources and a fresh answer. A's repeat was a `CACHE HIT` with similarity 1.000 and an identical answer.
  - CORS before/after (installed Starlette, `OPTIONS` preflight and a `GET` with a cookie; the value shown is the `Access-Control-Allow-Origin` returned):

    | Config | Origin | Preflight | GET with cookie |
    |---|---|---|---|
    | old `["*"]` + credentials | `http://localhost:3000` | 200 · echoed | echoed |
    | old `["*"]` + credentials | Vercel app origin | 200 · echoed | echoed |
    | old `["*"]` + credentials | `http://evil.example` | 200 · echoed | echoed |
    | new allowlist | `http://localhost:3000` | 200 · echoed | echoed |
    | new allowlist | Vercel app origin | 200 · echoed | echoed |
    | new allowlist | `http://evil.example` | 400 · none | none |
- Capture now (only what depends on today's app state and can't be recreated later):
  - [x] Two browser windows, two demo accounts, the same question; only the account with the demo PDF shows it as a source (demo documents only). **Deferred to Day 3**, while the `g6-*` test accounts still exist (they are deleted after the B1 fix). Captured on Day 3 with fresh demo accounts instead: `docs/posts/assets/post01-day03-two-account-isolation.png`
- Make when writing the post (recreatable any time from git, the brief or this log):
  - [ ] Terminal: `python -m pytest tests/test_semantic_cache.py -v` showing the 7 isolation tests passing
  - [ ] Code card: the old `if not user_doc_version` filter vs. the new `semantic_cache:{user_id}` key + exact match
  - [ ] Diagram: one shared cache list (before) vs. one list per user (after)
  - [ ] Table card: the CORS before/after table above
- Lesson / quote: "`if not version` looked like a null check, but version 0 is falsy. For every new user, that one word turned the filter off. Then the CORS fix showed that `*` with credentials doesn't mean 'any origin, no cookies'. Starlette echoed back *any* origin."
- Concept source: docs/briefs/day01.md#the-concept

### Day 2 — 2026-10-31 — Stop logging JWTs (G8) and wire in sanitize_query (G1)
- Takeaway: every chat request used to write the user's login token into the server logs, where anyone who could read the logs could reuse it. Now the logs keep only the page path, and a safety net scrubs any token that slips through. Copy-paste "ignore your instructions" attacks now get a polite refusal in the chat instead of reaching the AI.
- Numbers:
  - Local `app.log` lines containing `token=`: 420 before (counted, then deleted), 0 after a streamed chat, an injection and a keyword request. Uvicorn console: 0 `token=`, 0 `eyJ`.
  - Offline tests: 11 redaction/logging tests + 17 guard tests; 9/9 attack wordings refused, 6/6 study questions allowed (incl. "What is a system prompt?"). Backend suite 26 → 60 tests, all passing (incl. 6 answer-mode tests). First frontend tests in the repo: 3 React Testing Library tests (refusal bubble with no thumbs; a refused stream stops loading).
  - Duplicate logging fixed: one request wrote 2 lines to `app.log` before, 1 after (`setup_logging()` made idempotent).
  - Google login after the fix: the log shows "Redirecting user 1 to the frontend OAuth callback". 0 `token=`, 0 `eyJ`, 0 emails in either log.
  - Live injection refused over SSE in 6.3 ms, with no retrieval or Gemini call and 0 DB rows written.
- Capture now (only what depends on today's app state and can't be recreated later):
  - [ ] nothing today. The refusal bubble can be recreated any time with a demo account
- Make when writing the post (recreatable any time from git, the brief or this log):
  - [ ] Code card: `logger.info(f"Request: {request.method} {request.url}")` (before) vs. `request.url.path` + `RedactSecretsFilter` (after)
  - [ ] Terminal: `Select-String app.log -Pattern 'token='` → 420 hits before / 0 after (re-run on a fresh log)
  - [ ] Screenshot: the refusal bubble for "Ignore previous instructions…" (demo account)
  - [ ] Diagram: three places a URL token leaks (app middleware, OAuth log line, uvicorn access log) → one handler-level filter
  - [ ] Code card: the old 4-phrase list vs. the narrowed list, with "What is a system prompt?" allowed
- Lesson / quote: "The leak was in three places, and the third (uvicorn's access log) wasn't even our code. Then the check script leaked its own token through httpx's INFO log. Logging a URL is logging a password."
- Concept source: docs/briefs/day02.md#the-concept

### Day 3 — 2026-11-01 — Per-user uploads (G7), account deletion (B1) and first release
- Takeaway: uploaded files used to go into one shared folder under whatever name the browser sent, so two students uploading `notes.pdf` overwrote each other. Now every file gets a random name inside its owner's own folder. And "Delete account" — which always crashed — now really deletes everything: rows, files, search-index entries and cached answers.
- Numbers:
  - Live isolation (local backend, two fresh demo accounts, one demo PDF each, the same question): A's sources `[samples.pdf]`, B's `[table_test.pdf]` — 0 of A's sources reached B. Files stored as `uploads\8\<uuid>.pdf` and `uploads\9\<uuid>.pdf`; citations still show the original filenames.
  - Before G7, in the local DB: two users' document rows pointed at the same file, `uploads/DL_Unit5_RNN.pdf`.
  - Live account deletions through the UI: 3 deletes, all `200`, in 198 / 57 / 71.5 ms; `index_entries_removed` = 6 / 10 / 6 (FAISS + BM25 tombstones: 3+3, 5+5, 3+3 chunks); afterwards 0 rows in all 7 tables, no upload folder, no `semantic_cache:{id}` key.
  - ID reuse, observed live: after test accounts 3–7 were deleted, the next new account was given **id 3** again (SQLite reuses the highest freed id). Without purging the index and caches, it would have inherited the old user 3's chunks and cached answers.
  - Tests: backend 63 → 81 (12 upload-path, 3 re-upload, 3 account-deletion); frontend 3 → 7, including a full-router flow test.
- Capture now (only what depends on today's app state and can't be recreated later):
  - [x] Two browser windows, demo accounts A and B, the same question, each showing only its own PDF as a source — `docs/posts/assets/post01-day03-two-account-isolation.png` (gitignored)
- Make when writing the post (recreatable any time from git, the brief or this log):
  - [ ] Code card: `os.path.join("uploads", file.filename)` (before) vs. `new_upload_path(UPLOAD_ROOT, user.id, ext)` with the containment check (after)
  - [ ] Terminal: `python -m pytest tests/test_upload_storage.py -v` — `../evil.pdf`, `..\..\evil.PDF`, `/etc/passwd.pdf` all land in `uploads/7/<uuid>.pdf`
  - [ ] Diagram: one shared `uploads/` folder (before) vs. `uploads/{user_id}/{uuid}` (after)
  - [ ] Diagram: deleting a user touches five stores — SQLite, disk, FAISS, BM25, Redis — DB first, then the derived copies
  - [ ] Table card: the three live deletions (status, ms, `index_entries_removed`)
- Lesson / quote: "Deleting a user is a distributed transaction in disguise. And the id you just freed comes straight back: our very next sign-up got id 3, the id of an account deleted a minute earlier. Every cache and index keyed by user id has to forget it, or the new person inherits the old one's notes."
- Concept source: docs/briefs/day03.md#the-concept
