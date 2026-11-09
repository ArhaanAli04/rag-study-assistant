# Post 2 — "You can't improve RAG without measuring retrieval"

Publish after: Day 12 · Fed by days: 11–12 · Format: text + 2–3 images

## Hook
If the right chunk never reaches the prompt, no prompt change can fix the answer. Before
touching retrieval, I built a harness to measure it — here are the baseline numbers.

## Concepts to explain (plain words)
- Retrieval vs. generation failures — measure them separately
- Recall@k, MRR, nDCG@k — what each one tells you
- Relevance labels (qrels) at document + page level, so they survive re-chunking
- Synthetic questions from your own documents, paraphrased so keyword search isn't favoured
- LLM-as-judge: faithfulness, answer relevance, citation correctness
- Judge calibration against human labels

## Outline
1. Hook
2. Where RAG answers go wrong (retrieval miss vs. generation miss)
3. Building the question set (synthetic + real failed queries)
4. The three retrieval metrics, one line each
5. Baseline results table
6. Surprises: does the confidence score predict a hit? does truncation cut answers?
7. LLM-as-judge and how much to trust it (agreement %)
8. Lesson + repo link

## Visuals needed
- [ ] Diagram: question set → retriever → metrics; answers → judge → scores
- [ ] Table: baseline Recall@5/10, MRR, nDCG@10
- [ ] Chart: confidence score vs. hit rate
- [ ] Screenshot: eval CLI summary output

## Material log
<!-- /run-day appends one entry per day below, newest last. -->

### Day 11 — 2026-11-09 — Retrieval eval harness (E4)
- Takeaway: the first time we measured retrieval, the numbers showed the vector search had been
  ranking results backwards all along — and once it was fixed, the fancy hybrid blend was no better
  than vector search alone.
- Numbers (retrieval_v1: 61 questions, 55 answerable, 6 course files; production hybrid fusion):

  | Metric | Before B8 fix | After B8 fix |
  |---|---|---|
  | Hit@5 | 0.782 | **0.909** |
  | MRR@5 | 0.339 | **0.801** |
  | nDCG@10 | 0.317 | 0.872 |
  | Hit@5, 245-slide HPC deck (18 q) | 0.611 | **0.944** |
  | Evidence quote reaches the model (of 43) | 24 | 36 |

  - Fusion worse than either half alone (before the fix): blend Hit@5 0.782 / MRR@5 0.339 vs
    vector-only 0.945 / 0.309 and BM25-only 0.855 / 0.602. After: blend 0.909 / 0.801 is still
    ≤ vector-only 0.945 / 0.833.
  - The tell-tale sign: vector-only found the right pages (Hit@5 0.945) but put the best one last
    (MRR 0.309 → 0.833 after the fix, Hit@5 unchanged).
  - Confidence score vs hit: AUC 0.638 before, 0.332 after (5 misses) — it doesn't predict a hit;
    2 of 6 off-topic questions ("explain photosynthesis") still get strict grounding.
  - Blank slide 52 (a zero vector, the farthest possible) was the #1 result for "who made the first
    mechanical calculator" — the inversion turned the worst match into the best.
  - Synthetic questions: 78 requests → 52 drafts → 43 kept after review; 21 rejected for copying the
    slide's wording (overlap 0.56–0.78 vs kept ≤ 0.50).
- Capture now (only what depends on today's app state and can't be recreated later):
  - [ ] nothing today — every result is re-runnable from the committed dataset + cached embeddings
    (`python -m eval.retrieval --config baseline`, 0 API calls); the B8 "before" state is at commit
    `8c547b4`
- Make when writing the post (recreatable any time from git, the brief or this log):
  - [ ] Table card: the before/after table above (from `eval/results/*-{before,after}-b8.md`)
  - [ ] Bar chart: Hit@5 and MRR@5 for blend / vector-only / BM25-only, before and after
  - [ ] Code card: the one-line fix — `score = 1 - distance / 2` with the "d² = 2 − 2·cos" comment
  - [ ] Diagram: question set → served pass / deep pass / context assembly → metrics
  - [ ] Terminal card: the Markdown summary's ranking table
  - [ ] Chart: confidence vs Hit@5 by grounding band (strict hits less often than loose)
- Lesson / quote: "The bug wasn't in a model or a prompt — it was one sign. Lower is better for a
  distance, and the code read it as higher is better. Nothing but a labelled metric could see it."
- Concept source: docs/briefs/day11.md#the-concept
