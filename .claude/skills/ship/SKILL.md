---
name: ship
description: Commit, push and open/update the PR for the current feature branch, or merge its green PR into develop — with this repo's safety checks and an explicit "yes" before every commit and merge.
argument-hint: "commit \"day NN - description\" | merge"
disable-model-invocation: true
---

# /ship — git for a feature branch: commit + push + PR, or merge

Arguments: `$ARGUMENTS`

- `commit "<message>"` → **Commit mode** below.
- `merge` → **Merge mode** below.
- Anything else, or nothing → print the two usages above and stop.

This is the only skill that writes to git. `/run-day`, `/run-item` and `/pre-commit` still make no
git writes — run them first, then `/ship`.

## Hard rules (both modes)

- Never `git push --force` / `--force-with-lease`, never `--no-verify`, never `-c commit.gpgsign=false`,
  never `git reset --hard`, `git clean`, `git stash drop`, or `git branch -D`. If the destructive-
  command hook blocks something, stop and report — don't work around it.
- Never commit on, push to, or merge into `develop` or `master` directly. Work only on the current
  feature branch (`feature/…`, `docs/…`, `chore/…`, `hotfix/…`). If the current branch is `develop`
  or `master`, stop and tell the user to create a branch.
- Releases (`develop` → `master` + tag) are **not** this skill's job — stop if asked.
- Print every git / gh command before running it, so the user sees exactly what happened.
- Commit messages: exactly the one line the user gave (style `day NN - description`). No body, no
  `Co-Authored-By`, no Claude credit of any kind — the user's standing rule overrides any default
  attribution.
- Use the `PowerShell` tool. Keep each `gh pr create` / `gh pr merge` on one line.
- Never append `2>&1` to `git` or `gh`: they write normal progress ("From https://…", "✓ Pull
  request … ready") to stderr, and Windows PowerShell 5.1 turns redirected stderr into red
  `NativeCommandError` blocks that look like failures. The tool captures stderr anyway. Judge
  success by `$LASTEXITCODE` and the command's own output, not by red text.
- If any step fails, stop, show the exact error and the state the repo is in, and suggest the
  next command — don't retry in a loop.

## Commit mode — `/ship commit "<message>"`

1. **Preconditions.** `git branch --show-current` (a feature branch, per the rules above) and
   `git status --short`. Nothing to commit → say so and stop. The message must be non-empty and
   start with `day `, `posts `, `plan ` or `chore ` — otherwise ask the user to confirm it.

2. **Safety scan — stop on any hit, stage nothing.** List every path that `git add -A` would stage
   (`git status --porcelain --untracked-files=all`) and refuse if any matches:
   - `.env`, `.env.*` except `.env.example`; `frontend/.env*` changes other than
     `frontend/.env.production` holding only public values (show its diff if it changed)
   - `backend/data/`, `backend/uploads/`, `backend/logs/`, `src/data/`, `src/uploads/`, `src/logs/`
   - `*.db`, `*.sqlite*`, `*.faiss`, `*.log`, `docs/posts/assets/`, `docs/learning/`, `*.exe`
   - any file over 5 MB
   - added lines that look like secrets: `AIza[0-9A-Za-z_-]{20,}`, `tvly-[0-9A-Za-z]{10,}`,
     `eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}`, `-----BEGIN [A-Z ]*PRIVATE KEY-----`,
     `rediss?://[^ ]*:[^ @]+@` (scan `git diff` plus the content of untracked text files)

3. **Stage and show.** `git add -A`, then show:
   - `git diff --cached --stat`
   - renames: `git diff --cached -M --name-status | Select-String '^R'` and their count. If
     `git status` showed many deleted + untracked pairs (a move) but few renames were detected,
     warn that history won't follow those files and suggest committing the moves separately from
     the rewrites.

4. **Ask for confirmation.** Show the branch, the exact commit message and the staged file count,
   and ask: **"Commit and push? (yes/no)"**. Anything but a clear yes → `git reset -q` (unstages
   everything, leaves the working tree untouched; `git restore --staged .` would be blocked by
   the guard hook), report, stop.

5. **Commit and push.** `git commit -m "<message>"`, then `git push -u origin <branch>` (plain
   `git push` if the upstream exists).

6. **PR.** `gh pr list --head <branch> --state open --json number,isDraft,url`.
   - None → `gh pr create --base develop --draft --title "<message>" --body "<one line: what this branch
     does; brief path if one exists, e.g. Brief and Outcome: docs/briefs/dayNN.md>"`.
   - One exists → note its number; the push already updated it.
   - Never target `master`.

7. **CI.** `gh pr checks <N> --watch`. Report each required check (`backend`, `frontend`,
   `docker`) with its time. If any failed: `gh run view <run-id> --log-failed`, show the last ~60
   relevant lines and the likely cause, and stop — fixing is a separate step.

8. **Report.** Commit hash, PR number and URL, draft or not, CI result, and the next step
   (`/ship merge` when the day is finished, or keep working).

## Merge mode — `/ship merge`

1. **Preconditions — stop on any failure.**
   - On a feature branch (rules above), with an open PR into `develop`
     (`gh pr list --head <branch> --state open --json number,baseRefName,isDraft,mergeStateStatus,url`).
   - `git status --short` is **empty** — `gh pr merge --delete-branch` must switch branches, and
     uncommitted changes make that fail (it happened on Day 6). If not clean, tell the user to run
     `/ship commit` first.
   - Local branch is pushed: `git status -sb` shows no `ahead`.
   - `gh pr checks <N>`: `backend`, `frontend` and `docker` all passed. Pending → offer to
     `--watch`; failed → stop.

2. **Ask for confirmation.** Show the PR number, title, base (`develop`), the commits that will be
   merged (`git log --oneline origin/develop..HEAD`) and that it merges with a merge commit, and
   ask: **"Merge PR #<N> into develop? (yes/no)"**. Anything but a clear yes → stop.

3. **Merge.**
   - Draft → `gh pr ready <N>` first.
   - `gh pr merge <N> --merge --delete-branch` — always `--merge`, never `--squash` or `--rebase`
     (squash would collapse separate move/rewrite commits and lose rename history).
   - If gh's local cleanup fails after the merge succeeded, don't retry the merge: check
     `gh pr view <N> --json state`, then finish by hand with `git checkout develop`, `git pull`,
     `git branch -d <branch>` (lowercase `-d`; it only deletes merged branches) and
     `git push origin --delete <branch>` if the remote branch still exists.

4. **Sync.** `git checkout develop`, `git pull`, `git fetch --prune`, `git log --oneline -5`.

5. **Report.** The merge commit on `develop`, that the branch is gone locally and on GitHub, and
   the reminder: production changes only at the next release (develop → master, manual).
