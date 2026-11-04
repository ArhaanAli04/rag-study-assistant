# Post 5 — "5 retrieval upgrades, measured one at a time"

Publish after: Day 32 (v0.5.0) · Fed by days: 26–32 · Format: PDF carousel

## Hook
Everyone lists RAG techniques. I added them one at a time to a real app and measured each on
a fixed golden set. Some helped a lot; one barely mattered.

## Concepts to explain (plain words)
- Golden set and a CI regression gate
- Confidence calibration
- Reranking: bi-encoder vs. cross-encoder vs. LLM listwise
- Reciprocal Rank Fusion vs. weighted score fusion
- History-aware query rewriting and LLM query decomposition
- Multi-query expansion and HyDE
- Token-based chunking and context budgets
- Semantic-cache threshold tuning (precision/recall of cache hits)

## Slide outline
1. Hook
2. The measuring stick: golden set + CI gate
3. One slide per technique: what it is, the delta it gave
4. Summary table: technique → Recall@5 / faithfulness / latency / cost change
5. What didn't help, and why
6. Lesson + repo link

## Visuals needed
- [ ] Table: cumulative results per technique
- [ ] Chart: Recall@5 and latency after each step
- [ ] Diagram: final retrieval pipeline
- [ ] Example: one follow-up question before/after query rewriting

## Material log
<!-- /run-day appends one entry per day below, newest last. -->
