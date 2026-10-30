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
  - [ ] Two browser windows, two demo accounts, the same question; only the account with the demo PDF shows it as a source (demo documents only). **Deferred to Day 3**, while the `g6-*` test accounts still exist (they are deleted after the B1 fix)
- Make when writing the post (recreatable any time from git, the brief or this log):
  - [ ] Terminal: `python -m pytest tests/test_semantic_cache.py -v` showing the 7 isolation tests passing
  - [ ] Code card: the old `if not user_doc_version` filter vs. the new `semantic_cache:{user_id}` key + exact match
  - [ ] Diagram: one shared cache list (before) vs. one list per user (after)
  - [ ] Table card: the CORS before/after table above
- Lesson / quote: "`if not version` looked like a null check, but version 0 is falsy. For every new user, that one word turned the filter off. Then the CORS fix showed that `*` with credentials doesn't mean 'any origin, no cookies'. Starlette echoed back *any* origin."
- Concept source: docs/briefs/day01.md#the-concept
