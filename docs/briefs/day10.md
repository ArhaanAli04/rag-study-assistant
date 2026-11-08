# Day 10 — Dead code, dependencies and docs (T3) — release
Date: 2026-11-08 · Phase 3 — Codebase refactor — proper package structure · Items: T3, B3, B5
Branch: feature/day10-cleanup

## Scope
1. **Dead code.** Delete `backend/app/frontend.py` (the timeline says `src/frontend.py`; it moved
   on Day 7), `backend/app/document_delete_service.py`, `frontend/src/components/MessageBubble.js`.
2. **One-off DB scripts.** Delete root `fix_db.py`, `recreate_db.py`, `migrate_user_model.py` and
   `backend/app/{add_concept_tables,add_doc_version,run_migration,update_existing_sessions}.py`.
3. **Eval scripts → `backend/eval/`**, no longer importing `app.main`: `rag_metrics.py`,
   `rag_eval_runner.py`, `sample_eval_data.py`, `manual_eval.py`, `cache_tuner.py` (Decision 2).
4. **Dependencies.** Ask before each removal (Decision 4 table).
   - One UTF-8 requirements file; delete `src/requirements.txt` (Decision 3 on the format).
   - Remove `langchain*`, `qdrant-client`, `streamlit`; keep `langgraph` (Day 33) and `tiktoken`.
     **Not possible as written:** `ragas` requires `langchain`, `langchain-community`,
     `langchain-openai` and `instructor`, and `langgraph` requires `langchain-core`. So
     `langchain*` can only go if `ragas` goes too (Decision 1). `tiktoken` stays either way
     because `tavily-python` requires it.
5. **B3.** Drop the unused `opencv-python` pin, make the contrib build win, and remove the strict
   xfail on `test_table_extraction_on_image`. Touches requirements, so it needs your OK.
6. **B5.** Fix the `preprocess_image` deskew, remove the strict xfail on `test_unified_parser_image`,
   and record the OCR output before and after.
7. **Docs and tooling.** Rewrite CLAUDE.md's repo structure, module map and commands (not Current
   Status), and update the `.claude` hook and skill paths.
8. **Not in the timeline but implied** (Decisions 5–6):
   - `scripts/manual/*`: `layout.md` moves them to `backend/scripts/manual/` on Day 10.
   - `ruff.toml` promises F401 "on Day 10 after the dead-code pass".
9. **Release v0.2.0** (develop → master, tag) and **Verify** that Render and Vercel deploy green.
   Those steps are yours. I'll draft the release notes in the Outcome.

## Current behavior
- **Dead code**
  - `backend/app/frontend.py` is a 13-line Streamlit stub, and the only importer of `streamlit`.
  - `document_delete_service.py` is never imported (grep). It calls
    `vs.mark_delete_by_document_id`.
  - `MessageBubble.js` is never imported: the chat renders `MessageList.js`.
- **One-off scripts**
  - Every script hardcodes a pre-Day 7 path:
    - `fix_db.py` and `migrate_user_model.py` use `src/data/app.db`.
    - `recreate_db.py` uses `sys.path.insert(0,'src')` + `from db import …`, and it **deletes**
      `data/app.db`.
    - `add_concept_tables.py` and `add_doc_version.py` use a CWD-relative `data/app.db`.
  - `run_migration.py` just calls `init_db()`, which every startup already runs.
  - `update_existing_sessions.py` back-fills `topic='General'`.
  - The columns and tables these add are created by `init_db()` / `migrate_database()` in
    `db/database.py`.
  - `.claude/hooks/guard_commands.py:55` has a guard rule just for `recreate_db.py`.
- **Eval scripts**
  - `cache_tuner.py:5`, `manual_eval.py:1`, `rag_eval_runner.py:6` and `rag_metrics.py:16` import
    `index_builder`, `semantic_cache`, `retrieval_service` and `llm_client` from `app.main`. Since
    Day 9 those names don't exist, so all four fail at import.
  - Even before Day 9 the retrieval checks queried an index that is empty in a fresh process
    (I4: FAISS/BM25 live in memory), so they always reported misses. They also assume
    `db.query(User).first()` owns document 1 or 5.
  - `rag_metrics.py` passes `LLMClient` to `ragas.evaluate(llm=…)`, which RAGAS can't use (E1),
    and sets `OPENAI_API_KEY="dummy"`.
  - `.dockerignore` already excludes `backend/eval/`.
- **Requirements**
  - Root `requirements.txt`: 192 lines, UTF-16LE + CRLF. It is a full `pip freeze`: transitive
    packages are pinned next to direct ones, with no marker of which is which.
  - 37 pinned packages are required by no other pinned package (computed from the venv's
    metadata). Among them are leftovers of `src/requirements.txt`'s torch /
    sentence-transformers freeze that nothing requires any more: `scikit-learn`, `sympy`,
    `safetensors`, `tokenizers`. Also unused: `pdf2image`, `oauth` (an unrelated 2009 package;
    OAuth is Authlib), `bcrypt` (passlib is configured for `pbkdf2_sha256` only,
    `core/security.py:14`).
  - `src/requirements.txt` (190 lines) differs from the root file by 12 lines: it has `torch`,
    `transformers`, `sentence-transformers`, `pywin32` and `pypdf 5.9.0`, and lacks `Authlib`,
    `bcrypt`, `dnspython`, `email-validator` and `itsdangerous`. The host venv has `pypdf 5.9.0`
    installed (the root pins 3.17.4), so host and image already differ.
  - `src/` otherwise holds only untracked `__pycache__` and `.ruff_cache` leftovers.
- **B3**
  - Three wheels write into the same `cv2/` package: `opencv-python` (required by nothing),
    `opencv-python-headless` (required by `camelot-py`) and `opencv-contrib-python-headless`
    (required by `img2table`).
  - In the host venv today `cv2.ximgproc` exists but has no `niBlackThreshold`, so
    `img2table` fails.
  - `tables.py:45-47` then catches `Exception`, `print`s, and returns `[]`.
  - Test: `test_pptx_utils.py:106` is a strict xfail and xfails on the host (run today).
- **B5**
  - `image_preprocessing.py:23-34` builds coordinates from every pixel `> 0`, i.e. the white
    background too.
  - It feeds them as (row, col) to `minAreaRect` and applies the pre-4.5 `angle < -45` branch.
  - On OpenCV 4.12 the axis-aligned box returns 90, so the page is rotated −90°, and
    `warpAffine` crops it to the original w×h.
  - Test: `test_docx_pdf_utils.py:78` is a strict xfail and xfails on the host (run today).
- **Hooks and skills that still describe the old layout or encoding**
  - `.claude/hooks/edit_reminders.py:17-20`: the `(src/)?requirements.txt` reminder, which
    says UTF-16.
  - `.claude/skills/pre-commit/SKILL.md:21-23,50,64-68`: `src/**/*.py`, `src/requirements.txt`,
    and "confirm the encoding is still UTF-16LE".
  - `guard_commands.py:55`: the `recreate_db.py` rule.
  - `docs/claude-cheatsheet.md:113` describes that guard.
- **Docs**
  - The Dockerfile HEALTHCHECK comment still says start-period covers "the Gemini embedding call
    IndexBuilder makes at import time". That call was removed on Day 9.
  - `scripts/manual/README.md` still says `$env:PYTHONPATH = "src"`.
- **`scripts/manual/*`**: 11 scripts + README.
  - 10 of them import modules that haven't existed since Day 7/8: `pdf_utils`, `chunking`,
    `hybrid_retriever`, `concept_models`, `index_builder`, … as bare names, plus `sys.path`
    hacks to `scripts/manual/src`.
  - `test_concept_map_api.py` is HTTP-only (`requests` against `localhost:8000`). It overlaps
    `test_api_smoke.py` and Day 9's live checks.
- **Ruff**: rules are `E9, F63, F7, F82`. After the deletions above, `--select F401` finds 22
  unused imports, and ruff's defaults (`E4, E7, E9, F`) find 57.

## Why it matters
- **Dead code:** `document_delete_service.py` looks like the real delete path (I5). Someone
  wiring it in on Day 15 would build on a function that never ran. The Streamlit stub keeps
  `streamlit` and its ~15 transitive packages in the production image.
- **One-off scripts:** `python recreate_db.py` from the repo root deletes `data/app.db`. Today
  that is a stray file, but the scripts hardcode three different database locations, two of
  them wrong since Day 7. A script that "repairs" the wrong file is worse than none. Day 13's
  Alembic baseline replaces them all.
- **Eval scripts:** Day 11 builds `backend/eval/retrieval/` and needs `backend/eval/` to be a
  package that runs as `python -m eval.…` from `backend/`. The current scripts can't even be
  imported, so anyone (or Claude) trying them gets an `ImportError`.
- **Requirements:**
  - A full freeze with no list of direct dependencies is why the torch-era leftovers survived:
    removing a package means hand-computing its orphans.
  - UTF-16 makes `git diff` show the file as binary and breaks most tools (Dependabot, `grep`,
    the GitHub dependency graph).
  - Two lists already disagree on `pypdf` by a major version.
- **B3:** a PPTX whose slides contain table images (a common lecture-slide pattern) loses those
  tables silently, in production too. Day 5 confirmed this in the image Render builds.
- **B5:** the day image or handwritten-note upload is enabled, every scan comes back as `''`
  with no error.
- **Hooks and skills:** `/pre-commit` would flag a correct UTF-8 requirements file as broken,
  and it looks for backend code under `src/`, so its checks miss everything in `backend/`.
- **Release:** `develop` holds Days 4–9. Production still runs v0.1.1, so Day 9's three
  user-visible changes and the Day 7 layout reach users only with this release.

## The concept

### 1. Direct dependencies vs a lock file
A Python project has two different lists:
- **Direct dependencies** are what *your code* imports: `fastapi`, `google-genai`, `faiss-cpu`.
  You choose them, and each line needs a reason.
- **The lock** is the full resolved set, transitive packages included, pinned exactly so
  every install gives the same environment.

A `pip freeze` is only a lock: it can't tell you why `sympy` is there. When `torch` was removed
from the root file, its dependencies (`sympy`, `safetensors`, `tokenizers`, `scikit-learn`)
stayed pinned forever, because nothing marked them as "only for torch".

Production setups keep both lists:
- `requirements.in` → `requirements.txt` (pip-tools)
- `pyproject.toml` → `uv.lock` / `poetry.lock`

Regenerate the lock from the direct list; never hand-edit it. Pitfalls:
- **Platform-specific locks.** A freeze made on Windows can pin `pywin32`, which then fails to
  install on Linux. That is exactly what `src/requirements.txt` contains. Lock on the platform
  you deploy to.
- **Unconstrained re-resolution.** Regenerating without the old pins as constraints silently
  upgrades every transitive package. A cleanup turns into an upgrade.
- **Test tools in the runtime image.** `pytest` is pinned in the image because
  `scripts/dev.ps1 test` runs the suite inside the container. That is a conscious trade-off
  (dev/runtime split later), not an accident.

### 2. Why "remove X" is a graph problem
Removing a package is safe only if nothing that stays requires it. Here:
- `ragas` → `langchain`, `langchain-community`, `langchain-openai`, `instructor`, `datasets`,
  `openai`
- `langgraph` → `langchain-core` → `langsmith`
- `tavily-python` → `tiktoken`

pip will happily install a requirements file whose pins don't satisfy each other's metadata
only if you skip `pip check`. The usual result is a missing package at import, not at install.
Always finish a dependency change with `pip check`, the test suite, and an image build.

### 3. Wheel clashes: several distributions, one import name
`opencv-python`, `opencv-python-headless`, `opencv-contrib-python` and
`opencv-contrib-python-headless` are four *distributions* that all install the same *import
package*, `cv2/`. pip tracks files per distribution and doesn't detect the overlap, so the last
one written wins file by file. Uninstalling one deletes files the others need.

You can't tell pip "headless is satisfied by contrib-headless": there's no `Provides`
mechanism. The standard workaround is to install everything, then re-install the one build you
want *last* with `--force-reinstall --no-deps`, and to assert on a feature only that build has
(`cv2.ximgproc.niBlackThreshold`).

The bigger lesson is about the failure mode. B3 survived because:
- the code caught every exception and returned `[]`, and
- the test only asserted `isinstance(tables, list)`.

"Returns empty on error" plus "test checks the type" means the feature can be dead with CI
green.

### 4. Deskewing for OCR
Tesseract handles small skews poorly, so scans are rotated upright first. The classic approach:
- binarize so **text** pixels are foreground (inverted Otsu: dark ink → 255, paper → 0);
- fit the minimum-area rectangle around the foreground points;
- read its angle and rotate by the opposite.

Three pitfalls, all present in `preprocess_image`:
- **Foreground selection.** `np_img > 0` selects the paper, not the ink, so the rectangle is
  the whole page.
- **Angle convention.** OpenCV ≥ 4.5 returns angles in (0, 90]. Older versions returned
  [−90, 0). Code written for one silently does the wrong thing on the other: a straight page
  reports 90 and gets turned sideways. Normalize to a skew in (−45, 45].
- **Point order.** `minAreaRect` expects (x, y). `np.where` returns (row, col), i.e. (y, x),
  which mirrors the angle's sign.

Guard rails: skip the rotation when there is too little foreground to estimate from, and cap
the correction (real scans are rarely skewed > 45°).

### 5. Dead code and one-off scripts
Every file in the repo is a claim that it matters. Dead code costs:
- readers' attention;
- dependencies (`streamlit` exists only for a stub);
- wrong guidance (`document_delete_service.py` "deletes" by flagging a method that was never
  called).

Git history is the archive, so deletion is reversible. Migration scripts are a special case.
Once a schema tool (Alembic, Day 13) owns the schema, ad-hoc `ALTER TABLE` scripts become
hazards: they encode one machine's path and one moment's schema.

### 6. Release: integration branch → production
`develop` has collected six days of work. The release PR into `master` is a review checkpoint
for everything users will see. It is merged with a merge commit (so `master`'s first-parent
history is one commit per release), and the tag marks exactly what was deployed. Release notes
list **user-visible** changes, not commits.

Render and Vercel deploy `master` on push, so the merge *is* the deploy. Verifying both
deploys is the last step of the day, not an afterthought. CD gating comes on Days 21–22.

## Decisions

### 1. RAGAS and the `langchain*` removal
- **A — Keep `ragas` until Day 12:** today removes `streamlit` and `qdrant-client` (+ orphans).
  `langchain*` (except `langchain-core`, which `langgraph` needs) goes out with `ragas` on Day 12
  if the Gemini judge is chosen. The trade-off is that the image keeps langchain-community and
  friends for two more days.
- **B — Take Day 12's RAGAS decision today:** drop `ragas`, `datasets`, `langchain`,
  `langchain-community`, `langchain-openai`, `langchain-classic`, `langchain-text-splitters` and
  `openai` now, and remove the RAGAS class from `rag_metrics.py`. The trade-off is that it
  pre-empts a decision the timeline deliberately left for Day 12, together with the judge
  calibration.
- **Recommendation: A.** The timeline makes RAGAS-vs-judge an explicit Day 12 owner decision.
  Removing langchain today would force it, and the cost of waiting is only image size.

### 2. Eval scripts
- **A — Move all five to `backend/eval/` and rewire them** (the timeline):
  - `backend/eval/__init__.py`;
  - each script builds what it needs with `build_services()` (or `LLMClient(build_gemini_client())`);
  - run as `python -m eval.<name>` from `backend/`;
  - module-level code (`manual_eval.py`) goes under `main()`.
  The trade-off is a few lines of polish on scripts Days 11–12 replace, and the retrieval ones
  still find nothing until something is indexed in the same process (I4).
- **B — Delete them:** Days 11–12 build `backend/eval/` from scratch anyway, and git history
  keeps the old code. The trade-off is that it departs from the timeline and the layout row, and
  `cache_tuner.py` (CO5 threshold tuning, Day 32) is lost from view.
- **Recommendation: A.** It's cheap, matches the plan, and makes `backend/eval/` exist as a
  package before Day 11. Each script gets a one-line docstring note: "requires documents indexed
  in this process (I4)".

### 3. Requirements file format
- **A — One flat UTF-8 lock, hand-pruned:** convert to UTF-8 and delete the approved lines
  plus their orphans by hand. Only one file, but the next removal needs the same graph analysis
  again.
- **B — `requirements.in` (direct deps, one reason per line) + generated `requirements.txt`
  (UTF-8 lock):**
  - the lock is regenerated in `python:3.11-slim` (the image's platform) with
    `pip install -r requirements.in -c <old lock>` + `pip freeze`, so versions don't drift;
  - the exact command goes in the lock's header comment;
  - no new tool (pip-tools / uv not needed).
  The trade-off is two files, though only one is hand-edited, and the Dockerfile and CI keep
  installing `requirements.txt`.
- **Recommendation: B.** It answers "why is this here?" forever and makes future removals a
  one-line edit plus a regeneration. "One requirements file" in the timeline means no competing
  second list, which `src/requirements.txt` deletion delivers.

### 4. Which packages go (you asked to approve each removal)
Removing a row also drops its orphans: transitive packages that nothing kept requires. I'll list
the exact orphans removed in the Outcome.

| Package | Why it can go | Recommend |
|---|---|---|
| `streamlit` | only `frontend.py` (deleted today) | remove |
| `qdrant-client` | never imported; pgvector chosen 2026-11-04 | remove |
| `opencv-python` | required by nothing; one of B3's three wheels | remove (B3) |
| `scikit-learn`, `sympy`, `safetensors`, `tokenizers` | torch / sentence-transformers leftovers, required by nothing | remove |
| `pdf2image` | never imported | remove |
| `oauth` | never imported (unrelated 2009 lib; OAuth is Authlib) | remove |
| `bcrypt` | passlib uses `pbkdf2_sha256` only (`core/security.py:14`) | remove |
| `langchain*`, `datasets`, `openai` | required by `ragas` | Decision 1 |
| `instructor` | required by `ragas`; planned for S1 | keep |
| `langgraph`, `langchain-core`, `langsmith` | A1 (Day 33); `langsmith` also O1 | keep |
| `tiktoken` | required by `tavily-python`; C1 (Day 31) | keep |
| `pytest` | `dev.ps1 test` runs the suite in the image | keep |
| `httptools`, `watchfiles`, `h2` | `uvicorn[standard]` speedups / reload; `h2` is httpx HTTP/2 (check: it may orphan with qdrant) | keep unless orphaned |

### 5. `scripts/manual/*` (layout row: move to `backend/scripts/manual/`)
- **A — Delete all 11 + README:**
  - 10 import module names that haven't existed since Day 7–8;
  - their subjects (chunking, PPTX, concept extractor, retrieval) are covered by the offline
    suite;
  - `test_concept_map_api.py` is covered by `test_api_smoke.py` and Day 9's live checks.
  The trade-off is losing ad-hoc live-service probes, which nobody has run since Day 5.
- **B — Move to `backend/scripts/manual/` and port the imports:** follows the layout row. The
  trade-off is porting ~1000 lines of print-only scripts that duplicate tests.
- **Recommendation: A.** I'll update the layout row to "deleted".

### 6. Ruff tightening (`ruff.toml` promises it for Day 10)
- **A — Add `F401` only:** 22 unused imports, removed by hand-checked `--fix`. Side-effect
  imports, e.g. model modules imported to register tables with `Base`, are kept with `# noqa:
  F401` and a reason. This keeps the release diff mechanical.
- **B — ruff defaults (`E4, E7, E9, F`):** 57 findings, including 14 `E402` and a bare
  `except` (E722). That's real cleanup in parsers and caches, so it means behaviour-adjacent
  edits on release day.
- **Recommendation: A.** Leave a comment in `ruff.toml` that the defaults come with the next
  refactor of those modules. That isn't scheduled yet: say if you want it on a specific day.

### 7. B3 mechanism
- **A — Force-reinstall the contrib build last:** keep pins for `opencv-python-headless`
  (camelot's metadata needs it) and `opencv-contrib-python-headless`, and after
  `pip install -r requirements.txt` run `pip install --no-deps --force-reinstall
  opencv-contrib-python-headless==4.12.0.88`. This goes in the Dockerfile builder stage, the CI
  install step, and the documented venv setup. The trade-off is that any later `pip install`
  that reinstalls headless re-breaks it, but the (no longer xfail) test catches that.
- **B — Uninstall headless after install:** `cv2` is pure contrib. The trade-off is that
  `pip check` then reports camelot's requirement as missing forever, and `pip install` puts
  headless back.
- **Recommendation: A**, plus one assertion in the test that
  `cv2.ximgproc.niBlackThreshold` exists, so the failure message names the cause.

## Plan
Each checkpoint ends with `python -m py_compile` on changed `.py` files, `ruff check .` and
`python -m pytest`. Baseline today: 157 passed + 2 xfailed. File deletions use `Remove-Item` (no
git commands); you stage them.

**Checkpoint 1 — dead code, one-off scripts, manual scripts (deletions only, ~25 files)**
- delete `backend/app/frontend.py`, `backend/app/document_delete_service.py`,
  `frontend/src/components/MessageBubble.js`
- delete `fix_db.py`, `recreate_db.py`, `migrate_user_model.py`, `backend/app/add_concept_tables.py`,
  `backend/app/add_doc_version.py`, `backend/app/run_migration.py`, `backend/app/update_existing_sessions.py`
- delete `scripts/manual/` (11 scripts + README), if Decision 5 = A
- edit `.claude/hooks/guard_commands.py`: drop the `recreate_db.py` rule (its target is gone)
- checks: pytest, ruff, `cd frontend; npm run build`

**Checkpoint 2 — eval package (7 files)**
- add `backend/eval/__init__.py`
- move + rewire `rag_metrics.py`, `rag_eval_runner.py`, `sample_eval_data.py`, `manual_eval.py`,
  `cache_tuner.py` → `backend/eval/` (new file written, old removed; content kept ≥ 50 % similar
  so git sees renames). Their imports become `from eval.…`, and the `app.main` imports become
  `build_services()`.
- check: `python -c "import eval.rag_eval_runner, eval.manual_eval, eval.cache_tuner"` from
  `backend/` with the real `.env` (import only, no network: `build_services()` runs in `main()`,
  not at import)

**Checkpoint 3 — B5 (3 files)**
- before: run `DocumentParser("scan_handwritten.png").parse()` and save the OCR text (word count
  + first 200 chars)
- edit `backend/app/ingestion/ocr/image_preprocessing.py`: inverted-Otsu text mask; (x, y)
  points; normalize the angle to (−45, 45]; skip below a minimum foreground; same output size;
  type hints on the function I touch
- add `backend/tests/test_image_preprocessing.py`: a synthetic page rotated by +7° and −7°
  deskews to within 1°, and an upright page is left unrotated (catches the 90° bug)
- edit `backend/tests/test_docx_pdf_utils.py`: remove the B5 xfail
- after: the same OCR run; numbers in the Outcome

**Checkpoint 4 — requirements + B3 (≤ 8 files, plus the venv)**
- add `requirements.in` (approved direct deps, grouped and commented)
- regenerate `requirements.txt` as UTF-8 in `python:3.11-slim`, constrained by the current
  lock; `pip check` in the container
- delete `src/requirements.txt` (and, with your OK, the untracked `src/` cache leftovers)
- edit `Dockerfile` (builder: contrib force-reinstall; fix the stale HEALTHCHECK comment),
  `.github/workflows/ci.yml` (same force-reinstall line)
- edit `backend/tests/test_pptx_utils.py`: remove the B3 xfail, add the `niBlackThreshold`
  assertion
- **host venv (needs your OK, it changes your environment):** `pip uninstall -y opencv-python`
  then the contrib force-reinstall; optionally `pip install -r requirements.txt` so the venv
  matches the lock (would downgrade `pypdf` 5.9 → 3.17.4 to match the image)
- checks: host pytest; `.\scripts\dev.ps1 test` (rebuilt image); `docker build .`; image size
  before/after

**Checkpoint 5 — ruff F401 (≈ 20 files, mechanical)**
- `ruff.toml`: `select` gains `F401`; comment updated
- remove the unused imports, each reviewed for side effects
- checks: ruff, pytest

**Checkpoint 6 — docs, hooks, outcome**
- `CLAUDE.md` (not Current Status): repo structure, module map (eval row, dead-code row gone,
  ad-hoc scripts row gone), Tech Stack's "installed but never imported", requirements convention
  (UTF-8, `.in` + lock, the B3 install line), Key Commands (eval, venv setup), Known Issues
  (B3 / B5 / T3), Open Decisions (dependencies and dead code resolved)
- `docs/architecture/layout.md`: status line, eval / scripts / dead-code rows
- `docs/improvements.md`: status lines on T3, B3, B5
- `.claude/hooks/edit_reminders.py` (requirements reminder), `.claude/skills/pre-commit/SKILL.md`
  (paths, UTF-8, `.in`/lock check), `docs/claude-cheatsheet.md:113`
- brief `## Outcome` with the release-notes draft (Days 4–10 user-visible changes); post 9
  line; learning notes

New dependencies: **none.** Removals: Decision 4 table, each on your approval.

## UI integration
- **Dead code, one-off scripts, manual scripts, eval move, requirements, ruff, docs, hooks:**
  backend-only or tooling, no user-visible change. No endpoint, field or flag changes.
- **`MessageBubble.js` deleted:** no importer in `frontend/src` (grep), so the chat UI is
  unchanged. `npm run build` + Jest prove it.
- **B3:** user-visible in effect, with no UI change. Tables in PPTX slide images are now
  extracted and indexed, so chat answers can cite them through the existing sources rendering in
  `ChatWindow.js` / `MessageList.js`. No new field or state.
- **B5:** not reachable from any user path (`/upload` rejects images). Backend-only until image
  upload exists.

## Verification
- `python -m pytest`: 157 passed + 2 xfailed → **160+ passed, 0 xfailed** (2 former xfails + the
  new deskew tests).
- `.\scripts\dev.ps1 test` on the rebuilt image (the Linux / 3.11 / Render platform), which is
  the real B3 proof since Render builds the same image.
- In the image: `python -c "import cv2; assert hasattr(cv2.ximgproc, 'niBlackThreshold')"` and
  `pip check`.
- `docker build .`: image size before/after; `docker compose up` and `/health`.
- `ruff check .` clean with F401; `cd frontend; npm test -- --watchAll=false; npm run build`.
- B5 before/after: OCR word count and a text excerpt for `scan_handwritten.png`, host and container.
- Eval scripts import cleanly from `backend/` (`python -m eval.<name> --help` isn't available,
  so I'll check imports only).
- CI on the PR (all three jobs; `backend` now installs the new lock and the contrib line).
- After your release: Render deploy log green + `/health`; Vercel production deploy green + login
  smoke test.

## Risks & open questions
- **Lock regeneration may move versions.** The constraint file keeps every surviving package at
  its current pin, but a package whose pin conflicts after a removal gets re-resolved. I'll diff
  old vs new lock and list every version change. If any surviving package changes, I'll stop and
  ask.
- **Platform:** the lock is made on Linux. Windows-only dependencies (`colorama` for `tqdm` /
  `click` / `pytest`) then install unpinned on the host. That's harmless, but the venv is no
  longer bit-for-bit the lock.
- **B3 on the host:** the venv has all three OpenCV wheels. Without the venv step in
  Checkpoint 4, host pytest keeps failing `test_table_extraction_on_image` once the xfail is
  gone. Do I have your OK to change the venv?
- **B3 and camelot:** camelot imports `cv2` too. The contrib build is a superset of headless, so
  it should be fine, but `test_unified_parser_pdf` (camelot tables) is the check.
- **F401 auto-fix** can remove side-effect imports: model registration, `__init__` re-exports. I
  review each removal rather than trusting `--fix`.
- **Deleted one-off scripts:** anyone with a pre-Day 7 checkout who still needs them has
  history. CLAUDE.md's Blockers line (move `src\data` by hand) still applies and stays.
- **Release scope:** v0.2.0 ships Days 4–10. Day 9's three user-visible changes (POST `/chat`
  removed, B2 cap 30, merged safety list) plus B3 go in the notes. Should I also re-check the
  Day 3 checklist item "DEL `semantic_cache_entries` on Render's Redis DB 0 and 1", or was it
  done?
- **Recorded, not fixing:** `preprocess_image` names its output with
  `.replace('.png', …)`, so a `.jpeg`/`.tif` input overwrites itself. `tables.py` still swallows
  every exception with `print`. `README.md` drift is Day 61's rewrite.
