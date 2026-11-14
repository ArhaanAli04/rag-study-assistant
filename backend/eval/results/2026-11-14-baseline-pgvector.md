# Retrieval eval — baseline — 2026-11-14

production fusion (0.6 vector / 0.4 BM25), web off. Dataset `retrieval_v1.jsonl` (61 questions, sha256 `048a64094f77`), commit `de45311` (app/ or eval/ had uncommitted changes). Served pass top_k=5, deep pass top_k=10. Embedding cache: 616 hits, 0 API calls.

**How to read this.** Means with 95% bootstrap intervals over questions.

- **Hit@5** (any relevant page in the top 5) and **MRR@5** are the headline numbers. Both come from the served pass, exactly what the chat sends the model, and one answering page in that context is usually enough.
- **Recall@5** matters only for two-part questions (the *two-part* row): each part is answered on its own page, so finding one half is a partial answer. A single-intent question with several answering pages (work stealing is explained on three HPC slides) should be judged on Hit@5, not Recall: one of the three is a full answer.
- Recall@10, MRR@10 and nDCG@10 come from the deep pass (top 10) and show whether a miss was near.
- Labels are (document, page) and may be incomplete: a fact repeated on an unlabelled page counts as a miss.

## Ranking

| Slice | n | **Hit@5** | **MRR@5** | Recall@5 | Recall@10 | MRR@10 | nDCG@10 |
|---|---|---|---|---|---|---|---|
| all answerable | 55 | 0.909 [0.84–0.98] | 0.806 [0.72–0.89] | 0.897 [0.82–0.97] | 0.964 [0.91–1.00] | 0.824 [0.74–0.90] | 0.853 [0.78–0.92] |
| type: generated | 43 | 0.884 [0.79–0.98] | 0.752 [0.64–0.86] | 0.884 [0.79–0.98] | 0.953 [0.88–1.00] | 0.786 [0.68–0.88] | 0.827 [0.74–0.91] |
| type: hard | 12 | 1.000 [1.00–1.00] | 1.000 [1.00–1.00] | 0.944 [0.83–1.00] | 1.000 [1.00–1.00] | 0.958 [0.88–1.00] | 0.948 [0.88–1.00] |
| two-part questions | 5 | 1.000 [1.00–1.00] | 1.000 [1.00–1.00] | 0.867 [0.60–1.00] | 1.000 [1.00–1.00] | 1.000 [1.00–1.00] | 0.955 [0.88–1.00] |
| doc: B11-02 BDA Exp10.pdf | 7 | 1.000 [1.00–1.00] | 0.929 [0.79–1.00] | 1.000 [1.00–1.00] | 1.000 [1.00–1.00] | 0.929 [0.79–1.00] | 0.947 [0.84–1.00] |
| doc: B11-02-NLP Exp4.pdf | 5 | 1.000 [1.00–1.00] | 0.867 [0.60–1.00] | 1.000 [1.00–1.00] | 1.000 [1.00–1.00] | 0.900 [0.70–1.00] | 0.926 [0.78–1.00] |
| doc: BCT mod2,3,6.pdf | 7 | 0.857 [0.57–1.00] | 0.679 [0.36–0.93] | 0.857 [0.57–1.00] | 1.000 [1.00–1.00] | 0.806 [0.54–1.00] | 0.852 [0.65–1.00] |
| doc: DL_Unit5_RNN.pdf | 11 | 0.727 [0.45–1.00] | 0.614 [0.34–0.86] | 0.667 [0.39–0.91] | 0.909 [0.73–1.00] | 0.644 [0.39–0.88] | 0.686 [0.48–0.88] |
| doc: HPC Lecture.pptx | 18 | 0.944 [0.83–1.00] | 0.833 [0.67–0.97] | 0.944 [0.83–1.00] | 0.944 [0.83–1.00] | 0.810 [0.65–0.94] | 0.842 [0.70–0.95] |
| doc: test_doc1.pdf | 7 | 1.000 [1.00–1.00] | 1.000 [1.00–1.00] | 1.000 [1.00–1.00] | 1.000 [1.00–1.00] | 1.000 [1.00–1.00] | 1.000 [1.00–1.00] |

## Same page, different wording

Each student-wording (hard) question next to the generated question about the same page. Hit@5: generated 7/7, student wording 7/7.

| Hard | Generated | Hit@5 hard / generated | First relevant rank (top 10) hard / generated |
|---|---|---|---|
| h-03 | g-019 | 1 / 1 | 1 / 2 |
| h-06 | g-002 | 1 / 1 | 1 / 1 |
| h-08 | g-036 | 1 / 1 | 2 / 1 |
| h-09 | g-030 | 1 / 1 | 1 / 1 |
| h-10 | g-046 | 1 / 1 | 1 / 1 |
| h-11 | g-008 | 1 / 1 | 1 / 1 |
| h-12 | g-049 | 1 / 1 | 1 / 1 |

## Does confidence predict a hit?

AUC (confidence of Hit@5 questions vs misses): **0.328** (0.5 = no signal, 1.0 = perfect separation).

| Grounding band | Questions | Hit@5 rate |
|---|---|---|
| strict | 25 | 0.840 |
| loose | 30 | 0.967 |
| none | 0 | – |

Out-of-corpus negatives: 6, mean confidence 41.0, max 65.4; grounding {'strict': 0, 'loose': 4, 'none': 2}.

## Does compression cut answer spans?

Of 43 answerable questions with an evidence quote: dropped 1, not_retrieved 5, survived 35, truncated 2. `survived` = the quote is in the compressed context; `truncated` = its chunk was retrieved but the 800-character cut removed it; `dropped` = its chunk lost to the 6-chunk limit; `not_retrieved` = no served chunk on a relevant page holds the quote.

## Where does the flat 0.5 web score land?

Local candidates' hybrid scores: p25 0.148, median 0.332, p75 0.600, p90 0.750; 0.695 of them score below 0.5.
Web search is off in this config; run `--config web` for the slot share.

Questions the decomposer split into several sub-queries: 12.
