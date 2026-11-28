# PRODUCT-01 continuity review 01

**Status:** `ACCEPTANCE_CANDIDATE`
**Evidence level:** historical real-model traces + current deterministic formal API/Worker/MCP/Domain tests. No new paid Provider request or browser run.

## Baseline and scope

- Base branch: `codex/r1-final-integration-01`
- Base SHA: `7e9fd6809da778be7ffc27cd4c0d1ae7909d84e7`
- Working branch: `codex/product-01-continuity-review-01`
- Main checked at start: `60eee87bfe3cca522011316cb4cd2c0064ad291b`
- North Star Blob: `43dabda468506717c6956e676dfad4304c4f38e6`
- `AGENTS.md` Blob: `807b928686a4dd2cac7b15b3c354b9943c93c910`
- Review Skill Blob: `d405c8d413d633824b279202cc1503dab4cf0b03`

The original user workspace and its untracked files were not modified. Historical Gold, F01 / Slice 02 traces, and previous failure records remain unchanged.

## User journey and result

The existing deterministic formal path covers the requested continuous support work: protocol discovery/comparison; analysis of user-supplied JSON without treating it as server truth; trusted order binding; current Event Delivery/Receiver investigation; and a correction to `event-previous` without borrowing another Event's `PROCESSED` state. The existing tests also cover a `QUEUED` to `PROCESSED` fixture change and verify that no business action, approval, ActionIntent, Ledger, Delivery, or Handoff side effect is created by ordinary read-only chat.

The newly reproduced terminal path reaches the same Task/Event with `Delivery=ACKNOWLEDGED` and `Receiver=QUEUED` or `PROCESSED`. It records 8 successful deterministic MODEL calls and 6 successful MCP calls, then stops at the frozen model-call boundary before a final model answer. The persisted user result is correctly tagged `PROGRAM_LIMIT`. The source panel can disclose those Run's observations only after the read-only API revalidates the same Run, TaskBinding, versions and freshness. The default model/history source projection still rejects failed-Run observations. When the Receiver version changes, the source panel hides the saved result.

The existing Vue message projection already labels `PROGRAM_LIMIT` as a program notice and provides a “查看答复来源” disclosure that calls the source API when opened. No frontend change was needed. This was verified by static inspection only; no browser run was performed.

This is evidence that the formal deterministic execution path and source boundary work. It is not evidence that a live LLM would make the same decisions or finish within the existing budget.

## Issue classification

| Class | Finding | Disposition |
|---|---|---|
| A — unsafe write / authorization | No new authorization bypass or business write was found in the exercised path. Cross-principal revocation continues to deny source reads. | No change to authorization or action semantics. |
| B — deterministic execution/source/delivery | The old program-limit copy asserted that no current business fact had been retrieved. That is false when the Run has successful MCP observations but cannot obtain a final model response. Failed Runs were also rejected by the source projection, so users could not inspect still-current observations. | Fixed narrowly: neutral program notice; explicit read-only source-detail opt-in for failed `CHAT_READONLY` `ASSISTANT_V1` Runs; normal source revalidation still applies. No failed-Run content is promoted into later model context or treated as a final answer. |
| C — model reasoning / phrasing | F01's old turn 2 misdescribed whether the prior Run used tools. Slice 02's final wording implied follow-up was in progress without a scheduled follow-up action. Neither is reproduced by the deterministic code path, and one live sample cannot establish an architecture defect. | Preserve as model-quality observations. No answer guard or forced-query workflow added. |
| D — capability not verified | The live model behavior has not been repeated. Static inspection shows `create_assistant_model()` requires a supported `OPSPILOT_ASSISTANT_EXPERIMENT_ID` whenever the real Provider is enabled; Product-01's experiment identity additionally requires its one-shot authorization/claim. A normal no-experiment real Provider identity is therefore not currently demonstrated. | No provider authorization changes were made. Treat normal, non-experiment Provider operation as unverified and handle it under a separately authorized scope. |

Historical F01 records 8 real HTTP 200 Provider responses, 10 MCP calls and an application estimate of USD 0.018130. It records the model's mistaken prior-run wording and a later budget stop after a new Receiver observation. Historical Product-01 Slice 02 records a four-turn real DeepSeek session, 8 Provider calls and 9 MCP calls, with a `PARTIAL` outcome. These are historical real-model artifacts, not results of this review. The current trace (`TRACE_RAW.jsonl`) is deterministic fixture data only.

## G-ENGINE / G-AGENT / G-PRODUCT

- **G-ENGINE:** targeted formal API/Worker/MCP/Domain tests pass; source details remain read-only and revalidated; stale or revoked facts are hidden. No full repository test suite was run.
- **G-AGENT:** historical live traces show protocol discovery, comparison, direct material interpretation, Event correction and correct distinction between transport acceptance and Receiver state. The current run uses a deterministic fixture, so fresh autonomous model behavior is unverified.
- **G-PRODUCT:** the tested interface path preserves the original message-to-Run association, offers a program-limit notice without pretending it is a model answer, and permits the user to inspect valid observations. This is API/Worker evidence, not browser UX acceptance.

## Verification

1. `python -m pytest -vv -s --basetemp='D:\Temp\OpsPilot-product-01-continuity-review-01\pytest-final' tests/test_ar02_ar03_integration_01.py::test_terminal_model_cap_discloses_only_revalidated_failed_run_sources tests/test_ar02_ar03_integration_01.py::test_product_01_same_session_material_current_check_and_event_correction tests/test_ar02_ar03_integration_01.py::test_product_01_same_event_queued_to_processed_uses_new_observation tests/test_ar02_runtime.py::test_old_core_sources_revoke_and_ordinary_chat_cannot_borrow_observation tests/test_ar02_runtime.py::test_revocation_between_tool_and_model_stops_and_source_api_denies tests/test_m4_c1_hf_01.py::test_hf01_prior_followup_is_a_bounded_chat_context_block_with_provenance` — **7 passed, exit 0**.
2. `python -m pytest -vv -s --basetemp='D:\Temp\OpsPilot-product-01-continuity-review-01\pytest-provider-scope' tests/test_product_01_live_scope.py` — **1 passed, exit 0**, using explicit HTTPX MockTransport. No external Provider request.
3. `git diff --check` — **passed**.

The initial terminal-source RED is preserved in `TEST_LOG_RED.txt`. The final targeted logs and the full deterministic captured trace are preserved beside this report. The full `pytest` suite was not run. The first attempt using pytest's default C: temporary directory failed during fixture setup with Windows `WinError 5`; rerunning with an isolated D: `--basetemp` completed the tests. This is an environment/temp-path issue, not a test assertion result.

Committed evidence SHA-256: `TEST_LOG_RED.txt` `0e72aed04ca2344579f4b1d4339cb4505c7ea961e0c28a4b3d010d79019ad502`; `TEST_LOG_TARGETED.txt` `b47b5bcc5babc7e6483c73e8dd4d48d9477fadacb967d0dcc4d37081090b72ea`; `TEST_LOG_PROVIDER_SCOPE.txt` `87b355e7106e69e40f476a63e7fc002bdd3233e4af3713d9417fb3d3b22f7c86`; `TRACE_RAW.jsonl` `1927f554bb66e696d3808da64b1c6cdef1e623566e2847a3a4f1928c352dc908`. The original unmodified private RED and targeted logs remain in the D: temp evidence directory with SHA-256 `ca9c40beffbfc4e1b0dd178c6e09d8a2143bc7c5e75b038c5e2923f8ce5ddeaa` and `02a31b70a59af24ab702dcebee0e170c67867eb77f6edbfdb588cf3cce78bf85` respectively; public text copies only had trailing whitespace removed.

**Execution counts for this review:** real Provider requests = 0; browser automation = `NOT_RUN`; external business writes = 0. Local test fixtures performed only isolated Demo setup and a Receiver version/state mutation to prove stale-source invalidation.

## Provider path inspection

The production server injects `create_assistant_model` into `create_app`; `create_app` resolves the experiment ID and the Worker invokes the factory per Assistant Run. The factory is default-off when `OPSPILOT_ASSISTANT_PROVIDER_ENABLED` is not `1`, but when enabled it rejects an absent/unsupported experiment ID. The Product-01 live experiment has a one-shot authorization check and dispatch claim. Its existing `test_product_01_live_scope_requires_one_claim_and_one_reservation` passes with a mock transport, confirming the experiment path remains claim guarded. No normal Provider identity was added, no claim was created outside that test's temporary directory, and no provider code was changed.

## Six review questions

1. **What can the user now complete?** Inspect current Run observations after a budget-stop notice without being told falsely that no fact was retrieved.
2. **What does the model still decide?** Tool choice, order, clarification, whether to continue, and final wording remain model decisions; tests use a deterministic fixture and do not evaluate live autonomy.
3. **What observation changed the result?** Same-Event Receiver `QUEUED` and `PROCESSED` states remain distinct; source details are invalidated after the Receiver version changes.
4. **What authority was added?** None. The new endpoint behavior is read-only, owner-scoped, TaskBinding-checked and source-revalidated.
5. **What was reused or simplified?** Existing Assistant source projection, S3 evidence currentness, formal API/Worker and persisted call records. No new runtime, router, budget platform or workflow was added.
6. **What remains unproven?** Fresh real-model response quality, regular no-experiment Provider operation, and browser rendering/refresh. The full test suite is also not freshly verified.

## Remaining work and stop

The model-quality observations are not addressed here. A separate, explicitly scoped Provider-path task is needed before claiming ordinary non-experiment real-model operation. Browser validation remains under its existing STOP. No paid Provider request, external write, main merge, or R1 overall PASS is claimed.

The work stops at this deterministic continuity/source-delivery correction and is submitted as `ACCEPTANCE_CANDIDATE` for independent review.
