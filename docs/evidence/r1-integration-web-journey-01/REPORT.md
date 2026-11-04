# OpsPilot R1 Integration Web Journey — Report

**Status:** `ACCEPTANCE_CANDIDATE`
**R1-ENGINE:** `PARTIAL`
**R1-INTERACTIVE:** `HOLD / NOT_RUN / BLOCKED_BY_TOOL_ENVIRONMENT`

## What this run demonstrates

The new offline integration test exercised four same-Session requests through the formal FastAPI → Worker → `ASSISTANT_V1` path. J1 used the local MCP protocol discovery and comparison tools without a Task. J2 sent a JSON retry configuration in the same Session; the actual outbound model context retained it and the fixture answer labeled it as user-provided and unverified. J3 used the trusted order API to bind `ar03-order`, then obtained current same-Event Delivery and Receiver results. J4 started a distinct same-Task Run, read the current Event again, and verified two persisted `/messages` reads returned the same message IDs and bodies.

The run used a deterministic model fixture and local MCP/SQLite demo facts. It is evidence of product-path wiring and current source association, not evidence of live LLM behavior, browser usability, or production facts. The fixture established `Receiver=QUEUED`; the new journey did not run a PROCESSED case. The existing AR-02/AR-03 regression suite includes a formal Worker paired `QUEUED`/`PROCESSED` test, but this R1 run does not upgrade that to a real-model comparison.

## Per-turn result

| Turn | User goal | Actual deterministic choice / observation | User-visible result | Assessment |
|---|---|---|---|---|
| J1 | Ask what changes when moving from the old callback protocol to the new one | Fixture chose scoped document discovery and version comparison. The local response returned v1.0.0 and v2.0.0 with digests and one structural difference; `deployment_version_verified=false`. | The saved answer names the versions, reports a comparison, and states that without trusted order binding it cannot assess current customer state or online deployment. | `OFFLINE_FIXTURE_PATH_OK`; content quality is not a live-model result. |
| J2 | Ask whether a supplied `max_attempts: 5` configuration changes the prior conclusion | No tool call. The persisted outbound model request contains the preceding protocol context and current JSON material. | The answer treats `max_attempts=5` as user-provided, unverified material and recommends checking deployed configuration before confirming impact. | Positive material/context boundary. |
| J3 | Check whether this order's callback Event is processed | Trusted `/assistant/order` binds `ar03-order`; fixture calls Delivery and Receiver MCP. Persisted facts share Task and Event: Delivery `HTTP 202 / ACKNOWLEDGED`; Receiver `QUEUED`. Both have Observation and Evidence IDs. | The answer says 202 means accepted, not processed; current same-Event Receiver is QUEUED; online deployment remains unknown; no business operation was submitted. | Positive trusted binding and current-fact path. |
| J4 | Follow up on the same Event | A new Run in the same Task makes new Delivery and Receiver observations. Re-reading `/messages` twice yields the same IDs and bodies. | The answer again says the Event is not yet confirmed complete. | Positive API persistence/re-read behavior; not browser refresh, SSE, or correction flow. |

Full observed IDs, document digests, Event, Observation/Evidence IDs, versions, model-fixture decisions and protected table counts are in `TRACE.jsonl`. The raw focused test log is `runs/pytest-r1-offline-journey-08.log`.

## Existing capabilities and integration scope

Source inspection found the existing Vue workbench has the session chat, trusted order binding form, correction controls and source/inspector views. Existing API routes provide assistant messages, order binding, messages, sources and correction actions; the Worker dispatches `ASSISTANT_V1`. Existing tests cover unbound protocol discovery/comparison, trusted binding, same-Event Receiver outcomes, Context continuity, source revalidation and projection behavior. This candidate adds no production code: it adds one offline formal API/Worker integration test and its evidence.

The prior accepted true-provider evidence remains historical corroboration only. `docs/evidence/ar-03/material-remainder-live-01/campaign-01/REPORT.md` reports MAT-05 plus Skill OFF/ON from a real Provider run; `docs/evidence/ar-03/real-llm-02/REPORT.md` reports scenario A complete and B partial. They are not a fresh execution of this R1 four-turn journey, not browser evidence, and not evidence that the current fixture choices reflect a real model.

## Verification

- Final selected backend regression: **82 passed**, exit code 0, in 114.54 s. Command and exact modules are recorded in `runs/pytest-engine-regression-04.log`; this final pass includes the new persisted-MCP checks.
- Latest dedicated R1 journey after trace enrichment: **1 passed**, exit code 0. See `runs/pytest-r1-offline-journey-08.log`.
- Frontend conversation projection/recovery tests: **17 passed**, exit code 0, via Node's native strip-types test runner. This tests pure projection functions only.
- An attempt to run every frontend `*.test.ts` under Node 24 had 17 passing subtests but could not load `assistant-entry.test.ts`: Node's strip-only TypeScript mode does not support a parameter property in `frontend/src/api.ts`. This is a runner limitation; no frontend source was changed.
- Initial pytest with system Python failed collection because `langchain_core` is absent there. Reusing the existing project virtualenv produced the passing result; no dependencies were installed.
- `git diff --cached --check` is clean for source, test and report files when raw `runs/*.log` are excluded. The captured pytest logs contain whitespace used in terminal alignment; these original run outputs were retained unchanged.
- Full repository pytest, typecheck, production build, and changed-file ESLint: `NOT_RUN`. There are no frontend or business source changes; `frontend/node_modules` is absent in this worktree.
- Real browser, DOM, screenshot, SSE/reconnect, and live Provider checks: `NOT_RUN / BLOCKED` as applicable. No alternate browser automation was attempted.

## Scope and safety

- Provider HTTP: **0**.
- MCP calls in the successful fixture journey: **6** (2 protocol discovery/comparison; 2 current business reads in J3; 2 current business reads in J4).
- Protected business tables checked in the isolated DB: all 11 counts were zero (diagnoses, plans, approvals, action intents/ledgers, verification/delivery records and S2/S3 handoff queue/receipt tables).
- `prepare_s3_fixture()` is the demo fixture boundary; it did not record Agent-initiated business actions.
- No production source, North Star, AGENTS, frozen Gold, old Provider trace, historical receipt, or `main` was modified.

One earlier deterministic fixture run exhausted `TASK_AUX_PROVIDER_LIMIT` after it repeated full protocol discovery/comparison and several business reads in the same Task. The final fixture reuses prior protocol context and tests current-state re-observation. This remains a relevant capacity/strategy risk under a deliberately repetitive legal sequence; this task did not change the budget or establish that a real model would choose that sequence.

## Six review questions

1. **User change:** The offline formal API path now has an explicit same-Session J1–J4 wiring check for protocol consultation, pasted material, trusted order binding, current Event reads, and persisted answer re-read. The user has not yet seen this through a browser or live model in this task.
2. **Agent decision:** Only the deterministic fixture chose the calls. The test proves those legal tool results can reach the answer path; it does not prove real-model autonomous choice.
3. **Observation-driven behavior:** The fixture distinguishes current same-Event `202/ACKNOWLEDGED` plus `QUEUED` from “processed.” The selected regression suite also tests QUEUED/PROCESSED differences; the new journey itself uses QUEUED only.
4. **New restrictions and legal effect:** No hard restriction was added. Existing trusted binding and read-only scope were exercised; valid same-Task reads continued. Protected write counts remained zero.
5. **Simplification:** No production condition or module changed; no new runtime, timeline state, budget platform, or duplicate authority was created.
6. **Evidence and stop line:** 82 selected backend tests and 17 projection tests passed; the focused journey has a persisted MCP/Observation trace. Browser/DOM, live-model behavior, full pytest, typecheck and production build remain unverified. Stop here for independent review; do not start AR-04 or paid tests.

**Candidate decision:** `ACCEPTANCE_CANDIDATE` only. R1-ENGINE is `PARTIAL`; R1-INTERACTIVE remains `HOLD` pending a legally available browser run. No merge to `main` is requested or performed.
