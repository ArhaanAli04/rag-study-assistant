# Judge calibration — gemini-3.5-flash-lite — 2026-11-10

20 answers from `gemini-3.5-flash-lite` (mode `quick`), labelled blind (`generation_calibration_v1.labels.jsonl`). **Reference labels: Claude (claude-opus-5-5), blind; disagreements adjudicated by the owner.** Each answer was judged twice by `gemini-3.5-flash-lite` (prompts faith-v2, rel-v1, temperature default (1.0; 3.5 Flash-Lite ignores custom values)). Commit `8de3b1b`. Generator and judge are the same model (gemini-2.5-flash-lite is not served to new projects), so the reference labels, from a different model family, are the only check on self-preference.

A dimension is **trusted** only if the judge agrees with itself (≥ 0.80) and with the reference labels (κ ≥ 0.40, or agreement ≥ 0.80 when κ is undefined because one label covers everything). With 20 items κ's interval is wide: this separates usable from not, not 0.7 from 0.8.

| Dimension | Judge vs judge: agreement / κ | Judge vs reference: agreement / κ / weighted κ (n) | Trusted |
|---|---|---|---|
| faithfulness | 1.00 / 1.00 | 1.00 / 1.00 / 1.00 (17) | **yes** |
| relevance | 1.00 / 1.00 | 1.00 / 1.00 / 1.00 (18) | **yes** |
| citations | 1.00 / 1.00 | 1.00 / 1.00 / 1.00 (16) | **yes** |

## Label distributions — reference vs judge

- **faithfulness** — reference {'supported': 14, 'not_in_context': 3, 'contradicted': 0, 'no_claims': 3}; judge {'supported': 14, 'not_in_context': 3, 'contradicted': 0, 'no_claims': 3}
- **relevance** — reference {'full': 17, 'partial': 1, 'off_topic': 0, 'refusal': 2}; judge {'full': 17, 'partial': 1, 'off_topic': 0, 'refusal': 2}
- **citations** — reference {'correct': 14, 'some_wrong': 2, 'none': 4}; judge {'correct': 14, 'some_wrong': 2, 'none': 4}

## Judge MORE LENIENT than the reference labels (the self-preference risk)

None.

## Judge STRICTER than the reference labels

None.

## Other disagreements (no severity direction: no_claims / refusal / none involved)

None.

## Per answer

| Id | Type | Band | Faithfulness reference / judge / replica | Relevance reference / judge / replica | Citations reference / judge / replica | Fabricated (code) |
|---|---|---|---|---|---|---|
| g-002 | generated | strict | supported / supported / supported | full / full / full | correct / correct / correct | 0 |
| g-008 | generated | strict | supported / supported / supported | full / full / full | correct / correct / correct | 0 |
| g-015 | generated | loose | supported / supported / supported | full / full / full | correct / correct / correct | 0 |
| g-017 | generated | strict | not_in_context / not_in_context / not_in_context | partial / partial / partial | some_wrong / some_wrong / some_wrong | 0 |
| g-020 | generated | strict | supported / supported / supported | full / full / full | correct / correct / correct | 0 |
| g-024 | generated | loose | supported / supported / supported | full / full / full | correct / correct / correct | 0 |
| g-028 | generated | loose | supported / supported / supported | full / full / full | correct / correct / correct | 0 |
| g-029 | generated | loose | supported / supported / supported | full / full / full | correct / correct / correct | 0 |
| g-038 | generated | loose | supported / supported / supported | full / full / full | correct / correct / correct | 0 |
| g-040 | generated | strict | supported / supported / supported | full / full / full | correct / correct / correct | 0 |
| g-041 | generated | loose | supported / supported / supported | full / full / full | correct / correct / correct | 0 |
| g-050 | generated | strict | supported / supported / supported | full / full / full | correct / correct / correct | 0 |
| h-01 | hard | strict | supported / supported / supported | full / full / full | correct / correct / correct | 0 |
| h-03 | hard | loose | supported / supported / supported | full / full / full | correct / correct / correct | 0 |
| h-05 | hard | strict | supported / supported / supported | full / full / full | correct / correct / correct | 0 |
| h-09 | hard | loose | not_in_context / not_in_context / not_in_context | full / full / full | some_wrong / some_wrong / some_wrong | 0 |
| n-01 | negative | loose | no_claims / no_claims / no_claims | full / full / full | none / none / none | 0 |
| n-02 | negative | strict | no_claims / no_claims / no_claims | refusal / refusal / refusal | none / none / none | 0 |
| n-04 | negative | strict | no_claims / no_claims / no_claims | refusal / refusal / refusal | none / none / none | 0 |
| n-06 | negative | none | not_in_context / not_in_context / not_in_context | full / full / full | none / none / none | 0 |
