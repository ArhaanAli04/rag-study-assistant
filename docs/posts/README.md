# LinkedIn Post Series

Ten posts built from the 61-day timeline (`docs/timeline.md`). Each post bundles several
AI-engineering concepts, explains them in plain words, and shows how they were implemented
and measured in this project.

Material is gathered **while building**: at the end of every `/run-day`, Claude appends a
"Material log" entry to each post file the day feeds (see the mapping below). When a post's
"Publish after" day is done, its file already holds the takeaways, numbers and screenshot
list — writing the post is assembly, not recall.

## Day → post mapping

| Post | File | Fed by days | Publish after |
|---|---|---|---|
| 1 | `01-multi-tenant-security.md` | 1–3 | Day 3 (v0.1.0) |
| 2 | `02-measuring-retrieval.md` | 11–12 | Day 12 |
| 3 | `03-hybrid-search-postgres.md` | 13–17 | Day 17 (v0.3.0) |
| 4 | `04-observability-cost.md` | 23–25 | Day 25 |
| 5 | `05-retrieval-upgrades-measured.md` | 26–32 | Day 32 (v0.5.0) |
| 6 | `06-agentic-rag-langgraph.md` | 33, 34, 35, 37 | Day 37 (v0.6.0) |
| 7 | `07-indirect-prompt-injection.md` | 35 (moderation), 36 | Day 37 |
| 8 | `08-features.md` | 39, 44–52 (study features), 56–59 (UI) | Day 59 (v0.9.0) |
| 9 | `09-launch-recap.md` | **every day** (one line each), plus 60–61 | Day 61 (v1.0.0) |
| 10 | `10-projects-connectors-memory.md` | 18–20 (projects), 40–43 (connectors), 53–55 (memory) | Day 55 |

Days 4–10, 21–22 and 38 (Docker, CI, refactor, CD, auth hardening) feed only post 9. When days are added to or
moved in the timeline, update this table — `/run-day` reads it.

## Format for every post

- Structure: hook (a problem or a number) → the concept in plain words → what we built →
  the measured result → one honest lesson → repo link.
- Concept posts: PDF carousel, 6–10 slides. Features and launch: short demo video.
- Visuals: one architecture/flow diagram, one real screenshot, one before/after chart or
  table, at most one code snippet card.

## Rules

- Claim only measured numbers; say what was measured and on what set.
- Screenshots use demo documents only — never real users' notes. Langfuse traces contain
  chunk text.
- Security posts go out only after the fix is deployed, and describe the class of bug, not a
  step-by-step exploit.
