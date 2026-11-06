# AR-05 release regression boundary

Status: `ACCEPTANCE_CANDIDATE` pending the controlled regression result.

## Baseline and evidence

- Source base: `codex/ar05-recovery-revalidation-hf01@5b494fdaf20ae8eaf8fb5ec946319b2cb36fb2d0`.
- Remote `main` observed at `60eee87bfe3cca522011316cb4cd2c0064ad291b`; this task does not merge it.
- `PROJECT_NORTH_STAR.md` blob: `e36f2f75509738551ac6d4a2de5b4f9cf44a7991`.
- `AGENTS.md` blob: `f174a6ab7f23f9e6d8b3ef98d455b99a75193143`.
- `.agents/skills/opspilot-slice-review/SKILL.md` blob: `d405c8d413d633824b279202cc1503dab4cf0b03`.
- AR-04C paid contract blob: `eaed67e5a315adb6c49ee38c70f7d72351d057d3`; Gold blob: `f57913861101b9a0aaff6c3219d908dc8ce18762`; Cases blob: `4301b7feb2c79d4965105ae9587a07ade7226cdd`.
- Prior integrated full pytest log blob: `10e41cf18e063a35ddd791345326c0bbf779322c`; prior recovery/revalidation report blob: `1c899407367d05a3c79f76ca3d1b58b5b4be596b`.

## AR-04C one-shot and test applicability

The real `AR-04C-REAL-JOURNEY-01` execution used `execution_head_sha=c4922957a82a557dee8dfb254af4f740c3b34c4b`, freeze digest `69f15d7bbb04a09f3f8692c59bbed04d2db2e43b75e1b292302efd9b751d5d5a`, and an already consumed one-shot claim. The private local claim state is `CONSUMED`; claim SHA-256 `0678daa0ec717c8382d94a748d8a7fe96cf3051e63adfbcac133c362170aa9a7`, state SHA-256 `78545021e7cf5b65dfca515330a94b53e4e3a61cca24478f3321ceceb4cdafa8`. These records were inspected read-only and not changed. A distinct F01 recheck claim is also already `STOPPED`; it was not reused.

The current candidate is not the frozen execution branch or HEAD. Tests that exercise the old claim path cannot be treated as current-candidate release tests: a branch/HEAD-bound authorization must reject a different identity. The historical claim itself was never supplied to pytest, copied, reset, or replayed. The separate F01 recheck claim is `STOPPED` (claim SHA-256 `193d4f2a4572144a71d96309bf24572d25d82cef1835d293a9d7036ec6af0bc5`; state SHA-256 `2da3135d979500d5709778379eed66e246b8e6ddef049c052b704363472d34c23`) and was likewise not reused.

### The 12 failures in the historical full-suite log

| # | Exact node ID | Classification | Current release treatment |
|---:|---|---|---|
| 1 | `tests/test_ar04c_f01_recheck_preflight.py::test_recheck_authorization_claim_and_mock_send_are_scoped` | Offline Mock and temporary claim; F01 frozen branch identity is embedded in its temporary authorization. | Historical F01 evidence. It can only be meaningfully replayed against matching frozen source identity with a fresh test-only temp claim. Not run on this candidate. |
| 2 | `tests/test_ar04c_f01_recheck_preflight.py::test_formal_worker_uses_scoped_mock_transport_and_mcp` | Offline Mock/Worker and temporary claim; same F01 branch binding. | Same as #1; not evidence for this candidate and not run here. |
| 3 | `tests/test_ar04c_prelive_hf01.py::test_ar04c_authorization_positive_claim_is_atomic_and_head_bound` | Offline concurrent claim creation using test-only authorization/claim files; reads the actual branch/HEAD. | Replayable only with matching original source identity and fresh test-only files. On this branch both child processes reject at identity validation, so the atomic-winner assertion is not exercised. |
| 4 | `tests/test_ar04c_prelive_hf01.py::test_ar04c_claim_tamper_is_rejected_before_model_construction` | Offline test claim tamper case. | Current-branch mismatch rejects during initial claim creation, before the tamper check; not a valid candidate result. |
| 5 | `tests/test_ar04c_prelive_hf01.py::test_ar04c_authorization_change_after_claim_is_rejected` | Offline temporary authorization/claim mutation. | Current-branch mismatch prevents reaching the post-claim authorization-change check; not a valid candidate result. |
| 6 | `tests/test_ar04c_prelive_hf01.py::test_ar04c_unknown_stop_is_persisted_and_cannot_be_reclaimed` | Offline MockTransport dispatch and temporary campaign DB/claim. | Current-branch mismatch prevents dispatch setup; actual historical claim remains consumed and was not used. |
| 7 | `tests/test_ar04c_prelive_hf01.py::test_ar04c_consumed_claim_cannot_be_replayed_by_new_worker_process` | Offline subprocess replay using test-only claim files. | Current-branch mismatch prevents creation of the test claim; not a valid candidate result. |
| 8 | `tests/test_ar04c_prelive_hf01.py::test_ar04c_mock_provider_transport_requires_formal_dispatch_context` | Offline HTTPX MockTransport and temporary claim. | Current-branch mismatch preempts the dispatch-context assertion; no external request was made. |
| 9 | `tests/test_ar04c_prelive_hf01.py::test_ar04c_mock_provider_success_consumes_claim_before_http_and_pins_database` | Offline MockTransport, temporary claim and isolated experiment DB. | Current-branch mismatch preempts mock send; not a valid candidate result. |
| 10 | `tests/test_ar04c_prelive_hf01.py::test_ar04c_mock_provider_unknown_persists_stop_and_blocks_followup` | Offline injected connection error, temporary claim and isolated experiment DB. | Current-branch mismatch preempts dispatch; not a valid candidate result. |
| 11 | `tests/test_ar04c_real_journey_01.py::test_ar04c_formal_worker_mock_pair_keeps_current_queued_facts_and_memory_only_diff` | Pre-live test requiring global authorization and claim files to be absent; writes to the historical evidence path. | Its premise is false after the paid execution and rerunning would touch old evidence. Not rerun. |
| 12 | `tests/test_ar04c_real_journey_01.py::test_ar04c_paid_factory_fails_closed_without_authorization_and_claim` | Pre-live absence assertion for the global authorization and claim. | The one-shot claim exists and is consumed, so this precondition no longer holds. Not rerun; no deletion/reset. |

In the prior full run these 12 were failures within `40 failed, 701 passed`; the log is preserved unchanged. The failures are not counted as current passes or silently dropped from history.

The tests using temporary mock authorization/claims are not intrinsically paid requests. Their frozen identity binding nevertheless makes a run on this different candidate an invalid way to judge the old experiment. The two absence-precondition tests are no longer valid after the experiment, independently of branch identity.

## Current regression exclusions

The controlled run deselects 18 nodes in total: the 12 historical AR-04C failures above, five further synthetic authorization tests whose asserted identity is the old execution branch/HEAD, and one retired C1 RED. The additional five are:

1. `test_ar04c_execution_head_missing_from_authorization_fails_closed`
2. `test_ar04c_authorization_parameter_mismatch_cannot_create_claim[max_tokens-64]`
3. `test_ar04c_authorization_parameter_mismatch_cannot_create_claim[provider_reservation_usd_micro-1]`
4. `test_recheck_wrong_reservation_rejects_before_claim`
5. `test_legacy_authorization_path_remains_compatible`

Four of these synthetic authorization tests would fail closed at the candidate's intentionally different branch binding before testing the missing-field, parameter-mismatch, or reservation condition they name. `test_legacy_authorization_path_remains_compatible` explicitly mocks the historical branch and uses a temporary authorization/claim, so a pass would only demonstrate that mocked legacy path, not the candidate's real branch binding. Excluding all five keeps this run a current-candidate release check rather than a mixed-identity suite. Their exclusions are visible in the checked-in command file and are not counted as passes.

## C1 historical RED versus current contract

`tests/test_m4_autonomy_c1_red.py::test_explicit_protocol_followup_is_accepted_as_same_task_readonly_run_before_ttl_fix` is an intentionally retained historical RED for retired `READONLY_FOLLOWUP` classification. Current behavior is `FOLLOW_UP` with `readonly_action=INVESTIGATE`. The retired test is excluded, not rewritten, and not counted as passed.

The current-contract positive path remains in the controlled run: `tests/test_m4_autonomy_c1_acceptance_fix_01.py` exercises `FOLLOW_UP + INVESTIGATE`, and related existing C1/API/MCP regression tests remain selected. Its actual result and trace are recorded separately in `RESULTS.json` and the run log.

## Test selection

- Collection on the candidate: 751 tests.
- Controlled selection: 733 selected; 18 explicitly deselected.
- One full pytest invocation only, run from an isolated disposable worktree at the same source SHA. This isolates test-generated traces from historical evidence in the source worktree.
- The full run uses no configured Provider key or AR-04C paid-experiment enablement. All model transports in this run are deterministic test doubles / MockTransport.
- No real Provider request, browser automation, business write, claim mutation, or main merge is authorized or performed.

Final pass/fail/error counts and process exit code are recorded in `RESULTS.json` after the run exits.
