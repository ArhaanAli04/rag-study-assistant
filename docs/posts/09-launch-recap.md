# Post 9 — "51 days rebuilding a RAG app: what I'd do first next time"

Publish after: Day 51 (v1.0.0) · Fed by days: every day (one line each), plus 50–51 · Format: carousel + demo video

## Hook
I audited my own RAG app, found 41 gaps, fixed them and added six study features in 51 days. The numbers, the
architecture, and the order I'd do it in next time.

## Concepts to explain (plain words)
- The full architecture, one line per layer
- The before/after numbers from posts 1–8 in one table
- Engineering foundations in one slide: Docker, tests, CI/CD, migrations

## Slide outline
1. Hook
2. Architecture: before vs. after
3. The numbers table (from every post)
4. Engineering foundations (one slide)
5. What I'd do first next time (measure before optimizing, isolate tenants from day one…)
6. Links to posts 1–8, demo, repo

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
