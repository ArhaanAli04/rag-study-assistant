# Claude Code Quick Reference
# RAG Study Assistant

## Project Skills (type these inside claude)

| Command | When to use |
|---|---|
| `/run-day <N>` | Start a timeline day, e.g. `/run-day 1`. Reads Day N of `docs/timeline.md` and every tracker ID it names, writes `docs/briefs/dayNN.md`, and stops for your approval; then implements checkpoint by checkpoint. The default way to start each day. |
| `/run-item <ID>` | Work on one tracker item outside the timeline, e.g. `/run-item G6`, or a coupled group, `/run-item I4,I5,I6`. Writes a brief to `docs/briefs/<ID>.md` and stops for your approval before implementing. |
| `/pre-commit` | Before every commit: compile check, `pytest tests`, diff review against CLAUDE.md rules, frontend/Docker builds when relevant. Reports only — no git writes. |
| `/ship commit "<msg>"` · `/ship merge` | The only skill that writes to git. `commit`: safety scan (no `.env`, runtime data, `*.db`, secrets), stage, show renames, ask yes → commit, push, draft PR into `develop`, watch CI. `merge`: clean tree + green CI, ask yes → merge commit (never squash), delete branch, pull `develop`. Releases stay manual. |

Both live in `.claude/skills/`. Only you can start them; Claude won't invoke them on its own.

## Built-in Commands

| Command | What it does |
|---|---|
| `/clear` | Fresh conversation (aliases `/reset`, `/new`); CLAUDE.md loads again |
| `/compact` | Summarize the conversation to free context |
| `/context` | Show context-window usage |
| `/rewind` | Roll code and conversation back to a checkpoint |
| `/diff` | Review working-tree changes, including Claude's edits |
| `/btw` | Ask a side question without adding it to the conversation |
| `/plan` | Enter plan mode for a large change |
| `/model` | Switch model (saved as default) |
| `/usage` | Token usage and cost (alias `/cost`) |
| `/hooks` | View hook configuration; opening it also reloads hooks |
| `/skills` | List and manage skills |
| `/memory` | Edit CLAUDE.md files and auto memory |
| `/resume` | Return to an earlier conversation |
| `/export` | Export the conversation as plain text |
| `/doctor` | Diagnose Claude Code setup problems |

## Context Window Management Rules

- 0–50% → work freely
- 50–70% → finish the current step, then `/compact`
- 70–90% → `/compact` now
- 90%+ → `/clear`, then use the resume prompt below — the brief holds the plan

Check usage with `/context`. After `/clear` or `/compact`, the session-context hook re-adds git
state and the In Progress item automatically.

## Daily Ritual

The full command-by-command checklist (setup, PRs, release days, Days 1–3 exceptions) is
`rag_daily_command_sequence.pdf` in the repo root (gitignored, personal copy).

```
1. cd rag-study-assistant ; .\venv\Scripts\Activate.ps1
2. git checkout develop ; git pull origin develop
   git checkout -b <Branch: line of today's day in docs/timeline.md>
3. claude   (the session-context hook shows git state and any In Progress item)
4. /run-day <N>
5. Read docs/briefs/dayNN.md → approve, answer each Decision, or adjust
6. Watch it implement, confirming each checkpoint. If context gets heavy: /clear → resume prompt
7. /pre-commit → review the report and the diff
8. Tracker rows → Done (+ notes, before/after numbers), CLAUDE.md Current Status (or ask Claude)
9. /ship commit "day NN - description" → safety scan, staged summary, you answer yes → commit,
   push, draft PR into develop, CI watched (repeat at each commit point on refactor days)
10. /ship merge → you answer yes → PR merged with a merge commit, branch deleted, develop pulled
    (by hand instead: git status → git add -A → git commit → git push → gh pr create → gh pr merge)
```

## Anchor Prompt (when not using /run-day or /run-item)

```
This is the RAG Study Assistant project.
CLAUDE.md is loaded — re-read its Conventions and Known Issues sections.
Run `git status` and `git log --oneline -5`.
Today's item: [ID] — [title from docs/improvement-tracker.md].
Last session we completed: [one sentence, or "nothing yet"].

Context gathering only — do NOT create, edit, or delete any file except the brief.
1. Read the [ID] entry in docs/improvements.md and its row in docs/improvement-tracker.md.
2. Read every file and line range it cites, their callers, and any tracker items it references.
3. Write docs/briefs/[ID].md covering:
   - Current behavior, with file:line references
   - Why it's a problem, concretely
   - The underlying concept and how production AI systems handle it
   - Two approaches (2 sentences each) and your recommendation
   - Files you'd touch, and how we'll verify it (test or measurement)
   - Risks, dependencies on other items, and open questions for me
Then summarize it and wait for my go-ahead before implementing anything.
```

## Resume Prompt (after /clear in the middle of a day or item)

```
Resume Day [N]. Read docs/briefs/day[NN].md — approved decisions: [A/B per decision, plus any adjustments].
Run `git diff` to see what is already done, then continue the brief's Plan from the next checkpoint.
Same rules as /run-day Phase 3: a check after each file, confirm each checkpoint, no git writes,
and append ## Outcome to the brief when finished.
```

For a single item: `Resume [ID]. Read docs/briefs/[ID].md …` with the /run-item Phase 3 rules.

## Choosing the Next Item

- **One timeline day per session** — the brief stays focused and the diff stays reviewable.
- **Order:** follow `docs/timeline.md` day by day. Use `/run-item` only for work outside it.
- **Coupled groups and prerequisites:**
  - I4 + I5 + I6 share the index persistence and deletion code — do them together.
  - G6 before CO5 (fix the leak before tuning the cache).
  - E4 before R1, R4, or tuning any threshold (B2, CO5) — measure first.
  - C2 before C3 (memory retrieval needs the rewritten query).

## Hooks (automatic — `.claude/settings.json`)

| Hook | When | What it does |
|---|---|---|
| Command guard | Before every Bash/PowerShell command | Blocks `git reset --hard`, `checkout .`, `restore .`, `clean -f`, force-push, `stash drop/clear`, `branch -D`; recursive deletes of source dirs; deleting `backend/data`, `src/data` or `app.db`; Redis `FLUSHALL/FLUSHDB`; `alembic downgrade`; SQL `DROP` |
| Session context | Start, resume, `/clear`, `/compact` | Adds git state, last commit, and In Progress items with their brief paths to Claude's context |
| Ruff bug-only check | After Claude edits a `.py` file | `ruff check --select E9,F63,F7,F82` on that file; findings go back to Claude to fix |
| Edit reminders | After Claude edits a trap file | One-line notes: requirements.in vs the generated lock, Alembic, the SSE contract in `chat_pipeline.py`, `user_id` scoping, prompt layout |

Scripts live in `.claude/hooks/`; review or disable them with `/hooks`. The guard is a seatbelt
against accidents, not a security boundary.

## When Claude Goes Wrong

- Wrong direction for more than 5 minutes → `/rewind`, then clarify your prompt. `/rewind`
  restores files Claude edited; it doesn't undo what shell commands did.
- Unexpected change → `/diff` or `git diff` to see it, then fix or revert that file yourself.
- A hook blocked a command → read the reason. If you really want it, run it in your own terminal.
- A check fails twice → Claude should stop and report (global "When You Are Stuck" rule); choose the approach yourself.
- Context got large mid-item → `/clear`, then the resume prompt.
- The brief looks wrong or stale → `/run-day <N>` (or `/run-item <ID>`) again and choose "refresh".

## File Locations

| File | Purpose |
|---|---|
| `CLAUDE.md` | Project memory — loaded automatically every session |
| `~/.claude/CLAUDE.md` | Global personal preferences |
| `docs/improvements.md` | Evidence and direction for every item ID |
| `docs/improvement-tracker.md` | Status of every item (you update it) |
| `docs/timeline.md` | 61-day build plan — what `/run-day` reads (edit here, regenerate the docx) |
| `docs/briefs/dayNN.md` | Per-day brief and Outcome — your study notes |
| `docs/posts/` | LinkedIn series: 9 post outlines; `/run-day` appends each day's material log (mapping in `README.md`) |
| `docs/briefs/<ID>.md` | Per-item brief and Outcome (from `/run-item`) |
| `docs/claude-cheatsheet.md` | This file |
| `.claude/skills/run-day/SKILL.md` | `/run-day` workflow |
| `.claude/skills/run-item/SKILL.md` | `/run-item` workflow |
| `.claude/skills/pre-commit/SKILL.md` | `/pre-commit` checks |
| `.claude/skills/ship/SKILL.md` | `/ship` commit + PR + merge |
| `.claude/settings.json` | Hook registration |
| `.claude/hooks/*.py` | Hook scripts |
