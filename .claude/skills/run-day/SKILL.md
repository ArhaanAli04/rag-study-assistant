---
name: run-day
description: Start one day of the build timeline — read the day from docs/timeline.md, gather context, write a brief to docs/briefs/dayNN.md, and stop for approval before implementing anything.
argument-hint: "<day number, e.g. 1 or 15>"
disable-model-invocation: true
---

# /run-day — Work one timeline day: brief first, then build

Target: **Day $ARGUMENTS** of `docs/timeline.md`

If no day number was given, read CLAUDE.md's **Current Status** `Next:` line, propose that day,
and stop until the user confirms it. Below, `NN` is the day number zero-padded to two digits
(Day 1 → `day01`).

## Phase 1 — Orient (read-only)

1. CLAUDE.md is loaded automatically. If this session was compacted or cleared, re-read its
   **Current Status**, **Conventions for This Repo**, and **Known Issues** sections.
2. Run `git status`, `git branch --show-current`, and `git log --oneline -5`.
   - The current branch should be today's feature branch — the name on the day's
     `Branch:` line. If it is `develop` or `master`, stop and tell the user to run
     `git checkout -b <that name>` first; don't create it yourself.
   - If uncommitted changes from an earlier day are present, point them out before going on.
3. Read the `### Day <N> — …` section of `docs/timeline.md` in full, plus its phase heading
   (`## Phase …`) for context. If the section doesn't exist, say so and stop.
4. Collect every tracker ID the day names (G6, I4, CO5, …). For each one, read its entry in
   `docs/improvements.md` and its row in `docs/improvement-tracker.md`. If a row is already
   `Done` or `Skipped`, say so and ask whether to drop it from today's scope.
5. If `docs/briefs/dayNN.md` already exists, read it and ask whether to reuse it (skip to the
   approval question) or refresh it. Read any per-item briefs (`docs/briefs/<ID>.md`) for
   today's IDs too — they may hold earlier analysis.
6. Read every file and line range the day and its ID entries cite — always the real file,
   since line numbers drift — plus the callers of the code involved, related tests, and
   earlier days the bullets reference ("comes on Day 9", "the Day 16 script").
7. If the day depends on something an earlier day should have delivered (a script, a table, a
   test fixture) and it isn't in the code, report the gap — don't silently build it.

## Phase 2 — Brief (the only file you may write)

Write `docs/briefs/dayNN.md`. No other file may be created or modified in this phase.

```markdown
# Day N — <title from the timeline>
Date: YYYY-MM-DD · Phase P — <phase name> · Items: <IDs, or "none">
Branch: <branch from the timeline>

## Scope
The day's bullets, restated as a numbered list of deliverables. Mark anything the code makes
unnecessary, already done, or impossible as written — with the reason.

## Current behavior
What the code does today for each deliverable, with file:line references.

## Why it matters
A concrete failure scenario or limitation per deliverable: input/state → wrong outcome.

## The concept
The underlying AI-engineering, backend, or DevOps concepts behind today's work, how production
systems handle them, and the common pitfalls. Written to be studied later, not just skimmed.

## Decisions
One block for every bullet the timeline marks "Decision", and for any other real fork:
### <decision name>
- **A — <name>:** two sentences, including the main trade-off.
- **B — <name>:** two sentences, including the main trade-off.
- **Recommendation:** A or B, and why.
If there are no decisions, write "None".

## Plan
- Files to change or add, one line each, grouped by deliverable
- New dependencies, each marked "needs approval" (none unless the user approves)
- Checkpoints: split the work into steps of ≤ ~10 file operations; the user confirms between them

## UI integration
Required (CLAUDE.md rule: no backend work without its UI). For every deliverable that adds or
changes an endpoint, response field, status, flag, score, or feature:
- the frontend file(s) that will call or render it, and the control or screen the user sees
- loading, empty, and error states
Deliverables that are genuinely backend-only (refactor, tracing, migrations, tests) are listed
here as "backend-only — no user-visible change", with the reason. If the timeline day has no
UI bullet but the work is user-visible, add the UI work to the plan anyway and say so.

## Verification
The timeline's Verify/Test bullets made concrete: tests to add or run, manual checks, and — for
retrieval, prompt, or cache changes — what to measure before and after (eval harness once E4
exists).

## Risks & open questions
What could break, effects on later days, questions for the user.
```

Then summarize the brief in chat in 5–10 lines, list the decisions, and ask:
"Approve the plan with the recommended options, or change any decision?"

## STOP — wait for explicit approval

Do not modify any file other than the brief until the user approves the plan and answers every
decision.

## Phase 3 — Implement (only after approval)

1. Work checkpoint by checkpoint. At the end of each checkpoint, summarize what changed and wait
   for the user's go-ahead before starting the next.
2. After each file change, run the relevant check:
   - Python file → `python -m py_compile <file>` from the repo root
   - Code covered by an existing test → run that test: `python -m pytest tests/<file> -q`
   - New or changed endpoint → if the dev server is running, confirm the route appears at
     `http://localhost:8000/docs`; otherwise report that it was not verified
   - Frontend change → `cd frontend; npm run build` once at the end of the checkpoint
   - Docker or workflow file → validate it (`docker compose config`, or a dry run) where possible
3. Stay inside the approved plan. Record unrelated problems you notice under the brief's
   "Risks & open questions" instead of fixing them.
4. If a check fails twice for the same reason, stop and report as the global
   "When You Are Stuck" rule describes.
5. **UI integration check — before declaring the day done.** For each new or changed
   endpoint, response field, status or flag from today, find its caller in `frontend/src/`
   (search for the route path or field name). Any without a caller is unfinished work: wire
   it in now, or stop and ask — never leave it for "the UI phase".
6. Append an `## Outcome` section to the brief: files changed (one line each), checks run and
   their results, a **UI integration** table (backend change → frontend file → what the user
   sees, or "backend-only" with the reason), timeline bullets deferred or dropped (with the
   reason), and any before/after numbers for the tracker's Notes column.
7. **Post material — never skip, even on infrastructure days.** Read the "Day → post
   mapping" in `docs/posts/README.md` and find every post today feeds (post 9 is fed every
   day). Append one entry to the `## Material log` of each of those post files, newest last:

   ```markdown
   ### Day N — YYYY-MM-DD — <day title>
   - Takeaway: <one sentence a non-expert would understand>
   - Numbers: <measured before/after values with what was measured, or "none today">
   - Capture now (only what depends on today's app state and can't be recreated later):
     - [ ] <specific live screen, using demo documents only — or "nothing today">
   - Make when writing the post (recreatable any time from git, the brief or this log):
     - [ ] <code card, diagram, table card, re-runnable terminal output>
   - Lesson / quote: <one honest line — a surprise, a mistake, a trade-off>
   - Concept source: docs/briefs/dayNN.md#the-concept
   ```

   Post 9 gets a single line instead: `- Day N — <what shipped> — <one number or lesson>`.
   Use only numbers that were actually measured today; never estimate. Leave the post's other
   sections (hook, outline, visuals) untouched unless the user asks. If today's day is not in
   the mapping table, add only the post 9 line and mention the gap in chat.
8. **Learning notes — check every day.** Open `docs/learning/ai-concepts.md` (gitignored; if
   it is missing, say so and skip this step). Compare what was actually built today against
   its 19 concept headings. For each concept today's work used or changed:
   - If the section still holds the "_Not covered yet_" placeholder, replace it with:
     ```markdown
     **What it is** — plain words, 2–4 lines.
     **Why this project needed it** — the concrete problem in this app it solved.
     **How we used it** — files (path:line), approach, decisions taken and why, Day N.
     **What it's doing** — simple bullet points of what happens at runtime, step by step.
     **Results** — numbers measured today (with what and on what set), or "none yet".
     ```
   - If the section is already filled, append `#### Day N update — YYYY-MM-DD` with only what
     changed: new behaviour, new decisions, new numbers. Never rewrite earlier days' text.
   - Write only from what was built and measured today — never from the plan or estimates.
   If today touched none of the 19 concepts, write nothing and say "no concept notes today".
9. Summarize in chat: the same file-by-file list, check results and UI integration table,
   which concept sections were written or updated. Then visuals, in two separate lists:
   - **Capture now** — only screens that depend on the app's current state (a live feature
     with today's demo data, a trace, an eval run that is expensive to repeat). If none, say
     "nothing to capture today".
   - **Make later, when writing the post** — code cards, diagrams, table cards and any terminal
     output that can be re-run; these need no action today.
   Ask the user to act only on the first list.

## STOP — hand control back to the user

Files Claude may write in Phase 3: the approved plan's files, the brief's `## Outcome`, the
`## Material log` sections in `docs/posts/`, and concept sections in
`docs/learning/ai-concepts.md`.

Do NOT run `git add`, `git commit`, `git push`, `git merge`, `git checkout`, `git stash`,
`git reset`, `gh pr …`, or any git command other than `git status`, `git log`, `git diff`, and
`git branch --show-current`. Do NOT edit the tracker's Status/Notes columns or CLAUDE.md's
**Current Status** block unless the user asks.

These steps belong to the user, every time (see `rag_daily_command_sequence.pdf`):
- Run `/pre-commit` and review the report
- Update the tracker rows and CLAUDE.md's Current Status (or ask Claude to)
- Stage, commit, push, open and merge the PR into `develop`
- On release days, the develop → master release sequence

## Usage

```
/run-day 1
/run-day 15
```
