# Post 9 — "61 days rebuilding a RAG app: what I'd do first next time"

Publish after: Day 61 (v1.0.0) · Fed by days: every day (one line each), plus 60–61 · Format: text + 2–3 images + demo video

## Hook
I audited my own RAG app, found 41 gaps, fixed them and added projects, connectors, memory and six study features in 61 days. The numbers, the
architecture, and the order I'd do it in next time.

## Concepts to explain (plain words)
- The full architecture, one line per layer
- The before/after numbers from posts 1–8 and 10 in one table
- Engineering foundations in one paragraph: Docker, tests, CI/CD, migrations

## Outline
1. Hook
2. Architecture: before vs. after
3. The numbers table (from every post)
4. Engineering foundations (one paragraph)
5. What I'd do first next time (measure before optimizing, isolate tenants from day one…)
6. Links to posts 1–8 and 10, demo, repo

## Visuals needed
- [ ] Final architecture diagram (refresh of docs/architecture.png)
- [ ] Summary numbers table
- [ ] Demo video of the finished app

## Material log
<!-- /run-day appends one line per day below, newest last: "Day N — <what shipped> — <one number or lesson>". -->
- Day 1 — per-user semantic cache (G6), CORS allowlist (G4), debug prints → logging (O2), develop/feature git flow — live check: user B got 0 of user A's sources; a foreign origin's CORS preflight went from 200 to 400
- Day 2 — JWTs out of every log (G8: path-only request logs, handler-level redaction filter, uvicorn query strings stripped) and narrow prompt-injection refusals over SSE (G1) — token lines in app.log 420 → 0; a test also caught that the UI's "Step-by-step" mode had never worked (3 modes, 2 distinct prompts)
- Day 3 — per-user UUID upload storage (G7) and working account deletion across SQLite, disk, FAISS, BM25 and Redis (B1); release v0.1.0 prepared — live: B got 0 of A's sources, and SQLite handed a freed id (3) straight to the next sign-up, which the purge kept clean
- Day 4 — Docker-first dev: compose base + dev override with hot reload, multi-stage non-root backend image with a healthcheck, `.env.example`, `scripts/dev.ps1` — the old image had the local user database and 6 uploaded PDFs baked in (now 0 bytes of user data), and the Docker frontend had been calling the production API; backend reload measured at 13.5–15.1 s, 9.9 s of it one eagerly imported table/OCR library chain
- Day 5 — offline test safety net: pytest config fixed (T1), fakes for Gemini, Tavily and Redis at the SDK boundary, a socket guard, 18 API smoke tests incl. the SSE contract — 84 → 111 backend tests, no keys and no network, 23 s on the host; the new tests immediately found two silent production bugs: concept maps 500'd whenever a node had no sources (B4, fixed), and an OpenCV wheel clash has disabled image/PPTX table extraction (B3, Day 10)
- Day 6 — CI on GitHub Actions (backend: Python 3.11, ruff, offline pytest with zero secrets; frontend: Node 24 tests + production build; docker: both images) and branch protection on master and develop that binds the admin too — first cold run backend 6m54s / frontend 49s / docker 9m16s; a PR with one deliberately failing test (#5) was BLOCKED and closed unmerged; lesson: Actions caches are scoped to the ref that wrote them, so the first push to develop rebuilt Docker from scratch (9m02s) — the cache the PR run had just written wasn't visible to it
- Day 7 — the backend became one package (`backend/app/`, absolute `app.*` imports) with a `core/` layer: one typed pydantic-settings class for all 14 env vars (secrets as `SecretStr`, no more scattered `os.getenv`/`load_dotenv`) and a request-ID middleware that stamps every log line — 90 files moved with git history intact, 135 import lines rewritten, tests 111 → 134 green on host and in the container; lesson: the same config file had been loaded twice under two module names (`config.…` and `src.config.…`), and the only visible symptom was a duplicated deprecation warning (156 → 154 warnings once fixed)
- Day 8 — `backend/app/` regrouped into `db/`, `ingestion/`, `retrieval/`, `generation/`, `services/`, `schemas/` (42 modules, all recorded as git renames, imports rewritten from one old→new table; 134 tests green before and after), OCR/table libraries imported lazily, and six parser tests that had been passing without opening their files made real — the ingestion chain's share of startup fell 10.2 s → 5.8 s, but `app.main` still takes 23–25 s because each Gemini client costs ~3 s to build (Day 9); the first honest run of those tests found B5: image deskew rotates every scan 90° and OCR returns an empty string
