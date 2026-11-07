# Day 8 — Move ingestion, indexes, retrieval and generation modules
Date: 2026-11-07 · Phase 3 — Codebase refactor: proper package structure · Items: none
Branch: feature/day08-refactor-modules

## Scope
1. **Regroup the flat modules** of `backend/app/` into `db/`, `ingestion/`, `retrieval/`,
   `generation/`, `services/` (+ `services/caches/`) and `schemas/`, exactly as the Day 8 rows of
   `docs/architecture/layout.md` say, and fix every import that points at them.
   - **"git mv" as written isn't possible for Claude** (`/run-day` forbids git writes). Same as
     Day 7: plain moves, and git's rename detection records them as renames when you stage them,
     because only import lines change. You confirm with `git status` after `git add -A`.
   - **Stays flat today** (their days are later): `main.py` and `routes/auth_routes.py` (Day 9),
     the eval scripts, the one-off DB scripts, `frontend.py`, `document_delete_service.py` (Day 10).
     Their imports are updated so they keep pointing at the moved modules.
2. **Pure moves.** No behaviour change, so any test failure is an import problem.
3. **Pydantic models out of `main.py`** into `schemas/{documents,chat,quiz,feedback,auth,users}.py`;
   `concept_map_schemas.py` → `schemas/concept_maps.py`.
4. **Dockerfile, compose, `alembic/env.py`, root scripts — already done on Day 7.** The Dockerfile
   copies `backend/app/` as a whole and runs from `/app/backend`, so sub-packages need no change.
   `alembic/env.py` needs one import line (`app.db` → `app.db.database`). The root scripts
   (`fix_db.py`, `recreate_db.py`, `migrate_user_model.py`) use raw `sqlite3` and import nothing
   from `app`, so nothing to do. `scripts/manual/*` still use pre-Day 7 bare imports; Day 10 moves
   and fixes them (unchanged plan).
5. **Lazy-load the OCR / table libraries** (img2table, camelot, pytesseract, cv2) — its own commit
   after the moves. Target: backend import < 5 s.
6. **Fix `test_docx_pdf_utils.py`'s sample paths** so its six tests actually test something — its
   own commit after the moves.
7. **Verify:** the Day 5 smoke tests (`test_api_smoke.py`) pass unchanged.

## Current behavior
1. **62 flat modules.** `backend/app/` has 56 top-level modules plus `core/`, `routes/`,
   `services/`. The `app.*` imports that will change (measured with grep today):
   - `main.py:10-55` imports 20 of the moving modules, plus lazy imports at `main.py:302,981,1120,1131,1188` (`app.db`).
   - Inside the moving modules, e.g. `retrieval_service.py:6-17`, `indexing_pipeline.py:5-13`,
     `chunk_builder.py:3-5,41-42,136`, `chunking.py:19,42`, `unified_parser.py:2-6`.
   - Outside: `core/security.py:9` and `routes/auth_routes.py:6` (`app.db`), the eval scripts
     (`rag_eval_runner.py:4-7`, `rag_metrics.py:15-16`, `manual_eval.py:2`, `cache_tuner.py:4`),
     `run_migration.py:5`, `update_existing_sessions.py:1`, `document_delete_service.py:1-3`,
     `alembic/env.py:13`.
   - Tests: 11 test files import moved modules (e.g. `test_account_service.py:11-17`);
     `conftest.py:128` looks up `sys.modules["app.db"]` to dispose the engine at teardown.
   - No `importlib` / string-based imports, no `monkeypatch.setattr("app.x...")` strings, and the only `__file__`-relative path is `core/config.py:13`, which isn't moving. So the import lines are the whole surface.
2. **Baseline, measured today:** `python -m pytest` → **134 passed, 1 xfailed in 25.4 s**.
3. **Schemas in `main.py:82-137`:** `SearchRequest`, `ChatRequest`, `ChatResponse`, `QuizDifficulty`,
   `QuizRequest`, `FeedbackRequest`, `UserCreate`, `PasswordChange` (pydantic-v1 `@validator`),
   `ProfileUpdate`.
5. **Import cost is eager.** Every heavy library is imported at module top:
   `table_utils.py:2` (img2table), `pdf_table_utils.py:1-2` (camelot, pdfplumber),
   `ocr_utils.py:2,44` (pytesseract), `image_preprocessing.py:2` (cv2). They reach every app start
   through `main → indexing_pipeline → chunk_builder:41 → pptx_pipeline:3-4 → ocr_utils / table_utils`
   and `indexing_pipeline:12 → unified_parser:3-6`.
   **Measured today** (host venv, Python 3.12, fresh process each):
   | import | time |
   |---|---|
   | `app.indexing_pipeline` | 14.2 s warm (36.6 s on the very first, cold-cache run) |
   | `app.table_utils` alone | 8.3 s |
   | `app.pdf_table_utils` alone | 3.9 s |
   | `app.ocr_utils` alone | 3.6 s |
   | `app.image_preprocessing` alone | 1.1 s |
   | bare `python -c pass` | 0.2 s |
6. **`test_docx_pdf_utils.py:9,19,27,34,41,48`** use `"tests/samples/..."`, relative to the CWD.
   `conftest.py:117-120` chdirs to a temp dir before collection, so every `os.path.exists` is
   False and all six tests pass having run nothing. The files exist
   (`backend/tests/samples/table_test.pdf`, `scan_handwritten.png`, `test_style.docx`). The tests
   also `print()` instead of asserting, and three of them assert nothing at all.

## Why it matters
1. **Flat layout:** 56 modules in one directory with no visible boundaries. Day 9 has to build
   `api/deps.py` and a `ChatPipeline` service on top of `services/`, `retrieval/` and `generation/`;
   without the packages it would do the regrouping and the rewiring in one diff, and a test
   failure could be either.
2. **Pure moves:** if a move commit also changes logic, a red test can't tell you which.
   Keeping them separate is what makes the Day 5 smoke tests a proof of "nothing changed".
3. **Schemas in `main.py`:** Day 9's routers each need their request models. If the models stay
   in `main.py`, every router imports `main` — a circular import (main includes the routers).
5. **Import time:** `uvicorn --reload` restarts the process on every save. At 14 s per restart,
   a session with 40 saves loses ~10 minutes to waiting. In production it lengthens every Render
   cold start and pushes against the Dockerfile healthcheck's 60 s start period. And all of it
   is for libraries only the PPTX-image and table paths use; `/upload` doesn't accept images at all.
6. **Silent-pass tests:** a broken camelot, Tesseract or DOCX parser today shows up as six green
   ticks. Same pattern as B3 (the OpenCV wheel clash that made table extraction return nothing
   for months). A test that can't fail is worse than no test, because it's counted as coverage.

## The concept

### Packages, `__init__.py` and import paths
- A **regular package** is a directory with `__init__.py`. `import app.retrieval.vector_store`
  runs `app/__init__.py`, then `app/retrieval/__init__.py`, then the module, and caches each in
  `sys.modules` under its full dotted name.
- **The module's identity is its dotted name, not its file.** If the same file were reachable as
  `vector_store` and as `app.retrieval.vector_store`, Python would load it twice: two class
  objects, two singletons, and `isinstance` failing across them. Day 7 hit exactly this with
  `config.oauth_config` vs `src.config.oauth_config`. One root (`backend/`) and absolute imports
  make it impossible.
- **Empty `__init__.py` files** (no re-exports) keep the import graph explicit: every caller
  names the real module. Re-exporting from `__init__` (`from app.retrieval import RetrievalService`)
  is convenient but makes every `import app.retrieval` pay for importing everything in it —
  the opposite of today's lazy-loading goal.
- **Shadowing is gone with absolute imports.** `app/ingestion/parsers/docx.py` can do
  `from docx import Document` and get python-docx, because since Python 3 a bare `import docx`
  never means "the sibling file". It only breaks if someone puts `parsers/` itself on `sys.path`
  (e.g. running `python parsers/docx.py`), which the "one root" rule forbids.

### Layered architecture and the dependency rule
- `api → services → retrieval / generation / ingestion → db → core`. Dependencies point down only.
- **Why:** each layer can be tested by replacing the one below it, and cycles can't form.
- **Moving files reveals the violations that a flat directory hides.** After today's moves,
  grep shows three edges that break the rule (see Decisions). Production codebases enforce the
  rule with a tool (`import-linter` contracts, or `ruff`'s `TID251` banned imports); here we write
  the exceptions down in `layout.md` first and remove them as later days refactor.

### Refactoring safely: moves vs rewrites
- **Rename detection:** git stores snapshots, not moves. `git log --follow` and `git blame`
  reconstruct a rename when a deleted and an added file are ≥ 50 % similar. Changing only import
  lines keeps similarity near 100 %. Rewriting the file in the same commit can drop it below the
  threshold, and history appears to start at the move.
- **Characterisation tests:** the Day 5 smoke tests describe what the app does, not what it
  should do. Moves that keep them green are behaviour-preserving by definition; that's why they
  were written before the refactor.
- **Mechanical edits by script, reviewed by diff:** ~100 import lines are rewritten with an
  explicit old→new module table, not by hand. A table is reviewable in one screen; a hundred
  hand edits are not, and a missed one only fails at import time.

### Lazy imports and startup cost
- **Why imports are slow:** importing a module executes it. img2table pulls in polars, OpenCV and
  pandas; camelot pulls in pdfminer, OpenCV and matplotlib; each loads compiled extensions from
  disk. Most of the 14 s is reading and initialising those, not our code.
- **Function-local import:** `def extract_tables(...): import camelot`. The first call pays the
  cost; later calls hit `sys.modules` (a dict lookup). Simple, explicit, and greppable.
- **Alternatives:** PEP 562 module-level `__getattr__` (lazy attribute on first access),
  `importlib.util.LazyLoader`, or PEP 810 explicit lazy imports (Python 3.15). More magic, harder
  to read, and the owner's rules say explicit over implicit.
- **Pitfalls:**
  - The cost moves to the first request that needs it: the first PPTX upload after a restart
    gets ~8 s slower. Fine for an upload; not fine for a latency-critical path. Production
    systems pay it at startup ("warm-up") for hot paths and lazily for cold ones.
  - Import errors move too: a broken install used to crash at startup and now crashes on first
    use. Tests that exercise the path (today's fix in deliverable 6) are what catch it.
  - Type hints that name a lazy library's types need `if TYPE_CHECKING:` imports.
- **How to measure:** `python -X importtime -c "import app.main"` prints a per-module tree;
  wall-clock `Measure-Command` on a fresh process gives the number that matters.

### Tests that can't fail
- `if os.path.exists(path): ...assert...` passes when the file is missing. Relative paths make it
  depend on the CWD, which pytest, IDEs and conftest all change.
- **Fix:** anchor fixtures to `Path(__file__).parent`, make a missing fixture a failure (not a
  skip), and assert on content the sample is known to contain — "returns a list" is true even
  for an empty list.

## Decisions

### 1. Upward / sideways imports the moves expose
After the moves, three edges break `layout.md` rule 1:
- `retrieval/retrieval_service.py` → `services/caches/{query_cache,web_cache}` (upward: retrieval → services)
- `retrieval/{vector_store,index_builder}.py` → `ingestion/models.py` (`DocumentChunk`; sideways)
- `ingestion/indexing_pipeline.py` → `retrieval/{index_builder,keyword_index}` (sideways)
(`core/security.py` → `app.db` is a fourth, already planned away on Day 9 with `api/deps.py`.)
- **A — Move as the layout says; list the edges as known exceptions in `layout.md`:** pure moves
  stay pure, and each exception has an owner day (Day 9 injects the caches into `RetrievalService`
  and moves `IndexingPipeline` into `services/`; Day 13's pgvector chunk model replaces
  `DocumentChunk`). The trade-off is a few documented violations for ~1–5 weeks.
- **B — Change targets today to avoid them** (`query_cache`/`web_cache` under `retrieval/caches/`,
  `DocumentChunk` in `schemas/`, `indexing_pipeline` in `services/`): no exceptions, but it
  departs from the approved layout and moves files twice if Day 9 decides differently.
- **Recommendation: A.** The layout was approved on Day 7, and Day 9 is the day that rewires
  these dependencies anyway; today should stay mechanical.

### 2. How to lazy-load the heavy libraries
- **A — Function-local imports at each use site** (img2table, camelot, pdfplumber in
  `pdf_table_utils`, pytesseract, cv2): explicit and greppable, each library is paid for only by
  the function that needs it. The trade-off is repeating an import line in each function that uses it (~8 functions).
- **B — PEP 562 `__getattr__` or `importlib.util.LazyLoader`:** one place per module and the
  call sites stay untouched, but it's import magic that the owner's "explicit over implicit"
  rule argues against, and it hides when the cost is paid.
- **Recommendation: A.**

### 3. Where the lazy boundary sits
- **A — At the heavy libraries** (inside `tables/tables.py`, `tables/pdf_tables.py`, `ocr/ocr.py`,
  `ocr/image_preprocessing.py`): everything that merely imports these modules becomes cheap,
  including tests and eval scripts. The trade-off is touching four files.
- **B — At the one edge** (`chunk_builder` importing `pptx_pipeline` lazily, `indexing_pipeline`
  importing `unified_parser` lazily): two edits, but any other importer (tests, Day 10 eval,
  Day 9 services) pays the full cost again.
- **Recommendation: A.**

## Plan

Import rewriting uses a small script in the scratchpad (not committed) with an explicit
old → new module table per checkpoint; it rewrites `from app.<old> import` / `import app.<old>`
lines across `backend/`, `alembic/env.py`, and nothing else. The diff is what you review.

### Checkpoint 1 — `db/` and `ingestion/` (pure moves)
- `db.py` → `db/database.py`; `concept_models.py` → `db/models/concept_map.py`
- `indexing_pipeline.py`, `chunk_builder.py`, `chunking.py`, `models.py`, `text_preprocessing.py`,
  `upload_storage.py` → `ingestion/`; `utils_file.py` → `ingestion/file_hash.py`
- `pdf_utils.py`, `pptx_utils.py`, `pptx_pipeline.py`, `docx_utils.py`, `unified_parser.py` →
  `ingestion/parsers/{pdf,pptx,pptx_pipeline,docx,unified}.py`
- `ocr_utils.py`, `image_preprocessing.py` → `ingestion/ocr/{ocr,image_preprocessing}.py`
- `pdf_table_utils.py`, `table_utils.py` → `ingestion/tables/{pdf_tables,tables}.py`
- New empty `__init__.py`: `db/`, `db/models/`, `ingestion/`, `ingestion/parsers/`, `ingestion/ocr/`, `ingestion/tables/`
- Import rewrite across app, tests, `alembic/env.py`; `conftest.py:128` → `"app.db.database"`
- Check: `py_compile` on touched files, `python -m pytest`, `ruff check .`

### Checkpoint 2 — `retrieval/` and `generation/` (pure moves)
- `embedding_service.py` → `retrieval/embeddings.py`; `index_builder.py`, `vector_store.py`,
  `keyword_index.py`, `retrieval_service.py`, `reranker.py`, `query_decomposer.py`,
  `query_preprocessor.py`, `context_compressor.py` → `retrieval/`;
  `hybrid_retriever.py` → `retrieval/concept_map_retriever.py`;
  `web_search_client.py`, `web_scraper.py` → `retrieval/web/{search_client,scraper}.py`
- `llm_client.py`, `topic_classifier.py`, `concept_extractor.py` → `generation/`
- New `__init__.py`: `retrieval/`, `retrieval/web/`, `generation/`
- Import rewrite; same checks

### Checkpoint 3 — `services/`, `schemas/`, docs (pure moves)
- `chat_guards.py`, `document_service.py`, `session_service.py`, `account_service.py`,
  `concept_map_service.py` → `services/`
- `semantic_cache.py`, `cache.py` → `services/caches/{semantic_cache,query_cache}.py`; `web_cache.py` → `services/caches/web_cache.py`
- New `__init__.py`: `services/caches/`, `schemas/`
- `concept_map_schemas.py` → `schemas/concept_maps.py`; cut `main.py:82-137` into new
  `schemas/{documents,chat,quiz,feedback,auth,users}.py` (bodies copied verbatim) and import them in `main.py`
- `docs/architecture/layout.md`: status → "Days 7–8 applied", the Decision 1 exceptions listed under Rules
- `CLAUDE.md`: Repo Structure and Backend module map rows → new paths (the full rewrite stays Day 10)
- Import rewrite; same checks plus the Docker suite (`.\scripts\dev.ps1 test`) and `uvicorn app.main:app` start
- **→ You commit checkpoints 1–3 as the move commit(s)** before checkpoint 4.

### Checkpoint 4 — lazy imports (own commit)
- `ingestion/tables/tables.py`, `ingestion/tables/pdf_tables.py`, `ingestion/ocr/ocr.py`,
  `ingestion/ocr/image_preprocessing.py`: move img2table / camelot / pdfplumber / pytesseract / cv2
  imports into the functions that use them; `TYPE_CHECKING` imports for any type hints
- `ingestion/ocr/ocr.py`: the `tesseract_cmd` assignment from settings moves into a small
  helper called on first use (it currently runs at import)
- Measure before/after: `app.ingestion.indexing_pipeline` and `app.main` (stubbed key — see Verification) import time, 3 runs each; reload time under `uvicorn --reload`

### Checkpoint 5 — `test_docx_pdf_utils.py` (own commit)
- Anchor paths to `Path(__file__).parent / "samples"`; a missing sample fails the test
- Replace `print` with assertions on known content (table count / a cell value from
  `table_test.pdf`, words from `test_style.docx`, non-empty OCR text from `scan_handwritten.png`),
  determined by running each parser on the sample first
- If a real result shows a broken parser (e.g. camelot needs Ghostscript on Windows), stop and
  report it rather than weakening the assertion

### Checkpoint 6 — wrap-up
- `docs/briefs/day08.md` `## Outcome`; post 9 material line; `docs/learning/ai-concepts.md` check

New dependencies: **none.**

## UI integration
Backend-only — no user-visible change. Every deliverable is a file move, an import change, a
deferred import or a test fix; no endpoint, response field, status or flag is added or changed.
The SSE contract and every route stay byte-for-byte the same (the smoke tests check this). The
first PPTX upload after a restart gets slower (Checkpoint 4); the upload screen already shows a
spinner for the whole request, so no UI change is needed.

## Verification
- **After each move checkpoint:** `python -m pytest` → still **134 passed, 1 xfailed**, with
  `test_api_smoke.py` untouched (`git diff --stat backend/tests/test_api_smoke.py` empty);
  `ruff check .` clean; `grep` finds no `from app.<old flat name>` left.
- **After checkpoint 3:** `.\scripts\dev.ps1 test` (Linux, Python 3.11) green; `cd backend; uvicorn app.main:app` starts and `/docs` lists the same routes.
- **Renames:** after you stage (`git add -A`), `git status` should show every moved file as
  `renamed:`, not `deleted:` + `new file:`.
- **Lazy imports, before/after:** wall-clock import of `app.ingestion.indexing_pipeline` (baseline
  14.2 s warm) and of `app.main` with `GEMINI_API_KEY` set; target < 5 s. Reload time under
  `uvicorn --reload` (Day 4 baseline 13.5–15.1 s). Tests still pass, including
  `test_pptx_utils.py`, which exercises OCR + tables through the lazy path.
- **Test fix:** the six tests now open the samples (temporarily deleting a sample's path in
  the test makes it fail), and the suite count stays 134 + 1 xfail (same tests, real assertions).

## Risks & open questions
- **Module named `docx.py` / `pptx.py` / `pdf.py` under `parsers/`.** Safe with absolute imports
  (see The concept), but `python app/ingestion/parsers/docx.py` would shadow python-docx. Nobody
  runs these files directly; noted in case someone tries.
- **Stale `__pycache__` on the host** can hide a broken import locally; CI's clean checkout and the
  Docker test run are the real check.
- **Checkpoint 4 may not reach < 5 s:** `main.py` still builds `IndexBuilder` (a Gemini embedding
  call), Redis clients and the LLM client at import until Day 9's lifespan. I'll report the number
  measured, not round it to the target.
- **Checkpoint 5 may expose a real failure** (camelot needs Ghostscript for lattice mode;
  Windows host may lack it, CI may differ). If so, that's a finding to record (likely a new
  tracker item), not something to hide with a skip.
- **CLAUDE.md:** I'll update only the Repo Structure and module-map paths today so the file stays
  true; Current Status stays yours to edit.
- **`.claude/hooks/edit_reminders.py`** already matches the new paths (`(.+/)?`); no change.
- **Found in Checkpoint 4 — the < 5 s target is out of reach today, and not because of imports.**
  `-X importtime` on `app.main` after the lazy imports: the ingestion chain fell from 10.2 s to
  5.8 s cumulative, but `app.main`'s own body takes 7.1–9.2 s and `topic_classifier`'s 2.1–2.8 s.
  Timed directly: `IndexBuilder()` 3.43 s (a `genai.Client` plus one embedding call) and
  `LLMClient()` 2.81 s — each `google.genai.Client` construction costs ~3 s on this Windows host,
  and `main.py` builds several at import (embeddings, LLM, topic classifier). **For Day 9:** build
  one `genai.Client` in the lifespan and share it, and use the known embedding dimension instead of
  `IndexBuilder`'s startup embedding call. Both are behaviour changes, so not today.
- **`uvicorn --reload` on the Windows host:** in one measurement the first file change shut the
  worker down but didn't start a new one until a second change. Not investigated (reload trigger,
  not app code); worker start → "Application startup complete" was ~24 s.
- **Uncommitted from before today:** `.claude/skills/ship/SKILL.md` (+4 lines: don't append `2>&1`
  to git/gh). Not part of Day 8 — commit it separately or with today's docs.
