# Retrieval eval — vector_only — 2026-11-09

vector half alone (1.0 / 0.0), web off. Dataset `retrieval_v1.jsonl` (61 questions, sha256 `77de5343a291`), commit `1389aad`. Served pass top_k=5, deep pass top_k=10. Embedding cache: 619 hits, 0 API calls.

**How to read this.** Means with 95% bootstrap intervals over questions.

- **Hit@5** (any relevant page in the top 5) and **MRR@5** are the headline numbers. Both come from the served pass, exactly what the chat sends the model, and one answering page in that context is usually enough.
- **Recall@5** matters only for two-part questions (the *two-part* row): each part is answered on its own page, so finding one half is a partial answer. A single-intent question with several answering pages (work stealing is explained on three HPC slides) should be judged on Hit@5, not Recall: one of the three is a full answer.
- Recall@10, MRR@10 and nDCG@10 come from the deep pass (top 10) and show whether a miss was near.
- Labels are (document, page) and may be incomplete: a fact repeated on an unlabelled page counts as a miss.

## Ranking

| Slice | n | **Hit@5** | **MRR@5** | Recall@5 | Recall@10 | MRR@10 | nDCG@10 |
|---|---|---|---|---|---|---|---|
| all answerable | 55 | 0.945 [0.89–1.00] | 0.309 [0.26–0.37] | 0.939 [0.87–0.99] | 0.964 [0.91–1.00] | 0.157 [0.13–0.20] | 0.340 [0.31–0.37] |
| type: generated | 43 | 0.930 [0.86–1.00] | 0.310 [0.24–0.39] | 0.930 [0.86–1.00] | 0.953 [0.88–1.00] | 0.139 [0.11–0.17] | 0.317 [0.29–0.35] |
| type: hard | 12 | 1.000 [1.00–1.00] | 0.307 [0.25–0.38] | 0.972 [0.92–1.00] | 1.000 [1.00–1.00] | 0.223 [0.13–0.37] | 0.423 [0.36–0.50] |
| two-part questions | 5 | 1.000 [1.00–1.00] | 0.367 [0.27–0.47] | 0.933 [0.80–1.00] | 1.000 [1.00–1.00] | 0.156 [0.12–0.19] | 0.422 [0.39–0.45] |
| doc: B11-02 BDA Exp10.pdf | 7 | 1.000 [1.00–1.00] | 0.383 [0.23–0.61] | 1.000 [1.00–1.00] | 1.000 [1.00–1.00] | 0.306 [0.21–0.41] | 0.473 [0.39–0.56] |
| doc: B11-02-NLP Exp4.pdf | 5 | 1.000 [1.00–1.00] | 0.433 [0.27–0.72] | 1.000 [1.00–1.00] | 1.000 [1.00–1.00] | 0.134 [0.11–0.17] | 0.324 [0.30–0.36] |
| doc: BCT mod2,3,6.pdf | 7 | 0.857 [0.57–1.00] | 0.205 [0.12–0.27] | 0.857 [0.57–1.00] | 1.000 [1.00–1.00] | 0.141 [0.10–0.19] | 0.341 [0.30–0.39] |
| doc: DL_Unit5_RNN.pdf | 11 | 0.909 [0.73–1.00] | 0.426 [0.26–0.62] | 0.879 [0.67–1.00] | 0.909 [0.73–1.00] | 0.123 [0.09–0.15] | 0.322 [0.25–0.38] |
| doc: HPC Lecture.pptx | 18 | 0.944 [0.83–1.00] | 0.221 [0.18–0.27] | 0.944 [0.83–1.00] | 0.944 [0.83–1.00] | 0.100 [0.09–0.11] | 0.288 [0.25–0.32] |
| doc: test_doc1.pdf | 7 | 1.000 [1.00–1.00] | 0.295 [0.23–0.37] | 1.000 [1.00–1.00] | 1.000 [1.00–1.00] | 0.243 [0.11–0.50] | 0.376 [0.30–0.52] |

## Same page, different wording

Each student-wording (hard) question next to the generated question about the same page. Hit@5: generated 7/7, student wording 7/7.

| Hard | Generated | Hit@5 hard / generated | First relevant rank (top 10) hard / generated |
|---|---|---|---|
| h-03 | g-019 | 1 / 1 | 5 / 9 |
| h-06 | g-002 | 1 / 1 | 3 / 4 |
| h-08 | g-036 | 1 / 1 | 10 / 10 |
| h-09 | g-030 | 1 / 1 | 10 / 10 |
| h-10 | g-046 | 1 / 1 | 7 / 10 |
| h-11 | g-008 | 1 / 1 | 9 / 9 |
| h-12 | g-049 | 1 / 1 | 1 / 10 |

## Does confidence predict a hit?

AUC (confidence of Hit@5 questions vs misses): **0.763** (0.5 = no signal, 1.0 = perfect separation).

| Grounding band | Questions | Hit@5 rate |
|---|---|---|
| strict | 54 | 0.944 |
| loose | 1 | 1.000 |
| none | 0 | – |

Out-of-corpus negatives: 6, mean confidence 39.7, max 88.0; grounding {'strict': 1, 'loose': 5, 'none': 0}.

## Does compression cut answer spans?

Of 43 answerable questions with an evidence quote: dropped 6, not_retrieved 3, survived 32, truncated 2. `survived` = the quote is in the compressed context; `truncated` = its chunk was retrieved but the 800-character cut removed it; `dropped` = its chunk lost to the 6-chunk limit; `not_retrieved` = no served chunk on a relevant page holds the quote.

## Where does the flat 0.5 web score land?

Local candidates' hybrid scores: p25 0.092, median 0.674, p75 0.988, p90 1.000; 0.367 of them score below 0.5.
Web search is off in this config; run `--config web` for the slot share.

Questions the decomposer split into several sub-queries: 12.
