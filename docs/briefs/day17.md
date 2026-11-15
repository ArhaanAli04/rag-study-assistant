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
- Live, local Docker stack with the fake-free stack (real Gemini dev key): upload a demo PDF → generate
  a documents-only map on its subject → every node shows the PDF and a page that exists; generate with
  web off on an unrelated topic → the 422 message; delete the PDF → same topic → 422.
- No retrieval-quality change: `hybrid_retrieve`'s default path is untouched (`include_web=True`), so no
  E4 re-run is needed; one E4 baseline run is optional as a regression check (0 API calls, cached).
- Release (CP4): CO6 on Render — `/me` n = 30 and chat n ≥ 15, compared with Day 14's numbers in the
  Day 14 brief; the live checks in the runbook.

## Release runbook v0.3.0 (owner-run)

1. **Before the PR:** Day 17 merged into `develop`, CI green. `rag_staging` at `21f0595f83d5`
   (`alembic current` in a staging shell).
2. **Render env vars, before merging to master** (Render → service → Environment):
   `STORAGE_BACKEND=supabase`, `STORAGE_BUCKET=rag-prod`, `SUPABASE_S3_ENDPOINT`, `SUPABASE_S3_REGION`,
   `SUPABASE_S3_ACCESS_KEY_ID`, `SUPABASE_S3_SECRET_ACCESS_KEY` (values from `.env`; pasted only into
   Render). Check the `rag-prod` bucket exists and is private. Saving env vars redeploys **v0.2.2**,
   which ignores them — harmless.
3. **Release PR:** `gh pr create --base master --head develop --title "release v0.3.0"`; CI green;
   `gh pr merge <N> --merge`. Render auto-deploys `master`; the CMD runs `alembic upgrade head`
   (three revisions; `document_chunks` is empty, so the HNSW build is instant).
4. **Watch the deploy log:** three "Running upgrade" lines, then uvicorn up; `GET /health` 200.
5. **Live check (demo documents only):** log in → Documents shows v0.2.2 rows "Not searchable yet" →
   upload a demo PDF (status `new`, passages > 0) → chat question cites it → **restart the Render
   service** → a *new* question still cites it → concept map with "Your documents" on → nodes cite the
   PDF with pages → delete the PDF → Supabase dashboard → Storage → `rag-prod`: the object is gone.
6. **Reindex dry run** from a dev shell with production's `DATABASE_URL` / `DATABASE_SCHEMA=rag` /
   `STORAGE_BACKEND=supabase` (+ bucket `rag-prod`) for that shell only:
   `cd backend; python -m scripts.reindex_all` → expect "skipped: file missing" for v0.2.2 rows. No
   `--apply`.
7. **CO6 latency:** `python -m scripts.measure_latency --base-url https://rag-study-assistant-api.onrender.com`
   with a demo account's token in the env var; warm the service first; n = 30 `/me`, n = 15 chat turns.
8. **Tag:** `git checkout master; git pull origin master; git tag v0.3.0; git push origin v0.3.0`.
9. **Then** a PR `master` → `develop` is not needed (release merge only).
10. **Release notes:** documents uploaded before v0.3.0 must be uploaded again ("Not searchable yet");
    from now on uploads survive restarts and deploys.
- **No Redis flush** (user ids weren't reset; G9's condition doesn't apply).
- **Rollback:** the v0.2.2 image refuses to start on a schema at `21f0595f83d5`
  (`assert_schema_at_head`), so redeploying it is not a rollback. Plan: forward-fix on a hotfix branch.
  Storage-only problem: set `STORAGE_BACKEND=local` on Render (uploads work but don't survive restarts —
  v0.2.2's behaviour). Last resort: an owner-run `alembic downgrade 7cb8829683ab` on `rag` (drops
  `document_chunks` — loses every chunk indexed since the deploy), then redeploy v0.2.2.

## Risks & open questions

- **Prompt change (D1)** changes concept-map output, which has no eval. Mitigation: the ID parser is
  strict and tested; the live check looks at a real map. Concept maps still hand-parse JSON (S1, later).
- **Production embedding quota:** the live check's PDF upload + questions + a documents map spend from
  production's Gemini free tier (per text) — use a small demo PDF.
- **Render free tier spin-down** inflates the first latency samples — warm up first, discard the first
  request.
- The three untracked `docs/posts/templates/post02-*.html` files are from an earlier day (post 2) — not
  part of Day 17; commit them separately or leave them.
- Timeline wording to fix later (not today): "two revisions" → three; "run the reindex" → dry run.
- `ConceptExtractor` still uses bare `except Exception` in `extract_concepts_from_context` (`:347`) for
  the Gemini call; narrowing it means knowing `google-genai`'s error types — done only if I touch that
  block for D1 (I will), otherwise recorded.
