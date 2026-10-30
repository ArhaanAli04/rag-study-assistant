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
