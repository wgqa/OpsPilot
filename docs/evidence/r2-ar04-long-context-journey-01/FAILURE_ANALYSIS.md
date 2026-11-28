# R2-AR04 long-context failure analysis

**Evidence level:** deterministic Fixture outputs plus actual persisted local FastAPI/Worker/Domain rows, Context Manifests, and model `request_json`. This is evidence about L1/L2 availability and deterministic compaction stages. It is not evidence of live model comprehension (L3: `NOT_EVALUATED`).

## What remained in Domain and what reached the model

L1 is complete for all 12 question fact groups: every source remains readable in the common 29-message Domain snapshot. No source row was deleted or invalidated by this experiment. The strategy comparison is an L2 visibility result:

| Strategy | Fully available | Partial | Missing | Specific visibility gaps |
|---|---:|---:|---:|---|
| A `HYBRID` | 9/12 | 0 | 3 | Initial `/callback`, protocol transition, `max_attempts` change |
| B `ROLLING_SUMMARY` | 9/12 | 0 | 3 | Same as A |
| C `RECENT_WINDOW` | 3/12 | 3 | 6 | Formal correction and no-write constraint are critical gaps |
| D full-history reference | 12/12 | 0 | 0 | None in the fixed 12-question set |

A/B share the same retained raw sequence set, `[19, 21, 23, 25, 27, 28, 29]`, and a current Summary covering seq 1–18. Among their nine complete answers, five fact groups are Summary-only, two are raw-only, and two are present in both. The overlap is counted once. In particular, `Receiver=QUEUED` is present in selected raw history and is not credited to Summary; the deployed-version-unknown answer is visible from raw seq 21. `HTTP 202` not proving completion and the safe next action are visible in both raw history and Summary.

C selects the same recent raw sequence set and emits no Summary. Q03 has a clue for `req-483`, but the formal correction relationship is incomplete; Q04 has a relevant Event ID clue without the needed unchanged relationship; Q12 has a recent state clue without enough of the required constraints. Q03 and Q09 are the two recorded critical visibility gaps. D sends raw seq 1–29 and is a larger-budget reference, not a same-budget ranking.

## Why A/B lost these facts

The recorded calls show two distinct loss stages in `opspilot/domain/chat.py`:

1. **`/callback` is discarded while preparing the second compression request.** In Q02, the first deterministic Fixture compression result places the seq 3 assertion (`endpoint=/callback`) in `user_assertions`. Before the next compression call, `_summary_prompt_projection` maps source IDs to sequence references and `_compact_summary_document` prepares a bounded `previous_summary` (call site around line 1750). The second request's actual `previous_summary` contains only the newer seq 15 user assertion; the seq 3 endpoint no longer appears. This is a deterministic priority/budget loss before the second Fixture response, rather than an answer to the user question being unavailable in Domain.
2. **The version timeline is discarded while persisting the next Summary.** The first compression result contains the complete seq 11 statement: `v1.2 → v1.3`, `max_attempts 3 → 5`, and deployed version unknown. In the second compression request's `previous_summary`, `_compact_summary_document` truncates the timeline text to 48 characters. The version transition and `3 → 5` remain in that intermediate text, while the final characters of the unknown-version clause are cut. The second Fixture response still includes the seq 11 timeline item plus new seq 14, 16, and 18 tool-result items. The final `_compact_summary_document` call before persistence keeps at most three timeline entries, prioritizes the newest entries, and drops seq 11. The current Summary therefore has tool-result entries but no protocol transition or retry-count change. This is why Q06 and Q07 are `MISSING` in the final model input even though the complete facts existed in the first compression result and in Domain history.

The compacting logic is at [`chat.py`](../../../opspilot/domain/chat.py) around `_compact_summary_document` (line 1192), its previous-summary projection call around line 1750, and its post-validation/persistence call around line 2240. The actual first/second requests and results are retained in [`MODEL_REQUESTS.jsonl.gz`](MODEL_REQUESTS.jsonl.gz); per-question final Summary JSON, selected history, and Manifest evidence are in [`RESULTS.json`](RESULTS.json) and [`RUN_DETAILS.jsonl.gz`](RUN_DETAILS.jsonl.gz).

These observations identify loss under this fixed Fixture workload. They do not establish that a live provider will choose the same wording or preserve the same facts. Natural-language summary fidelity and whether an agent can answer correctly from a visible fact are `NEEDS_LIVE_SEMANTIC_EVAL`.

## Safety and source integrity findings

- A/B compression made 48 attempts across 24 question-strategy runs; all succeeded. There were no recorded compression failures or blocked runs.
- Across all 48 answer runs, Summary citations resolved to existing Domain source IDs; projected Summary IDs were current. The runner's source-integrity checks found no stale or missing source IDs.
- Q08's deployment-version unknown remains visible in selected raw history; it must not be reported as preserved by the current Summary.
- The synthetic tool result's HTTP 202 / `ACCEPTED` is not treated as completion. `Receiver=QUEUED` is the latest visible observation, and the task remains unresolved.
- L1 retention does not imply L2 visibility: `/callback`, v1.2 → v1.3, and `max_attempts` 3 → 5 remain in the Domain rows while absent from the final A/B prompt for their questions.
- The earlier C06 long-user-message RED and its historical result are not changed. The fail-closed behavior remains; this experiment did not widen token limits or alter the production compressor.
- Provider calls and external business writes are both zero. The Fixture's dummy usage is not provider token usage or cost.

## Minimal follow-up candidate (not implemented)

Review only the bounded-priority behavior in `_compact_summary_document` at `opspilot/domain/chat.py:1192` and add a focused regression case with an older `user_assertions` endpoint and more than three timeline items, including a protocol transition and unresolved deployed version. The test should assert the final persisted Summary retains the priority facts or that an explicit, reviewable omission is surfaced. Do not simply raise the output cap: more retained facts can evict the initial goal, constraints, corrections, or unresolved work. Any behavior change belongs in a separately authorized repair slice; this audit makes no production change.

## Evidence references

- Fixed facts and source clauses: [`QUESTIONS.json`](QUESTIONS.json)
- L1/L2 rows and budgets: [`RESULTS.json`](RESULTS.json)
- Same-history digests: [`HISTORY_SNAPSHOT.json`](HISTORY_SNAPSHOT.json)
- Frozen prior WP3 Trace and results: `../r2-ar04-compaction-audit-01/case_traces/WP3_INFORMATION_RETENTION.json` and `../r2-ar04-compaction-audit-01/RESULTS.json` (unchanged)
- Earlier C06 RED record: `../r2-ar04-compaction-c06-hf01/` (unchanged)
