# Post 4 — "What one RAG request actually costs"

Publish after: Day 22 · Fed by days: 20–22 · Format: PDF carousel

## Hook
One chat message in my study app makes N model calls and costs $X. I couldn't have told you
that before adding tracing — and one prompt-layout change cut the bill by Y%.

## Concepts to explain (plain words)
- Traces and spans — a timeline of one request, step by step
- Token accounting: prompt, output and cached tokens
- Implicit prompt caching — why a stable prompt prefix is cheaper
- Prompt management and versioning outside the code
- User feedback attached to the trace that produced the answer

## Slide outline
1. Hook with the cost number
2. Anatomy of one request (span tree)
3. Where the latency goes (p50/p95 per stage)
4. Where the tokens go
5. Prompt caching: before/after layout, cached-token %
6. Prompt versions and comparing them by score
7. Thumbs-down → trace: debugging a bad answer in one click
8. Lesson + repo link

## Visuals needed
- [ ] Screenshot: Langfuse trace tree (demo documents only)
- [ ] Chart: latency per stage
- [ ] Chart: cost per chat before/after the cache-friendly layout
- [ ] Diagram: prompt layout before/after (what stays constant)

## Material log
<!-- /run-day appends one entry per day below, newest last. -->
