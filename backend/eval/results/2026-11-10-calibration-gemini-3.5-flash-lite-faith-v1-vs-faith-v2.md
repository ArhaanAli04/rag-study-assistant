# Judge calibration — faith-v1 vs faith-v2 — 2026-11-10

Same 20 answers and reference labels (Claude (claude-opus-5-5), blind; disagreements adjudicated by the owner); relevance prompt unchanged. **faith-v2's agreement is optimistic: its rules were written after reading this set's disagreements, so it was tuned on the data it is scored on.** The full run is its first unseen test.

| Dimension | Judge vs judge faith-v1 → faith-v2 | Judge vs reference faith-v1 → faith-v2 (agreement / κ) | Trusted |
|---|---|---|---|
| faithfulness | 0.95 → 1.00 | 0.90 / 0.76 → 1.00 / 1.00 | yes → yes |
| relevance | 1.00 → 1.00 | 1.00 / 1.00 → 1.00 / 1.00 | yes → yes |
| citations | 0.95 → 1.00 | 0.90 / 0.75 → 1.00 / 1.00 | yes → yes |

## Labels faith-v2 changed (judge / replica)

| Id | Dimension | Reference | faith-v1 | faith-v2 |
|---|---|---|---|---|
| g-017 | faithfulness | not_in_context | supported / not_in_context | not_in_context / not_in_context |
| g-017 | citations | some_wrong | correct / some_wrong | some_wrong / some_wrong |
| h-09 | faithfulness | not_in_context | supported / supported | not_in_context / not_in_context |
| h-09 | citations | some_wrong | correct / correct | some_wrong / some_wrong |

## faith-v2 disagrees with an adjudicated supported / correct label

None: no answer ruled supported (or correct) was marked otherwise by either pass.
