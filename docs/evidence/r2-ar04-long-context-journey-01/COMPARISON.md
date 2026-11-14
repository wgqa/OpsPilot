# R2-AR04 long-context comparison

**Evidence:** offline Fixture runs through the local FastAPI/Worker/Domain and SQLite checkpointer; actual persisted model `request_json`, Summary rows, and Context Manifests. Token values are local `tiktoken:cl100k_base:0.14.0` estimates. Provider usage and L3 answer accuracy are not measured.

## Outcomes

| Group | Configuration | L1 Domain facts | L2 complete | Partial | Missing | Mean final Prompt tokens | Compression calls / failures |
|---|---|---:|---:|---:|---:|---:|---:|
| A | `HYBRID`, W=16,384, input limit=12,000 | 12/12 | 9/12 (75%) | 0 | 3 | 8,449 | 24 / 0 |
| B | `ROLLING_SUMMARY`, W=16,384, input limit=12,000 | 12/12 | 9/12 (75%) | 0 | 3 | 8,449 | 24 / 0 |
| C | `RECENT_WINDOW`, W=16,384, input limit=12,000 | 12/12 | 3/12 (25%) | 3 | 6 | 7,813 | 0 / 0 |
| D | Full-history reference, `HYBRID`, W=65,536, input limit=60,000 | 12/12 | 12/12 (100%) | 0 | 0 | 39,476 | 0 / 0 |

The L1 column shows that every required fact group remains in the common 29-row Domain history. Differences in L2 come from selection and summary handling. D uses a larger budget and is an upper-bound reference, not a same-budget winner. A/B have five summary-only questions, two raw-only questions, two questions available from both sources, and three missing questions. The two overlapping questions are counted once in the 9/12 availability total.

## Per-question L2 status

| Question | A HYBRID | B ROLLING_SUMMARY | C RECENT_WINDOW | D Full history |
|---|---|---|---|---|
| Q01 Initial goal | `AVAILABLE_SUMMARY` | `AVAILABLE_SUMMARY` | `MISSING` | `AVAILABLE_RAW` |
| Q02 Initial `/callback` endpoint | `MISSING` | `MISSING` | `MISSING` | `AVAILABLE_RAW` |
| Q03 Formal Request ID correction | `AVAILABLE_SUMMARY` | `AVAILABLE_SUMMARY` | `PARTIAL` | `AVAILABLE_RAW` |
| Q04 Event ID unchanged | `AVAILABLE_SUMMARY` | `AVAILABLE_SUMMARY` | `PARTIAL` | `AVAILABLE_RAW` |
| Q05 Rejected timeout hypothesis | `AVAILABLE_SUMMARY` | `AVAILABLE_SUMMARY` | `MISSING` | `AVAILABLE_RAW` |
| Q06 v1.2 → v1.3 | `MISSING` | `MISSING` | `MISSING` | `AVAILABLE_RAW` |
| Q07 `max_attempts` 3 → 5 | `MISSING` | `MISSING` | `MISSING` | `AVAILABLE_RAW` |
| Q08 Deployed version unknown | `AVAILABLE_RAW` | `AVAILABLE_RAW` | `AVAILABLE_RAW` | `AVAILABLE_RAW` |
| Q09 No credential changes / business writes | `AVAILABLE_SUMMARY` | `AVAILABLE_SUMMARY` | `MISSING` | `AVAILABLE_RAW` |
| Q10 HTTP 202 is not completion | `AVAILABLE_RAW` | `AVAILABLE_RAW` | `AVAILABLE_RAW` | `AVAILABLE_RAW` |
| Q11 Latest `Receiver=QUEUED` observation | `AVAILABLE_RAW` | `AVAILABLE_RAW` | `AVAILABLE_RAW` | `AVAILABLE_RAW` |
| Q12 Safe next step while completion is unknown | `AVAILABLE_RAW` | `AVAILABLE_RAW` | `PARTIAL` | `AVAILABLE_RAW` |

Availability uses the fixed source-specific fact clauses in `QUESTIONS.json`. `PARTIAL` means the selected prompt contains a relevant clue but lacks the relationship or constraint needed for a reliable answer. A fact appearing as both raw and Summary is counted once; the per-run `available_sources` field records the overlap.

## Context and cost comparison

| Group | Shared raw-history estimate | Mean estimate before preparation | Mean runtime reserved tokens | Mean input budget after reserve | Mean final Prompt estimate | Compression input estimates, total | Summary output estimate, total |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 35,009 | 35,397 | 4,185 | 7,815 | 8,449 | 130,572 | 6,012 |
| B | 35,009 | 35,397 | 4,184 | 7,816 | 8,449 | 130,572 | 6,012 |
| C | 35,009 | 21,956 | 4,531 | 7,469 | 7,813 | 0 | 0 |
| D | 35,009 | 35,397 | 5,218 | 54,782 | 39,476 | 0 | 0 |

Values are per-run group means rounded to the nearest token, except the two compression totals, which are sums over all 24 compression attempts in that group. For C, `estimated_before` is the candidate after recent-window selection; compare its 21,956 estimate with the same 35,009 shared raw-history estimate, not with A/B/D's full-candidate estimate. Runtime reserve accounts for trusted system/tool overhead before choosing history. The `512` output reserve and `1,024` safety margin are also present in the recorded budget.

Each A/B question triggered two compression attempts; all 48 attempts succeeded. Their raw selected history was seq `[19, 21, 23, 25, 27, 28, 29]`, with the current Summary covering seq 1–18. C selected the same recent raw sequence set but added no Summary. D sent raw seq 1–29. Every A/B Summary citation mapped to an existing Domain message and every Summary in the final prompt was current: 48/48 runs had zero missing/stale citation IDs. Across the complete experiment there were 48 answer requests and 48 compression requests, all served by the deterministic local Fixture; `provider_requests=0`.

The local Fixture writes dummy usage metadata. It is not provider usage or cost evidence. Compression input and Summary output totals above are estimates calculated from the persisted calls and Domain rows.

## Fixed request invariants

Across the 48 actual answer requests, `RESULTS.json` records one static `SYSTEM` policy digest, one Tool Schema digest, and one model ID (`R2_AR04_DETERMINISTIC_FIXTURE`). The per-run `WORK_CONTEXT`, selected history, Summary, and Manifest vary by question and strategy and are retained in the actual request evidence.

## Interpretation

- A and B have the same L2 counts in this Fixture run. Five questions are answerable from Summary only, two from raw history only, and two from both; three questions are missing from the final prompt.
- C uses fewer estimated input tokens and makes no compression calls, but only three questions have all required facts. Three further questions have incomplete clues, and six are missing.
- D exposes the whole synthetic history and all twelve fact groups, at roughly 4.7 times the A/B final-prompt token estimate. D is intentionally outside the equal-budget comparison.
- L3 remains `NOT_EVALUATED`. The Fixture's scripted output cannot establish model recall, answer quality, or autonomous next-step quality.
