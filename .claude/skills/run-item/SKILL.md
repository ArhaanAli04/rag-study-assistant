---
name: run-item
description: Start a work session on one improvement-tracker item — gather context, write a brief to docs/briefs/, and stop for approval before implementing anything.
argument-hint: "<tracker ID, e.g. G6, or a coupled group like I4,I5,I6>"
disable-model-invocation: true
---

# /run-item — Work one tracker item: brief first, then build

Target: **$ARGUMENTS**

This is one ID from `docs/improvement-tracker.md`, or a comma-separated group of tightly
coupled IDs (e.g. `I4,I5,I6`). If no ID was given, ask the user for one and stop.

## Phase 1 — Orient (read-only)

1. CLAUDE.md is loaded automatically. If this session was compacted or cleared, re-read its
   **Current Status**, **Conventions for This Repo**, and **Known Issues** sections.
2. Run `git status` and `git log --oneline -5`.
3. Read the entry for each target ID in `docs/improvements.md` and its row in
   `docs/improvement-tracker.md`. If the row is already `Done` or `Skipped`, say so and ask
   before continuing.
4. If `docs/briefs/<ID>.md` already exists, read it and ask whether to reuse it (skip to the
   approval question) or refresh it.
5. Read every file and line range the entry cites — always the real file, since line numbers
   drift — plus the callers of the code involved, related tests, and the entries of any other
   tracker IDs it references.
6. If uncommitted changes (`git status`) touch the same files, point that out before going on.

## Phase 2 — Brief (the only file you may write)

Write `docs/briefs/<ID>.md`. For a group, name the file after the first ID and list all IDs
in the title. No other file may be created or modified in this phase.

```markdown
# <ID> — <title>
Date: YYYY-MM-DD · Priority: P? · Related: <other IDs>

## Current behavior
What the code does today, with file:line references.

## Why it's a problem
A concrete failure scenario: input/state → wrong outcome.

## The concept
The underlying AI-engineering or backend concept, how production systems handle it, and the
common pitfalls. Written to be studied later, not just skimmed.

## Options
### A — <name>
Two sentences, including the main trade-off.
### B — <name>
Two sentences, including the main trade-off.
**Recommendation:** A or B, and why.

## Plan (for the recommended option)
- Files to change or add, one line each
- New dependencies (none unless the user approves)
- Checkpoints, if the work exceeds ~10 file operations

## Verification
Tests to add or run, manual checks, and — for retrieval, prompt, or cache changes — what to
measure before and after.

## Risks & open questions
What could break, dependencies on other tracker items, questions for the user.
```

Then summarize the brief in chat in 5–10 lines and ask:
"Proceed with option A, switch to B, or adjust the plan?"

## STOP — wait for explicit approval

Do not modify any file other than the brief until the user approves an option.

## Phase 3 — Implement (only after approval)

1. Implement in small steps, following CLAUDE.md conventions and the global rules. After each
   file change, run the relevant check:
   - Python file → `python -m py_compile <file>` from the repo root
   - Code covered by an existing test → run that test: `python -m pytest tests/<file> -q`
   - New or changed endpoint → if the dev server is running, confirm the route appears at
     `http://localhost:8000/docs`; otherwise report that it was not verified
   - Frontend change → `cd frontend; npm run build` once at the end of the phase
2. Stay inside the approved plan. Record unrelated problems you notice under the brief's
   "Risks & open questions" instead of fixing them.
3. If a check fails twice for the same reason, stop and report as the global
   "When You Are Stuck" rule describes.
4. Append an `## Outcome` section to the brief: files changed (one line each), checks run and
   their results, and anything deferred.
5. Summarize in chat: the same file-by-file list and check results.

## STOP — hand control back to the user

Do NOT run `git add`, `git commit`, `git push`, `git stash`, `git reset`, or any git command
other than `git status`, `git log`, and `git diff`. Do NOT edit the tracker's Status/Notes
columns or CLAUDE.md's **Current Status** block.

These steps belong to the user, every time:
- Run `/pre-commit` and review the report
- Stage and commit
- Update the tracker row and CLAUDE.md's Current Status
- Push

## Usage

```
/run-item G6
/run-item I4,I5,I6
```
