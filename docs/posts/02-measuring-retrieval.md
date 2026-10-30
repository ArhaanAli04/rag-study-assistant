# Post 2 — "You can't improve RAG without measuring retrieval"

Publish after: Day 12 · Fed by days: 11–12 · Format: PDF carousel

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

## Slide outline
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
