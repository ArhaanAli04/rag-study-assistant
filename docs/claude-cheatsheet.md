# Claude Code Quick Reference
# RAG Study Assistant

## Project Skills (type these inside claude)

| Command | When to use |
|---|---|
| `/run-item <ID>` | Start work on one tracker item, e.g. `/run-item G6`, or a coupled group, `/run-item I4,I5,I6`. Writes a brief to `docs/briefs/<ID>.md` and stops for your approval before implementing. |
| `/pre-commit` | Before every commit: compile check, `pytest tests`, diff review against CLAUDE.md rules, frontend/Docker builds when relevant. Reports only — no git writes. |

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

```
1. cd rag-study-assistant ; claude
   (the session-context hook shows git state and any In Progress item)
2. Pick ONE item (or coupled group) from docs/improvement-tracker.md
   and set its Status to "In Progress".
3. /run-item <ID>                       (or paste the anchor prompt below)
4. Read docs/briefs/<ID>.md → reply "go with A", "go with B", or adjustments
5. Watch it implement. If context gets heavy: /clear → paste the resume prompt
6. /pre-commit → review the report and the diff
7. You: git add → git commit → git push
8. You: tracker row → Done (+ notes, before/after numbers), CLAUDE.md Current Status → commit
```

## Anchor Prompt (when not using /run-item)

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

## Resume Prompt (after /clear in the middle of an item)

```
Resume [ID]. Read docs/briefs/[ID].md — the approved option is [A/B] [plus any adjustments].
Run `git diff` to see what is already done, then continue the brief's Plan from there.
Same rules as /run-item Phase 3: a check after each file, no git writes,
and append ## Outcome to the brief when finished.
```

## Choosing the Next Item

- **One item or coupled group per session** — the brief stays focused and the diff stays reviewable.
- **Suggested order:** G6 → G8 → G7 → B1 → I4,I5,I6 → R5 → E4 → R1, fitting the tiny P0s
  (G4, G1, O2) into any session; then CO4 → G5 → C2 → C3.
- **Coupled groups and prerequisites:**
  - I4 + I5 + I6 share the index persistence and deletion code — do them together.
  - G6 before CO5 (fix the leak before tuning the cache).
  - E4 before R1, R4, or tuning any threshold (B2, CO5) — measure first.
  - C2 before C3 (memory retrieval needs the rewritten query).

## Hooks (automatic — `.claude/settings.json`)

| Hook | When | What it does |
|---|---|---|
| Command guard | Before every Bash/PowerShell command | Blocks `git reset --hard`, `checkout .`, `restore .`, `clean -f`, force-push, `stash drop/clear`, `branch -D`; recursive deletes of source dirs; deleting `src/data` or `app.db`; `recreate_db.py`; Redis `FLUSHALL/FLUSHDB`; `alembic downgrade`; SQL `DROP` |
| Session context | Start, resume, `/clear`, `/compact` | Adds git state, last commit, and In Progress items with their brief paths to Claude's context |
| Ruff bug-only check | After Claude edits a `.py` file | `ruff check --select E9,F63,F7,F82` on that file; findings go back to Claude to fix |
| Edit reminders | After Claude edits a trap file | One-line notes: requirements encoding, Alembic, the two chat endpoints, `user_id` scoping, prompt layout |

Scripts live in `.claude/hooks/`; review or disable them with `/hooks`. The guard is a seatbelt
against accidents, not a security boundary.

## When Claude Goes Wrong

- Wrong direction for more than 5 minutes → `/rewind`, then clarify your prompt. `/rewind`
  restores files Claude edited; it doesn't undo what shell commands did.
- Unexpected change → `/diff` or `git diff` to see it, then fix or revert that file yourself.
- A hook blocked a command → read the reason. If you really want it, run it in your own terminal.
- A check fails twice → Claude should stop and report (global "When You Are Stuck" rule); choose the approach yourself.
- Context got large mid-item → `/clear`, then the resume prompt.
- The brief looks wrong or stale → `/run-item <ID>` again and choose "refresh".

## File Locations

| File | Purpose |
|---|---|
| `CLAUDE.md` | Project memory — loaded automatically every session |
| `~/.claude/CLAUDE.md` | Global personal preferences |
| `docs/improvements.md` | Evidence and direction for every item ID |
| `docs/improvement-tracker.md` | Status of every item (you update it) |
| `docs/briefs/<ID>.md` | Per-item brief and Outcome — your study notes |
| `docs/claude-cheatsheet.md` | This file |
| `.claude/skills/run-item/SKILL.md` | `/run-item` workflow |
| `.claude/skills/pre-commit/SKILL.md` | `/pre-commit` checks |
| `.claude/settings.json` | Hook registration |
| `.claude/hooks/*.py` | Hook scripts |
