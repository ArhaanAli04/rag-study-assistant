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

### Day 12 — 2026-11-09/10 — Generation eval with an LLM judge (E1, E2)
- Takeaway: we taught a second AI call to check every answer sentence by sentence against the
  pages it was given. Before trusting it, we checked it against a separate set of blind labels.
  Then we used it to move the app to a model with 25× the daily free quota, knowing the answers
  still meet a fixed bar.
- Numbers (retrieval_v1, 61 questions, `gemini-3.5-flash-lite`, `quick` mode, web off; judge
  `gemini-3.5-flash-lite`, prompt `faith-v2`):

  | Metric | Value |
  |---|---|
  | Faithfulness, strict grounding (n=27) | **0.956** [0.87–1.00] (≈ 0.963 after the owner overruled one judge call) |
  | Faithfulness, answerable questions (n=55) | 0.956 |
  | Contradicted claims | **0 of 186** |
  | Full relevance, answerable (n=55) | **0.982** |
  | Citations pointing at a page the model was shown | 151 of 151 |
  | Cited claims the judge says the page supports | 0.954 |

  - **Retrieval → generation** (the link between post 2's two halves):

    | Retrieval | Faithfulness | Full relevance |
    |---|---|---|
    | A labelled page reached the context (n=50) | 0.976 | 100% |
    | No labelled page reached it (n=5, small) | 0.760 | 80% |

  - Judge calibration on 20 blind reference labels (Claude, adjudicated by the owner), each
    answer judged twice:

    | | faith-v1 | faith-v2 |
    |---|---|---|
    | Faithfulness agreement | 0.90 (κ 0.76) | 1.00 (κ 1.00) |
    | Citations agreement | 0.90 (κ 0.75) | 1.00 (κ 1.00) |
    | Judge agrees with itself | 0.95 | 1.00 |

    Relevance agreement was 1.00 under both. v2 is optimistic, because it was tuned on those 20.
  - Every v1 disagreement went the same way, with the judge more lenient: it accepted "the
    *first* mechanical calculator" when the page never says "first", and it accepted GRU facts
    stretched to all RNNs.
  - Model switch (B9): the free tier gives 20 → 500 requests a day. 2.5-flash-lite answered
    HTTP 404 "no longer available to new users", so no side-by-side comparison was possible.
  - RAGAS dropped: 22 packages left the lock (158 → 136 pins).
- Capture now (only what depends on today's app state and can't be recreated later):
  - [ ] nothing today — answers and verdicts are cached (`eval/.cache/generation.sqlite`, 0 API
    calls to re-render), and the summaries are committed (`eval/results/2026-11-10-*.md`)
- Make when writing the post (recreatable any time from git, the brief or this log):
  - [ ] Table card: the headline gate table (strict faithfulness / contradicted / relevance)
  - [ ] Bar chart: faithfulness and full relevance, "relevant page in context" vs "not" (the
    retrieval → generation link)
  - [ ] Diagram: question → `prepare_answer` → answer → claim split → per-claim verdict + citation
    check
  - [ ] Code card: one judged claim, showing the verdict, the evidence quote and the citation
    support, using demo text
  - [ ] Table card: calibration v1 → v2, judge vs judge and judge vs reference
- Lesson / quote: "Before you trust an AI grader, grade the grader. Our judge agreed with the
  labels 90% of the time, and every miss went the same way: it was too kind."
- Concept source: docs/briefs/day12.md#the-concept
