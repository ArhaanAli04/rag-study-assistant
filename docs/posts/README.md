# LinkedIn Post Series

Nine posts built from the 51-day timeline (`docs/timeline.md`). Each post bundles several
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
| 4 | `04-observability-cost.md` | 20–22 | Day 22 |
| 5 | `05-retrieval-upgrades-measured.md` | 23–29 | Day 29 (v0.4.0) |
| 6 | `06-agentic-rag-langgraph.md` | 30, 31, 32, 34 | Day 34 (v0.5.0) |
| 7 | `07-indirect-prompt-injection.md` | 32 (moderation), 33 | Day 34 |
| 8 | `08-features.md` | 36–45 (study features), 46–49 (UI) | Day 49 (v0.7.0) |
| 9 | `09-launch-recap.md` | **every day** (one line each), plus 50–51 | Day 51 (v1.0.0) |

Days 4–10, 18–19 and 35 (Docker, CI, refactor, CD, auth hardening) feed only post 9. When days are added to or
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
