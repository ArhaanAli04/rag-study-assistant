# Day 3 — Per-user uploads (G7), account deletion (B1) and first release
Date: 2026-11-01 · Phase 1 — Security fixes & git workflow · Items: G7, B1
Branch: feature/day03-g7-b1 (current branch, working tree clean)

## Scope
1. **G7a — server-generated storage path.** Save every upload to
   `uploads/{user_id}/{uuid4}{ext}`; the client filename is kept only in `Document.file_name`.
2. **G7b — containment check.** Resolve the final path and refuse (500 + log, never write)
   anything that is not inside the upload root. With server-generated names this can only
   trip on a bug, but it is the backstop the timeline asks for.
3. **G7c — keep the human filename everywhere it is shown (added to scope).** Today the
   displayed name is *derived from the path* in three places (`document_service.py:7`,
   `chunk_builder.py:9,39,70`). With UUID paths, citations would read
   `3f2a….pdf` and document versioning would stop working (it matches on `file_name`).
   The client name has to be passed through explicitly — sanitized to a bare basename.
4. **G7d — duplicate upload cleanup (added to scope).** When `register_document` finds an
   identical file (same name + hash) it returns the old row; the freshly written UUID file
   would then be an orphan. Delete it in that case. (Re-indexing duplicates chunks — that is
   I6, untouched.)
5. **G7e — Docker volume.** `docker-compose.yml`: mount a named volume `uploads` at
   `/app/src/uploads`.
6. **G7f — existing rows.** Leave old `file_path` values (`uploads/<name>.pdf`) as they are; note
   it in the tracker. Nothing to build.
7. **B1a — the crash.** `delete_account` queries `Session` (SQLAlchemy's class) instead of
   `ChatSession`.
8. **B1b — account service.** New `account_service.py` deletes, in one DB transaction:
   messages, chat sessions, documents, concept-map nodes, concept maps, failed queries, the user.
   After the commit: files on disk, index entries, user-scoped caches.
9. **B1c — index entries.** Tombstone the user's FAISS chunks (`deleted: True`, already honoured
   at search time) **and** the BM25 entries — BM25 has no deleted check today, so it needs one.
   True removal comes with pgvector (Day 15).
10. **B1d — user-scoped caches (added to scope, see Decision 1).** Delete Redis
    `semantic_cache:{user_id}` and drop the user's entries from the in-process L1 cache.
11. **UI — Account settings "Delete account"** gets a loading state, an inline error with the
    server's message, and a short success summary before redirecting (today: `alert()`s only).
12. **Tests** — upload-path tests (`../evil.pdf` lands in `uploads/<user_id>/`) and an
    account-deletion test (nothing of user A remains, user B untouched).
13. **Clean-up** — after the fix, delete the test accounts `g6-a-751103`, `g6-b-751103`,
    `g6-a-8e49ad`, `g6-b-8e49ad` (users 3–6) and `day02-check@example.com` (user 7) via
    `DELETE /user/delete` on the running local server, then confirm their rows and files are
    gone. Destructive — I'll ask before running it.
14. **Release (yours, not mine — the skill forbids git writes):** develop → master `--no-ff`,
    push both, tag `v0.1.0`; on Render rotate `JWT_SECRET_KEY`, set `ALLOWED_ORIGINS`, `DEL
    semantic_cache_entries` on DB 0 and DB 1; mark G6, G8, G7, G4, G1, O2, B1 Done; verify
    Render health, Vercel login (email + Google), streaming chat. Checklist in the Outcome.

## Current behavior
- **Upload** — `src/main.py:175-213`: `validate_upload` (`:152-173`) checks only the extension
  and size; then `os.path.join(UPLOAD_DIR, file.filename)` (`:186`) with the raw client name,
  shared by all users. The response returns `saved_path` (the server path; no frontend caller).
- **Name derivation** — `document_service.py:7` and `chunk_builder.py:9,39,70` split the path on
  `/` and `\` to get the displayed name. `register_document` (`document_service.py:10-19`)
  matches the previous version by `(user_id, file_name)`; its early `return existing` skips
  `db.close()` (session leak).
- **Live evidence of G7 in the local DB** — users 1 and 2 both have a document row pointing at
  `uploads/DL_Unit5_RNN.pdf` (one file on disk, two owners). `src/uploads/` also holds 4 files
  with no document row.
- **Docker** — `docker-compose.yml:12-15` mounts `./src/data` and `./src/logs` only; uploads go to
  `/app/src/uploads` (container layer). `Dockerfile:28` creates `src/data/uploads`, which no code
  uses.
- **Delete account** — `src/main.py:431-443`. Line 438 `db.query(Session).filter(Session.user_id
  …)` → `AttributeError` → 500 via the global handler, nothing committed. Even fixed, it skips
  `failed_queries`, concept maps/nodes, files and index entries. `Message`/`Document` deletes are
  bulk `query().delete()`, which bypass ORM cascades, and SQLite runs with
  `PRAGMA foreign_keys = 0`, so nothing cascades at the DB level either.
- **Indexes** — `vector_store.py:37-44` `mark_delete_by_document_id` exists (only caller: dead
  `document_delete_service.py`); `search` skips `deleted` at `:59`. `keyword_index.py:37-58` has
  no deleted check at all.
- **ID reuse** — the `users` table is `id INTEGER PRIMARY KEY` without `AUTOINCREMENT`, so SQLite
  hands out `max(id)+1`. User 7 is the current max: delete it and the next registration is user 7.
- **Caches** — `semantic_cache:{user_id}` (no TTL); `RetrievalService._manual_l1_cache`
  (`retrieval_service.py:57`, keyed `(user_id, query, doc_version)`); `query_cache:*` (hashed
  key, TTL 1 h).
- **Frontend** — `AccountSettingsModal.js:100-121` calls `DELETE /user/delete` behind a confirm
  step; success → `alert` + redirect, failure → `alert('Failed to delete account')`, no loading
  state, so a double click sends two requests. `DocumentsPage.js:45-72` uploads and ignores the
  response body; `DocumentList.js:49-52` shows `doc.filename` and picks the icon from `doc.path`.

## Why it matters
- **G7a/b** — user 1 and user 2 upload `notes.pdf`: user 2's file overwrites user 1's on disk;
  both rows now point at user 2's content, and any later re-index or download serves the wrong
  user's file. A filename like `../../src/main.pdf` writes outside `uploads/`.
- **G7c** — without threading the name through, the first UUID upload would show
  `Sources: 3f2a9c….pdf` in every citation, and re-uploading a newer `notes.pdf` would create an
  unrelated document instead of version 2.
- **G7e** — `docker compose up --build` recreates the container: every uploaded file is gone while
  the `documents` rows still point at them.
- **B1** — a user clicks "Delete account" → 500, their data stays forever. Fixed naively, their
  failed queries, concept maps, files and indexed chunks would remain.
- **B1c/d (ID reuse)** — delete user 7 without purging runtime state; someone registers and
  becomes user 7 in the same process. Their chat retrieves the old user 7's chunks (FAISS/BM25
  filter on `user_id == "7"`) and their first question can hit the old user's semantic cache.
  That is the G6 leak again, through a different door.

## The concept
**Never let the client name a server path.** A filename is untrusted input like any other.
Path traversal (`../`), absolute paths, Windows drive letters and device names (`CON`, `NUL`),
NTFS alternate data streams (`file.pdf:evil`), Unicode look-alikes and trailing dots/spaces all
exist because people tried to *sanitize* names. The robust pattern is not to sanitize at all:
generate the storage key yourself (UUID or content hash), keep the original name only as
display metadata, and store the mapping in the database. S3, GCS and every serious upload
service work this way — the "filename" is an object key you chose.

**Defence in depth: resolve and contain.** Even with generated names, compute
`Path(root, user_id, name).resolve()` and check `is_relative_to(root.resolve())` before writing.
`resolve()` collapses `..` and follows symlinks; comparing strings with `startswith` is the
classic bug (`/uploads2` starts with `/uploads`). The check costs nothing and turns a future
regression into a refused write instead of a silent escape.

**Tenant isolation on disk.** Prefixing storage with the tenant id (`uploads/{user_id}/…`)
makes ownership visible in the path, lets "delete everything of user X" be one `rmtree`, and is
the same idea as a per-tenant key prefix in object storage or Redis (`semantic_cache:{user_id}`).

**Containers are disposable; state lives in volumes.** A container's writable layer dies with the
container. Anything that must survive `docker compose up --build` needs a bind mount (host
directory) or a named volume (managed by Docker). Named volumes are portable and permission-
friendly; bind mounts are easy to inspect. On PaaS hosts like Render the filesystem is ephemeral
unless a persistent disk is attached — production systems put uploads in object storage.

**Deleting a user is a distributed operation.** The data lives in SQLite, on disk, in two
in-memory indexes and in Redis. There is no transaction spanning all of them (no two-phase
commit here), so you *order* the steps for the safest failure: commit the database deletion
first (the source of truth — once it is gone, the account no longer exists and nothing can
reach the leftovers through the API), then remove the derived copies (files, index entries,
caches) best-effort with logging. The opposite order risks deleting files and then failing the
DB commit, leaving an account whose documents no longer exist. Large systems formalise this
with tombstones, an outbox table, or a background "erasure job" that retries until every store
confirms. Regulations like GDPR Art. 17 ("right to erasure") make this a legal requirement,
including derived data such as embeddings and caches.

**ORM pitfalls in deletion.** `session.query(Model).filter(...).delete()` emits one `DELETE`
statement and **skips ORM cascades** (`cascade="all, delete-orphan"` only fires on
`session.delete(obj)`). SQLite also ignores `ON DELETE CASCADE` unless `PRAGMA foreign_keys=ON`
is set per connection. So you either delete children explicitly in dependency order (nodes →
maps, messages → sessions) or load objects and let the ORM cascade. Explicit is clearer and
avoids loading thousands of rows.

**Soft vs hard deletion in vector indexes.** Flat FAISS indexes store vectors by position;
removing one means rebuilding or using an `IndexIDMap` with `remove_ids`. The common interim
pattern is a tombstone: mark the metadata deleted and filter at query time, then compact
periodically. Pitfall: tombstoned vectors still consume the over-fetch budget (`top_k * 5`), so
a user surrounded by many deleted chunks can get fewer results. Vector DBs (pgvector, Qdrant)
make deletion a real `DELETE` — that is Day 15.

**Identifier reuse.** SQLite's `INTEGER PRIMARY KEY` reuses the highest freed id; `AUTOINCREMENT`
or Postgres sequences never do. Any system that keys caches or index entries by user id must
either guarantee ids are never reused or purge everything keyed by the id at deletion.

## Decisions
### 1. Index and cache state at account deletion (SQLite id reuse)
- **A — purge at deletion:** tombstone the user's FAISS and BM25 entries, `DEL
  semantic_cache:{user_id}`, drop their L1 cache entries. Covers id reuse for everything except
  `query_cache:*` (hashed keys, used only by `POST /search`, which the frontend never calls; 1 h
  TTL).
- **B — A plus `AUTOINCREMENT` on `users`:** ids are never reused, but SQLite can't add
  `AUTOINCREMENT` to an existing table — it needs a table rebuild migration in `db.py`, on a
  database that Day 13 replaces with Postgres (sequences never reuse ids).
- **Recommendation: A.** It closes the realistic leak today with no migration; B's guarantee
  arrives for free with Postgres in ten days.

### 2. Order of DB deletion vs file / index removal
- **A — DB first, then derived data:** commit the row deletions in one transaction, then remove
  files, tombstone indexes and purge caches, logging (not raising) any failure. Worst case: an
  orphaned file or cache entry nobody can reach through the API.
- **B — files first, then DB:** if the commit fails, the account still exists but its documents'
  files are gone, and the user sees broken documents.
- **Recommendation: A.**

### 3. Legacy flat-path files of a deleted user
- **A — delete only if no other user's row references the same path:** `uploads/DL_Unit5_RNN.pdf`
  is shared by users 1 and 2 today; deleting user 2 must not delete user 1's file. Plus `rmtree`
  of `uploads/{user_id}/`.
- **B — never touch legacy files:** only `rmtree` the per-user directory; old flat files stay
  until Day 16 rebuilds everything.
- **Recommendation: A** — the deleted user's own legacy files really are deleted (users 3 and 5
  have private flat files today), and the shared-path guard is one query.

### 4. Upload root location
- **A — keep `src/uploads`, add a named volume `uploads:/app/src/uploads`:** matches the timeline
  and keeps every existing `file_path` valid.
- **B — move to `data/uploads` (already bind-mounted, already created by the Dockerfile):** no
  new volume, but existing rows point at `uploads/…` and would break.
- **Recommendation: A.** I'll leave the unused `mkdir src/data/uploads` in the Dockerfile alone
  (Day 4 is the Docker day) and note it.

## Plan
**Checkpoint 1 — G7 (7 files)**
- `src/upload_storage.py` (new): `UPLOAD_ROOT`, `display_name(client_name) -> str` (basename,
  strips `/`, `\`, control chars; falls back to `document{ext}`), `new_upload_path(root,
  user_id, ext) -> Path` (UUID name + containment check, raises `UnsafeUploadPath`),
  `user_upload_dir(root, user_id)`.
- `src/main.py`: `upload_file` uses the helpers, writes the file, passes the display name on;
  deletes the new file when `register_document` returns an existing identical row; drops
  `saved_path` from the response (server internals, no caller).
- `src/document_service.py`: `register_document(user_id, file_path, file_name)`; `try/finally`
  close.
- `src/indexing_pipeline.py`, `src/chunk_builder.py`: optional `file_name` parameter used instead of
  the path-derived name.
- `docker-compose.yml`: named volume `uploads`.
- `tests/test_upload_storage.py` (new).

**Checkpoint 2 — B1 (8 files)**
- `src/account_service.py` (new): `delete_user_account(db, user, *, vector_store, bm25_index,
  semantic_cache, retrieval_service, upload_root) -> AccountDeletionSummary` (dataclass of counts).
- `src/vector_store.py`: `mark_deleted_by_user(user_id) -> int`.
- `src/keyword_index.py`: `mark_deleted_by_user(user_id) -> int`; `search` skips `deleted`.
- `src/semantic_cache.py`: `clear_user(user_id)`.
- `src/retrieval_service.py`: `l1_cache_purge_user(user_id)`.
- `src/main.py`: `delete_account` calls the service, returns `{"message", "deleted": {...counts}}`.
- `tests/test_account_service.py` (new): in-memory SQLite + fakes; A deleted, B intact,
  shared legacy file kept.

**Checkpoint 3 — UI, live checks, clean-up (1 file + verification)**
- `frontend/src/components/AccountSettingsModal.js`: deleting state, inline error, summary.
- `npm run build`; live API check (needs the dev server + Redis running); delete test users 3–7
  (asks first); Outcome, post material, learning notes.

New dependencies: none.

## UI integration
| Change | Frontend | What the user sees |
|---|---|---|
| `DELETE /user/delete` works and returns `deleted` counts | `AccountSettingsModal.js` | "Confirm Delete" becomes "Deleting…" (disabled, no double submit); on success an inline green line "Account deleted — N documents, N chats removed", then redirect to `/login`; on failure an inline red message with the server's `detail` (or a network-error message), button re-enabled |
| `POST /upload` stores under a UUID path, drops `saved_path` | `DocumentsPage.js` (unchanged) | Nothing changes visibly — that is the point: the list and citations still show the original filename. Verified live: upload a file and check the Documents list and a cited answer |
| Upload volume, containment check, index tombstones, cache purge | — | backend-only — storage and isolation internals with no new field or state |

No empty state applies to the delete action.

## Verification
- `python -m pytest tests/test_upload_storage.py tests/test_account_service.py -q`, then the whole
  `tests` folder (no regressions in the Day 1–2 tests).
- Upload tests: `../evil.pdf`, `..\\..\\evil.PDF`, `/etc/passwd.pdf`, `C:\\x\\y.docx`, empty-ish names
  → path is inside `root/<user_id>/`, name is `<uuid hex>.<lower ext>`, display name is the bare
  basename; a forced escape (patched name) raises `UnsafeUploadPath`.
- Account test: users A and B each with sessions, messages, documents, failed queries, a concept map
  with nodes, files in `root/<id>/`, a legacy shared flat file, FAISS/BM25 entries, a semantic-cache
  key and L1 entries → after deleting A: zero A rows in all 7 tables, A's directory gone, shared file
  kept, A's index entries tombstoned and missing from BM25/FAISS search, B's everything intact.
- `docker compose config` validates the compose change.
- Live (server running): register → upload a demo PDF → chat → `DELETE /user/delete` → check DB rows,
  `uploads/<id>/` and a fresh registration that reuses the id gets no old sources. Then delete
  users 3–7 and confirm with a DB query and `ls src/uploads`.
- Frontend: `npm run build`; `npm test -- --watchAll=false`.
- No retrieval or prompt change, so no eval numbers.

## Risks & open questions
- **Importing `db` creates `data/` in the CWD** (`db.py:82-84`); the account test runs from the repo
  root, so it creates an empty, gitignored `./data`. I'll point the test at an in-memory engine and
  leave `db.py` alone (Day 7–10 refactor).
- **Render has no volume for uploads** — files are lost on every deploy there regardless of G7e. The
  index is lost too (I4), so they go together until Day 13–16. Worth saying in the release notes.
- `DELETE /documents/{id}` still leaves the file and index entries (I5, Day 15) — now with UUID files it
  is easier to fix, but out of scope.
- `query_cache:*` entries of a deleted user survive up to 1 h (Decision 1); only `POST /search` reads them.
- Tombstoned vectors stay in FAISS until restart (memory only, never returned).
- Orphan files in `src/uploads/` with no document row (4 today) — not touched.
- Unused `mkdir src/data/uploads` in `Dockerfile:28` — leave for Day 4.
- Release steps on Render (JWT rotation logs everyone out) are yours; I'll give the checklist.
- Found during implementation: one-off scripts that call `load_dotenv()` from outside the repo
  don't find the root `.env` (it searches from the *script's* folder), and every Redis client then
  falls back to `localhost:6379` instead of the compose port 6380. Bit the users 3–7 clean-up
  (see Outcome). Day 4 (Docker-first dev) is a natural place to make `REDIS_URL` explicit.

## Outcome
Decisions taken: 1A, 2A, 3A, 4A (all as recommended).

### Files changed
**Backend**
- `src/upload_storage.py` (new) — `display_name`, `file_extension`, `new_upload_path` (UUID name, containment check), `ensure_inside_root`, `is_inside_user_dir`, `UnsafeUploadPath`
- `src/main.py` — `upload_file` stores under `uploads/{user_id}/{uuid}{ext}` and calls `register_upload`; `saved_path` dropped from the response; `UPLOAD_DIR` removed; `delete_account` calls the account service and returns `deleted` counts
- `src/document_service.py` — `register_document(user_id, file_path, file_name, session_factory)` with the session always closed; new `register_upload` (identical re-upload: drop the new copy if the row is already per-user, otherwise move a legacy row to the new per-user copy and keep the legacy file)
- `src/indexing_pipeline.py`, `src/chunk_builder.py` — optional `file_name` so citations show the original filename
- `src/account_service.py` (new) — `delete_user_account` + `AccountDeletionSummary`
- `src/vector_store.py`, `src/keyword_index.py` — `mark_deleted_by_user`; BM25 `search` now skips tombstones
- `src/semantic_cache.py` — `clear_user`; `src/retrieval_service.py` — `l1_cache_purge_user`

**Frontend**
- `frontend/src/components/AccountSettingsModal.js` — "Deleting…" state, inline error, `AuthContext.logout()` then `/login`
- `frontend/src/utils/accountDeletion.js` (new) — summary hand-off through `sessionStorage` (every access in try/catch) and the notice text
- `frontend/src/pages/LoginPage.js`, `frontend/src/components/LoginForm.js` — green one-time notice
- `frontend/src/App.js` — `AppRoutes` exported (for tests)
- `frontend/package.json` — `jest.moduleNameMapper` for the router packages (**deviation**, see below)

**Tests**
- `tests/test_upload_storage.py` (12), `tests/test_document_service.py` (3), `tests/test_account_service.py` (3) — new
- `frontend/src/components/AccountSettingsModal.test.js` (3), `frontend/src/AccountDeletionFlow.test.js` (1) — new

**Config / docs**
- `docker-compose.yml` — named volume `uploads:/app/src/uploads`
- `.gitignore` — `docs/posts/assets/` (post screenshots)
- `docs/timeline.md` — Day 5 note: the router now works in Jest

### Deviations from the plan
- **Re-upload over a legacy path** (your review after CP1): an identical re-upload whose existing
  row points at a pre-G7 flat path is moved to the new per-user copy instead of re-indexing the
  shared file, which another user may have overwritten. Moved into `register_upload` so it is
  tested offline.
- **`frontend/package.json` jest config** (option B, approved): CRA's Jest 27 ignores package
  `exports`, and `react-router-dom` 7.10.1's `"main"` points at a file it doesn't ship. The mapper
  points `react-router-dom`, `react-router` and `react-router/dom` at their existing CJS builds.
  Nothing else was added to the jest config.
- **Notice fix:** the first version passed the deletion summary as navigation state. Live, no notice
  showed: `logout()` flips `isAuthenticated`, the route guard's `<Navigate to="/login" replace />`
  wins, and the state is lost. Reproduced with `AccountDeletionFlow.test.js` (real `AppRoutes` at
  `/chat`), then fixed by writing the summary to `sessionStorage` before `logout()`; `LoginPage`
  reads it once and removes it in an effect (StrictMode-safe). My earlier modal-only test missed
  this because it rendered an unguarded route — the lesson is to test flows through the real router.
- **Files touched beyond the plan:** `LoginPage.js`, `LoginForm.js`, `utils/accountDeletion.js`,
  `App.js` (all for the notice), `.gitignore`, `docs/timeline.md`.

### Checks
| Check | Result |
|---|---|
| `py_compile` on every changed Python file | pass |
| `python -m pytest tests -q` | **81 passed** (63 before today) |
| `npm test -- --watchAll=false` | **7 passed**, 4 suites (3 before today); `AccountDeletionFlow` failed before the notice fix, passes after |
| `npm run build` | compiled; warnings only in untouched files |
| `docker compose config --quiet` | valid |
| Routes in `/openapi.json` (dev server) | `/upload`, `/user/delete` present |
| Live upload (demo accounts A=8, B=9) | stored as `uploads\8\1102f141….pdf` / `uploads\9\f22aed58….pdf`; `/documents` and citations show `samples.pdf` / `table_test.pdf` |
| Live isolation, same question in both | A's sources `[samples.pdf]`, B's `[table_test.pdf]` — **0 of A's sources reached B** |
| Live UI delete, accounts 8 and 9 | 200 in 198 ms / 57 ms; `index_entries_removed` 6 / 10 (FAISS + BM25: 3+3, 5+5 chunks); 0 rows in all 7 tables, no `uploads\8` / `\9`, `semantic_cache:8/9` gone on DB 0 and 1 |
| Live UI delete after the notice fix (fresh account) | got **id 3** — SQLite reused a freed id, as predicted in Decision 1. 200 in 71.5 ms, `index_entries_removed=6`; green notice shown, gone after reload, no token in localStorage; 0 rows, no `uploads\3`, no `semantic_cache:3` |
| Users 3–7 clean-up (one-off script calling `delete_user_account`, not committed, deleted after) | DB rows and both `g6_userA_private_*.pdf` removed; 0 rows for 3–7 in all 7 tables; `DL_Unit5_RNN.pdf` and the 4 orphans kept. Redis clear failed (script didn't load `.env`, see Risks) — logged per decision 2A; the 3 leftover keys on DB 0 were then removed with `DEL` and verified 0 on DB 0 and 1 |
| `token=` / `eyJ` in `app.log` after all of today's requests | 0 |

### UI integration
| Backend change | Frontend file | What the user sees |
|---|---|---|
| `DELETE /user/delete` works and returns `deleted` counts | `AccountSettingsModal.js`, `utils/accountDeletion.js`, `LoginPage.js`, `LoginForm.js` | "Confirm Delete" → "Deleting…" (both buttons disabled); on success logged out and on `/login` with a green "Your account was deleted — N documents and N chats removed." shown once; on failure an inline red message with the server's `detail` and the buttons re-enabled; network error → "Your account was not deleted" |
| `POST /upload` stores under UUID paths, `saved_path` removed | `DocumentsPage.js`, `DocumentList.js` (unchanged) | no visible change — the list and citations keep the original filename (verified live) |
| Containment check, per-user dirs, Docker volume, index tombstones, cache purge | — | backend-only: storage and isolation internals with no new field or state |

### Timeline bullets deferred or dropped
- **Release (develop → master, push, tag `v0.1.0`, Render secrets, tracker Done)** — not done by me;
  the skill forbids git writes and Render changes. Checklist below.
- Nothing dropped.

### Release checklist (yours, in order)
1. `/pre-commit`, review the report; `git status`, commit on `feature/day03-g7-b1`
   ("day 03 - per-user uploads (G7), account deletion (B1)"), merge into `develop`.
2. `git checkout master`, `git status` clean, `git merge --no-ff develop`.
3. **Render env before the first deploy of these commits:** new `JWT_SECRET_KEY` (logs everyone
   out — tokens were in logs before G8); `ALLOWED_ORIGINS=https://rag-study-assistant-chi.vercel.app`.
4. `git push origin develop`, `git push origin master` (first push of both), `git tag v0.1.0`,
   `git push origin v0.1.0`.
5. **Render Redis:** `DEL semantic_cache_entries` on DB 0 and DB 1 (legacy shared key, G6).
6. Verify: Render `/health` is `{"status":"ok"}`; Vercel login with email and Google; a streamed
   chat; one upload (note: Render has no disk for `uploads/` — files and the in-memory index are
   lost on every deploy until Days 13–16).
7. Tracker: mark G6, G8, G7, G4, G1, O2, B1 Done. Suggested Notes —
   - **G7:** "Day 3. `uploads/{user_id}/{uuid}{ext}` + resolve/containment check; client name only in `Document.file_name` and citations. Identical re-upload over a legacy flat path moves the row to a per-user copy. 15 offline tests. Live: two demo accounts, B got 0 of A's sources. Existing rows keep their old flat `file_path` (rebuilt on Day 16). Docker named volume `uploads`."
   - **B1:** "Day 3. `account_service.delete_user_account`: 7 tables in one transaction, then files, FAISS + BM25 tombstones, semantic + L1 cache. Live UI deletes: 200 in 57–198 ms, `index_entries_removed` 6/10/6, 0 rows left. SQLite reused freed id 3 for a new account — the purge is what keeps it clean. Test accounts 3–7 deleted."
8. CLAUDE.md Current Status; the "Blockers" line can drop the test-account item.

### Numbers for the tracker's Notes column
- Backend tests 63 → 81; frontend tests 3 → 7.
- Live isolation: 0 of A's sources reached B (same question, two demo accounts).
- Live account deletion: 3 UI deletes returned 200 in 198 / 57 / 71.5 ms; `index_entries_removed` 6 / 10 / 6.
- 8 account deletions today: test accounts 3–7 (script), demo accounts 8 and 9 and the live-check account (new id 3) via the UI. `users` table: 7 rows at the start of the day → 2 (ids 1 and 2).
