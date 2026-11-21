# Day 19 — Projects UI
Date: 2026-11-21 · Phase 6 — Projects · Items: none (no tracker ID; timeline feature)
Branch: feature/day19-projects-ui

## Scope

1. **`/projects` page:** project cards showing name, file count, chat count and last activity.
   Create, rename, archive and delete, each with confirmation where it destroys or hides something.
2. **`/projects/:id` page:**
   - a files panel: upload into the project, remove a file;
   - the instructions editor, with save state and the character limit;
   - the project's chat list (each one opens the chat);
   - "New chat in this project".
3. **Navigation:**
   - a Projects link in the sidebar and in the top navigation;
   - the chat header shows the chat's project, with a switcher for new chats.
   - **Already done on Day 18** (`ChatProjectScope.js`): the header label and the new-chat picker.
     Today adds only a link from the header's project name to `/projects/:id`, and the picker
     preselected from "New chat in this project".
4. **States everywhere:** loading, empty ("create your first project — e.g. one per course") and
   error.
5. **Verify:** create a project, upload two files, start a chat. Answers cite only those files and
   follow the instructions.

**Found gap, added to the scope:** the API has accepted and returned `description` since Day 18
(`schemas/projects.py:30,41,56`), but no screen shows it or lets the user edit it. Under the owner's
rule ("no backend work without its UI") that is unfinished Day 18 work. Today it goes on the create
form, the cards and the detail page.

**Backend: no change needed.** Every field and route today's pages need already exists:
- `GET /projects` returns `last_activity`, `document_count`, `chat_count`, `description` and
  `archived`;
- `GET /projects/{id}` returns `documents` and `chats`;
- `PATCH` / `DELETE /projects/{id}`, `POST /upload` with `project_id`, `PATCH /documents/{id}`,
  `DELETE /documents/{id}`;
- `GET /chat/stream` with `project_id`.

## Current behavior

- **Routes:** `App.js:15-38` has `/chat`, `/documents`, `/quiz` and `/concept-maps`. There is no
  `/projects`, and `*` redirects to `/login`.
- **Top navigation:** `TopNav.js:113-172` has icon buttons for Concept Maps, Quiz and Documents
  (each swaps to "Back to Chat" on its own page). No Projects button.
- **Projects panel on the Documents page:**
  - The panel (`DocumentsPage.js:214-220` → `ProjectPanel.js`) lists projects with counts, a
    name-only create form, and per row (`ProjectRow.js`) rename, instructions, archive, an
    expandable files/chats list, and a delete dialog.
  - Archived and active projects are mixed in one list.
  - `last_activity` and `description` aren't shown.
  - The expanded row's files and chats are plain text: a chat can't be opened from there, and a
    file can't be removed there.
- **Uploads:** the upload code lives inline in `DocumentsPage.js:88-120` as a raw `fetch` with
  `FormData`, and the document delete in `:138-164`. Neither can be reused by another page.
- **Chat page:**
  - `ChatPage.js:13-14` keeps `activeSessionId` in component state only. Nothing reads the URL, so
    another page can't open a given chat or start a chat in a given project.
  - `ChatWindow.js:25` starts the picker at `""` (No project).
- **Chat header:** `ChatProjectScope.js:16-26` shows "Project: X" / "No project" as plain text.
- **Sidebar:** `SessionSidebar.js:251-260` has only "New Chat". The project badge and "Move to
  project" exist (Day 18).

## Why it matters

- **Projects are hard to find.** A student opening the app lands on `/chat`. Projects are reachable
  only by guessing that the Documents page holds them. The app's main organizing idea has no place
  of its own.
- **No overview of a course.** "Which of my courses did I study this week, and how much material
  does each have?" needs counts plus last activity on one screen. Today it means expanding rows one
  by one, and the last activity isn't shown anywhere.
- **Dead ends.** The expanded row lists a project's chats, but clicking one does nothing. It lists
  files, but a misplaced file can only be fixed by going back to the main documents list and
  finding it among every other course's files.
- **Starting a project chat takes four steps.** Go to chat, click New Chat, open the picker, choose
  the project. Pick the wrong one and the chat is locked to it after the first message
  (`ChatWindow.js:293`). From the project page it should be one click.
- **Missing description.** A student with "DL Unit 5" and "DL Unit 6" has nowhere to note what each
  covers, although the database already stores it.

## The concept

**The URL is application state.** In a single-page app the router maps a URL to a screen, but the
URL can also carry *which* thing the screen shows: `/projects/7`, `/chat?session=42`,
`/chat?project=7`. Putting that state in the URL instead of in component memory buys three things:
- **refresh works:** reloading `/projects/7` shows project 7, not a blank default;
- **back / forward work:** the browser history becomes the navigation history;
- **pages can link to each other** without sharing a store: the project page doesn't need to reach
  into the chat page's state, it just links to `/chat?project=7`.

The rule of thumb is "anything you'd want to survive a refresh or be linkable goes in the URL;
transient UI (an open menu, a half-typed name) stays in component state". The pitfall is treating
the URL as a one-off command instead of a source of truth:
- `?project=7` means "a new chat preselected to 7";
- once that chat is created and the URL changes to `?session=42`, the old parameter must be gone,
  or a refresh would start yet another new chat.

React Router's `useSearchParams` / `useParams` read it. Navigating with `replace` updates it without
adding a history entry.

**Never trust a URL id.** `/projects/9999` or another user's `/projects/12` is typed, not clicked.
The server already answers 404 for both (Day 18: another user's id behaves exactly like a missing
one). The page must turn that into a "Project not found" state with a way back, not a spinner
forever or a crash on `undefined.name`. A non-numeric id (`/projects/abc`) never needs a request.

**List / detail, and keeping them consistent.** The list page shows summaries (counts, last
activity) and the detail page shows the full resource. After a mutation (upload, move, rename) the
summaries go stale. There are three common answers:
- **refetch after every write (pessimistic):** simple and always correct, one extra request;
- **update the local copy from the write's response:** fewer requests, but you duplicate the
  server's logic. What does a delete do to `chat_count`?
- **optimistic updates with rollback:** fastest UI, the most code and the most edge cases.

At this app's scale, refetching is the right default, and it's what the Day 18 pages already do.
Optimism pays off when latency is felt on every keystroke, not on a rename.

**The four states of every async view.** Each data-backed region is in one of four states:
- **loading:** say what is loading;
- **empty:** say what to do next. An empty state is an onboarding moment ("create one per
  course"), not just "nothing here";
- **error:** say what failed, and offer a retry;
- **ready.**

Pitfalls:
- an error rendered as the empty state ("No projects yet" when the request actually failed);
- a spinner that never ends when a request throws before `finally`;
- **a stale response overwriting a newer one**, e.g. navigating from `/projects/3` to
  `/projects/4` while 3's request is still in flight. The fix is to ignore a response whose request
  is no longer current: a `cancelled` flag in the effect's cleanup, or an `AbortController`.

**Destructive actions need friction proportional to the damage.**
- Archive is reversible: one click and a notice.
- Delete removes data: a dialog that names what will happen ("its 3 chats move to No project") and
  makes the user choose what happens to the files. Day 18's dialog deliberately has no default
  choice.
- "Remove from project" is ambiguous: does it delete the file or detach it? The label has to say
  which.

**Unsaved edits.** A long instructions text edited and then left by navigating away is lost
silently. Common answers:
- a visible "unsaved changes" marker;
- a `beforeunload` prompt for tab closes;
- a router navigation blocker. React Router's `useBlocker` needs a data router
  (`createBrowserRouter`), and this app uses `<BrowserRouter>`.

A visible marker is the cheap, honest middle ground.

## Decisions

### 1. The Documents page's Projects panel
- **A — Replace it with a link to `/projects`:** the Documents page keeps the project picker on
  upload, the project filter, the badges and "Move to…" (file-centric work). Project management
  (create, rename, instructions, archive, delete) lives only on the Projects pages. `ProjectPanel.js`
  and `ProjectRow.js` are deleted, and their reusable pieces move into a shared module.
- **B — Keep the panel as well:** two places to manage projects, so two sets of tests and two UIs
  to keep in step, and the panel's dead-end file/chat lists stay.
- **Recommendation: A.** The Day 18 brief planned this ("Day 19 can move the panel's pieces into the
  dedicated pages"), and CLAUDE.md's rule is to delete dead code. The Documents page gets a one-line
  "Manage projects →" link where the panel was.

### 2. How the Projects pages open chats
- **A — URL parameters on `/chat`:** `/chat?project=7` opens a new chat with project 7 preselected,
  and `/chat?session=42` opens an existing chat. `ChatPage` reads them, and once the new chat exists
  it replaces `?project=7` with `?session=42`. The sidebar's clicks update `?session=` too, so a
  refresh keeps the open chat.
- **B — React Router location state** (`navigate("/chat", { state: { projectId } })`): no URL
  change and less code, but a refresh or a copied link loses the choice, and back/forward don't
  restore it.
- **Recommendation: A.** It's the pattern from The concept, and it fixes a small existing annoyance:
  today a refresh on `/chat` always drops you into a blank new chat. An unknown or another user's
  session id gets the existing "Unable to load previous messages" state (the server returns 404).
  An unknown or archived project id falls back to No project, with a note.

### 3. "Remove" a file on the project page
- **A — Two explicit actions per file:** "Move to No project" (`PATCH /documents/{id}` with `null`:
  the file stays, general chats can cite it) and "Delete" (`DELETE /documents/{id}`, every version,
  with a confirm). Each label says what it does.
- **B — One "Remove" that deletes:** fewer buttons. But "remove from this project" most naturally
  reads as detach, so users would lose files they meant to keep.
- **Recommendation: A.** Delete is irreversible, so the button that does it says "Delete".

**Approved 2026-11-21:** 1A, 2A, 3A. Owner's answers and additions:
1. **Last activity counts uploads:** the latest of the newest message and the newest document
   upload, computed in `list_with_counts`. The route stays plain `def`, a backend test covers it,
   and "No activity yet" shows only when the project has neither chats nor files. This lands in
   checkpoint 1 with the list page. It supersedes the "Last activity" default below.
2. **B15 stays with B11 / B12**, not today.
3. **Styling:** no redesign and no new colour scheme. The new pages stay tidy and consistent with
   the existing Tailwind patterns:
   - consistent card spacing and radius;
   - hover and focus states;
   - lucide icons on empty states;
   - a readable hierarchy: the name, then a meta line in muted text;
   - a responsive grid down to phone width.
4. **Close-out:** correct the `rag_staging` status in CLAUDE.md (Current Status "Next", the Data &
   State Supabase row) and in the Day 16 / 17 / 18 briefs (see Risks).

Not decisions (sensible defaults, stated so they can be overridden):
- **Archived projects** are listed in a separate "Archived (N)" section under the active cards,
  collapsed by default. Their detail page:
  - shows an "Archived" banner with "Unarchive";
  - hides the upload;
  - disables "New chat in this project". Archive blocks new uploads and chats (Day 18, 409);
  - keeps existing chats openable.
- **Last activity** is the backend's value: the newest message in any of the project's chats
  (`repositories/projects.py:16`). It is shown relative ("2 hours ago"). With no chats it shows
  "No chats yet · created Nov 19". Uploads don't count as activity (Risks).
- **Card order:** as the API returns them (newest project first). Sorting by activity is a UI
  overhaul question (Days 56–59).
- **Deleting from the detail page** goes back to `/projects` with the deletion notice.
- **Unsaved instructions:** the editor shows "Unsaved changes" while the text differs from the saved
  value. No navigation blocker (see The concept).

## Plan

### Checkpoint 1: `/projects` list page, navigation, Documents page cleanup (≈ 11 file operations)
- `frontend/src/components/ProjectEditors.js` (new): `RenameForm`, `InstructionsEditor` (+ "Unsaved
  changes"), `DescriptionEditor` and `DeleteDialog`, moved out of `ProjectRow.js` (same behavior,
  same labels, so the tests carry over).
- `frontend/src/components/ProjectCard.js` (new):
  - shows name, description, "N files · M chats", last activity, and an Archived badge;
  - actions: Open, Rename, Archive/Unarchive, Delete (the dialog).
- `frontend/src/pages/ProjectsPage.js` (new):
  - TopNav;
  - create form (name + optional description, limits shown);
  - active cards grid, and a collapsed "Archived (N)" section;
  - states: loading, error + retry, empty ("Create your first project — e.g. one per course");
  - the success notice.
- `frontend/src/services/projectsApi.js`: `formatLastActivity(project)`.
- `frontend/src/App.js`: route `/projects`. Until checkpoint 2 adds `/projects/:projectId`, a
  card's "Open" button isn't rendered, so there is no placeholder route.
- `frontend/src/components/TopNav.js`: a Projects button (`FolderKanban` icon, already in
  `lucide-react`), with the same "Back to Chat" swap as the others.
- `frontend/src/components/SessionSidebar.js`: a "Projects" link under "New Chat".
- `frontend/src/pages/DocumentsPage.js`: remove the panel, add the "Manage projects →" link (keep
  picker, filter, badges, move).
- Delete `frontend/src/components/ProjectPanel.js`, `ProjectRow.js`, `ProjectPanel.test.js`.
- Tests:
  - `frontend/src/pages/ProjectsPage.test.js` (new): the panel's 18 cases carried over (create,
    rename, instructions, archive, delete both ways, refusals), plus cards with last activity /
    description, the Archived section and navigation to `/projects/:id`;
  - `DocumentsPage.test.js`: drop the panel assumptions, add a test for the link.

### Checkpoint 2: `/projects/:id` detail page, chat hand-off (≈ 10)
- `frontend/src/services/documentsApi.js` (new): `uploadDocument(file, projectId)` and
  `deleteDocument(id)`, moved out of `DocumentsPage.js` (same requests, same error messages).
  `DocumentsPage.js` calls them.
- `frontend/src/pages/ProjectDetailPage.js` (new):
  - header: name, description (editable), counts, Archived banner, Rename / Archive / Delete;
  - **Files:**
    - `DocumentUpload` locked to this project (its picker hidden);
    - per file: "Not searchable yet", "Move to No project" and "Delete" (confirm);
  - **Instructions:** `InstructionsEditor`;
  - **Chats:** each one links to `/chat?session=<id>`, with its last message time;
  - "New chat in this project" → `/chat?project=<id>`;
  - states:
    - loading; an error with retry; "Project not found" (404 or a non-numeric id) with a link back;
    - empty files ("Upload this course's slides and notes"), empty chats ("No chats yet — start
      one");
  - a stale-response guard on the id.
- `frontend/src/components/DocumentUpload.js`: a `showProjectPicker` prop (default true), so the
  detail page hides the picker.
- `frontend/src/pages/ChatPage.js`:
  - reads `?session=` / `?project=`;
  - sidebar selection and "New Chat" write `?session=` / clear the parameters;
  - a created chat replaces `?project=` with `?session=`;
  - passes `initialProjectId`.
- `frontend/src/components/ChatWindow.js`: `initialProjectId` preselects the new-chat picker, once
  the projects have loaded. An id that isn't an active project falls back to No project, with the
  note "That project isn't available for new chats".
- `frontend/src/components/ChatProjectScope.js`: the project name links to `/projects/:id` (it needs
  the session's `project_id`, which `GET /sessions` already returns).
- Tests:
  - `frontend/src/pages/ProjectDetailPage.test.js` (new): loading / not found / error; upload sends
    `project_id`; move out; delete; archived hides upload; the chat links; "New chat" goes to
    `/chat?project=`;
  - `ChatWindow.test.js`: the preselected project is sent on the first message, and an archived or
    unknown id falls back;
  - `ChatPage` URL handling (a new `pages/ChatPage.test.js`, or inside `ChatWindow.test.js` if the
    mock setup is shared).

### Checkpoint 3: live verification + close-out
- The live check below; then the brief's `## Outcome`, the post 9 / 10 material log and the learning
  notes.

**New dependencies:** none. React Router 7 and lucide-react are already installed.

## UI integration

| Backend capability (existing) | Frontend file | What the user sees | Loading / empty / error |
|---|---|---|---|
| `GET /projects` (counts, `last_activity`, `description`, `archived`) | `ProjectsPage.js`, `ProjectCard.js` | cards; Archived section | "Loading projects…"; "Create your first project — e.g. one per course"; error + Try again |
| `POST /projects` (name, description) | `ProjectsPage.js` | create form with limits | "Creating…"; 409 duplicate name inline |
| `PATCH /projects/{id}` (name, description, instructions, archived) | `ProjectCard.js`, `ProjectDetailPage.js`, `ProjectEditors.js` | rename, description, instructions (counter / 4000, Unsaved / Saving… / Saved), Archive / Unarchive | busy buttons; error next to the control |
| `DELETE /projects/{id}?documents=` | `ProjectEditors.js` (`DeleteDialog`) on card and detail page | the two-choice dialog; notice; back to `/projects` from the detail page | "Deleting…"; refusal (409 name clash) kept in the dialog |
| `GET /projects/{id}` (documents, chats) | `ProjectDetailPage.js` | files and chats panels | loading; not found; error + retry; empty files / chats |
| `POST /upload` `project_id` | `ProjectDetailPage.js` via `documentsApi.js` | upload straight into the project | existing upload states; hidden when archived |
| `PATCH /documents/{id}` `null`, `DELETE /documents/{id}` | `ProjectDetailPage.js` | "Move to No project", "Delete" per file | per-row busy; error banner |
| `GET /chat/stream` `project_id` | `ChatPage.js`, `ChatWindow.js` | "New chat in this project" lands with the project preselected | fallback note for an archived or unknown id |
| `GET /sessions` `project_id` | `ChatProjectScope.js` | the header's project name links to its page | — |
| `GET /sessions/{id}/messages` | `ChatPage.js` | a project's chat opens from its page; refresh keeps the open chat | existing "Unable to load previous messages" |

No backend change today, so there is no backend-only row.

## Verification

- **Frontend tests** (`cd frontend; npm test -- --watchAll=false`): 84 today. The panel's 18 tests
  move to `ProjectsPage.test.js`, plus the new detail-page, chat hand-off and navigation tests; all
  green. Then `npm run build` with `CI=true`.
- **Backend:** no code change. The full suite isn't required by the change, but CI runs it on the
  PR anyway.
- **Eval:** nothing to measure. No retrieval, prompt or cache change.
- **Live check (the timeline's Verify)**, set up like Day 18:
  - venv backend on 8010 with the eval Gemini key, `WEB_SEARCH_ENABLED=false`, local `rag`;
  - a CRA dev server on 3010 pointed at 8010;
  - one throwaway account, deleted afterwards (summary + independent row check);
  - demo PDFs only.

  Steps:
  1. `/projects` empty state; create "Biology" with a description; the card shows "0 files · 0
     chats · No chats yet".
  2. Open it; upload two demo PDFs on the detail page; both are listed and searchable; the card
     counts 2 files.
  3. Save instructions (e.g. "Answer in exactly 3 bullet points"); "Saved".
  4. Upload a third demo PDF with No project on the Documents page (the control: it must never be
     cited).
  5. "New chat in this project" → `/chat?project=<id>`, project preselected; ask a question that
     the No-project PDF would also match. The answer cites only the two Biology files and follows
     the instructions. After the answer the URL is `/chat?session=<id>`, and a refresh keeps the
     chat.
  6. Back on the project page the chat is listed and opens; last activity reads "Just now" /
     minutes ago.
  7. "Move to No project" on one file → the count drops; Archive → upload hidden, New chat
     disabled; Unarchive.
  8. Delete the project with "keep files": notice, back on `/projects`, its chat now shows "No
     project".
  9. `/projects/999999` → "Project not found".
- Citations are judged from the live answer and its `metadata.sources`, not from reloaded chips
  (B15).

## Risks & open questions

- **B15 is still open:** chips turn into "Source" after the first answer and in reloaded chats.
  Opening a project's chat from its page reloads it, so its old answers show broken chips. That's
  pre-existing and planned with B11 / B12, but it will be more visible now that chats are opened
  from project pages. Should B15 be pulled into today? My suggestion: no, keep it with B11 / B12 on
  one day as planned.
- **Last activity ignores uploads:** a project where you only uploaded files this week shows "No
  chats yet". Making uploads count needs a backend change (max of message and document times in
  `list_with_counts`). Should it be added today as a small backend change, or left as is?
- **`?session=` for a chat that isn't yours** returns 404 from the server, and the chat shows the
  existing error. That's fine for security (no data leaks), but the message is generic.
- **Refresh during a new chat's first stream:** the URL changes to `?session=` only after `[DONE]`.
  A refresh mid-stream lands on `?project=` and starts a new blank chat, while the half-finished
  one still appears in the sidebar. This is acceptable and noted.
- **No navigation blocker for unsaved instructions** (BrowserRouter). There is a visible marker
  instead. Moving to a data router is a UI-overhaul question.
- **Day 20 overlap:** Day 20 adds the project's concept maps to the Projects page and the session
  filter by project. Today's detail page leaves room for a "Concept maps" panel but doesn't fake
  one.
- **`rag_staging` is at head** (correction, 2026-11-21). It was still at `500c410270f5` until
  2026-11-20: the Day 16 staging migration was never applied, although the docs said it was. The
  owner applied `21f0595f83d5` and `1e74b84340ae` on 2026-11-20; `alembic check` is clean and
  `current` = `1e74b84340ae (head)`. The only pre-release step left for Day 20 is production
  (backup, then the migration through the image). The Day 19 close-out corrects CLAUDE.md and the
  Day 16 / 17 / 18 briefs where they say otherwise.
