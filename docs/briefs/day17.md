# Day 17 — Concept maps use your documents (R5) — release v0.3.0
Date: 2026-11-15 · Phase 5 — Postgres + pgvector data layer · Items: R5 (+ release v0.3.0, CO6 Render latency from Day 16)
Branch: feature/day17-r5-concept-maps

## Scope

1. **Shared retrieval service (R5, backend).** Already done on Day 9: `ConceptMapRetriever` takes the
   app's `RetrievalService` from `services/container.py:111-112`, no private `IndexBuilder`, no extra
   embedding call at startup; `test_app_factory.py:46` asserts the sharing. Nothing left to build here —
   but reading the path found three bugs that stop "use documents" from being correct even with the
   shared service (deliverables 2–4).
2. **The map's retrieval must see the user's current documents.** `doc_version` is never passed, so the
   L1 cache key is always `(user, topic, 0)`: after an upload or a delete in the same process, a repeated
   topic replays the old ranking (a deleted document can still be cited — the I5 promise broken for maps).
3. **"Documents only" must not run web search.** `hybrid_retrieve` always calls Tavily and embeds every
   web chunk when the service's `web_search_enabled` is on; the retriever then throws those results away.
4. **Node sources = document + page, and they must be real.** The extractor's context shows
   `[Document i] file.pdf:` with no page, and the model writes `sources` free-text (it can invent a file
   name). Timeline UI bullet: "ConceptNodeDetails shows the source document and page".
5. **Test:** a document indexed through the pipeline (`POST /upload`) is returned by the concept-map
   retriever — through `POST /api/concepts/generate` with `use_documents=true, use_web=false`.
6. **UI:** "use documents" toggle in `CreateMapForm.js` (today: `const [useDocuments] = useState(false)`
   and no button at all — the toggle was removed, not just disabled), with loading / empty / error states;
   `ConceptNodeDetails.js` shows document + page.
7. **CLAUDE.md Data & State.** Mostly already true (Day 15 wrote "chunks in Postgres", "files in
   FileStorage"). What's left is the production half: after the release, Render = Supabase Storage
   (`rag-prod`) and Postgres chunks; remove the "until v0.3.0" caveats. Done after the release's live
   check, not before.
8. **Release v0.3.0** (develop → master, tag). Per CLAUDE.md, releases stay **manual** (owner): this brief
   holds the runbook. Corrections to the timeline bullet:
   - production gets **three** revisions, not two: `9e72706d7449`, `500c410270f5` **and** Day 16's
     `21f0595f83d5` (content_hash index), all proven on `rag_staging`.
   - "run the reindex on production" → **dry run only** (Day 16 decision): v0.2.2 rows have no stored
     files, so `--apply` has nothing to index; expect every row "skipped: file missing".
9. **CO6 on Render** (Day 16's release checklist): n = 30 `/me`, n ≥ 15 chat turns, after re-creating
   the latency script (the Day 14 one was a scratchpad file).

## Current behavior

- `api/routes/concepts.py:39-47` calls `generate_concept_map` without the user's `doc_version`;
  `services/concept_map_service.py:61-67` calls the retriever without it either; the retriever's default
  is `doc_version: int = 0` (`retrieval/concept_map_retriever.py:31`), forwarded into
  `hybrid_retrieve(..., doc_version=0)`, whose L1 key is `(user_id, query, doc_version)`
  (`retrieval_service.py:89-93, 235`).
- Documents-only branch (`concept_map_retriever.py:87-105`) calls `hybrid_retrieve`, which at
  `retrieval_service.py:388-396` runs `get_web_chunks` (Tavily + `_embed_texts` on every web chunk,
  `:196`) whenever `self.web_search_enabled` — production default on — and then filters web results out.
- Docs + web (`:64-84`) and web-only (`:108-133`) — web-only catches bare `Exception` (`:131`).
- Extractor context: `concept_extractor.py:378-385` — `[Document i] {file_name}:` + text; no page.
  Prompt asks for `"sources": ["Source URL or filename"]` (`:89-90`). `_add_source_attribution`
  (`:260-266`) fills empty `sources` with the *first* retrieved source of that type — a guess.
- Storage: `concept_map_service.py:166` `','.join(sources)`; read back with `.split(',')` (`:314`).
  The model column comment says "JSON array" (`db/models/concept_map.py:62`) — it isn't. A file name or
  a "p. 3" label with a comma splits into two sources.
- `ConceptMapRetriever.format_context_for_llm` (`:183-230`) has **no caller** (grep) — dead code; it
  is the only place that put the page into a context.
- Chunk metadata from `PgChunkSearch` (`pg_chunk_search.py:38-46`): `file_name`, `page_num`,
  `chunk_index`, `document_id`.
- An empty map (no context) is saved and returned with 200 and 0 nodes
  (`concept_extractor.py:296-298`, test `test_concept_map_without_context_is_empty_and_skips_the_llm`);
  the UI then lists a "0 concepts" map.
- Frontend: `CreateMapForm.js:8` hard-codes `useDocuments = false`; the sources grid (`:103-137`) has
  only the Web card. `ConceptNodeDetails.js:85-101` already renders non-URL sources as `📄 {source}`.
  `GET /documents` returns `chunks` per document (`DocumentList.js:74` uses `chunks === 0`).

## Why it matters

- **Stale L1 (2):** user generates a map on "TCP congestion" with documents → deletes `networks.pdf` →
  generates the same topic again → the L1 hit returns the deleted document's chunks; the map cites a
  file that no longer exists. Same for upload: a new file is ignored until the process restarts or the
  cache evicts.
- **Wasted web calls (3):** a documents-only map spends a Tavily request and embeds ~5–20 web chunks
  per generation — on the free embedding tier (~1,000 texts/day, counted per text, Day 16) that is quota
  a student's upload needed.
- **Invented sources (4):** the model sees `[Document 3] notes.pdf:` and may write `"lecture.pdf"` or
  `"Document 3"`; the node detail then shows a source that isn't one. No page means a student can't
  find the passage.
- **Empty map saved:** a documents-only map for a topic not in the user's files is stored as a
  0-concept map instead of telling the user why.

## The concept

**Dependency injection and shared state.** A service that builds its own collaborators (R5 before
Day 9: a private `IndexBuilder`) silently gets *different state* from the rest of the app — here an
index nothing writes to. Injecting the one shared instance from a composition root (`container.py`)
makes "which index am I searching" a wiring fact you can test (`test_app_factory.py`), not a hope.
Pitfall: DI alone doesn't make the *call* correct — every per-request input that changes the answer
(user, document set version, source switches) still has to be passed. That is today's bug.

**Cache keys must contain every input that changes the output.** The L1 cache key is
`(user_id, query, doc_version)`. Invalidation-by-version only works if callers pass the real version;
a constant `0` turns versioning into "never invalidate". Adding a per-call `include_web` switch makes it
a new input, so it must join the key — otherwise a documents-only result could be replayed to the chat,
or a chat result (with web chunks) to a documents-only map. Production systems treat the cache key as a
function signature: if you add a parameter, you add it to the key, and a test proves two different
inputs miss each other.

**Grounded attribution by ID, not by name.** Letting an LLM free-write citations ("Source: notes.pdf")
invites fabrication: names that look plausible but weren't in the context. The robust pattern is to
**number the evidence** (`[D1] notes.pdf — p. 4`, `[W2] url`), ask the model to cite only those IDs,
then **resolve IDs to sources in code** and drop any ID that wasn't given. Citation validity becomes a
dictionary lookup instead of an LLM judgement (the same idea as the generation eval's code-checked
citation validity, Day 12). Pitfalls: the model may cite an ID range ("D1–D3") or a bare filename —
parse strictly and drop what doesn't resolve; keep the source label human-readable (file + page) since
that's what the student acts on.

**Release engineering for a schema-changing deploy.** v0.3.0 changes where durable data lives (Render
disk → Supabase Storage, in-memory FAISS → Postgres). Ordering matters: config before code (env vars
set before the deploy, or the new code falls back to the wiped local disk), migrations before the app
(the image's CMD runs `alembic upgrade head`, then the app refuses a schema not at head), then a live
smoke test that exercises the *new durability* (restart → still cited). Rollback is asymmetric: the
three revisions are additive, but the v0.2.2 image refuses to start on a schema at a revision it
doesn't know (`assert_schema_at_head`), so "redeploy the old image" is not a rollback — forward-fix is
the plan, and a downgrade is an owner-run last resort. Measuring latency before/after (CO6) on the real
topology (Render Singapore → Supabase Mumbai) is what tells you whether round-trip cutting paid off;
local numbers can't, because local round trips are ~0.1 ms instead of ~63 ms.

## Decisions

### D1 — Node source attribution
- **A — Numbered evidence + IDs resolved in code:** the context labels each block `[D1] notes.pdf — p. 4`
  / `[W1] title (url)`, the prompt asks for `"source_ids": ["D1", "W1"]`, and the extractor maps IDs to
  display strings (`notes.pdf — p. 4`, the URL), dropping unknown IDs and setting `source_type` from what
  resolved (document / web / both). Sources can't be invented; costs a prompt change and parsing code.
- **B — Page in the context, free-text sources:** add the page to `[Document i]` headers and ask the
  model to write `"notes.pdf (p. 4)"`. Small change, but still unverified — a node can show a file or
  page that wasn't retrieved.
- **Recommendation:** A. It's the only one where "nodes cite the uploaded material" is checkable by a
  test, and it removes the "first source of that type" guess in `_add_source_attribution` (B4's test
  changes accordingly: an unresolvable node gets no sources rather than a guessed one).

### D2 — How node sources are stored and returned
- **A — Keep `sources: List[str]` (display strings), store as a real JSON array:** `sources_json =
  json.dumps(sources)`, read with `json.loads`, legacy comma-joined rows read the old way. No migration,
  no API shape change; the page lives inside the string (`notes.pdf — p. 4`).
- **B — Structured sources:** `sources: [{type, file_name, page, url}]` in the API and storage. The UI
  can render page as its own chip and Day 50's citation viewer could link to it, but it changes the
  response schema, both frontend renderers and every legacy row on read.
- **Recommendation:** A. It fixes the comma bug and ships the visible feature today; Day 50 (PDF citation
  viewer) is the natural day to go structured, when a page link has somewhere to go.

### D3 — Documents-only maps and web search
- **A — Per-call `include_web` on `hybrid_retrieve`, part of the L1 key:** default `True` (chat
  unchanged); the documents-only branch passes `False`, so no Tavily call and no web-chunk embeddings.
- **B — Keep filtering web results after the fact:** no `RetrievalService` change, but every
  documents-only map spends a Tavily request and its embedding quota for nothing.
- **Recommendation:** A. Small, testable (fake web client records 0 calls), and the key change is the
  correctness half of it.

### D4 — A map with no context
- **A — Refuse it:** if retrieval returns no results at all, return 422 with a message naming the
  selected sources ("No passages in your documents match this topic — try another topic or turn on web
  search"), skip the LLM, save nothing. The existing empty-map test changes to expect 422 and no row.
- **B — Keep saving a 0-concept map:** current contract; the UI would have to detect `nodes == []` and
  explain after the fact, and the list fills with empty maps.
- **Recommendation:** A. An empty map is not a result; this also makes documents-only on an unrelated
  topic an explicit, testable empty state.

### D5 — The CO6 latency script
- **A — Commit it as `backend/scripts/measure_latency.py`:** `/me` × n and chat turns × n against a base
  URL with a test account's token from an env var; prints median / p90 per endpoint. Reusable for Day 21–22's
  post-deploy checks and for every future "did this get faster" question; uses `httpx`
  (already a dependency? — verified at implementation; if not, `requests`, else stop and ask).
- **B — Scratchpad again:** nothing to maintain, but Day 14's script was lost exactly this way and had to
  be "re-created" — the numbers stop being reproducible.
- **Recommendation:** A.

## Plan

### Checkpoint 1 — backend (≈ 9 file operations)
- `backend/app/retrieval/retrieval_service.py` — `hybrid_retrieve(..., include_web: bool = True)`; web
  step runs only if `self.web_search_enabled and include_web`; L1 key gains `include_web` (the three
  L1 helpers + `l1_cache_purge_user` keep working on `key[0]`).
- `backend/app/retrieval/concept_map_retriever.py` — `doc_version` required (no default); documents-only
  passes `include_web=False`; web-only's bare `except Exception` narrowed to the web client's real
  errors (read `retrieval/web/search_client.py` first); delete dead `format_context_for_llm`; type hints.
- `backend/app/generation/concept_extractor.py` — numbered context with page (`[D1] file — p. N`,
  `[W1] title (url)`), prompt asks for `source_ids`, resolver maps IDs → display strings + `source_type`;
  `_add_source_attribution` keeps the summary, drops the first-source guess.
- `backend/app/services/concept_map_service.py` — `generate_concept_map(..., doc_version: int)`;
  no-context → `ValueError`-style refusal mapped to 422 (D4); `sources_json` as JSON with legacy read.
  The `traceback.print_exc()` / bare `except:` lines in the functions touched are replaced by
  `logger.exception` / specific exceptions (owner rules) — only in code I edit.
- `backend/app/api/routes/concepts.py` — pass `current_user.doc_version`; 422 for the no-context case.
- Tests: `backend/tests/test_concept_maps.py` (new) —
  - upload a PDF through `/upload` → generate with documents only → `sources.documents > 0`, every node
    source is `<file> — p. N` of the uploaded file, fake web client called 0 times (the timeline's test);
  - delete that document → same topic again → 422, not a replay (doc_version reaches the L1 key);
  - documents-only for a user with no documents → 422, no map row;
  - `include_web` is part of the L1 key (a `True` result is not replayed to a `False` call).
  `backend/tests/test_concept_extractor.py` — ID resolution (unknown IDs dropped, both types → `both`),
  B4 test adjusted; legacy comma-joined `sources_json` still reads. `test_api_smoke.py` empty-map test
  → 422.
- New dependencies: none.

### Checkpoint 2 — frontend (≈ 6 file operations)
- `frontend/src/components/CreateMapForm.js` — a "Your documents" card next to "Web Search"; on mount
  fetch `GET /documents`, count documents with `chunks > 0`:
  - loading: card shows "Checking your documents…", disabled;
  - none: card disabled, "Upload a document first" with a link to the Documents page; default
    documents off;
  - some: card enabled, **on by default** (with web), subtitle "Search your N indexed documents";
  - fetch error: card disabled, "Couldn't load your documents"; web still usable;
  - 422 from generate: the existing error box shows the server's message.
- `frontend/src/components/ConceptNodeDetails.js` — document sources render file name and page
  separately (split on the `—` separator the backend writes, fallback to the raw string), e.g.
  `📄 notes.pdf · page 4`.
- Tests: `frontend/src/components/CreateMapForm.test.js` (new: enabled + sent in the payload with
  indexed docs; disabled with the hint with none; 422 message shown), `ConceptNodeDetails.test.js` (new:
  document + page, URL source, legacy plain filename).
- `npm test -- --watchAll=false` and `npm run build`.

### Checkpoint 3 — release prep (≈ 4 file operations)
- `backend/scripts/measure_latency.py` (D5) — stdlib/`httpx` only, no secrets printed, token from an env
  var, base URL as an argument.
- This brief: `## Release runbook v0.3.0` (below, refined with anything found in CP1–2).
- Then the owner runs `/pre-commit`, `/ship commit`, `/ship merge` (PR → develop).

### Checkpoint 4 — release (owner-run, I assist)
- Runbook below; after the live check: CLAUDE.md Data & State + the "until v0.3.0" caveats (only if
  asked), `## Outcome`, posts 3 and 9, learning notes.

## UI integration

| Backend change | Frontend file | What the user sees |
|---|---|---|
| `use_documents` actually retrieves the user's chunks | `CreateMapForm.js` | a "Your documents" card, on by default when they have indexed documents; disabled with "Upload a document first" when not; "Checking your documents…" while loading; "Couldn't load your documents" on error |
| Node sources = `file — p. N` resolved from retrieved chunks | `ConceptNodeDetails.js` | `📄 notes.pdf · page 4` under Sources; web sources stay links |
| No context → 422 with a message | `CreateMapForm.js` (existing error box) | "No passages in your documents match this topic…" instead of a saved 0-concept map |
| `include_web` / `doc_version` in the L1 key | backend-only — no new UI; the visible effect is that a deleted document stops appearing in maps |
| `measure_latency.py` | backend-only — an operator script |

## Verification

- `python -m pytest -q` on `rag_test` (suite 363 → ~370), `ruff check .`, `npm test -- --watchAll=false`
  (20 → ~25), `npm run build`.
- **Live, in a real browser** (owner's change 1, 2026-11-15) — **never the Docker backend**: it reads
  `.env`'s production Gemini key. The venv backend on a spare port (:8001) with the **eval** key on local
  `rag`; a second frontend dev server (:3001) with `REACT_APP_API_URL=http://localhost:8001`; a
  throwaway account, deleted afterwards (confirmed); a demo PDF only. **Correction:** the plan said
  "Tavily off", started as `$env:TAVILY_API_KEY = ""` — in Windows PowerShell that *deletes* the
  variable, so the app used `.env`'s real Tavily key on every :8001 run. Effect: **none in this
  concept-map check** (documents-only maps skip the web — `include_web=False` — and no `websearch:*`
  key from its time window exists), **21 live Tavily searches in the latency run** (below). Since then
  the switch is `WEB_SEARCH_ENABLED=false` in the shell (new setting, Day 17), for every local check:
  1. before any upload: the card says "No indexed documents yet", the link goes to `/documents`;
  2. upload a small PDF → "Search your 1 indexed document", on by default;
  3. documents-only map on the PDF's subject → open 2–3 nodes: each shows the PDF and a page, and the
     page really covers that concept (spot-check against the PDF). Screenshot (map + an open node with
     "📄 file · page N") to `docs/posts/assets/` (gitignored) for post 3;
  4. documents-only map on an unrelated topic → the 422 message in the error box;
  5. delete the PDF → the same topic → 422.

  **Results (2026-11-15, owner in the browser; :8001 eval key + :3001; account 27; demo PDF
  `photosynthesis-demo.pdf`, 3 pages built with PyMuPDF — light reactions / Calvin cycle / limiting
  factors, one per page):**
  1. pass — "No indexed documents yet", link to `/documents`.
  2. pass — "Search your 1 indexed document", on by default.
  3. pass — "Photosynthesis": Light-Dependent Reactions → p. 1 + p. 3, Calvin Cycle → p. 3 + p. 2,
     Limiting Factors → p. 3. The right page always present; the extra p. 3 justified (it covers light
     and CO₂ limiting those stages). Screenshot `docs/posts/assets/post03-concept-map-documents.png`.
  4. **fail, then fixed** — "French Revolution", documents only, built a map from photosynthesis text:
     vector search always returns the nearest chunks, so "nothing found" (422) only happens with no
     chunks at all. Owner's fix (no similarity threshold — no calibration data, B2): the extractor
     prompt asks the model for `off_topic: true` + no concepts when the passages don't discuss the
     topic; the service turns it into 422 "Your documents don't seem to cover '<topic>'. Try another
     topic or turn on web search.", nothing saved. Also: node sources sorted by file and page, then URLs.
     Re-run after the fix: "French Revolution" → that message (pass); "Photosynthesis" → still a map,
     Calvin Cycle now "page 2, page 3" (pass); "Calvin cycle" → 11 concepts / 11 connections, so a
     narrower topic isn't refused (pass); "Cellular respiration" → refused with the off-topic message
     (correct: the PDF doesn't cover it).
  5. pass — after deleting the PDF the "Your documents" card is disabled ("No indexed documents yet" +
     the upload link), so the UI never sends the request; the API's 422 for it is covered by
     `test_concept_maps.py`.
  - Found: the map list showed "46.282801862394514% confident" → rounded to a whole percent in the list
    and the viewer (`utils/formatConfidence.js`). The 46 itself, for a PDF that fully covers the topic,
    is recorded under B2 in `docs/improvements.md` (Day 26 replaces the heuristic).
  - Clean-up: account 27 deleted through `DELETE /user/delete` (4 maps; the PDF was already deleted);
    afterwards 0 rows for user 27 in all 7 tables, no orphaned map nodes, no `backend/uploads/27/`, no
    `semantic_cache:27` in Redis DB 0 or 1; login refused (401). Both servers stopped.
- No retrieval-quality change: `hybrid_retrieve`'s default path is untouched (`include_web=True`), so no
  E4 re-run is needed; one E4 baseline run is optional as a regression check (0 API calls, cached).
- Release (CP4): CO6 on Render with `backend/scripts/measure_latency.py` (owner's change 2): warm-up
  first and discarded; 30 × `/health`, 30 × `/me`; **15 distinct chat questions** (a repeat is replayed
  from the semantic cache, CO5 — the script also detects a replay and excludes it); per turn the time to
  the first `metadata` frame and to `[DONE]`; median / p90 for `/me`, chat → metadata, chat → total. The
  token comes from `RAG_LATENCY_TOKEN` and is never printed (httpx's URL logging is silenced: chat URLs
  carry `?token=`). Compared in the Outcome with Day 14's v0.2.2 numbers: `/me` 256.4 ms p50, chat →
  metadata 9170 ms p50 (+1.45 s over SQLite). Method note: all turns go to one session created by the
  warm-up turn, so none pays for topic tagging; Day 14's n = 5 turns don't record which they did.
- **Script check, local (2026-11-15):** :8001 (venv, eval key, local `rag`), throwaway account 28
  (deleted afterwards: 0 rows in 7 tables, no Redis key, login 401), `--n 3 --chat 15`. 15 fresh turns,
  0 replayed, 0 failed — confirmed server-side: `semantic_cache:28` held 16 entries (one per fresh
  answer), 1 session, 32 messages, 16 distinct questions. Report: `/me` p50 15.4 / p90 20.1 ms; chat →
  metadata p50 8113 / p90 12018 ms; chat → [DONE] p50 9604 / p90 13573 ms. **Not CO6 numbers** (local
  round trips ≈ 0.1 ms), and inflated by two things found when the owner asked where 8 s went:
  - **The script itself, ~2.05 s per turn on turns 2–15** (client time − the server's
    `REQ GET /chat/stream … ms`, which matched within 15 ms on turn 1; the /health p90 of 2079 ms is
    the same). It stopped reading each stream at `[DONE]`, so httpx closed the connection and every
    next request reconnected — on Windows' `localhost` apparently ~2 s (IPv6 tried first, uvicorn on
    127.0.0.1; not verified), on Render a TLS handshake. **Fixed:** read to the end;
    `tests/test_measure_latency.py` runs a real local HTTP/1.1 server and counts connections (3 → 1);
    re-run below.
  - **Live Tavily on every sub-query** (the PowerShell mistake above): 21 searches = 16 questions + 5
    second sub-queries; all 21 `websearch:*` keys created 18:34–18:37. Step breakdown, from the run's
    log plus a scratch harness that timed 2 turns in-process (Tavily forced off, web results from that
    Redis cache, throwaway user 29 deleted): semantic-cache lookup ~0.5 s (its embedding), open turn
    ~25–35 ms, per sub-query query embedding ~0.5 s + search ~55–60 ms, web-chunk embedding 0–0.75 s
    (47 cached web texts over 21 searches; median 0 — the domain allowlist drops most results),
    topic tagging 0 (849 ms when it runs), prompt build ~0. A 1-sub-query turn took 5.4 s server-side
    (median of 11) vs ~1.1 s in the harness → **live Tavily ≈ 3.8–4.3 s per sub-query**; the 4
    two-sub-query turns took 9.2–11.1 s. Recorded under CO2 in `docs/improvements.md`; production
    does this on every turn (web search is always on), which explains most of Day 14's chat latency.
  - **No 429 / retry** in the run's log or the harness; the Day 16 pacing (100 texts / 60 s) and the
    60 s 429 wait apply only to the upload embedder (`container.py`: the chat-path embedder has
    `max_attempts=1`, no `texts_per_minute`).
- **Re-run with the fixed script and `WEB_SEARCH_ENABLED=false`** (same setup, throwaway account 30,
  deleted afterwards: 0 rows in 7 tables, no Redis key, login 401): 15 fresh, 0 replayed, 0 failed
  (`semantic_cache:30` 16 entries, 16 distinct questions); `websearch:*` keys 21 → 21, so 0 Tavily
  calls. **Client − server per turn: 4–6 ms on all 15 turns** (was 2019–2088 ms on turns 2–15).
  | Metric (local, eval key, no web) | p50 ms | p90 ms |
  |---|---|---|
  | /health (n = 3) | 3.7 | 5.2 |
  | /me (n = 3) | 13.9 | 16.9 |
  | chat → metadata (n = 15) | 971.9 | 1442.9 |
  | chat → [DONE] (n = 15) | 2640.7 | 3062.6 |

  The four ~1.43 s turns are the four two-sub-query questions (one more ~0.47 s query embedding each).

## Release runbook v0.3.0 (owner-run)

PowerShell from the repo root unless a step says otherwise. Never print a URL, key or `.env` value:
every secret goes into an env var through `Read-Host -AsSecureString` (not echoed, not on any command
line, not in shell history) and is removed afterwards.

1. **Before the PR:** Day 17 merged into `develop`, CI green. `rag_staging` at `21f0595f83d5`
   (`alembic current` in a staging shell).
2. **Back up production's `rag` schema** (owner's change 3) with the compose image's `pg_dump`
   (`pgvector/pgvector:0.8.2-pg17`, Postgres 17 = Supabase's 17.11, nothing to install). Production's
   URL isn't in `.env`: copy `rag_app`'s session-pooler URL from Render's `DATABASE_URL`. The dump goes
   to `backend/data/backups/` (gitignored by `data/`, checked with `git check-ignore`):
   ```powershell
   $secure = Read-Host "Production DATABASE_URL (rag_app, session pooler)" -AsSecureString
   # pg_dump wants libpq's scheme, not SQLAlchemy's postgresql+psycopg://
   $env:DUMP_URL = ([System.Net.NetworkCredential]::new('', $secure).Password) -replace '^postgresql\+psycopg://', 'postgresql://'
   Remove-Variable secure
   New-Item -ItemType Directory -Force backend\data\backups | Out-Null
   # -e DUMP_URL without a value passes the variable from this shell; it never appears on the command line
   docker run --rm -e DUMP_URL -v "${PWD}\backend\data\backups:/backup" pgvector/pgvector:0.8.2-pg17 sh -c 'pg_dump "$DUMP_URL" --schema=rag --format=custom --no-owner --file=/backup/rag-prod-v0.2.2-2026-11-15.dump'
   Remove-Item Env:DUMP_URL
   # Verify: table names from the dump's table of contents — no rows are printed
   docker run --rm -v "${PWD}\backend\data\backups:/backup" pgvector/pgvector:0.8.2-pg17 pg_restore --list /backup/rag-prod-v0.2.2-2026-11-15.dump | Select-String ' TABLE (DATA )?rag '
   ```
   Expect 8 tables, each as `TABLE` and `TABLE DATA`: `users`, `sessions`, `messages`, `documents`,
   `failed_queries`, `concept_maps`, `concept_map_nodes` and `alembic_version` (no `document_chunks`
   yet — v0.2.2 is at `7cb8829683ab`). A non-zero exit or a missing table → stop.
3. **Render env vars, before merging to master** (Render → service → Environment):
   `STORAGE_BACKEND=supabase`, `STORAGE_BUCKET=rag-prod`, `SUPABASE_S3_ENDPOINT`, `SUPABASE_S3_REGION`,
   `SUPABASE_S3_ACCESS_KEY_ID`, `SUPABASE_S3_SECRET_ACCESS_KEY` (values from `.env`; pasted only into
   Render). Saving env vars redeploys **v0.2.2**, which ignores them — harmless.
   **Then check the bucket** (owner's change 5): Supabase dashboard → Storage → `rag-prod` exists and is
   marked **Private** (not Public). If it's missing or public, stop: without it every upload returns 503.
4. **Release PR:** `gh pr create --base master --head develop --title "release v0.3.0" --body "…"`;
   wait for `backend`, `frontend`, `docker` green (`gh pr checks <N> --watch`); then
   `gh pr merge <N> --merge` — **never `--delete-branch`** (it would delete `develop`). Render
   auto-deploys `master`; the CMD runs `alembic upgrade head` (three revisions: `9e72706d7449`,
   `500c410270f5`, `21f0595f83d5`; `document_chunks` is empty, so the HNSW build is instant).
5. **Watch the deploy log:** three "Running upgrade" lines, then uvicorn up; `GET /health` 200.
6. **Live check** (a demo account and demo documents, plus one real v0.2.2 document — owner's change 4):
   1. log in → Documents shows the v0.2.2 rows with "Not searchable yet";
   2. **re-upload `f1_deferred_fixes.pdf`** (one of the owner's v0.2.2 rows) → notice says it is
      searchable again (status `reindexed`), the badge is gone → a **new** question about it cites it;
   3. upload a demo PDF (status `new`, passages > 0) → a chat question cites it;
   4. **restart the Render service** (Manual Deploy → Restart) → a *new* question still cites it;
   5. Concept maps → "Your documents" is on → a documents-only map on the demo PDF's subject → nodes
      show the PDF with pages;
   6. delete the demo PDF → Supabase dashboard → Storage → `rag-prod` → `uploads/<user id>/`: its object
      is gone (the re-uploaded `f1_deferred_fixes.pdf` stays).
7. **Reindex dry run** (owner's change 5) — production's settings for this shell only, **no `--apply`**:
   ```powershell
   .\venv\Scripts\Activate.ps1
   Set-Location backend
   $secure = Read-Host "Production DATABASE_URL (rag_app, postgresql+psycopg://)" -AsSecureString
   $env:DATABASE_URL = [System.Net.NetworkCredential]::new('', $secure).Password
   Remove-Variable secure
   $env:DATABASE_SCHEMA = "rag"; $env:STORAGE_BACKEND = "supabase"; $env:STORAGE_BUCKET = "rag-prod"
   python -m scripts.reindex_all
   Remove-Item Env:DATABASE_URL, Env:DATABASE_SCHEMA, Env:STORAGE_BACKEND, Env:STORAGE_BUCKET
   Set-Location ..
   ```
   The S3 credentials come from `.env` (the same key serves both buckets). Expect every v0.2.2 row
   "skipped: file missing" except the one re-uploaded in step 6 (it has chunks, so it isn't listed).
8. **CO6 latency** (a demo account; its token from the browser's `localStorage` after login). On Render
   web search is on, as in production, so the chat numbers include ~4 s of Tavily per sub-query — the
   same as Day 14's, so the before/after stays comparable; CO6's change shows as the difference:
   ```powershell
   .\venv\Scripts\Activate.ps1
   Set-Location backend
   $secure = Read-Host "Demo account JWT" -AsSecureString
   $env:RAG_LATENCY_TOKEN = [System.Net.NetworkCredential]::new('', $secure).Password
   Remove-Variable secure
   python -m scripts.measure_latency --base-url https://rag-study-assistant-api.onrender.com
   Remove-Item Env:RAG_LATENCY_TOKEN
   Set-Location ..
   ```
   16 chat turns (1 warm-up + 15) spend production's Gemini free tier; run it once.
9. **Tag** (owner's change 5 — annotated):
   ```powershell
   git checkout master; git pull origin master
   git tag -a v0.3.0 -m "v0.3.0 - persistent search and files, faster uploads and chat, concept maps from your documents"
   git push origin v0.3.0
   ```
10. **Release notes:** documents uploaded before v0.3.0 must be uploaded again ("Not searchable yet");
    from now on uploads survive restarts and deploys; concept maps can use your documents.
- **No Redis flush** (user ids weren't reset; G9's condition doesn't apply).
- **Rollback:** the v0.2.2 image refuses to start on a schema at `21f0595f83d5`
  (`assert_schema_at_head`), so redeploying it is not a rollback. Plan: forward-fix on a hotfix branch.
  Storage-only problem: set `STORAGE_BACKEND=local` on Render (uploads work but don't survive restarts —
  v0.2.2's behaviour). Last resort: an owner-run `alembic downgrade 7cb8829683ab` on `rag` (drops
  `document_chunks` — loses every chunk indexed since the deploy), then redeploy v0.2.2; step 2's dump
  restores the v0.2.2 rows if a downgrade goes wrong (`pg_restore --clean --schema=rag`).

## Risks & open questions

- **Prompt change (D1)** changes concept-map output, which has no eval. Mitigation: the ID parser is
  strict and tested; the live check looks at a real map. Concept maps still hand-parse JSON (S1, later).
- **Production embedding quota:** the live check's PDF upload + questions + a documents map spend from
  production's Gemini free tier (per text) — use a small demo PDF.
- **Render free tier spin-down** inflates the first latency samples — warm up first, discard the first
  request.
- The three untracked `docs/posts/templates/post02-*.html` files (post 2 images) go in the Checkpoint 3
  commit (owner's change 6), docs only.
- Timeline wording to fix later (not today): "two revisions" → three; "run the reindex" → dry run.
- Resolved in CP1: `ConceptExtractor`'s Gemini call now catches `genai_errors.APIError` and
  `httpx.HTTPError` only.
- Found in CP1, left as is: `retrieval_service.py`'s web step in `hybrid_retrieve` still catches bare
  `Exception`; it could use `WEB_SEARCH_ERRORS` now.

## Outcome

### Checkpoints 1–3 — R5 and release prep (2026-11-15, PR #23 → `develop`)
- **Commits:** `cff9c33` (backend: D1, D2, D3, D4), `2cca9cb` (frontend), `73192f0` (off-topic refusal,
  sources ordered by page, latency script connection reuse, `WEB_SEARCH_ENABLED`, rounded confidence,
  G10 and CO2 recorded, post 2 templates). Merged in PR #23.
- **D1–D5 as recommended (all A):**
  - Concept maps cite numbered evidence (`[D1] file — p. N`, `[W1] url`), and the code resolves the
    model's `source_ids`, dropping unknown ids.
  - Node sources are stored as a real JSON array, and legacy comma-joined rows are still read.
  - `include_web` is a per-call switch and part of the L1 key. Documents-only maps make 0 Tavily calls.
  - A map with no context returns 422 and nothing is saved.
  - `backend/scripts/measure_latency.py` is committed.
- **Added during the live check (owner's fix, Verification step 4):**
  - The extractor returns `off_topic: true` when the passages don't discuss the topic, and that becomes
    a 422 "Your documents don't seem to cover '<topic>'…".
  - Node sources are sorted by file and page, then URLs.
- **Bug found by a test:** with the constant `doc_version = 0`, a deleted document's chunks kept coming
  from the L1 cache. The test fails with the old constant and passes with the fix.
- **Checks:** backend suite 363 → **381**, frontend 20 → **42**, `ruff check .` clean, `npm run build`
  ok, CI green on PR #23 and on the release PR #24.

### UI integration (as shipped)

| Backend change | Frontend file | What the user sees |
|---|---|---|
| `use_documents` retrieves the user's chunks (doc_version in the L1 key, no web search when off) | `CreateMapForm.js` | a "Your documents" card. It is on by default and says "Search your N indexed documents" when there are indexed documents. With none, it is disabled with "No indexed documents yet" and a link to `/documents`. While loading it shows "Checking your documents…", and on a failed fetch "Couldn't load your documents" (web stays usable) |
| Node sources resolved from cited ids to `file — p. N`, sorted by file and page | `ConceptNodeDetails.js` | `📄 notes.pdf · page 4` under Sources; web sources stay links; legacy plain strings still render |
| No context or off-topic → 422 with a message | `CreateMapForm.js` (existing error box) | "Your documents don't seem to cover '<topic>'. Try another topic or turn on web search." instead of a saved map |
| Map confidence (unchanged backend value) | `MapListView.js`, `ConceptMapViewer.js` (`utils/formatConfidence.js`) | a whole percent ("46% confident") instead of "46.282801862394514%" |
| `WEB_SEARCH_ENABLED` setting, `measure_latency.py` | backend-only (an operator switch and an operator script) | — |

### Release v0.3.0 (2026-11-17, PR #24 `develop` → `master`, annotated tag `v0.3.0` on `3325a89`)
- **Step 2 — backup:**
  - `pg_dump` of production's `rag` schema taken before the deploy.
  - `pg_restore --list` showed **8 tables, each as `TABLE` and `TABLE DATA`**, as expected.
  - The dump stays in `backend/data/backups/` (gitignored).
- **Step 3 — config before code:**
  - The six storage variables were set on Render.
  - `rag-prod` exists and is **private** (checked in the Supabase dashboard).
  - `/health` was ok before and after the env-var redeploy (still v0.2.2).
- **Steps 4–5 — deploy:**
  - CI green, and the release merged as a merge commit.
  - Render's log shows three migrations, `7cb8829683ab → 9e72706d7449 → 500c410270f5 → 21f0595f83d5`,
    then "Database schema is at head", then live.
- **Step 6 — live check on production:**
  1. `f1_deferred_fixes.pdf` (a real v0.2.2 row) showed "Not searchable yet".
  2. Re-uploading it gave the notice "searchable again — indexed 8 passages" (`reindexed`) and the
     badge went away. The size now shows 10.78 KB and the row is still Version 1, because a reindex
     doesn't bump the version. A **new** question about it cited pages 1–3.
  3. A demo PDF was uploaded, and the RuBisCO question cited page 2.
  4. After a **Render restart**, a new question still cited the demo PDF (page 3). This is the
     durability v0.3.0 exists for (I4).
  5. A documents-only concept map was built: 14 concepts, 67% confidence, 2 documents.
  6. The demo PDF was deleted, and only the F1 file is left in `rag-prod` (I5 on the real bucket).
- **Step 7 — reindex dry run on production:**
  - Result: **1 active document in total**, 0 would be indexed, 1 skipped (has chunks), 0 "file missing".
  - **Not what the runbook expected.** It assumed several v0.2.2 rows, all "skipped: file missing".
    Production had only one active document, the F1 row re-uploaded in step 6, so there was nothing
    for the reindex to report as missing.
- **No Redis flush** (user ids were not reset; G9 doesn't apply).

### CO6 on Render — latency, v0.2.2 (Day 14) vs v0.3.0
Measured with `python -m scripts.measure_latency` against production, after the release. There was a
warm-up turn first, which was discarded. Web search was on, as in production and as on Day 14.

| Metric (p50) | v0.2.2 (Day 14) | v0.3.0 (Day 17) | p90 v0.3.0 |
|---|---|---|---|
| `/health` | — | 63.2 ms | — |
| `/me` (n = 30) | 256 ms | **188 ms** | 193.9 ms |
| `/me` − `/health` | 190 ms | **125 ms** | — |
| chat → `metadata` | ~9.2 s (n = 5) | **8426 ms** (n = 12) | 13100 ms |
| chat → `[DONE]` | 11.0 s (n = 5) | **10811 ms** (n = 12) | 19285 ms |

- **n = 12 of 15 turns.** Three turns were cut: `RemoteProtocolError` ×2, and one stream ended
  without `[DONE]`.
  - Render's events show "Instance failed: health check timed out after 5 seconds", then recovery.
  - The cause was **B14**: `async def` routes did blocking work on the event loop, so `/health`
    couldn't answer during a chat and Render killed the instance. Pre-existing, not a v0.3.0
    regression. Fixed by hotfix v0.3.1 (below).
- **`/me`: 256 → 188 ms.** The gap over `/health` went from 190 to 125 ms, about **2 round trips** at
  ~63 ms. `test_round_trips.py` counts **3** for `/me`. The number is recorded as measured, not
  attributed.
- **Chat → `metadata`: about 0.75 s faster (9.2 → 8.4 s).** That is the same direction as Day 16's
  estimate but **smaller** (the estimate was ≈ 2.1 → 0.7 s, so ≈ 1.4 s saved). This is not a
  confirmation of the estimate:
  - n = 12, against Day 14's n = 5;
  - live Tavily dominates each turn (≈ 4 s per sub-query, measured locally in this brief's
    Verification);
  - the p90 is 13.1 s.
  Removing web-search latency (CO2) is the bigger lever.

### Hotfix v0.3.1 (2026-11-17, PR #25 → `master`, tag `v0.3.1` on `24e4e4a`; back-merged to `develop` in PR #26)
- B14 fixed. Details and measurements are in `docs/improvements.md` (B14) and the tracker:
  - routes are plain `def`, and the SSE generators are sync;
  - an upload holds no DB connection while it embeds;
  - deleting a document during indexing returns 409;
  - `doc_version` is bumped atomically.
  - Live (local): the worst `/health` was 0.47 s during a 136 s upload plus a chat turn.
- The CO6 chat numbers above were taken on v0.3.0, before this fix. A re-run on v0.3.1 would give the
  full n = 15. It is not done yet (it spends production's free tier).

### Found during the live check
- **B15 (new, P1): source chips turn into a plain "Source" after the first answer of a new chat.**
  - When a new session id arrives, `ChatWindow.js` refetches `GET /sessions/{id}/messages`.
  - That endpoint returns `sources` as comma-split strings (`routes/sessions.py`), because
    `messages.sources` stores a comma-joined list of file names or URLs (`chat_pipeline.py`).
  - `MessageList.js` renders `source.file_name || source.url || 'Source'`, and a string has neither
    field.
  - Pre-existing (the same code is in v0.2.2). The chips are visible on every new chat. Recorded in
    `docs/improvements.md` and the tracker. Related: B11, B12.

### Release notes (v0.3.0 + v0.3.1)
- **Your uploads now survive restarts and deploys.** Files live in cloud storage and the searchable
  passages in the database. Before, every server restart made uploaded documents unsearchable.
- **Upload documents from before v0.3.0 again.** They show "Not searchable yet", and re-uploading the
  same file makes it searchable without a new version.
- **Concept maps can use your documents.** Each concept shows the file and page it came from. A topic
  your documents don't cover is refused with a message instead of producing a map from unrelated text.
- **Faster uploads:** embeddings in batches, unchanged passages reused, and a notice on large files.
  Chat makes a third as many database round trips.
- **v0.3.1:** the server keeps answering health checks during long chats and uploads, so Render no
  longer restarts it mid-answer.

### Left open
- B15 (chips), B11 (feedback on reload), B12 (chip duplicates). The three should be fixed together on
  one day, backend + `ChatWindow.js` / `MessageList.js`.
- A CO6 chat re-measure on v0.3.1 with n = 15.
- Timeline wording ("two revisions", "run the reindex") is still to fix, as noted in Risks.
- `hybrid_retrieve`'s web step still catches bare `Exception` (Risks).
