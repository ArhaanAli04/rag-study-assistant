# Retrieval eval — keyword_only — 2026-11-09

BM25 half alone (0.0 / 1.0), web off. Dataset `retrieval_v1.jsonl` (61 questions, sha256 `77de5343a291`), commit `31b4a18`. Served pass top_k=5, deep pass top_k=10. Embedding cache: 619 hits, 0 API calls.

**How to read this.** Means with 95% bootstrap intervals over questions.

- **Hit@5** (any relevant page in the top 5) and **MRR@5** are the headline numbers. Both come from the served pass, exactly what the chat sends the model, and one answering page in that context is usually enough.
- **Recall@5** matters only for two-part questions (the *two-part* row): each part is answered on its own page, so finding one half is a partial answer. A single-intent question with several answering pages (work stealing is explained on three HPC slides) should be judged on Hit@5, not Recall: one of the three is a full answer.
- Recall@10, MRR@10 and nDCG@10 come from the deep pass (top 10) and show whether a miss was near.
- Labels are (document, page) and may be incomplete: a fact repeated on an unlabelled page counts as a miss.

## Ranking

| Slice | n | **Hit@5** | **MRR@5** | Recall@5 | Recall@10 | MRR@10 | nDCG@10 |
|---|---|---|---|---|---|---|---|
| all answerable | 55 | 0.855 [0.76–0.95] | 0.602 [0.50–0.71] | 0.842 [0.75–0.93] | 0.903 [0.82–0.97] | 0.600 [0.49–0.70] | 0.659 [0.57–0.75] |
| type: generated | 43 | 0.814 [0.70–0.93] | 0.545 [0.43–0.66] | 0.814 [0.70–0.93] | 0.884 [0.79–0.98] | 0.542 [0.42–0.66] | 0.622 [0.52–0.72] |
| type: hard | 12 | 1.000 [1.00–1.00] | 0.806 [0.64–0.96] | 0.944 [0.83–1.00] | 0.972 [0.92–1.00] | 0.806 [0.64–0.96] | 0.791 [0.68–0.89] |
| two-part questions | 5 | 1.000 [1.00–1.00] | 0.667 [0.43–0.90] | 0.867 [0.60–1.00] | 0.933 [0.80–1.00] | 0.667 [0.43–0.90] | 0.660 [0.57–0.75] |
| doc: B11-02 BDA Exp10.pdf | 7 | 1.000 [1.00–1.00] | 0.738 [0.52–0.93] | 1.000 [1.00–1.00] | 1.000 [1.00–1.00] | 0.738 [0.52–0.93] | 0.804 [0.64–0.95] |
| doc: B11-02-NLP Exp4.pdf | 5 | 1.000 [1.00–1.00] | 0.667 [0.43–0.90] | 1.000 [1.00–1.00] | 1.000 [1.00–1.00] | 0.667 [0.43–0.90] | 0.752 [0.58–0.93] |
| doc: BCT mod2,3,6.pdf | 7 | 0.857 [0.57–1.00] | 0.583 [0.29–0.86] | 0.857 [0.57–1.00] | 1.000 [1.00–1.00] | 0.601 [0.32–0.88] | 0.703 [0.49–0.90] |
| doc: DL_Unit5_RNN.pdf | 11 | 0.636 [0.36–0.91] | 0.400 [0.17–0.65] | 0.576 [0.30–0.85] | 0.788 [0.55–1.00] | 0.412 [0.19–0.66] | 0.465 [0.29–0.66] |
| doc: HPC Lecture.pptx | 18 | 0.833 [0.67–1.00] | 0.507 [0.33–0.69] | 0.833 [0.67–1.00] | 0.833 [0.67–1.00] | 0.486 [0.30–0.68] | 0.556 [0.39–0.73] |
| doc: test_doc1.pdf | 7 | 1.000 [1.00–1.00] | 1.000 [1.00–1.00] | 1.000 [1.00–1.00] | 1.000 [1.00–1.00] | 1.000 [1.00–1.00] | 0.970 [0.91–1.00] |

## Same page, different wording

Each student-wording (hard) question next to the generated question about the same page. Hit@5: generated 7/7, student wording 7/7.

| Hard | Generated | Hit@5 hard / generated | First relevant rank (top 10) hard / generated |
|---|---|---|---|
| h-03 | g-019 | 1 / 1 | 1 / 2 |
| h-06 | g-002 | 1 / 1 | 1 / 1 |
| h-08 | g-036 | 1 / 1 | 3 / 1 |
| h-09 | g-030 | 1 / 1 | 1 / 1 |
| h-10 | g-046 | 1 / 1 | 1 / 4 |
| h-11 | g-008 | 1 / 1 | 1 / 2 |
| h-12 | g-049 | 1 / 1 | 1 / 1 |

## Does confidence predict a hit?

AUC (confidence of Hit@5 questions vs misses): **0.290** (0.5 = no signal, 1.0 = perfect separation).

| Grounding band | Questions | Hit@5 rate |
|---|---|---|
| strict | 44 | 0.818 |
| loose | 11 | 1.000 |
| none | 0 | – |

Out-of-corpus negatives: 6, mean confidence 47.7, max 83.4; grounding {'strict': 2, 'loose': 4, 'none': 0}.

## Does compression cut answer spans?

Of 43 answerable questions with an evidence quote: dropped 3, not_retrieved 8, survived 30, truncated 2. `survived` = the quote is in the compressed context; `truncated` = its chunk was retrieved but the 800-character cut removed it; `dropped` = its chunk lost to the 6-chunk limit; `not_retrieved` = no served chunk on a relevant page holds the quote.

## Where does the flat 0.5 web score land?

Local candidates' hybrid scores: p25 0.023, median 0.317, p75 0.768, p90 1.000; 0.623 of them score below 0.5.
Web search is off in this config; run `--config web` for the slot share.

Questions the decomposer split into several sub-queries: 12.
