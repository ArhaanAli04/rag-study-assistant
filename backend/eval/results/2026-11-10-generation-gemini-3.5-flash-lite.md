# Generation eval — gemini-3.5-flash-lite — 2026-11-10

Dataset `retrieval_v1.jsonl` (61 questions, sha256 `048a64094f77`), commit `8de3b1b`. Generator `gemini-3.5-flash-lite`, mode `quick`, temperature default (LLMClient sets none). Judge `gemini-3.5-flash-lite` (prompts faith-v2, rel-v1), temperature default (1.0; 3.5 Flash-Lite ignores custom values). Retrieval: baseline config (web off, L1 off), top_k=5. Judged 61 of 61.

**How to read this.** Faithfulness = supported claims / all claims of an answer, judged against exactly the text the model was given; refusals have no claims and no score. `not_in_context` is allowed under `loose` and `none` grounding (the prompt permits general knowledge there) and is a violation under `strict`; `contradicted` is a bug under every band. Means with 95% bootstrap intervals.

## Headline

| Metric | Value |
|---|---|
| Faithfulness, all scored answers | 0.907 [0.84–0.97] (n=58) |
| Faithfulness, strict band | 0.956 [0.87–1.00] (n=27) |
| Claims: supported / not_in_context / contradicted | 168 / 18 / 0 of 186 |
| Contradicted-claim rate | 0.000 |
| Full relevance, answerable | 0.982 (n=55) |
| Abstention: answerable / negatives | 0.000 / 0.333 |
| Citations: valid / fabricated / malformed | 151 / 0 / 0 (valid rate 1.000) |
| Answers with ≥1 citation | 55 of 61 |
| Judge: cited claims the citation supports | 0.954 |

## By grounding band

| Band | Answers | Faithfulness | not_in_context rate | Contradicted rate |
|---|---|---|---|---|
| strict | 29 | 0.956 [0.87–1.00] (n=27) | 0.047 | 0.000 |
| loose | 31 | 0.893 [0.79–0.98] (n=30) | 0.113 | 0.000 |
| none | 1 | 0.000 [0.00–0.00] (n=1) | 1.000 | 0.000 |

## Retrieval → generation

Answerable questions split by whether a labelled page reached the model's context (the E4 question, asked of the context the answer was generated from).

| Context | Answers | Faithfulness | Full relevance |
|---|---|---|---|
| relevant page in context | 50 | 0.976 [0.95–1.00] (n=50) | 1.000 |
| no relevant page in context | 5 | 0.760 [0.40–1.00] (n=5) | 0.800 |

## Relevance

Answerable: {'full': 54, 'partial': 1, 'off_topic': 0, 'refusal': 0}. Negatives: {'full': 4, 'partial': 0, 'off_topic': 0, 'refusal': 2}.

Out-of-corpus negatives, refusals per grounding band (a refusal is asked for only under `strict`; `loose` / `none` allow a general-knowledge answer): strict 2/2, loose 0/3, none 0/1.

## Absolute gate (used when no paired comparison is possible)

Strict-band faithfulness 0.956 (≥ 0.9), contradicted-claim rate 0.000 (≤ 0.05), full relevance on answerable 0.982 (≥ 0.8): **pass**.

## Owner review (2026-11-10)

**h-02 is a judge false positive on unseen data.** The judge marked "The Gated Recurrent Unit (GRU) has fewer
gates compared to LSTM" `not_in_context` under strict grounding. The material says GRU "combines the forget and
input into a single update gate" and has two gates, and the judge itself marked those claims supported. "Fewer
gates than LSTM" follows directly from them: an inference between stated facts, which the owner ruled stays
supported. The cached verdict is left as it is, and the judge is not revised again. With h-02 corrected (5/5),
strict-band faithfulness is ≈ 0.963 (26.0 / 27) instead of 0.956. The gate passes either way.

## Known limitations of the judge

- **Same model as the generator.** `gemini-3.5-flash-lite` judges its own answers, because
  `gemini-2.5-flash-lite` is not served to new projects. The only check on self-preference is the 20 blind
  reference labels (Claude, claude-opus-5-5; disagreements adjudicated by the owner).
- **faith-v2 was tuned on the calibration set.** Its two rules (unstated superlatives and firsts; scope shifts)
  were written from that set's disagreements, so its perfect agreement there is optimistic. This run is its first
  unseen test.
- **Over-strict on inferences between stated facts (h-02).** It can mark a comparison drawn from two stated facts
  as `not_in_context`, and on this run that cost one strict claim.
- **Not a paired comparison.** The gate shows 3.5 meets fixed bars, not that it is better than 2.5. The strict
  interval's lower bound (0.87) is below the 0.90 bar; the gate uses the point estimate (owner's rule).

## Per question

| Id | Type | Band | Faithfulness | Claims (s/n/c) | Relevance | Citations valid/total |
|---|---|---|---|---|---|---|
| g-001 | generated | loose | 1.00 | 3/0/0 | full | 3/3 |
| g-002 | generated | strict | 1.00 | 3/0/0 | full | 2/2 |
| g-003 | generated | strict | 1.00 | 2/0/0 | full | 2/2 |
| g-004 | generated | loose | 1.00 | 5/0/0 | full | 3/3 |
| g-005 | generated | loose | 1.00 | 5/0/0 | full | 4/4 |
| g-006 | generated | loose | 1.00 | 3/0/0 | full | 3/3 |
| g-007 | generated | loose | 1.00 | 1/0/0 | full | 1/1 |
| g-008 | generated | strict | 1.00 | 3/0/0 | full | 3/3 |
| g-009 | generated | strict | 1.00 | 4/0/0 | full | 3/3 |
| g-010 | generated | strict | 1.00 | 2/0/0 | full | 2/2 |
| g-011 | generated | loose | 1.00 | 3/0/0 | full | 3/3 |
| g-012 | generated | loose | 1.00 | 2/0/0 | full | 2/2 |
| g-013 | generated | loose | 1.00 | 3/0/0 | full | 3/3 |
| g-015 | generated | loose | 1.00 | 4/0/0 | full | 3/3 |
| g-016 | generated | strict | 1.00 | 3/0/0 | full | 3/3 |
| g-017 | generated | strict | 0.00 | 0/3/0 | partial | 3/3 |
| g-019 | generated | strict | 1.00 | 2/0/0 | full | 2/2 |
| g-020 | generated | strict | 1.00 | 3/0/0 | full | 2/2 |
| g-021 | generated | loose | 0.80 | 4/1/0 | full | 3/3 |
| g-022 | generated | loose | 1.00 | 3/0/0 | full | 3/3 |
| g-023 | generated | strict | 1.00 | 4/0/0 | full | 2/2 |
| g-024 | generated | loose | 1.00 | 3/0/0 | full | 5/5 |
| g-025 | generated | loose | 1.00 | 5/0/0 | full | 4/4 |
| g-027 | generated | loose | 1.00 | 2/0/0 | full | 2/2 |
| g-028 | generated | loose | 1.00 | 3/0/0 | full | 2/2 |
| g-029 | generated | loose | 1.00 | 3/0/0 | full | 3/3 |
| g-030 | generated | loose | 1.00 | 2/0/0 | full | 2/2 |
| g-031 | generated | loose | 1.00 | 2/0/0 | full | 2/2 |
| g-034 | generated | loose | 1.00 | 4/0/0 | full | 4/4 |
| g-036 | generated | strict | 1.00 | 2/0/0 | full | 2/2 |
| g-038 | generated | loose | 1.00 | 2/0/0 | full | 2/2 |
| g-040 | generated | strict | 1.00 | 5/0/0 | full | 4/4 |
| g-041 | generated | loose | 1.00 | 3/0/0 | full | 3/3 |
| g-042 | generated | loose | 0.67 | 2/1/0 | full | 3/3 |
| g-043 | generated | strict | 1.00 | 1/0/0 | full | 1/1 |
| g-045 | generated | loose | 1.00 | 3/0/0 | full | 3/3 |
| g-046 | generated | loose | 1.00 | 3/0/0 | full | 3/3 |
| g-047 | generated | strict | 1.00 | 2/0/0 | full | 1/1 |
| g-048 | generated | strict | 1.00 | 4/0/0 | full | 2/2 |
| g-049 | generated | loose | 0.67 | 2/1/0 | full | 3/3 |
| g-050 | generated | strict | 1.00 | 4/0/0 | full | 3/3 |
| g-051 | generated | strict | 1.00 | 3/0/0 | full | 3/3 |
| g-052 | generated | strict | 1.00 | 3/0/0 | full | 2/2 |
| h-01 | hard | strict | 1.00 | 4/0/0 | full | 5/5 |
| h-02 | hard | strict | 0.80 | 4/1/0 | full | 3/3 |
| h-03 | hard | loose | 1.00 | 3/0/0 | full | 4/4 |
| h-04 | hard | strict | 1.00 | 5/0/0 | full | 3/3 |
| h-05 | hard | strict | 1.00 | 2/0/0 | full | 2/2 |
| h-06 | hard | strict | 1.00 | 3/0/0 | full | 3/3 |
| h-07 | hard | loose | 1.00 | 6/0/0 | full | 4/4 |
| h-08 | hard | strict | 1.00 | 3/0/0 | full | 2/2 |
| h-09 | hard | loose | 0.67 | 2/1/0 | full | 2/2 |
| h-10 | hard | strict | 1.00 | 6/0/0 | full | 3/3 |
| h-11 | hard | strict | 1.00 | 2/0/0 | full | 3/3 |
| h-12 | hard | strict | 1.00 | 3/0/0 | full | 3/3 |
| n-01 | negative | loose | – | 0/0/0 | full | 0/0 |
| n-02 | negative | strict | – | 0/0/0 | refusal | 0/0 |
| n-03 | negative | loose | 0.00 | 0/3/0 | full | 0/0 |
| n-04 | negative | strict | – | 0/0/0 | refusal | 0/0 |
| n-05 | negative | loose | 0.00 | 0/4/0 | full | 0/0 |
| n-06 | negative | none | 0.00 | 0/3/0 | full | 0/0 |
