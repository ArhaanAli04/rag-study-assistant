# Retrieval eval — keyword_only — 2026-11-14

BM25 half alone (0.0 / 1.0), web off. Dataset `retrieval_v1.jsonl` (61 questions, sha256 `048a64094f77`), commit `de45311` (app/ or eval/ had uncommitted changes). Served pass top_k=5, deep pass top_k=10. Embedding cache: 616 hits, 0 API calls.

**How to read this.** Means with 95% bootstrap intervals over questions.

- **Hit@5** (any relevant page in the top 5) and **MRR@5** are the headline numbers. Both come from the served pass, exactly what the chat sends the model, and one answering page in that context is usually enough.
- **Recall@5** matters only for two-part questions (the *two-part* row): each part is answered on its own page, so finding one half is a partial answer. A single-intent question with several answering pages (work stealing is explained on three HPC slides) should be judged on Hit@5, not Recall: one of the three is a full answer.
- Recall@10, MRR@10 and nDCG@10 come from the deep pass (top 10) and show whether a miss was near.
- Labels are (document, page) and may be incomplete: a fact repeated on an unlabelled page counts as a miss.

## Ranking

| Slice | n | **Hit@5** | **MRR@5** | Recall@5 | Recall@10 | MRR@10 | nDCG@10 |
|---|---|---|---|---|---|---|---|
| all answerable | 55 | 0.891 [0.80–0.96] | 0.559 [0.46–0.66] | 0.879 [0.79–0.96] | 0.903 [0.82–0.98] | 0.526 [0.42–0.63] | 0.600 [0.51–0.69] |
| type: generated | 43 | 0.860 [0.74–0.95] | 0.453 [0.35–0.56] | 0.860 [0.74–0.95] | 0.884 [0.79–0.98] | 0.414 [0.31–0.53] | 0.523 [0.43–0.63] |
| type: hard | 12 | 1.000 [1.00–1.00] | 0.938 [0.81–1.00] | 0.944 [0.83–1.00] | 0.972 [0.92–1.00] | 0.926 [0.78–1.00] | 0.877 [0.75–0.97] |
| two-part questions | 5 | 1.000 [1.00–1.00] | 1.000 [1.00–1.00] | 0.867 [0.60–1.00] | 0.933 [0.80–1.00] | 1.000 [1.00–1.00] | 0.875 [0.75–0.97] |
| doc: B11-02 BDA Exp10.pdf | 7 | 1.000 [1.00–1.00] | 0.690 [0.50–0.86] | 1.000 [1.00–1.00] | 1.000 [1.00–1.00] | 0.690 [0.50–0.86] | 0.770 [0.63–0.89] |
| doc: B11-02-NLP Exp4.pdf | 5 | 1.000 [1.00–1.00] | 0.740 [0.42–1.00] | 1.000 [1.00–1.00] | 1.000 [1.00–1.00] | 0.672 [0.32–1.00] | 0.746 [0.47–1.00] |
| doc: BCT mod2,3,6.pdf | 7 | 0.857 [0.57–1.00] | 0.560 [0.27–0.86] | 0.857 [0.57–1.00] | 0.857 [0.57–1.00] | 0.571 [0.29–0.86] | 0.631 [0.36–0.86] |
| doc: DL_Unit5_RNN.pdf | 11 | 0.636 [0.36–0.91] | 0.442 [0.20–0.70] | 0.576 [0.30–0.85] | 0.697 [0.42–0.94] | 0.433 [0.18–0.70] | 0.450 [0.24–0.67] |
| doc: HPC Lecture.pptx | 18 | 0.944 [0.83–1.00] | 0.426 [0.29–0.58] | 0.944 [0.83–1.00] | 0.944 [0.83–1.00] | 0.364 [0.21–0.53] | 0.492 [0.36–0.63] |
| doc: test_doc1.pdf | 7 | 1.000 [1.00–1.00] | 0.821 [0.61–1.00] | 1.000 [1.00–1.00] | 1.000 [1.00–1.00] | 0.774 [0.52–1.00] | 0.809 [0.61–0.98] |

## Same page, different wording

Each student-wording (hard) question next to the generated question about the same page. Hit@5: generated 7/7, student wording 7/7.

| Hard | Generated | Hit@5 hard / generated | First relevant rank (top 10) hard / generated |
|---|---|---|---|
| h-03 | g-019 | 1 / 1 | 1 / 3 |
| h-06 | g-002 | 1 / 1 | 1 / 1 |
| h-08 | g-036 | 1 / 1 | 9 / 5 |
| h-09 | g-030 | 1 / 1 | 1 / 1 |
| h-10 | g-046 | 1 / 1 | 1 / 7 |
| h-11 | g-008 | 1 / 1 | 1 / 1 |
| h-12 | g-049 | 1 / 1 | 1 / 4 |

## Does confidence predict a hit?

AUC (confidence of Hit@5 questions vs misses): **0.357** (0.5 = no signal, 1.0 = perfect separation).

| Grounding band | Questions | Hit@5 rate |
|---|---|---|
| strict | 38 | 0.868 |
| loose | 17 | 0.941 |
| none | 0 | – |

Out-of-corpus negatives: 6, mean confidence 27.6, max 72.7; grounding {'strict': 1, 'loose': 2, 'none': 3}.

## Does compression cut answer spans?

Of 43 answerable questions with an evidence quote: dropped 1, not_retrieved 6, survived 34, truncated 2. `survived` = the quote is in the compressed context; `truncated` = its chunk was retrieved but the 800-character cut removed it; `dropped` = its chunk lost to the 6-chunk limit; `not_retrieved` = no served chunk on a relevant page holds the quote.

## Where does the flat 0.5 web score land?

Local candidates' hybrid scores: p25 0.000, median 0.167, p75 0.732, p90 1.000; 0.666 of them score below 0.5.
Web search is off in this config; run `--config web` for the slot share.

Questions the decomposer split into several sub-queries: 12.
