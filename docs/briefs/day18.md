# Day 18 — Projects data model, API and project-scoped retrieval
Date: 2026-11-17 · Phase 6 — Projects · Items: none (no tracker ID; timeline feature)
Branch: feature/day18-projects-core

## Scope

1. **Alembic revision:** `projects` table (id, user_id FK, name, description, instructions, created_at,
   archived_at); nullable `project_id` FK on `documents` and `sessions`. NULL = "no project", so existing
   rows need no backfill.
2. **API:** `POST/GET /projects`, `GET/PATCH/DELETE /projects/{id}` (the GET returns files, chats and
   counts). Upload and session creation accept `project_id`. Documents and chats can be moved between
   projects.
3. **Ownership and deletion:** every project route checks ownership, and another user's project id
   returns 404. Deleting a project asks what to do with its documents (delete them, or move them to "no
   project"). Account deletion (B1) removes projects.
4. **Project-scoped retrieval:** the project filter joins `user_id` in the pgvector and full-text WHERE
   clauses. A project chat searches only its project's documents. A chat outside any project searches
   either the unassigned documents or all documents (**Decision 1**).
5. **Project instructions:** user-written text sent in the final user turn as delimited data, never in
   the system instruction (CO4 / G5 rule).
6. **UI:** the timeline asks for a project selector on the upload and a project column / filter in the
   document list. **This brief adds more** (Decision 6): every endpoint today gets a control, per the
   owner's rule.
7. **Test:** two projects of one user retrieve disjointly; another user's project id is refused.
8. **Verify:** a chat in project A never cites a document from project B.

**Pulled forward from Day 20 (required, not optional):** the scope has to be part of the L1 retrieval
cache key and the semantic-cache filter today. Today both caches key on `(user, doc_version, …)`
only. A question asked in project A and then the same question in project B would replay A's ranking
(L1) or A's whole answer (semantic cache), and deliverable 8 would fail. Day 20 keeps the other cache
work (concept maps / quizzes per project, the efficiency follow-up).

## Current behavior

- **No project concept.** `Document` (`backend/app/db/models/document.py:11-24`) and `Session`
  (`db/models/chat_session.py:11-21`) belong only to a user.
- **Versioning is keyed on `(user_id, file_name)`:** `documents_repo.latest_version` /
  `list_versions` (`db/repositories/documents.py:47-63`). `register_upload` uses them
  (`services/document_service.py:60-126`), and so does `delete_document`, which removes every version
  of a file name (`document_service.py:136-157`).
- **Search filters by user only.** `_VECTOR_SEARCH` / `_KEYWORD_SEARCH`
  (`db/repositories/chunks.py:112-149`) filter on `c.user_id = :user_id AND d.is_active`. Both
  already `JOIN documents d`, so a `d.project_id` condition costs no new join.
  `PgChunkSearch.search` (`retrieval/pg_chunk_search.py:55-69`) takes only `user_id`.
- **L1 cache key:** `(user_id, query, doc_version, include_web)` (`retrieval/retrieval_service.py:84-99`).
- **Semantic cache:** filters entries on `user_id`, `doc_version` and `mode`
  (`services/caches/semantic_cache.py:82-85`).
- **Sessions are created implicitly.** `GET /chat/stream` with `session_id=0` creates one in
  `get_or_create_session` (`services/session_service.py:18-39`), inside the turn's first transaction
  (`chat_pipeline.py:133-152`).
- **Prompt:** `LLMClient.build_prompt` (`generation/llm_client.py:99-156`) builds the system
  instruction from grounding + mode only. The context and the question go in `current_user_text`.
  Nothing user-written except the question reaches the prompt.
- **Account deletion** (`services/account_service.py:48-112`) deletes children explicitly, then the
  user. `ON DELETE CASCADE` on every `user_id` is the safety net.
- **Frontend:**
  - `DocumentsPage.js` uploads a bare `file` form field (`:47-76`).
  - `DocumentList.js` renders cards with no grouping.
  - `ChatWindow.js:126-131` builds the stream URL with no scope.
  - Its header (`:239-262`) shows only the title.

## Why it matters

- **Retrieval leaks across courses.** A student with "DL Unit 5" and "BDA" notes asks "explain
  normalization". The answer mixes batch normalization (DL) with database normalization (BDA), and the
  BDA chunks often win on keyword overlap. Today nothing can stop that.
- **Caches cross scopes.** Without the scope in the keys, "What is normalization?" asked in BDA after
  the same question in DL replays the DL answer and DL citations. The semantic cache matches at
  cosine ≥ 0.92, so even near-identical wordings replay.
- **File names collide.** Students reuse names ("Unit 1.pdf" in every course). Under today's
  `(user_id, file_name)` versioning, uploading BDA's "Unit 1.pdf" would deactivate DL's "Unit 1.pdf" as
  an older "version" and delete its chunks.
- **Instructions are untrusted.** An instruction like "ignore the context and answer from memory", if
  placed in the system instruction, would outrank the grounding rules. Pasted text (a syllabus copied
  from a web page) can carry injected instructions.
- **Unchecked ids leak data.** A route that loads `Project` by id without `user_id` lets user 2 read
  user 1's instructions and file list (an IDOR, the class behind G6 / G7).

## The concept

**Hierarchical tenancy.** Multi-tenant apps nest scopes: an account (tenant) holds workspaces (here:
projects), which hold resources. Every query is filtered by the full path (`user_id` and
`project_id`). A child id is never trusted on its own, because ids are guessable integers. Production
systems resolve the scope once, at the edge ("load the project WHERE id = ? AND user_id = ?, else 404"),
then pass the resolved scope object down. Lower layers receive a value they cannot widen, not a raw
id. Answering 404 instead of 403 for another tenant's id is deliberate: a 403 confirms the id exists.

**Filtering inside vector search (pre- vs post-filtering).** There are two ways to restrict an ANN
search to a subset:
- **Post-filtering:** search top-k globally, then drop rows outside the scope. It returns fewer than k
  results, or none, when the scope is a small share of the data.
- **Pre-filtering:** put the condition in the same query.

pgvector's HNSW index is a hybrid of the two. With a WHERE clause, the index walks `hnsw.ef_search`
(default 40) candidates and filters them. A selective filter can therefore still starve the result.
pgvector 0.8 (production runs 0.8.2) adds iterative index scans (`SET hnsw.iterative_scan =
relaxed_order`), which keep walking until k rows pass the filter. Today the planner picks an exact scan
at our sizes (Day 15), so results are exact. This is the trap to remember when the corpus grows: a
project filter makes the filter more selective than "this user" alone. The usual production answers:
- iterative scans,
- partial indexes per large tenant,
- partitioning by tenant.

**Every input that changes the output belongs in the cache key.** A cache is correct only if its key
covers every input that changes the result. Day 17 found this for `include_web`, and today it is the
scope. Two ways to get there:
- **Key the cache by scope:** different keys, so no cross-talk by construction.
- **Version it:** bump a counter when the scope's content changes. `doc_version` does this for
  documents.

Instructions change the answer but not the retrieval. So they belong in the semantic cache's key
(which caches answers), not in the L1 key (which caches rankings). The common pitfall is a cache keyed
on "what the user typed" while hidden inputs (scope, model, instructions, mode) vary.

**User-written instructions are data, not policy.** LLM APIs give the system instruction more weight
than user turns. Platforms with project instructions (ChatGPT Projects, Claude Projects) still treat
them as lower-privilege than their own policy. This app's rule (CLAUDE.md, G5) is that anything a user
or a document can write goes in the final user turn, fenced with delimiters, and is labelled as
preferences that cannot override the rules above it. Two more reasons:
- **The prompt cache (CO4):** a stable system-instruction prefix stays cacheable, while
  per-project text varies.
- **Injection:** a fence plus a label doesn't make injection impossible. It makes the model's job
  unambiguous and keeps the policy text out of reach.

**Nullable FK vs a default project.** Representing "no project" as NULL needs:
- no backfill,
- no extra row per user,
- no special id to protect from deletion.

The cost is `IS NULL` / `IS NOT DISTINCT FROM` in every lookup, and SQL's `NULL = NULL` is not true.
The alternative, a real "Inbox" project per user, makes every query uniform but needs a data migration
and a rule that it can't be deleted. Delete semantics are part of the model:
- `ON DELETE SET NULL` on `documents.project_id` / `sessions.project_id` is the safety net.
- The service still asks the user (delete or unassign) and does it explicitly. This is the same
  "explicit first, cascade as backstop" pattern as B1.

## Decisions

### 1. What a chat outside any project searches
- **A — Unassigned documents only:** `project_id IS NULL` documents. Projects are fully isolated, as in
  Claude / ChatGPT Projects, and moving a file into a project removes it from general chats. A student
  who has moved everything into projects gets no document context in a general chat.
- **B — All the user's documents:** the general chat becomes "search everything" and a project chat
  narrows it. Nothing disappears on a move. The cost is that project files (and only their files, not
  their instructions) leak into general chats, so the scope rule is "projects narrow, general widens".
- **Recommendation: A.** The timeline leans this way. "Move to project" then has one clear meaning,
  and existing users see no change, because all of today's documents are unassigned. The chat header
  says what it searches ("No project: searching unassigned documents"), so it isn't a silent surprise.

### 2. Document identity across projects (same file name in two projects)
- **A — Version key `(user_id, project_id, file_name)`:** "Unit 1.pdf" in DL and in BDA are separate
  documents with separate versions. Uploading identical bytes into a second project creates a second
  document, but CO3 reuses the stored vectors by content hash (0 embedding calls).
- **B — Keep `(user_id, file_name)` across projects:** a file name is one document. Uploading it into
  another project moves it, or is refused. This is simpler, but courses reuse names ("Unit 1",
  "Lecture 3") and this would silently treat one course's file as a new version of another's.
- **Recommendation: A.** It is the only option that keeps two courses' "Unit 1.pdf" apart. Moving a
  document into a project that already has an active file of that name returns 409 ("rename or delete
  the other one first").

### 3. Where the project filter lives in search
- **A — On `documents.project_id`, through the existing join:** chunks stay as they are. Moving a
  document is one UPDATE of its version rows, with no chunk rewrite. The filter is one more condition
  on a table already joined.
- **B — Denormalize `project_id` onto `document_chunks`:** the filter could later get its own
  composite / partial index on the chunks table. Every move must then update every chunk of every
  version in the same transaction, and two copies of the truth can drift.
- **Recommendation: A.** The searches already `JOIN documents`. An index on
  `documents(user_id, project_id)` covers the lookup, and at today's sizes the planner uses an exact
  scan anyway. Revisit B together with HNSW iterative scans if a project's share of a large corpus gets
  small (Risks).

### 4. Deleting a project: its chats
- **A — Chats move to "no project":** history is kept, and the chat then searches unassigned
  documents. The documents choice (delete / unassign) is a required query parameter, as the timeline
  says.
- **B — Chats are deleted with the project:** nothing is left over. It loses study history silently,
  and the timeline only asks about documents.
- **Recommendation: A.** Deleting chats should be the user's explicit act in the sessions sidebar. The
  confirm dialog states "its N chats move to No project".

### 5. Cache scope today
- **A — Scope in the cache keys now (pulled forward from Day 20):**
  - L1 key gains the scope;
  - semantic-cache entries gain a scope field: `all` / `none` / `p:<id>`, plus a hash of the project's
    instructions, so editing them stops replaying old answers;
  - lookups require an exact match;
  - old entries have no scope field, so they miss once.
- **B — Leave the keys for Day 20 and bypass the semantic cache for project chats today:** less code
  today. The L1 cache would still cross scopes, unless it were bypassed too, and that is half of A
  anyway.
- **Recommendation: A.** Without it, Verify fails. It's ~20 lines and two tests. Day 20 keeps the
  concept-map / quiz scope and the per-project `doc_version` efficiency note.

### 6. How much UI ships today
- **A — A minimal control for every new endpoint today:**
  - a "Projects" panel on the Documents page (create, rename, edit instructions, archive, delete
    with the documents choice, file / chat counts from `GET /projects`);
  - project selector on upload, project filter + badge + "Move to…" on document cards;
  - a project picker in the chat header for new chats (a label for existing ones);
  - "Move to project" in the session sidebar's menu.

  Day 19 then turns these into the dedicated `/projects` pages.
- **B — Only the timeline's UI bullet (upload selector + filter):** the PATCH / DELETE / move / chat
  endpoints wait for Day 19. Less work today, but it breaks the owner's rule "no backend work without
  its UI, never UI later".
- **Recommendation: A.** The rule is explicit. The cost is that part of today's panel gets replaced on
  Day 19, which the rule accepts ("the UI overhaul restyles existing screens").

**Approved 2026-11-19:** 1A, 2A, 3A, 4A, 5A, 6A. Archived projects' existing chats stay usable;
archive only blocks new uploads and new chats. Owner's additions:
1. Security tests: another user's project id → 404 on every route that takes one (open, edit,
   archive, delete, upload into it, move a document into it, move a chat into it, start a chat in
   it). Plus: a chat in A never cites B's document, and after moving that document into A, it can.
2. All new routes are plain `def` (B14 guard test).
3. A test that the prompt is byte-for-byte unchanged without instructions and that instructions
   only appear in the final user turn. After Checkpoint 3, the E4 baseline from the cache (0 API
   calls) must stay Hit@5 50/55, MRR@5 0.808.
4. Live check: venv backend, eval key, `WEB_SEARCH_ENABLED=false`, local `rag`, throwaway accounts
   deleted afterwards; in the browser: two projects with one demo PDF each, a chat in A cites only
   A's PDF; move the PDF to B and A's chat no longer cites it; a general chat sees neither.
5. Stop after each checkpoint for `/pre-commit` and `/ship commit`.

Not decisions (sensible defaults, stated so they can be overridden):
- **Limits:** name 1–80 characters, unique per user (409 on a duplicate, archived projects
  included). Description ≤ 500 characters. Instructions ≤ 4,000 characters.
- **Archive:** `PATCH {archived: true|false}` sets or clears `archived_at`. An archived project is
  hidden from pickers, and refuses new uploads and new chats (409). Its existing chats keep working.
- **Session scope is fixed at creation:** `project_id` on `/chat/stream` is read only when a new
  session is created. An existing session always uses its own `project_id`, so a stale UI can't
  re-scope a chat mid-way. Moving a chat is the explicit `PATCH`.
- **`POST /search` stays scope "all"** (no UI caller sends a project), and so do concept maps until
  Day 20.

## Plan

### Checkpoint 1: data model + migration (≈ 8 file operations)
- `backend/app/db/models/project.py` (new): `Project` model, `uq_projects_user_id_name`,
  `user_id` FK CASCADE.
- `backend/app/db/models/document.py`, `chat_session.py`: nullable `project_id` FK → `projects.id`
  `ON DELETE SET NULL`, plus an index (`ix_documents_user_id_project_id`, `ix_sessions_project_id`).
- `backend/app/db/models/__init__.py`: import `Project`.
- `alembic/versions/<rev>_projects.py`: autogenerated against the local Postgres, then reviewed by
  hand. Run `alembic upgrade head` + `alembic check`, and downgrade / upgrade once on local `rag`.
- `backend/app/db/scope.py` (new):
  - `DocumentScope` (frozen dataclass: `all` / `unassigned` / `project(id)`);
  - its SQL condition, built only from fixed strings;
  - its cache key.
- `backend/app/db/repositories/projects.py` (new): `get_owned`, `list_with_counts` (one grouped
  query), `create`, `name_taken`.

### Checkpoint 2: projects API, moves, upload / session scope, account deletion (≈ 10)
- `backend/app/schemas/projects.py` (new): create / update / response models with the limits above.
- `backend/app/services/project_service.py` (new):
  - `delete_project(documents="delete"|"unassign")`: rows in one commit, then stored files, then a
    `doc_version` bump;
  - `move_document`: every version of the file name, 409 on a name clash, `doc_version` bump;
  - `move_session`.
- `backend/app/api/routes/projects.py` (new): the five routes, plain `def` (B14 guard), 404 for
  anything not owned. `main.py`: include the router.
- `backend/app/db/repositories/documents.py`: `project_id`-aware `latest_version` /
  `list_versions` (`IS NOT DISTINCT FROM`), `list_active` returns the project name.
- `backend/app/services/document_service.py`: `register_upload(project_id)`, version key
  `(user, project, name)`. `delete_document` deletes the versions in the same project only.
- `backend/app/api/routes/documents.py`:
  - `POST /upload` takes an optional `project_id` form field (404 / 409 archived);
  - `PATCH /documents/{id}` `{project_id}` (move);
  - `GET /documents` adds `project_id`, `project_name`.
- `backend/app/api/routes/sessions.py` + `db/repositories/sessions.py`: `GET /sessions` adds
  `project_id`, `project_name`; `PATCH /sessions/{id}/project`.
- `backend/app/services/account_service.py`: delete projects explicitly (counted in the summary).
- Tests (new): `backend/tests/test_projects_api.py`:
  - CRUD, limits, duplicate name, another user's id → 404 on every route (and as an upload /
    move / chat target);
  - delete with both document choices;
  - same file name in two projects stays two documents.

  Extend `test_account_service.py`.

### Checkpoint 3: project-scoped retrieval, caches, instructions (≈ 10)
- `backend/app/db/repositories/chunks.py`: the scope condition in `_VECTOR_SEARCH` /
  `_KEYWORD_SEARCH`. Default `DocumentScope.all()`, so the eval and concept maps are unchanged.
- `backend/app/retrieval/pg_chunk_search.py`, `retrieval_service.py` (`scope` param, L1 key), and
  `context_assembly.py`: pass `scope` through.
- `backend/app/services/answer_preparation.py` and `generation/llm_client.py`:
  - `project_instructions: str | None`, fenced in `current_user_text`;
  - the output is **byte-identical when None**, so the generation-eval cache keys don't move.
- `backend/app/services/chat_pipeline.py`, `session_service.py`, `api/routes/chat.py`:
  - `project_id` query param for new sessions;
  - the session's project and instructions are loaded in the turn's first transaction: an outer join
    in the same statement, so the follow-up round-trip budget stays 11;
  - a new session with a project costs +1 SELECT (the ownership check).
- `backend/app/services/caches/semantic_cache.py`: `scope_key` on store and lookup.
- Tests (new): `backend/tests/test_project_retrieval.py` (Postgres, fake embedder):
  - projects A and B retrieve disjointly, and unassigned sees neither;
  - a project chat's SSE `metadata.sources` never names B's file;
  - L1 / semantic cache don't cross scopes;
  - instructions appear only in the final user turn, fenced.

  Update `test_semantic_cache.py`, `test_llm_modes.py` (or `test_answer_preparation.py`), and
  `test_round_trips.py`, whose budgets must stay unchanged.

### Checkpoint 4: frontend (≈ 10)
- `frontend/src/services/projectsApi.js` (new): fetch helpers, following `apiClient.js` patterns.
- `frontend/src/components/ProjectPanel.js` (new): list + counts, create, rename, instructions
  textarea with a character counter and save state, archive toggle, delete dialog with the documents
  choice.
- `frontend/src/components/DocumentUpload.js`: a "Project" select (No project + active projects).
- `frontend/src/pages/DocumentsPage.js`: load projects, filter select (All / No project /
  each project), send `project_id` on upload, move handler, panel.
- `frontend/src/components/DocumentList.js`: project badge and a "Move to…" select per card.
- `frontend/src/components/ChatWindow.js`:
  - new chat: project picker in the header, plus the scope line ("Searching: <project> files" /
    "No project: unassigned documents");
  - existing chat: a read-only label;
  - sends `project_id`.
- `frontend/src/components/SessionSidebar.js` (+ `ChatPage.js` if it owns the session list): project
  badge, "Move to project" action.
- Tests: `ProjectPanel.test.js` (new). Extend `DocumentsPage.test.js` (upload sends the project,
  filter) and `ChatWindow.test.js` (stream URL carries `project_id` for a new chat only).

### Checkpoint 5: live verification + close-out
- Local stack (venv or Docker, `WEB_SEARCH_ENABLED=false`): two projects, one demo file each. Chat in
  A, inspect the sources, repeat the same question in B (cache), then an unassigned chat.
- Brief `## Outcome`, post 10 + post 9 material log, learning notes.

**New dependencies:** none.

## UI integration

| Backend change | Frontend file | What the user sees | Loading / empty / error |
|---|---|---|---|
| `POST/GET /projects` | `ProjectPanel.js`, `DocumentsPage.js` | "Projects" panel: list with file / chat counts, "New project" form | spinner while loading; "No projects yet: create one per course"; inline error, and 409 "a project with that name exists" |
| `PATCH /projects/{id}` (name, description, instructions, archived) | `ProjectPanel.js` | rename, instructions editor (0 / 4000 counter, Saving… / Saved), Archive / Unarchive | save button disabled while saving; error inline |
| `DELETE /projects/{id}?documents=` | `ProjectPanel.js` | confirm dialog: "Delete its N files" / "Move files to No project"; chats move to No project | button busy state; error inline; notice on success |
| `GET /projects/{id}` (files, chats, counts) | `ProjectPanel.js` (expand a project row) | the project's files and chats listed under it | row spinner; "No files / chats yet"; error inline |
| `POST /upload` `project_id` | `DocumentUpload.js` | "Project" select next to the file | existing upload states; 404 / 409 shown in the existing error banner |
| `PATCH /documents/{id}` (move) | `DocumentList.js` | "Move to…" select per card; badge with the project name | select disabled while moving; 409 name clash in the error banner |
| `GET /documents` `project_id`, `project_name` | `DocumentList.js`, `DocumentsPage.js` | badge per card; filter All / No project / each project | "No documents in this project" empty state |
| `GET /chat/stream` `project_id` | `ChatWindow.js` | project picker for a new chat + scope line | picker disabled while streaming; projects failing to load → "No project" only, with a note |
| `GET /sessions` `project_id`, `project_name`; `PATCH /sessions/{id}/project` | `SessionSidebar.js`, `ChatWindow.js` | project badge on sessions; "Move to project"; header label on an existing chat | error alert on a failed move, as rename does today |
| Scope in the caches, scope SQL, instructions in the prompt | — | backend-only: these change which chunks and answers a chat gets, visible through the controls above | — |
| Migration, `ON DELETE SET NULL`, account deletion of projects | — | backend-only: schema and cleanup, no new screen | — |

## Verification

- **Migration:**
  - local `rag`: `alembic upgrade head`, `alembic check` (no diff), downgrade −1 / upgrade once;
  - `rag_test`: conftest's downgrade base / upgrade head on every run;
  - CI runs the same steps.
- **Tests** (`python -m pytest -q`, Postgres `rag_test`): the full suite (396 today) plus the new
  files, all green.
  - **Retrieval:** two projects of one user retrieve disjointly (vector and keyword halves), and
    unassigned sees neither.
  - **Refusals:** another user's project id is refused on every project route, as an upload
    target, as a move target and as a chat `project_id` (404, nothing created).
  - **Chat:** a chat in project A: no `metadata.sources` entry from B's file. Repeated in B: no
    semantic-cache or L1 replay.
  - **Prompt:** `build_prompt` without instructions is byte-identical to today's. With
    instructions, they appear only in `current_user_text`, inside the fence, and never in
    `system_instruction`.
  - **Round trips:** `test_round_trips.py` budgets unchanged (first turn, follow-up, `/me`).
- **Frontend:** `npm test -- --watchAll=false` (42 today, plus the new tests), then `npm run build`.
- **Eval:** no retrieval or prompt change for the default scope. The eval runs with scope "all" and no
  instructions, so its prompts and cache keys are identical. Measurement is not needed; a check run is
  optional: `python -m eval.retrieval --config baseline --label day18-scope-all` should reproduce
  Hit@5 50/55 at 0 API calls.
- **Manual (Verify bullet), local stack:**
  - project A with demo PDF 1, project B with demo PDF 2 (both demo documents);
  - in A, ask a question both could answer: sources only from PDF 1;
  - the same question in B: only PDF 2, no cache replay (log: CACHE MISS);
  - a new unassigned chat: neither file cited.

## Risks & open questions

- **HNSW + a selective filter (future):** see The concept. Today's exact scan is unaffected. When the
  corpus grows, a project filter can starve HNSW results below k. Record it under I1, and consider
  `hnsw.iterative_scan = relaxed_order` with the eval on the Day 28–32 retrieval days.
- **`doc_version` stays per user** (timeline Day 20): any upload in any project invalidates every
  scope's cache entries. That is correct but wasteful, and stays noted for Day 20.
- **Concept maps keep searching all documents until Day 20**, while a general chat searches only
  unassigned ones (Decision 1A). This is a short-lived inconsistency, and Day 20 adds the project choice
  to maps.
- **The B15 / B11 / B12 source-chip bugs are untouched.** Verifying "never cites B" uses the SSE
  `metadata.sources` and the answer text, not the reloaded chips (which B15 breaks).
- **Production:**
  - this revision reaches Supabase `rag` only with the Day 20 release (v0.4.0);
  - `rag_staging` should get it before then, so the release runbook has a tested upgrade;
  - the rows are all `project_id = NULL`, so there is no backfill.
- **Migration naming:** autogenerate must not emit drops. Review by hand; the FKs need explicit
  names from the naming convention.
- **Semantic-cache entries written before today** have no scope and miss once per user. That's
  acceptable: the cache has no TTL, and they would otherwise sit unused.
- **Day 19 overlap (Decision 6A):** the Documents-page panel duplicates part of Day 19's `/projects`
  page. Day 19 can move the panel's pieces into the dedicated pages rather than rebuild them.
- **Open:** should an archived project's existing chats stay usable (the default above), or become
  read-only?
