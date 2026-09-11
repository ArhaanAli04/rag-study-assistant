---
name: pre-commit
description: Run this repo's pre-commit checks on the uncommitted changes and report the results. Makes no git writes.
disable-model-invocation: true
---

# /pre-commit — Checks before committing

This repo has no Makefile, linter, type checker, or CI, so this command is the quality gate.
Run the steps in order and stop at the first failure:
- If the failure is in code changed this session, fix it and rerun that step.
- If it looks pre-existing or unrelated to this session's change, report it and ask before
  fixing anything.

## 1. What changed (read-only)

- `git status --short` (includes untracked files) and `git diff --stat`, then `git diff` for
  the review in step 4.
- Group the changed files: backend (`src/**/*.py`), tests (`tests/`), frontend
  (`frontend/**`), Docker (`Dockerfile`, `docker-compose.yml`), dependencies
  (`requirements.txt`, `src/requirements.txt`), docs.

## 2. Backend compile check — only if `.py` files changed

```powershell
python -m py_compile <each changed .py file>
```

## 3. Tests

```powershell
python -m pytest tests -q
```

Pass `tests` explicitly — `pytest.ini` is ignored until T1 is fixed.

## 4. Diff review against the rules

Review only added or changed lines. Report each finding with file:line.

| Check | Source |
|---|---|
| `print(` added in `src/` | Global: use `logging` |
| Bare `except:` or broad `except Exception` without meaningful handling | Global |
| New or changed Python functions without type hints | Global |
| `TODO` comments, or placeholders that silently do nothing instead of raising `NotImplementedError` | Global |
| Commented-out code left behind | Global: delete dead code |
| Hardcoded keys, tokens, or passwords; any change to `.env` files or `frontend/.env.production` | CLAUDE.md: Secrets |
| Search filters, cache keys, or file paths for user data not scoped by `user_id` | CLAUDE.md |
| A change to a user's document set without a `User.doc_version` bump | CLAUDE.md |
| Pipeline logic changed in only one of `POST /chat` / `GET /chat/stream` | CLAUDE.md |
| Retrieved or web text placed in the system instruction; new per-turn variation added to it | CLAUDE.md, G5, CO4 |
| New third-party imports, or any dependency-file change | Global: no new dependencies without approval |
| `import main` / `from main import` in eval or experiment code | CLAUDE.md |

## 5. Dependencies — only if a requirements file changed

- Confirm the approved dependency is the only addition.
- Confirm the encoding is still UTF-16LE (Git Bash: `file requirements.txt`). The Dockerfile
  installs the root `requirements.txt`, so that is the copy that must be correct.

## 6. Frontend — only if `frontend/` changed

```powershell
cd frontend; npm run build
```

There is no lint script, and `npm test` only runs the default CRA test in watch mode — skip it.

## 7. Docker — only if `Dockerfile`, `docker-compose.yml`, or `requirements.txt` changed

```powershell
docker build -t rag-backend:precommit .
```

If Docker isn't running, mark this step as skipped with that reason.

## 8. Not covered — list these in the report

- Alembic migration checks (misconfigured until T2)
- Live chat behavior (needs Gemini, Tavily, and Redis) — suggest a manual check if the change
  touches chat, retrieval, or caching
- Retrieval quality (no eval harness until E4)

## Report

1. A table: Step | Result (pass / fail / skipped + reason) | Notes.
2. Findings from step 4, each with file:line.
3. If the work came from `/run-item`, remind the user of their manual steps: commit, update the
   tracker row and CLAUDE.md's Current Status, and check that the brief has an `## Outcome`
   section.
4. A suggested commit message (text only) that a future reader with no context would
   understand.

## STOP — hand control back to the user

Do NOT run git write commands (`add`, `commit`, `push`, `stash`, `reset`, `checkout`,
`restore`, `rebase`). Do NOT edit the tracker's Status/Notes columns or CLAUDE.md's
Current Status block. Report the results and stop.
