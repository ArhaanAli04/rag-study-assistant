# Day 6 — Continuous integration on GitHub Actions
Date: 2026-11-06 · Phase 2 — Dev foundation: Docker, tests & CI · Items: none (touches T3 via the requirements-encoding decision)
Branch: feature/day06-ci

## Scope
1. **`.github/workflows/ci.yml`** — runs on pull requests to `develop` / `master` and on pushes.
   - **backend:** Python 3.11 (matches Docker), pip cache, install `requirements.txt`, `ruff check`, `pytest`.
   - **frontend:** Node LTS, `npm ci`, `npm test -- --watchAll=false`, `npm run build`.
   - **docker:** build the backend and frontend images, no push.
2. **Decision: `requirements.txt` encoding.** It's UTF-16LE with CRLF. The timeline says convert it to UTF-8 only if pip in CI can't read it. **Very likely unnecessary:** the file starts with a UTF-16LE BOM (`FF FE`), pip decodes BOM-marked requirement files, and the Docker build already runs `pip install -r requirements.txt` on Linux. The first CI run confirms it (Decision 1).
3. **Branch protection.** `master` requires a PR and green CI. `develop` requires green CI. Force-push is disabled on both.
4. **From here on, feature → develop merges go through a PR** (`gh pr create`) so CI runs on every change. This has been true in practice since Day 4 (PRs #1–#3). Today makes it enforced.
5. **Verify:** a PR with a deliberately failing test is blocked. Fixing the test turns CI green and the merge is allowed.

Not in the timeline but required for CI to mean anything: **one ruff configuration** shared by CI and the Claude Code hook. Today the rule list lives only in `.claude/hooks/ruff_check.py:21` (see Decision 2).

## Current behavior
1. **No CI exists.** `git ls-files .github` returns nothing. Every check is manual: `/pre-commit`, `python -m pytest`, `npm test`. CLAUDE.md lists "any CI/CD workflow" under *Not present*.
   - **Backend checks today:**
     - `python -m pytest` → 111 passed + 1 strict xfail, offline. `tests/conftest.py` fakes Gemini, Tavily and Redis and blocks sockets (Day 5). It needs no secrets, so it can run in CI unchanged.
     - The suite reaches OCR code: `src/pptx_pipeline.py:3` → `ocr_utils` → `pytesseract`. The Tesseract binary is on the host via `TESSERACT_PATH`, and the Docker runtime stage installs `tesseract-ocr`, `tesseract-ocr-eng` and `poppler-utils` (`Dockerfile:22-26`). A bare Ubuntu runner has neither.
   - **Ruff:**
     - Ruff 0.15.18 is installed on the host but is **not in `requirements.txt`**.
     - There's no `ruff.toml` or `pyproject.toml`. The hook passes `--select E9,F63,F7,F82` itself (`ruff_check.py:21,60`).
     - Measured today:
       - The bug-only set passes on the whole repo.
       - Adding `F401` gives **31 findings** (28 in `src/`, 3 in `scripts/manual/`).
       - Ruff's defaults (`E4,E7,E9,F`) give **90 findings**: 31 F401, 26 E402, 16 F541, 9 F811, 2 E712, 2 E722, 2 E741, 1 E711, 1 F841.
   - **Frontend:**
     - `package-lock.json` is tracked, so `npm ci` works.
     - `npm run build` already passes with `CI=true` (fixed for Vercel in v0.1.1).
     - The local Node version is 22.23.4. `frontend/Dockerfile:6` uses `node:20-alpine`.
   - **Docker:**
     - The backend `Dockerfile` has two stages (builder venv → slim runtime).
     - `frontend/Dockerfile` has `deps → dev / build → nginx`, and the nginx stage is the default target. `docker compose -f docker-compose.yml` builds both.
2. **Requirements encoding.** The first bytes are `FF FE 61 00` (BOM, then `a` in UTF-16LE), 192 lines. `Dockerfile:15-16` installs it with pip on Linux, and Render builds that image today.
3. **Branch protection.** The repo is public. `gh api …/branches` reports `master protected=false` and `develop protected=false`. Anyone with push rights (you) can push straight to either branch or force-push.
   - The CLAUDE.md release flow is "merge `develop` → `master` locally with `--no-ff`, push both, tag". That flow is a direct push to `master`, so it conflicts with "master requires a PR" (see Decision 3).
4. **PR flow.** PRs #1–#3 merged Days 4–5 into `develop`. That was a habit, not a rule.

## Why it matters
1. **No CI:**
   - Day 7–10 moves every module. Suppose a moved import works on the host only because of a stale `__pycache__` or the venv's Python 3.12. Without CI it merges, and Render (3.11, clean image) fails the deploy.
   - Day 5 found B4 (concept maps returned 500) only because a test was written. A test that nobody is *forced* to run stops catching anything.
   - **Concrete example:** a Day 8 PR deletes `ocr_utils.py` but `pptx_pipeline.py` still imports it. The host suite would pass if a stale `.pyc` were importable. CI's fresh checkout fails, and the PR can't merge.
2. **Encoding:** a requirements file pip can't parse means CI installs nothing and every job fails. That's worth one check, not a pre-emptive rewrite of a file Day 10 cleans anyway.
3. **No protection:**
   - A late-night `git push origin develop` skips CI entirely, and a `--force` push can silently drop a merged day.
   - Vercel builds `master` with `CI=true`. v0.1.0 shipped a frontend build that failed there because of ESLint warnings (fixed in v0.1.1). A required `frontend` check catches that class of bug before `master`.
4. **No enforced PR flow:** CI on pushes alone tells you a branch is broken *after* it landed. Required checks on PRs stop it *before*.
5. **The verify step proves the gate.** A protection rule with a misspelled check name never blocks anything (see The concept → required checks).

## The concept

### Continuous integration
CI means every change is built and tested automatically, on a clean machine, before it joins the shared branch. The point isn't the tests themselves (you can run those locally). The point is **removing "works on my machine"**:
- a fresh checkout, so no untracked files or stale caches
- a pinned interpreter
- a clean dependency install
- no access to your `.env`

A CI run answers one question: *does the code as committed, and only as committed, work?*

GitHub Actions terms:
- **workflow:** a YAML file in `.github/workflows/`
- **trigger:** the `on:` block — `push`, `pull_request`, `workflow_dispatch` (manual)
- **job:** runs on a fresh VM, the runner. Jobs run in parallel unless `needs:` chains them.
- **step:** a shell command (`run:`) or a reusable action (`uses:`)

Each job reports a **check run** to the commit or PR. Branch protection gates merges on those check runs.

### Hermetic CI and why Day 5 came first
A CI job should need **no secrets** to test the code. Secrets in CI mean:
- forks can't run it (GitHub withholds secrets from fork PRs)
- a compromised dependency can exfiltrate them
- tests become slow, flaky and expensive (live Gemini calls cost money and are rate-limited)

Day 5's conftest fakes Gemini, Tavily and Redis at the SDK boundary and refuses network sockets, so CI runs the full suite with zero secrets. Secrets belong to *deploy* jobs (CD, Days 21–22), never to test jobs.

### Environment parity
CI should match production where it matters:
- the same Python minor version (3.11, as the Docker image and Render use)
- the same system packages (Tesseract, Poppler)
- the same build flags (`CI=true` for the CRA build, as Vercel uses)

The **docker job** is the strongest parity check: it builds the exact image Render builds. If `pip install` fails inside `python:3.11-slim`, CI fails before Render does.

Pitfall: testing on the host's 3.12 while deploying on 3.11. The two differ in typing features, deprecations and wheel availability.

### Caching
A clean VM reinstalls everything, which is slow. CI caches are keyed on a lockfile hash:
- `setup-python` with `cache: pip` keys on `requirements.txt`
- `setup-node` with `cache: npm` keys on `package-lock.json`
- Docker BuildKit's `type=gha` cache stores image layers in the Actions cache

When a lockfile changes, the key changes and the cache rebuilds. Pitfalls:
- caching `node_modules` directly instead of npm's download cache, which breaks across Node versions
- forgetting `cache-dependency-path` when the lockfile isn't at the repo root

### Required status checks
Branch protection lists **check names** that must be green before a merge. Pitfalls:
- **Names must match exactly.** The name is the job's `name:` (or its id if there's no name). A typo means the rule waits forever ("Expected — waiting for status"), or, if the name is never reported, it blocks every PR. That's why today's verify step uses a deliberately failing PR.
- **Path filters break required checks.** If a workflow skips itself with `paths:` for docs-only PRs, a required check never reports and the PR is stuck. Use filters *inside* jobs, or no filters at all. Today: no filters.
- **"Require branches to be up to date"** (`strict`) forces a rebase or merge of the base branch before merging, so CI tests the real merge result. It's useful with many parallel PRs. With one PR per day it mostly adds clicks.
- **Admin enforcement.** By default, repo admins can bypass protection. For a solo owner, that makes the rules advisory. `enforce_admins` makes them bind you too, which is the point of a gate. The cost is that emergencies also need a PR.
- **Required approvals.** You can't approve your own PR. A solo repo that requires 1 approval can never merge, so it must stay at 0.

### Concurrency, permissions and supply chain
- `concurrency:` with `cancel-in-progress` stops superseded runs when you push twice quickly. That saves minutes and avoids confusing out-of-order results.
- `permissions: contents: read` gives the workflow's `GITHUB_TOKEN` least privilege. The default can be read/write on older repos. A test job never needs to write.
- Third-party actions run code with that token. Pinning `@v4` trusts the tag, which the maintainer can move. Pinning a full commit SHA is the hardened option (after the 2025 `tj-actions/changed-files` compromise, it's standard advice for production). Today uses only official GitHub and Docker actions on major tags. SHA pinning plus Dependabot can come with CD on Day 21.

### Linting in CI: ratchets, not big bangs
Turning on a full rule set over legacy code produces 90 findings at once. People then either mass-autofix (a huge, unreviewable diff in files about to move anyway) or disable the linter.

The usual pattern is a **ratchet**:
- gate on the rules that are already clean (definite bugs)
- tighten the set when the code is cleaned up (here, Day 10's dead-code pass)
- never loosen it

Keeping one config file (`ruff.toml`) means the editor hook, local runs and CI enforce the same thing.

### CI vs CD
CI verifies. CD ships. Render and Vercel already auto-deploy on push to `master`, which is CD without a CI gate. Today adds the gate *before* `master`. Days 21–22 make the deploy itself wait for CI, add staging, and add post-deploy checks.

## Decisions

### 1. `requirements.txt` encoding (timeline "Decision")
- **A — Keep UTF-16LE for now:** pip reads it via the BOM (the Docker build proves it on Linux). The first CI run confirms it on the runner, and Day 10 (T3) converts it together with the dependency cleanup. No churn today, but the file keeps its trap for tools that ignore BOMs (`git diff` shows it as binary, `cache-dependency-path` hashing is fine either way).
- **B — Convert to UTF-8 + LF today:** removes the trap now and makes the file diffable before Day 10 edits it. It's a whole-file rewrite (192 lines) outside today's purpose, and CLAUDE.md's encoding convention would need updating today rather than with T3.
- **Recommendation: A**, per the timeline's "only if pip chokes". If the first CI run shows pip failing on it, I stop and ask (as the timeline says) before converting.

### 2. Ruff in CI — rule set and how ruff gets installed (new tool → needs approval)
- **A — Ratchet:** add a `ruff.toml` selecting the bug-only set (`E9,F63,F7,F82`, already clean repo-wide) plus `target-version = "py311"`. The hook reads that file instead of its own `--select`, and CI installs a pinned `ruff==0.15.18` in the backend job only (not in `requirements.txt`, so the Docker image doesn't grow). Day 10 (T3) adds `F401` and then ruff's defaults after deleting dead code.
- **B — Ruff defaults now:** select `E4,E7,E9,F` and fix all 90 findings today (56 auto-fixable, 34 by hand: E402 in scripts, bare excepts, `== True`). Stricter from day one, but it's a large diff across ~40 legacy files that Days 7–9 move and split anyway, with no behavior change to show for it.
- **Recommendation: A.** CI gates on what's clean today and tightens on Day 10. Installing ruff as a pinned CI-only tool is a new dependency in the CI environment, so it needs your OK.

### 3. Branch protection — enforcement and the release flow
- **A — Classic branch protection with `enforce_admins` on both branches:**
  - `master`: PR required, 0 approvals, required checks `backend` / `frontend` / `docker`.
  - `develop`: same required checks.
  - Both: no force-push, no deletion, not strict.
  - Rules bind you too, so releases become a **PR `develop` → `master`** merged with "Create a merge commit" (equivalent to `--no-ff`), then `git tag vX.Y.Z` on the merge commit and `git push --tags`. The CLAUDE.md Git-flow bullet changes accordingly.
- **B — Same rules without admin enforcement:** you keep the local `--no-ff` merge + push release flow unchanged, but every rule is bypassable by you, so in practice nothing is enforced (and GitHub shows "bypassed" on direct pushes).
- **Recommendation: A.** A gate you can walk around isn't a gate, and the PR-based release is what `docs/timeline.md:39` already describes ("Release days: PR develop → master").
- **Note:** "develop requires green CI" also blocks direct pushes in practice (a pushed commit has no checks yet), so both branches effectively require PRs. That matches timeline bullet 4.
- **Who applies it:** this changes GitHub settings (outward-facing). I'll run the `gh api` calls in checkpoint 2 **only after the first CI run has reported the three check names** and you confirm. Or you can run them yourself; the exact commands go in the Outcome either way.

### Approved 2026-11-06
1A, 2A, 3A. Ruff 0.15.18 pinned, CI job only. Official actions on major-version tags are OK; add
"pin actions to commit SHAs" to Day 60's security review in the timeline. `npm ci` locally is fine.
Owner additions and changes:
- **Node 24 everywhere:** Vercel builds production on Node 24.x (v0.1.1 built there), so
  `ci.yml` uses Node 24 and `frontend/Dockerfile` moves to `node:24-alpine`. CLAUDE.md notes
  that Vercel's Node.js Version setting is 24.x and must stay in sync with CI.
- **`ci.yml`:** top-level `permissions: contents: read`; triggers `pull_request` + `push` to
  `develop` and `master` (never `pull_request_target`); concurrency group per ref with
  cancel-in-progress; `timeout-minutes` on every job.
- **Branch protection, both `master` and `develop`:** require a PR with 0 approvals; required
  checks = the three job names; not strict; block force-pushes and deletions; include
  administrators. Show the `gh api` commands and wait for OK before running them.
- **CLAUDE.md Git flow:** a release is a PR `develop` → `master` (merge commit), then a tag; a
  hotfix is a PR into `master`, then a PR `master` → `develop`.
- **Gate test:** the failing-test PR is closed after it's shown blocked, never merged, and its
  branch deleted.
- Stop after each checkpoint.

## Plan

### Checkpoint 1 — workflow + ruff config (5 file operations, all local)
- `.github/workflows/ci.yml` — new. Workflow `CI`:
  - **Triggers:**
    - `pull_request` to `develop`, `master`
    - `push` to `develop`, `master` (runs after merge too; feature-branch pushes are covered by their PR, so no double runs)
    - `workflow_dispatch`
  - **Workflow settings:**
    - `permissions: contents: read`
    - `concurrency: ci-${{ github.ref }}`, cancel in progress
  - **Job `backend`** (ubuntu-latest, 20 min timeout):
    - `actions/checkout@v4`
    - `actions/setup-python@v5` with Python 3.11, `cache: pip`, `cache-dependency-path: requirements.txt`
    - `apt-get install tesseract-ocr tesseract-ocr-eng poppler-utils`, mirroring the Dockerfile runtime stage
    - `pip install -r requirements.txt`
    - `pip install ruff==0.15.18`
    - `ruff check .`
    - `python -m pytest -q`, with no secrets and no `.env`; the conftest supplies dummies
  - **Job `frontend`** (ubuntu-latest, 15 min timeout, working directory `frontend`):
    - `actions/setup-node@v4` with Node 22 (matches local; see Risks on Docker's Node 20), `cache: npm`, `cache-dependency-path: frontend/package-lock.json`
    - `npm ci`
    - `npm test -- --watchAll=false` (Actions sets `CI=true`)
    - `npm run build`
  - **Job `docker`** (ubuntu-latest, 30 min timeout):
    - `docker/setup-buildx-action@v3`
    - `docker/build-push-action@v6` twice, `push: false`, `cache-from` / `cache-to: type=gha` with a per-image `scope`: backend (context `.`) and frontend (context `./frontend`, default nginx target)
- `ruff.toml` — new:
  - `target-version = "py311"`
  - `[lint] select = ["E9","F63","F7","F82"]`
  - a comment saying Day 10 ratchets it to F401 and then the defaults
  - `extend-exclude = ["frontend"]` (`venv` is already gitignored and ruff honours `.gitignore`)
- `.claude/hooks/ruff_check.py` — drop the hard-coded `--select` so the hook reads `ruff.toml`. Update the docstring and message to say where the rules live. The `RUFF_RULES` constant is deleted.
- **Local checks** (the same commands CI runs):
  - `ruff check .`
  - `python -m pytest -q`
  - YAML parse of `ci.yml`
  - `cd frontend; npm ci; npm test -- --watchAll=false; npm run build` (`npm ci` reinstalls `node_modules`; tell me if you'd rather I skip it and use `npm test` on the existing install)
  - `docker build` of both images, or `docker compose -f docker-compose.yml build`
  - one hook dry-run on a `.py` file
- **Then you:** commit, push `feature/day06-ci`, open the PR into `develop` → first real CI run. I read the results with `gh run view` (read-only) and record timings.

### Checkpoint 2 — branch protection (after the first green run; GitHub settings, no files)
- `gh api -X PUT repos/ArhaanAli04/rag-study-assistant/branches/master/protection` with:
  - `required_status_checks: {strict: false, contexts: [backend, frontend, docker]}`
  - `enforce_admins: true`
  - `required_pull_request_reviews: {required_approving_review_count: 0}`
  - `restrictions: null`, `allow_force_pushes: false`, `allow_deletions: false`
- The same for `develop`, with `required_pull_request_reviews: null` (green checks only, as the timeline says).
- Read back with `gh api …/protection` and paste the result into the Outcome.
- Order matters: protecting `develop` **before** today's PR merges means today's PR is the first one gated.

### Checkpoint 3 — the gate test + docs (≈ 5 file operations)
- **Verify (you run the git/gh parts; the skill forbids me pushing):**
  1. On a throwaway branch from `develop`, add one commit with `assert False` in a new `tests/test_ci_gate.py`.
  2. Open a PR. `backend` goes red and the merge button is blocked.
  3. Delete the file in a second commit. CI goes green and the merge is allowed.
  4. Close the PR without merging and delete the branch.

  I'll give the exact commands and read the run results with `gh` (read-only).
- `CLAUDE.md`:
  - Git flow: releases go via a PR `develop` → `master` with a merge commit, then tag. Branch protection is described.
  - Key Commands: `ruff check .` (reads `ruff.toml`).
  - *Not present*: remove "any CI/CD workflow" and note CI exists and CD is Day 21.
  - Claude Code Setup: the hook reads `ruff.toml`.

  (Not the Current Status block.)
- `docs/claude-cheatsheet.md` — only if it describes the release or merge commands that change. I'll check first and list the exact lines before editing.
- Brief `## Outcome`, then the post 9 material-log line. Days 4–10 feed only post 9.
- `docs/learning/ai-concepts.md`: CI isn't one of the 19 AI concepts, so it most likely gets no notes. I'll check and say so.

**New dependencies:** `ruff==0.15.18` installed in the CI job only (needs approval, Decision 2). GitHub Actions used: `actions/checkout@v4`, `actions/setup-python@v5`, `actions/setup-node@v4`, `docker/setup-buildx-action@v3`, `docker/build-push-action@v6`. These are CI tooling, not app dependencies, but listed here for your approval too. Nothing is added to `requirements.txt` or `package.json`.

## UI integration
Backend-only — no user-visible change. Today adds a CI workflow, a lint config, a hook tweak and GitHub branch settings. No endpoint, response field, status, flag or screen changes. The frontend is only *tested and built* by CI, not modified.

## Verification
- **Local, before the first push:**
  - `ruff check .` clean
  - `python -m pytest -q` → 111 passed + 1 xfailed (Day 5 baseline 23.3 s host)
  - `npm test -- --watchAll=false` → 11 passed
  - `npm run build` with no warnings
  - both images build
  - `ci.yml` parses
- **First CI run on the PR:**
  - all three jobs green
  - pip reads the UTF-16 `requirements.txt` (Decision 1)
  - the xfail stays an xfail on Linux (B3 behaves the same as in the container)
  - Record wall time per job, cold (first run) and warm (a re-run with caches).
- **Protection:** `gh api …/branches/{master,develop}/protection` shows the three contexts, `enforce_admins.enabled: true`, `allow_force_pushes.enabled: false`. A direct `git push origin develop` of a new commit is rejected; you can try this optionally with an empty commit on a scratch clone.
- **Gate test:** failing PR blocked → fixed PR mergeable (Checkpoint 3).
- No retrieval, prompt or cache changes, so no eval numbers.

## Risks & open questions
- **OpenCV wheel clash (B3) on the runner:** three `cv2` wheels, and pip's install order decides which wins. In the slim container a headless build won and the suite passed (`opencv-python` non-headless needs `libGL`, which ubuntu-latest has anyway). If the runner ends up with a different winner, `test_table_extraction_on_image` could XPASS(strict) and fail CI. That would be good news about B3, but it would block today's PR. If it happens, I report it and don't touch requirements (Day 10).
- **Backend job time:** a cold `pip install` of ~190 pinned packages (camelot, img2table, faiss, opencv ×3) may take several minutes. The pip cache helps on later runs. The numbers get recorded, not guessed.
- **Docker job time:** the backend image cold build may take 5–10 min. The GHA layer cache keeps warm runs short. If it's too slow to be a required check, an option is to require only `backend` + `frontend` and keep `docker` informative. I'd ask before changing.
- **Node versions:** CI uses Node 22 to match your machine, but `frontend/Dockerfile` uses `node:20-alpine`, and Node 20 reached end-of-life in April 2026. Vercel's Node setting isn't visible from the repo. **Question:** bump the Dockerfile to `node:22-alpine` today (one line, rebuilt by the docker job), or leave it for Day 10's cleanup?
- **Jest worker warning (Day 5):** if "A worker process has failed to exit gracefully" shows up in CI, follow the Day 5 note (`--detectOpenHandles`, fake the timer in the triggering test).
- **Release flow change (Decision 3A):** Day 10's v0.2.0 release becomes PR-based. `docs/timeline.md:39` already says so; CLAUDE.md is updated in checkpoint 3.
- **Render / Vercel deploy on `master` push without waiting for CI:** unchanged today. With 3A, nothing reaches `master` without green CI anyway. Gating the deploy itself is Day 21.
- **Found, not fixed:** 28 unused imports in `src/` and 3 in `scripts/manual/` (Day 10, T3 ratchet); `frontend/Dockerfile` Node 20 EOL (question above — answered: bumped to Node 24).

## Outcome

### CI measurements
First run — PR #4 (`feature/day06-ci` → `develop`, head `d10ed52`), run 42098435785, cold caches,
2026-11-05 19:55–20:04 UTC. All three jobs from `github-actions` (app id 15368):

| Job | Result | Wall time | Notes |
|---|---|---|---|
| backend | success | 6m54s | pip read the UTF-16LE `requirements.txt` (Decision 1A holds); ruff 0.15.18 clean; pytest **111 passed, 1 xfailed in 23.95 s** — the B3 strict xfail stays an xfail on Linux |
| frontend | success | 49s | Node 24; 5 suites / 11 tests passed; `npm run build` with `CI=true`; no Jest worker warning |
| docker | success | 9m16s | backend + frontend images built, no push |

Other checks on the PR, not required (external integrations): GitGuardian Security Checks,
Vercel Preview Comments, Vercel (commit status).

### Branch protection (applied 2026-11-06, owner-approved)
Same body for both branches (required checks bound to the GitHub Actions app, id 15368, so a
same-named check from another integration can't satisfy them). To restore the rules (e.g. after
Day 60's history purge), save this as `branch-protection.json` **outside the repo** and re-run the
commands below, then the read-back:

```json
{
  "required_status_checks": {
    "strict": false,
    "checks": [
      { "context": "backend",  "app_id": 15368 },
      { "context": "frontend", "app_id": 15368 },
      { "context": "docker",   "app_id": 15368 }
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "required_approving_review_count": 0,
    "dismiss_stale_reviews": false,
    "require_code_owner_reviews": false
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_linear_history": false,
  "required_conversation_resolution": false,
  "lock_branch": false
}
```

```bash
B=<path to branch-protection.json>
gh api -X PUT repos/ArhaanAli04/rag-study-assistant/branches/develop/protection --input "$B"
gh api -X PUT repos/ArhaanAli04/rag-study-assistant/branches/master/protection  --input "$B"
for br in develop master; do
  gh api repos/ArhaanAli04/rag-study-assistant/branches/$br/protection --jq \
   "\"$br: checks=\([.required_status_checks.checks[] | \"\(.context)@\(.app_id)\"]) strict=\(.required_status_checks.strict) pr_approvals=\(.required_pull_request_reviews.required_approving_review_count) enforce_admins=\(.enforce_admins.enabled) force_push=\(.allow_force_pushes.enabled) deletions=\(.allow_deletions.enabled) linear=\(.required_linear_history.enabled)\""
done
```

Read-back on 2026-11-06:

```
develop: checks=["backend@15368","frontend@15368","docker@15368"] strict=false pr_approvals=0 enforce_admins=true force_push=false deletions=false linear=false
master:  checks=["backend@15368","frontend@15368","docker@15368"] strict=false pr_approvals=0 enforce_admins=true force_push=false deletions=false linear=false
```

Right after: PR #4 `mergeable=MERGEABLE mergeStateStatus=CLEAN` — the existing green run satisfies
the new rules.

### First push run on `develop`
PR #4 merged (`132182f`, merge commit). `push` run 42101715872: **success** — frontend 41s,
backend 1m40s, docker 9m02s. Docker was effectively cold again: Actions caches are scoped to the
ref that wrote them, and a PR's caches (`refs/pull/4/merge`) aren't readable from `develop`.
`gh cache list` afterwards shows the BuildKit layers and the backend/frontend cache indexes now
stored under `refs/heads/develop`, which every later PR into `develop` can read.

### Gate test (timeline Verify) — passed
Run by Claude under a one-time, owner-granted exception to the run-day "no git writes" rule,
limited to the throwaway branch `test/ci-gate`.
- `git worktree add ..\rag-ci-gate -b test/ci-gate origin/develop`; one commit `ca50abf` adding
  `tests/test_ci_gate.py` (a single `assert False`); pushed with an explicit refspec
  (`test/ci-gate:test/ci-gate` — `worktree add` had set the branch to track `origin/develop`).
- **PR #5** "DO NOT MERGE - day 06 CI gate test" → `develop`. **Run 42103753219:**
  `backend` **failure** (`FAILED tests/test_ci_gate.py::test_ci_gate_blocks_merge` — 1 failed,
  111 passed, 1 xfailed in 27.02 s; nothing else failed), `frontend` success, `docker` success
  (external Vercel and GitGuardian checks also green).
- **`mergeStateStatus = BLOCKED`** while open (`mergeable = MERGEABLE`: no conflicts, blocked only by
  the required check). `gh pr merge` was never run — BLOCKED is the proof.
- Closed **unmerged** (`state=CLOSED`, `mergedAt=null`, 2026-11-05T20:32:01Z).
- Cleanup: worktree removed and pruned by Claude. The local and remote branch were deleted by the
  owner: the repo's `guard_commands.py` hook blocks `git branch -D`, and `gh pr close
  --delete-branch` stopped before the remote delete because the worktree still held the branch
  (lesson: remove the worktree *before* `gh pr close --delete-branch`). Verified afterwards:
  `git ls-remote --heads origin test/ci-gate` and `git branch --list test/ci-gate` both empty;
  `develop` (`132182f`) and `master` (`60f52bf`) untouched.
- The "fixing it turns CI green and allows the merge" half of the timeline bullet is shown by
  PR #4 (green → `CLEAN` → merged) rather than by fixing PR #5, which the owner chose to close
  unmerged.

### Files changed
**Checkpoint 1 — merged in PR #4 (`d10ed52`)**
- `.github/workflows/ci.yml` — new: `backend`, `frontend`, `docker` jobs; `pull_request` + `push` to develop/master + `workflow_dispatch`; `permissions: contents: read`; per-ref concurrency with cancel-in-progress; `timeout-minutes` 25 / 15 / 30
- `ruff.toml` — new: `target-version = "py311"`, bug-only `E9,F63,F7,F82`, ratchet note for Day 10
- `.claude/hooks/ruff_check.py` — reads `ruff.toml` instead of its own `--select`; `RUFF_RULES` deleted
- `frontend/Dockerfile` — `node:20-alpine` → `node:24-alpine`
- `docs/briefs/day06.md` — brief + approvals

**Checkpoint 2 — GitHub settings, no files:** branch protection on `develop` and `master` (above).

**Checkpoint 3 — `feature/day06-docs`**
- `docs/briefs/day06.md` — this Outcome
- `CLAUDE.md` — Git flow (protection rules; day PRs; PR-based release with a merge commit, then tag; hotfix PR into `master`, then `master` → `develop`); repo tree (`.github/workflows/ci.yml`, `ruff.toml`); Tech Stack `CI` row; Working: CI; Not present: "any CI/CD workflow" → CD only (Days 21–22); Key Commands: `ruff check .`, `gh pr checks`, `gh run list`; Node.js 24 kept in sync across Vercel, CI and the Dockerfile; hooks line (rules from `ruff.toml`). Current Status block untouched
- `docs/timeline.md` — Day 60: pin GitHub Actions to commit SHAs (owner request)
- `docs/posts/09-launch-recap.md` — Day 6 material-log line

### Checks
| Check | Result |
|---|---|
| `python -m py_compile .claude/hooks/ruff_check.py` | ok |
| `ruff check .` (settings resolved from `ruff.toml`) | All checks passed |
| Hook dry-run: `src/main.py` / file with an undefined name | exit 0 / exit 2 with `F821` |
| `ci.yml` YAML parse | 3 jobs, triggers, permissions, timeouts as intended |
| Local `python -m pytest -q`, no API keys | 111 passed, 1 xfailed (57.8 s, Docker build in parallel) |
| Local `npm ci` + `npm test -- --watchAll=false` + `npm run build`, `CI=true`, Node 22 | 11/11 tests; build without warnings |
| Local `docker compose -f docker-compose.yml build`; frontend image on `node:24-alpine` | both built; Node v24.22.2 |
| CI run on PR #4 (cold) | all green — backend 6m54s, frontend 49s, docker 9m16s |
| CI push run on `develop` (`132182f`) | all green — backend 1m40s, frontend 41s, docker 9m02s |
| Branch protection read-back | as approved, both branches |
| Gate test, PR #5 | backend red, `BLOCKED`, closed unmerged |

### UI integration
| Change | Frontend | What the user sees |
|---|---|---|
| CI workflow, `ruff.toml`, hook, branch protection | — | backend-only / repo tooling: no endpoint, field, status, flag or screen changed |
| `frontend/Dockerfile` Node 24 | — | nothing: same static bundle; only the Docker build image's Node changed (Vercel already on 24.x) |

### Deferred / dropped
- Decision 1A: `requirements.txt` stays UTF-16LE — pip read it on the runner; conversion stays with T3 on Day 10.
- Ruff ratchet (F401, then defaults; 28 + 3 findings measured) → Day 10.
- Pinning actions to commit SHAs → Day 60 (added to the timeline).
- Gating the Render/Vercel deploys themselves on CI → Days 21–22.
- No learning notes: none of the 19 concept headings in `docs/learning/ai-concepts.md` covers CI.

### Follow-ups found today
- **Day 60's history purge needs a force-push**, which protection now blocks for everyone
  (`enforce_admins`). If that decision is ever taken, protection on the affected branch must be
  lifted temporarily and restored with the same body. Added to Day 60's decision bullet in
  `docs/timeline.md` (owner request); the body and commands are in this Outcome.
- **Cleanup order** for any future throwaway-worktree PR: `git worktree remove` before
  `gh pr close --delete-branch`.

### Numbers for the tracker / post 9
- CI cold (PR #4): backend 6m54s, frontend 49s, docker 9m16s. Push on `develop`: 1m40s / 41s /
  9m02s. pytest inside CI: 111 passed, 1 xfailed in 23.95 s.
