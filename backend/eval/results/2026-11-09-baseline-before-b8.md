# Retrieval eval — baseline — 2026-11-09

production fusion (0.6 vector / 0.4 BM25), web off. Dataset `retrieval_v1.jsonl` (61 questions, sha256 `77de5343a291`), commit `1389aad`. Served pass top_k=5, deep pass top_k=10. Embedding cache: 545 hits, 74 API calls.

**How to read this.** Means with 95% bootstrap intervals over questions.

- **Hit@5** (any relevant page in the top 5) and **MRR@5** are the headline numbers. Both come from the served pass, exactly what the chat sends the model, and one answering page in that context is usually enough.
- **Recall@5** matters only for two-part questions (the *two-part* row): each part is answered on its own page, so finding one half is a partial answer. A single-intent question with several answering pages (work stealing is explained on three HPC slides) should be judged on Hit@5, not Recall: one of the three is a full answer.
- Recall@10, MRR@10 and nDCG@10 come from the deep pass (top 10) and show whether a miss was near.
- Labels are (document, page) and may be incomplete: a fact repeated on an unlabelled page counts as a miss.

## Ranking

| Slice | n | **Hit@5** | **MRR@5** | Recall@5 | Recall@10 | MRR@10 | nDCG@10 |
|---|---|---|---|---|---|---|---|
| all answerable | 55 | 0.782 [0.67–0.87] | 0.339 [0.26–0.43] | 0.736 [0.62–0.84] | 0.779 [0.67–0.88] | 0.193 [0.14–0.26] | 0.317 [0.26–0.38] |
| type: generated | 43 | 0.744 [0.60–0.86] | 0.336 [0.24–0.44] | 0.744 [0.60–0.86] | 0.744 [0.60–0.86] | 0.148 [0.10–0.21] | 0.281 [0.22–0.34] |
| type: hard | 12 | 0.917 [0.75–1.00] | 0.353 [0.23–0.50] | 0.708 [0.53–0.88] | 0.903 [0.79–1.00] | 0.353 [0.19–0.54] | 0.445 [0.35–0.55] |
| two-part questions | 5 | 1.000 [1.00–1.00] | 0.440 [0.23–0.74] | 0.600 [0.53–0.67] | 0.767 [0.60–0.93] | 0.382 [0.13–0.72] | 0.417 [0.26–0.56] |
| doc: B11-02 BDA Exp10.pdf | 7 | 0.857 [0.57–1.00] | 0.440 [0.23–0.65] | 0.857 [0.57–1.00] | 1.000 [1.00–1.00] | 0.296 [0.20–0.40] | 0.464 [0.38–0.55] |
| doc: B11-02-NLP Exp4.pdf | 5 | 1.000 [1.00–1.00] | 0.483 [0.30–0.75] | 1.000 [1.00–1.00] | 1.000 [1.00–1.00] | 0.157 [0.13–0.18] | 0.346 [0.32–0.37] |
| doc: BCT mod2,3,6.pdf | 7 | 0.857 [0.57–1.00] | 0.229 [0.13–0.34] | 0.786 [0.50–1.00] | 0.857 [0.57–1.00] | 0.134 [0.07–0.21] | 0.309 [0.19–0.41] |
| doc: DL_Unit5_RNN.pdf | 11 | 0.727 [0.45–1.00] | 0.417 [0.20–0.64] | 0.636 [0.39–0.85] | 0.667 [0.39–0.91] | 0.213 [0.08–0.40] | 0.287 [0.17–0.41] |
| doc: HPC Lecture.pptx | 18 | 0.611 [0.39–0.83] | 0.155 [0.09–0.22] | 0.583 [0.36–0.81] | 0.583 [0.36–0.81] | 0.077 [0.05–0.12] | 0.186 [0.12–0.26] |
| doc: test_doc1.pdf | 7 | 1.000 [1.00–1.00] | 0.600 [0.35–0.89] | 0.929 [0.79–1.00] | 1.000 [1.00–1.00] | 0.440 [0.18–0.74] | 0.539 [0.36–0.74] |

## Same page, different wording

Each student-wording (hard) question next to the generated question about the same page. Hit@5: generated 7/7, student wording 6/7.

| Hard | Generated | Hit@5 hard / generated | First relevant rank (top 10) hard / generated |
|---|---|---|---|
| h-03 | g-019 | 1 / 1 | 2 / 5 |
| h-06 | g-002 | 1 / 1 | 2 / 4 |
| h-08 | g-036 | 0 / 1 | 10 / 9 |
| h-09 | g-030 | 1 / 1 | 10 / 10 |
| h-10 | g-046 | 1 / 1 | 3 / 10 |
| h-11 | g-008 | 1 / 1 | 6 / 6 |
| h-12 | g-049 | 1 / 1 | 1 / 10 |

## Does confidence predict a hit?

AUC (confidence of Hit@5 questions vs misses): **0.638** (0.5 = no signal, 1.0 = perfect separation).

| Grounding band | Questions | Hit@5 rate |
|---|---|---|
| strict | 44 | 0.773 |
| loose | 11 | 0.818 |
| none | 0 | – |

Out-of-corpus negatives: 6, mean confidence 42.4, max 80.0; grounding {'strict': 1, 'loose': 4, 'none': 1}.

## Does compression cut answer spans?

Of 43 answerable questions with an evidence quote: dropped 3, not_retrieved 13, survived 24, truncated 3. `survived` = the quote is in the compressed context; `truncated` = its chunk was retrieved but the 800-character cut removed it; `dropped` = its chunk lost to the 6-chunk limit; `not_retrieved` = no served chunk on a relevant page holds the quote.

## Where does the flat 0.5 web score land?

Local candidates' hybrid scores: p25 0.381, median 0.467, p75 0.600, p90 0.600; 0.525 of them score below 0.5.
Web search is off in this config; run `--config web` for the slot share.

Questions the decomposer split into several sub-queries: 12.
