# Day 11 — Retrieval eval harness (E4)
Date: 2026-11-09 · Phase 4 — Evaluation baseline · Items: E4 (also answers B2's open threshold question; finds a new bug, proposed B8)
Branch: feature/day11-e4-retrieval-eval

## Scope

1. **`backend/eval/retrieval/` package** that builds `RetrievalService` directly (never imports
   `app.main`, no `build_services()` Redis clients), with web search and the L1 cache disabled.
2. **Corpus**: 3–5 real course PDFs/PPTX in `backend/eval/corpus/`, gitignored (private course
   material), pinned by a committed `manifest.json` (file name + sha256) so every result names the
   exact files it ran on.
3. **Question set** `backend/eval/datasets/retrieval_v1.jsonl`:
   - LLM-generated questions over sampled chunks, prompted to paraphrase, plus a lexical-overlap
     filter that rejects questions copying the chunk's wording (so BM25 isn't favoured).
   - Real hard queries from `failed_queries` and thumbs-down messages — **mostly impossible as
     written**: the local DB holds 1 failed query (`"hello how are you"`, confidence 0) and 0
     thumbs-down messages; Render's database isn't reachable from here (and may not survive
     deploys). Replaced by a hand-written hard set (Decision 4) plus a mining script that will pick
     up real ones once they exist.
   - Relevance labelled at document (`file_name`) + page level, so labels survive re-chunking.
     DOCX chunks have `page_num = None` (`chunk_builder.py:145`), so DOCX can only be labelled at
     document level — the corpus sticks to PDF/PPTX.
4. **Metrics in plain Python**: Recall@5, Recall@10, MRR, nDCG@10 (plus Hit@5, which equals
   Recall@5 when a question has one relevant page).
5. **Open questions answered with numbers**:
   - Does the confidence score predict a hit? (hit rate per grounding band + AUC)
   - Does the 800-character compression cut answer spans? (evidence quote survival after
     parent expansion + `SimpleContextCompressor`)
   - Where does the flat 0.5 web score land? (`web` config: local hybrid score distribution vs 0.5,
     web share of the top 5, local Recall@5 change)
6. **CLI**: `python -m eval.retrieval --config baseline` → `backend/eval/results/{date}-{config}.json`
   plus `{date}-{config}.md`.
7. **Verify**: baseline numbers recorded in the tracker's Notes column for E4 (the owner edits the
   tracker — I'll supply the line).

Not in scope: generation quality (Day 12), replacing the old `rag_eval_runner.py` / `manual_eval.py`
(Day 12 rewrites them), a CI eval gate (E3, P2).

## Current behavior

- **No retrieval metric exists.** `eval/rag_eval_runner.py:44-56` prints whether document id 1
  shows up for two hardcoded queries, against the in-memory indexes of its own process — which are
  empty (I4), so it always prints `False`.
- **Web search can't be turned off.** `hybrid_retrieve` always calls `get_web_chunks`: 3 results
  below confidence 60, else 2 (`retrieval_service.py:389-397`), and it lazy-builds a
  `WebSearchClient` itself (`:128-129`). Errors are swallowed by a bare `except Exception`
  (`:396`). The only reason `test_confidence.py` runs offline is that `TAVILY_API_KEY` is empty.
- **The L1 cache can't be turned off.** Every `hybrid_retrieve` stores its result
  (`retrieval_service.py:446`), and a repeated `(user, query, doc_version)` returns the stored copy
  (`:211-213`), so a second config in the same process would read the first config's results.
- **Fusion weights are hard-wired** at `0.6 / 0.4` in `__init__` (`retrieval_service.py:51-52`).
- **New bug, found while reading for today (proposed B8): the vector half is ranked backwards.**
  `FaissVectorStore` is an `IndexFlatL2` (`vector_store.py:11`) and `search` returns
  `(squared L2 distance, metadata)` tuples (`:84`), where *lower is closer*. `hybrid_retrieve`
  unpacks that distance as `score` (`retrieval_service.py:234-240`), min-max normalizes it with
  higher = better (`:259-270`) and adds `0.6 × norm` to the fusion (`:303`). The closest chunk of
  the vector top-k gets vector score 0.0 and the farthest gets 1.0. The 0.4 BM25 half is
  unaffected, and only BM25 keeps the true best match near the top. The fake in
  `test_confidence.py:23-27` returns dicts with a higher-is-better `score`, so no test catches it.
  Confidence is computed from the same fused score (`:313-329`), so the grounding level is
  affected too.
- **Production retrieval parameters**: `ChatWindow.js:129` sends `top_k=5`; `ChatPipeline._retrieve`
  (`chat_pipeline.py:146-169`) decomposes the query, calls `hybrid_retrieve(top_k=5,
  rerank_top_k=5)` per sub-query, expands to parent pages (`MAX_PARENT_BLOCKS = 3`), then
  compresses to 6 chunks × 800 characters (`context_compressor.py:13`). The parent blocks carry no
  `score`, so `score_of` gives them 0.0 (`context_compressor.py:26-33`) and `nlargest(6)` keeps the
  5 children plus at most 1 parent.
- **Embeddings**: one Gemini call per text (`embeddings.py:35-47`, I3). A failed call is logged and
  becomes a zero vector, not an error (`:45-47`). The candidate corpus below is roughly 250 chunks,
  so every run that indexes from scratch makes about 250 embedding calls.
- **Candidate corpus already on disk** (`backend/uploads/`, flat pre-Day 3 paths; page and character
  counts measured with pypdf today): `DL_Unit5_RNN.pdf` 107 pp / 22.3k chars,
  `BCT mod2,3,6.pdf` 63 pp / 21.8k chars, `test_doc1.pdf` 5 pp / 7.7k chars,
  `B11-02 BDA Exp10.pdf` 4 pp / 8.0k chars, `B11-02-NLP Exp4.pdf` 3 pp / 4.0k chars,
  `B11_21_NLP_EXP9.pdf` 3 pp / 3.6k chars. No real-course PPTX on disk (only
  `tests/samples/sample{1,2}.pptx`).
- **The container test run can't see `backend/eval/`.** `.dockerignore` excludes it, and
  `docker-compose.override.yml:16` mounts only `backend/tests/`, so a test that imports
  `eval.retrieval.metrics` passes on the host and in CI but fails in `.\scripts\dev.ps1 test`.

## Why it matters

- **No metric:** Days 15–16 (pgvector, `ts_rank_cd` replacing BM25, 3072 → 1536 dimensions),
  26–31 (reranker, RRF, HyDE) all say "measure with E4". Without a baseline, each of those is a
  guess. The vector-inversion bug shows how much a guess can hide: the app has shipped for months
  with its main retrieval signal ranked backwards, and nothing but a labelled metric reveals it.
- **Web on during eval:** the score depends on Tavily's results that day, costs a credit per
  question, and web chunks take top-5 slots that have no labels. They would count as misses, so
  Recall@5 measures the web as much as the documents.
- **L1 on during eval:** run `baseline` then `vector_only` in one process and the second run silently
  returns the first run's rankings. The comparison reads as "no difference."
- **Confidence never validated (B2's residual):** a question gets `strict` grounding (≥ 70) and the
  model is told to stay inside the context. If confidence doesn't predict that the right page was
  retrieved, `strict` answers are confidently wrong. If it is low on good hits, the model is let off
  the leash for no reason.
- **Compression:** a 1000-character chunk is cut to 800 (`context_compressor.py:42-43`), so any
  answer in its last fifth never reaches the model. Retrieval would score a hit and the answer
  would still be wrong. Only a span-level check separates the two.
- **0.5 web score:** if most local hybrid scores fall below 0.5, web chunks outrank the user's own
  documents on most questions, and the "sources" panel shows web pages for questions the notes
  answer.

## The concept

### Evaluate retrieval separately from generation
A RAG answer can fail in two places: the right passage never reached the prompt (retrieval), or it
did and the model misused it (generation). End-to-end answer scores mix the two, so a prompt tweak
can't be told apart from a ranking regression. Production teams keep a **retrieval eval** (does the
ranked list contain the relevant passages, and how high?) that is cheap, deterministic and runs on
every retrieval change, and a separate **generation eval** (Day 12, LLM-as-judge) that is slower and
noisier. Retrieval is upstream: no prompt can fix a passage that never reached it, so its ceiling caps
the whole system.

### The metrics, and what each one is blind to
For one question with relevant set *R* and ranked list *L* (1-indexed):
- **Recall@k** = |R ∩ L[:k]| / |R|. "Did we find it within k?" Ignores order inside the k.
  With |R| = 1 it equals **Hit@k**. Recall@5 is the number that matters here because 5 is what the
  chat actually sends to the model.
- **MRR** = mean over questions of 1 / rank of the first relevant item (0 if none in the cut-off).
  It rewards putting *one* relevant item first and ignores the others. A drop from rank 1 to rank 2
  halves it, so it is sensitive at the top and nearly blind below rank 5.
- **nDCG@k** = DCG@k / IDCG@k, with DCG = Σ gainᵢ / log₂(i + 1). It discounts by position smoothly
  and handles several relevant items. With binary gains (relevant = 1) it sits between MRR and
  Recall in behaviour. IDCG is the DCG of the ideal ordering (all relevant items first), so the
  score is 1.0 at best.
- Report the **mean with a confidence interval** (bootstrap over questions). With 60 questions,
  one question is 1.7 points of Recall, so a "+2 points" change is noise unless the interval says
  otherwise.

### Label at a granularity that survives change
Labelling **chunk ids** breaks the dataset the moment chunk size changes (Day 26+ experiments) or
the index is rebuilt (uuid4 ids, `chunk_builder.py:29`). Labelling **(document, page)** survives
re-chunking. A retrieved chunk counts as relevant when its `file_name` and `page_num` match a label.
**Pitfall:** several chunks from the same relevant page would count multiple times and push
nDCG above 1. Dedupe by page in the ranked list first: only the first chunk from a relevant page
earns gain, and later chunks of it count as neither hit nor miss.

### Synthetic questions without favouring BM25
LLM-generated questions are the standard way to bootstrap a dataset (RAGAS's testset generator,
LlamaIndex's `generate_question_context_pairs`), but they have two known biases:
1. **Lexical leakage:** the generator copies phrases from the chunk, so exact-term BM25 looks
   brilliant and embeddings look weak. Fix: prompt for paraphrase *and* enforce it, by rejecting
   questions whose content-word overlap with the source chunk is above a threshold.
2. **Answerability and context-dependence:** "What does this slide show?" has no answer outside
   the slide. Fix: prompt for self-contained questions, have the model return a verbatim evidence
   quote, drop questions whose quote isn't in the chunk, and have a human review the draft before
   it's frozen.

A known limitation is **incomplete labels**: the same fact may appear on another page that isn't
labelled, so a "miss" can be a correct answer. Teams reduce this by pooling (reviewing the top
results of several systems), which is out of scope today and noted in the result summary.

### Hard queries and negatives
Synthetic questions are clean and single-hop, and real users aren't. A useful set mixes in:
abbreviations and misspellings ("expln lstm vanishing grad"), vague student phrasing, two-part
questions (exercises `QueryDecomposer`), and **out-of-corpus negatives**: questions the documents
don't answer. Negatives have no recall; they test whether *confidence* drops when it should. The
data flywheel is to mine failed queries and thumbs-downs into the next dataset version (`v2`), and
never edit `v1` in place, so old results stay comparable.

### Is the confidence score calibrated?
A score is useful for routing (strict / loose / none grounding) if higher scores mean higher odds of
a hit. Two cheap checks: **hit rate per band** (do ≥ 70 questions hit more often than 30–70 and
< 30?), and **AUC**, the probability that a random hit question scores higher than a random miss
question (0.5 = useless, 1.0 = perfect; computed from ranks, no library). A well-ranked but
miscalibrated score can be fixed by moving thresholds. A score with AUC ≈ 0.5 has to be replaced.

### Measure the system you ship, not a cleaner one
The eval has to call the same code path the chat uses, with the same `top_k`. A harness that
re-implements "the retrieval steps" drifts from production within weeks. The fix is to give
production code explicit switches (web on/off, cache on/off, weights) with production defaults, and
have both chat and eval call one function. A second pitfall is **caches**: any cache keyed on the
query (L1 here, Redis in production) makes a second run measure the first run.

### Score-direction bugs
Distance (lower = closer: L2) and similarity (higher = closer: cosine, inner product) are easy to
mix up. FAISS `IndexFlatL2` returns *squared* L2. For L2-normalized vectors (ours,
`embeddings.py:53-55`) d² = 2 − 2·cos, so cos = 1 − d²/2 converts exactly and keeps the score in
[−1, 1]. Normalizing with min-max does not fix direction, only scale. Production systems guard this
with a unit test that the nearest neighbour gets the highest fused score.

### Making the eval cheap enough to run every time
Indexing the corpus means ~250 embedding calls per run (I4: nothing persists). An **on-disk
embedding cache** keyed by `sha256(model | dimension | text)` makes every later run nearly free and
fully deterministic. **Pitfall:** `EmbeddingService` turns API errors into zero vectors, and caching
those poisons every later run. The cache must refuse all-zero vectors, and the runner aborts if any
appear.

## Decisions

### 1. How the eval switches off web search and the L1 cache, and reaches production's post-processing
- **A — Production switches + one shared function:** `RetrievalService.__init__` gains
  `web_search_enabled=True`, `l1_cache_enabled=True`, `vector_weight=0.6`, `keyword_weight=0.4`
  (production defaults unchanged), and `ChatPipeline._retrieve`'s loop (decompose → retrieve →
  parent expansion → compress) moves to one function in `app/retrieval/context_assembly.py` that both
  chat and eval call. This touches two app files and needs a small test, but the eval provably measures
  the code the chat runs.
- **B — Eval-only shims:** the eval injects a stub `web_client` that returns `[]`, a no-op web cache,
  and a fresh `RetrievalService` per config, and copies the expand + compress steps into the eval.
  No app change, but it reaches into an attribute the class lazily builds itself, and the copied
  steps drift from `ChatPipeline`.
- **Recommendation: A** — explicit switches are what the timeline asks for ("with web search and the
  L1 cache disabled"), and the shared function is the only way the compression answer stays true
  after later days change `ChatPipeline`.

### 2. The vector-distance inversion (proposed new ID B8)
- **A — Baseline first, fix today, record both:** measure `baseline` with the bug as-is (that is
  the real v0.2.0 number), then convert distance to similarity in `hybrid_retrieve`
  (`cos = 1 − d²/2`) with a regression test, re-run, and record before/after. It changes production
  ranking and the confidence distribution (and so the grounding level) today, which is
  what the harness exists to measure.
- **B — Measure only, fix on a later day:** record the bug as B8 with the numbers, and fix it on
  Day 26 with the other retrieval upgrades. Day 11 stays a pure measurement day, but every chat
  answer stays degraded for ~15 more days, and Days 15–16 would compare pgvector against a broken
  FAISS baseline.
- **Recommendation: A** — it is a ~5-line fix, the before/after is the best possible demo of why E4
  exists, and pgvector on Day 15 should be compared against a correct baseline. It goes in its own
  checkpoint and its own commit, so it can be reverted alone.

### 3. Which files form the corpus
- **A — Reuse what's on disk:** `DL_Unit5_RNN.pdf`, `BCT mod2,3,6.pdf`, `test_doc1.pdf`,
  `B11-02 BDA Exp10.pdf`, `B11-02-NLP Exp4.pdf` (5 PDFs, ~245 chunks, two big slide decks plus
  three short lab write-ups with partly overlapping ML/NLP vocabulary, which gives real distractors).
  No PPTX, so the PPTX parser path isn't measured.
- **B — Owner supplies 3–5 fresh files:** you drop real course files (ideally at least one PPTX)
  into `backend/eval/corpus/`. This covers both parsers and avoids `B11_21_NLP_EXP9.pdf`, which by
  its roll number may be someone else's work, but needs files from you before Checkpoint 3.
- **Recommendation: A plus one real PPTX from you if you have one** — I'm leaving out
  `B11_21_NLP_EXP9.pdf` either way. Corpus files are gitignored; `manifest.json` (names + sha256) is
  committed.

### 4. Hard queries, given there are none to mine
- **A — You write 10–15 by hand, and a mining script runs anyway:** about 10 hard in-corpus queries
  (abbreviations, typos, vague phrasing, two-part) plus about 5 out-of-corpus negatives, labelled by
  you with my help (I propose page labels from the top-10 results, and you confirm). `mine_feedback.py`
  exports `failed_queries` + thumbs-down rows for future `v2` sets. It costs you ~30 minutes, but
  the set stops being all-synthetic and the confidence check gets negatives.
- **B — Generated questions only today:** ship `v1` as ~60 generated questions and add hard
  queries in `v2` once real feedback exists. It needs nothing from you, but there are no negatives,
  so "does confidence drop when the documents can't answer?" stays unanswered.
- **Recommendation: A** — the negatives are what make the confidence question answerable at all.

### 5. Embedding cache for the eval
- **A — On-disk cache (stdlib `sqlite3`) in `backend/eval/.cache/`, gitignored:** wraps
  `EmbeddingService` inside the eval only, keyed by `sha256(model|dim|text)`, refuses zero vectors.
  After the first run, indexing and queries make no API calls, and results are reproducible.
- **B — No cache:** every run makes ~250 + 2 × questions embedding calls. Simpler, but it is slow
  and spends API quota on every config, and that adds up with five configs today and re-runs on
  every later retrieval day.
- **Recommendation: A** — no new dependency, eval-only, and it turns the harness into something you
  will actually re-run.

### 6. Model for question generation
- **A — `gemini-2.5-flash`:** stronger at paraphrase and self-contained questions. A one-off
  ~60–80 calls, through the same `google-genai` client (no new dependency).
- **B — `gemini-2.5-flash-lite`:** the app's model, cheapest, but more copied wording and
  slide-dependent questions to filter out.
- **Recommendation: A** — the questions are generated once and frozen, so quality beats cost.
  Generation runs once and is never part of a metric run.

## Plan

Package layout (all new unless marked):

```
backend/eval/retrieval/
├── __init__.py
├── __main__.py         ← CLI: python -m eval.retrieval --config <name> [--dataset …] [--limit N]
├── configs.py          ← frozen dataclass RetrievalConfig + CONFIGS: baseline, vector_only,
│                         keyword_only, web
├── corpus.py           ← load manifest, verify sha256, index files into a fresh IndexBuilder + BM25
│                         through the real IndexingPipeline (eval user id "eval")
├── embedding_cache.py  ← CachedEmbeddingService (sqlite3, refuses zero vectors)
├── dataset.py          ← typed records (EvalQuestion, RelevantPage), JSONL load/validate
├── metrics.py          ← recall_at_k, mrr, ndcg_at_k, page dedup, bootstrap CI, AUC — pure Python
├── runner.py           ← per question: served pass (production top_k=5) + deep pass (top_k=10),
│                         context assembly → evidence survival; aggregates; writes JSON + Markdown
├── generate_questions.py ← one-off: sample chunks per doc → Gemini JSON → paraphrase filter →
│                           datasets/retrieval_v1.draft.jsonl for review
└── mine_feedback.py    ← one-off: failed_queries + thumbs-down rows → datasets/hard_candidates.jsonl
backend/eval/corpus/manifest.json   ← committed; the corpus files themselves are gitignored
backend/eval/datasets/retrieval_v1.jsonl ← committed after your review
```

Why two passes: production sends `top_k=5` and gets 5 results back, so there is no rank 6–10 to
measure. Recall@5, MRR@5, confidence and the compression check come from the **served** pass with
exactly production's parameters. Recall@10, MRR@10 and nDCG@10 come from a **deep** pass with
`top_k = rerank_top_k = 10`, which also changes min-max normalization and confidence, so the deep
pass's own top 5 is not reported. The embedding cache makes the second pass free.

Each question line:
`{"id", "question", "type": "generated|hard|negative", "relevant": [{"file_name", "page"}],
"evidence": "<verbatim quote or null>", "source_chunk_chars": int}`

### Checkpoint 1 — production switches + shared context assembly (Decision 1A; 5 files)
- `backend/app/retrieval/retrieval_service.py` — constructor switches; skip `get_web_chunks` and
  L1 lookup/store when off.
- `backend/app/retrieval/context_assembly.py` (new) — `assemble_context(...) -> AssembledContext`
  (decompose → `hybrid_retrieve` per sub-query → parent expansion → compress), plus
  `RERANK_TOP_K` / `MAX_PARENT_BLOCKS` moved here.
- `backend/app/services/chat_pipeline.py` — `_retrieve` calls it, with no behaviour change.
- `backend/tests/test_retrieval_switches.py` (new) — web off ⇒ no web client built; L1 off ⇒ a
  repeat query is recomputed; weights respected.
- Run: `python -m pytest -q` (full suite, `test_api_smoke.py` guards the SSE contract).

### Checkpoint 2 — harness core, offline-testable (≈8 files)
- `eval/retrieval/{__init__,configs,dataset,metrics,embedding_cache,corpus,runner,__main__}.py`
- `backend/tests/test_retrieval_metrics.py` (new) — hand-computed cases for every metric, page
  dedup, negatives excluded from recall, AUC ties, cache refuses zero vectors.
- `docker-compose.override.yml` — mount `./backend/eval:/app/backend/eval:ro` so
  `.\scripts\dev.ps1 test` can import it (the image still excludes it).
- `.gitignore` — `backend/eval/corpus/*` except `manifest.json`, `backend/eval/.cache/`,
  `backend/eval/results/*.json` (the Markdown summaries are committed; decide in review if you'd
  rather commit the JSON too).

### Checkpoint 3 — corpus + dataset (≈5 files; needs your corpus files, and your review)
- Copy the chosen files to `backend/eval/corpus/`, write `manifest.json`.
- `eval/retrieval/generate_questions.py` → run once → `retrieval_v1.draft.jsonl` (~60 questions,
  ~12 per document weighted by chunk count, paraphrase filter: reject if > 50% of the question's
  content words appear in the chunk; threshold reported).
- `eval/retrieval/mine_feedback.py` → run once (expected: 1 row today).
- **You review** the draft and write the hard set (Decision 4A); I propose labels for your hard
  queries from deep-pass results. Then it's frozen as `retrieval_v1.jsonl`.

### Checkpoint 4 — baseline run and the open questions (≈3 files)
- Run `baseline`, `vector_only`, `keyword_only`, `web` → `results/2026-11-09-*.{json,md}`.
- The `.md` summary per run: the metrics table with 95% bootstrap CIs, a per-type and per-document
  breakdown, the confidence table (bands × hit rate, AUC, negatives' confidence), evidence
  survival (% of served hits whose quote survives compression; how many are cut by the 800-character
  limit vs dropped by `nlargest(6)`), and for `web` the local hybrid score percentiles vs 0.5, the
  web share of the top 5, and the Recall@5 change vs baseline.

### Checkpoint 5 — B8 fix (only if Decision 2A; 3 files)
- `retrieval_service.py` — tuple results converted with `1 − d²/2` before normalization.
- `backend/tests/test_retrieval_switches.py` (or a new `test_vector_score_direction.py`) — the
  nearest neighbour gets the highest vector score.
- `docs/improvements.md` — B8 entry (evidence, direction). Re-run all four configs → after numbers.

### Checkpoint 6 — docs and wrap-up
- Brief `## Outcome`, post 2 + post 9 material log entries, learning notes; CLAUDE.md module map
  and Key Commands mention `python -m eval.retrieval` (only if you ask — the Current Status block
  stays yours).

**New dependencies: none.** stdlib `sqlite3`, `hashlib`, `json`, `random`, `statistics`; existing
`google-genai`, `numpy`, `faiss`, `rank-bm25`.

## UI integration

**Backend-only — no user-visible change** for the harness (Checkpoints 2–4): it is an offline
developer tool, never served by the API and excluded from the image. Checkpoint 1 adds constructor
switches whose production defaults reproduce today's behaviour exactly, so there is no new endpoint,
field or flag. Checkpoint 5 (B8) changes ranking and therefore which sources and confidence the chat
shows, but it adds no field or state. The existing sources panel and confidence badge in
`ChatWindow.js` render the corrected values unchanged.

## Verification

- Checkpoint 1: full offline suite green on host; `.\scripts\dev.ps1 test` green in the container;
  `ruff check .` clean.
- Checkpoint 2: `test_retrieval_metrics.py` — Recall/MRR/nDCG on hand-worked rankings (e.g.
  relevant at rank 3 of 10 → MRR 1/3, nDCG = (1/log₂4)/1 = 0.5), dedup case, all-zero-vector
  refusal.
- Checkpoint 3: every dataset line validates; every `evidence` quote is found in its labelled page's
  text; the overlap distribution of kept vs rejected questions is printed.
- Checkpoint 4: two consecutive `baseline` runs give identical numbers (determinism, with the cache
  warm); the second run makes zero embedding calls (counted by the cache).
- Checkpoint 5: before/after for all four configs in the Outcome; `vector_only` should move the most
  (its ranking is fully inverted before the fix).
- Tracker Notes line for E4 (and B8): supplied in the Outcome for you to paste.

## Risks & open questions

- **The inversion makes today's baseline a bug measurement.** If you pick 2B, Days 15–16 compare
  pgvector against it. Say so in their briefs.
- **Small set:** ~60–75 questions gives wide intervals (a 95% CI of roughly ±10 points on Recall@5).
  It's good enough to catch the inversion and big regressions, not 2-point tuning. E3 (P2) grows it.
- **Slide-PDFs are thin:** `DL_Unit5_RNN.pdf` averages ~210 characters per page, so many pages make
  near-empty chunks; the generator will skip chunks under ~200 characters, which under-samples slides.
- **Incomplete labels** (the same fact on another page) count as misses; noted in every summary.
- **`EmbeddingService` swallows API errors into zero vectors** (`embeddings.py:45-47`); in the app this
  silently corrupts the index. The eval aborts on them, and the app-side fix is outside today's scope
  (record under I3 on Day 16).
- **`hybrid_retrieve` swallows every web error** with a bare `except Exception` (`:396`), against the
  owner's rule. It is untouched today apart from the switch; noted for G5 / Day 35.
- **`semantic_search` / `POST /search` also returns raw L2 distances** labelled as scores. No
  frontend caller (`/search` isn't used in `frontend/src`); left as is, noted in B8.
- **Question:** is any of these files *not* yours to put in a committed manifest by name
  (`B11-02 …` lab write-ups)? The manifest only holds names + hashes, never content.
  Answered: the B11-02 files are the owner's; `B11_21_NLP_EXP9.pdf` was left out.

## Outcome
Date: 2026-11-09. Five commits on `feature/day11-e4-retrieval-eval` → draft PR #14 into `develop`.
CI (`backend`, `frontend`, `docker`) green on the first four; the fifth is this commit. Owner
decisions: 1A, 2A, 3A (without `B11_21_NLP_EXP9.pdf`, plus the owner's `HPC Lecture.pptx`), 4A, 5A,
6A changed mid-day (see Deviations).

### Commits and files
- **`5bfdfe6` — Checkpoint 1 (6 files):** `retrieval/retrieval_service.py` (switches `web_search_enabled`,
  `l1_cache_enabled`, `vector_weight`, `keyword_weight`; production defaults); new
  `retrieval/context_assembly.py` (`assemble_context`, `AssembledContext`, `RERANK_TOP_K`,
  `MAX_PARENT_BLOCKS`); `services/chat_pipeline.py` (`_retrieve` calls it); new
  `tests/test_retrieval_switches.py` (6 tests); `CLAUDE.md` (v0.2.0 released); this brief
- **`1389aad` — Checkpoints 2 + 3 (20 files):** new `backend/eval/retrieval/` — `__main__` (CLI),
  `runner` (served / deep / context passes, aggregation, JSON + Markdown), `metrics` (Hit@k, Recall@k,
  MRR, nDCG@k with page dedup, bootstrap CI, AUC), `dataset` (format, validation, `multi_part`,
  `paired_with`, `problems_against_corpus`), `configs`, `corpus` (manifest, sha256, indexing through
  `IndexingPipeline`), `embedding_cache` (sqlite, paced, resumable, blank text → zero vector),
  `rate_limit`, `key_guard`, `generate_questions` (resumable, quota-aware), `mine_feedback`;
  `eval/corpus/manifest.json`; `eval/datasets/retrieval_v1.jsonl`; new `tests/test_retrieval_eval.py`;
  `.gitignore`; `docker-compose.override.yml` (mounts `eval/` read-only for the container tests);
  `docs/{improvements,improvement-tracker,timeline}.md` (B8, B9, B10)
- **`8c547b4` — Checkpoint 4 (3 files):** `eval/results/2026-11-09-{baseline,vector_only,keyword_only}-before-b8.md`
- **`31b4a18` — Checkpoint 5 (7 files):** `retrieval/retrieval_service.py` (distance → cosine; the
  unused 3-tuple branch removed); new `tests/test_vector_score_direction.py` (3 tests, a real
  `FaissVectorStore`); three `*-after-b8.md` summaries; B8 in the tracker and `improvements.md`
- **Checkpoint 6 (this commit):** `CLAUDE.md` (module map, flow step 3, Feature Status, Key Commands,
  Known Issues B2/B8/B9/B10, Current Status); `docs/timeline.md` (Day 26 and Day 29 notes);
  `docs/improvement-tracker.md` (E4); this Outcome; `docs/posts/02-measuring-retrieval.md` and
  `09-launch-recap.md` material log; the three `*-after-b8.md` summaries re-stamped with commit
  `31b4a18` (re-run, 0 API calls, numbers identical)

### Checks run
| Check | Result |
|---|---|
| Host `python -m pytest` | 166 at start → 172 (CP1) → 195 (CP2) → 214 (CP3) → **217** (CP5) |
| Container `.\scripts\dev.ps1 test` | 172 → 195 → 214 → **217** |
| `ruff check .` | clean after every checkpoint |
| `docker compose config` | valid after the `eval/` mount |
| CI on PR #14 | green on `5bfdfe6`, `1389aad` (delayed by a GitHub Actions incident, then passed), `8c547b4`, `31b4a18` |
| Dataset vs corpus | 61 questions, every labelled page exists, all 43 evidence quotes on their pages |
| Determinism | `after-b8` re-run on `31b4a18`: identical numbers; 0 API calls |

### Measured (retrieval_v1, 55 answerable questions; production fusion = `baseline`)
| Metric | Before B8 fix | After B8 fix |
|---|---|---|
| **Hit@5** | 0.782 [0.67–0.87] | **0.909** [0.84–0.98] |
| **MRR@5** | 0.339 [0.26–0.43] | **0.801** [0.71–0.88] |
| Recall@5 / Recall@10 | 0.736 / 0.779 | 0.897 / 0.964 |
| MRR@10 / nDCG@10 | 0.193 / 0.317 | 0.851 / 0.872 |
| Hit@5 generated / hard | 0.744 / 0.917 | 0.884 / 1.000 |
| Hit@5 HPC Lecture.pptx (18 q) | 0.611 | 0.944 |
| Evidence quote reaches the model (of 43) | 24 (3 truncated, 3 dropped) | 36 (1 truncated, 1 dropped) |
| Confidence AUC (hit vs miss) | 0.638 | 0.332 (5 misses) |
| Negatives (6) at strict grounding | 1 | 2 |
| Local hybrid scores below the flat 0.5 web score | 52.5% | 67.9% |
| vector_only Hit@5 / MRR@5 | 0.945 / 0.309 | 0.945 / **0.833** |
| keyword_only Hit@5 / MRR@5 | 0.855 / 0.602 | 0.855 / 0.602 (unchanged) |

Findings: before the fix, production fusion was worse than either half alone; after it, fusion
(0.909 / 0.801) is still ≤ vector_only (0.945 / 0.833) — R4 (Day 29) must beat vector_only. The
confidence score doesn't predict a hit before or after (bands ordered wrongly) — replace it on Day 26.
The regex decomposer splits 12 of 61 questions, mostly single-intent ones containing "and"; before
the fix, 5 of the 6 evidence losses were split questions (R2). Student wording didn't hurt: all 7
hard/generated pairs hit at rank 1–2 after the fix.

Quota on the eval project (2026-11-09): `gemini-3.5-flash-lite` 78 of 500; `gemini-embedding-001`
478 of 1,000 (392 corpus texts + query and sub-query embeddings; every later run 0).

### UI integration
| Backend change | Frontend file | What the user sees |
|---|---|---|
| `RetrievalService` switches, `context_assembly.py` | — | backend-only: production defaults reproduce the old behaviour; no endpoint, field or flag |
| Eval harness, dataset, results | — | backend-only developer tool, excluded from the image |
| B8 fix | existing sources list and confidence badge in `ChatWindow.js` / `MessageList.js` (unchanged) | better-ranked sources and different confidence values; no new field or state |

### Deviations from the plan
- **Decision 6A → `gemini-3.5-flash-lite`.** The first generation run (`gemini-2.5-flash`) hit a 20
  requests/day free-tier limit after 20 calls, and it ran on the production key (22/20) before the
  eval project existed. `gemini-2.5-flash-lite` has the same 20/day limit; 3.5 Flash Lite allows 500.
  78 requests made 52 drafts (26 rejected: 21 copied wording, 3 empty, 2 non-verbatim quotes); the
  owner deleted 9.
- **Added:** `key_guard.py` (the eval refuses `.env`'s production key), `rate_limit.py` (≤ 14 RPM for
  generation; 90 RPM / 27K estimated TPM for embeddings), a resumable progress file for generation
  and a per-vector-committed embedding cache (a stop keeps everything paid for).
- **Labels pooled from FAISS + BM25, not the deep pass:** the deep pass is hybrid fusion with the B8
  inversion, so its ranks were shown for information only.
- **Headline metric:** Hit@5 (with MRR@5), at the owner's request; Recall@5 for two-part questions.
  Added a two-part slice and a hard/generated pair comparison.
- **Hard queries:** written by the owner (12 + 6 negatives); mining found 1 candidate
  (`hello how are you`, used as n-01).
- **Blank chunks:** the eval's embedding cache gives empty text a zero vector without an API call,
  mirroring production (B10).
- **Recorded, not fixed:** B9 (P1, Day 12), B10 (P2, Day 16).

### Deferred
- `--config web` (Tavily on; embeds every web chunk) → another day, with `--limit`.
- Confidence replacement → Day 26 (timeline note). RRF vs vector_only → Day 29 (timeline note).
- `semantic_search` / `POST /search` still return raw distances (no frontend caller) → Day 15 rewrite.

### Tracker Notes (written today at the owner's request)
- **E4:** Done (`web` run deferred). **B8:** Done with before/after. **B9** (P1), **B10** (P2): added.
