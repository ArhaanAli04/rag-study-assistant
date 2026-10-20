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
5. Append an `## Outcome` section to the brief: files changed (one line each), checks run and
   their results, timeline bullets deferred or dropped (with the reason), and any before/after
   numbers for the tracker's Notes column.
6. Summarize in chat: the same file-by-file list and check results.

## STOP — hand control back to the user

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
