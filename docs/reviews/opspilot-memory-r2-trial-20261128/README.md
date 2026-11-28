# OpsPilot memory and R2 integration trial

Status `ACCEPTANCE_CANDIDATE`, pending independent review.

## Baseline

| Ref | SHA |
| --- | --- |
| Remote main | `60eee87bfe3cca522011316cb4cd2c0064ad291b` |
| Common ancestor of both merge parents | `5b494fdaf20ae8eaf8fb5ec946319b2cb36fb2d0` |
| First parent, P0 and AR-05 trial | `5ef2a3c13db22c05d2d56e65cc4ccdd1efe0a6c9` |
| Second parent, `codex/r2-ar04-live-retest-version-admission-01` | `b7c444586c0ee782109e3d5931034abb27a3d597` |
| Personal profile recall fix already in the second parent's history | `91f55f6520b0333359d29482472aebd9f3fe3fb0` |

The implementation was done in its own worktree. The target branch is `codex/opspilot-memory-r2-trial-20261128`. Compare the merge commit against both parents to distinguish inherited work from conflict resolutions.

| File | First parent blob | Second parent and candidate blob |
| --- | --- | --- |
| `PROJECT_NORTH_STAR.md` | `e36f2f75509738551ac6d4a2de5b4f9cf44a7991` | `43dabda468506717c6956e676dfad4304c4f38e6` |
| `AGENTS.md` | `f174a6ab7f23f9e6d8b3ef98d455b99a75193143` | `807b928686a4dd2cac7b15b3c354b9943c93c910` |
| `.agents/skills/opspilot-slice-review/SKILL.md` | `d405c8d413d633824b279202cc1503dab4cf0b03` | `d405c8d413d633824b279202cc1503dab4cf0b03` |

Checked the v1.0 implementation baseline, current API, access, state, event recovery and memory lineage contracts, M2-01 and M2-02 deferred gates, AR-04 Gold, the pre-existing P0 RED, and the AR-05 release regression boundary. Existing evidence and review files retain their Git contents. The AR-04A and AR-04B Gold blobs remain `6c8ba3867e2dad983abe6f1b85bd559fc28e36ac` and `f5056cbb3344208e2e34671ea08a50963d3aea3d`. Lock file blobs are `de16e1113ac250511cee8d7b6a079b88b1ca4f99` for Python and `b732ef421d59fcb6eaa1e64b311801fd8b2dc760` for the frontend.

## Integration changes

- The R2 parent carries the C01 personal memory branches, including explicit memory, optional consolidation, cross-session profile recall, per-owner controls and stream/export provenance. R2 also brings session pagination, Context Builder and summary updates, and runtime Provider grants. This trial connects those paths to the earlier P0 and AR-05 integration.
- The Domain validates user history through admitted commands and their Run sources before history selection or compaction. The Assistant prepares the request from current history and appends the current Run's tool exchanges. Confirmed conditions enter the separate `CURRENT TASK CONDITIONS` block and count toward the same input budget. Saved bound history and condition revisions undergo validation before dispatch or replay.
- The S3 workbench keeps the condition review panel on the bound Task alongside the R2 chat and personal memory controls. Both legacy model classification paths apply the existing authorization rule. The merge leaves the R2 migration sequence through v24 intact and adds the existing P0 condition-review field as an idempotent v25 migration.
- The first integration run lost personal recall because source checking replaced the local source ID still needed by the memory lookup. The fix takes the ID from the validated persisted message. The initial offline assertion failures and SDK captures remain available locally. History source rejection retains the existing S3 display error code. Two frontend test expectations now use the stable Run and source message identifiers already used by R2.
- If a compression source becomes invalid during a model request, source filtering can leave enough context to answer directly. The trial reproduced the original Run failure with the mock transport. The fix invalidates the compression attempt, retains the settled dispatch in the ledger and rebuilds context. A second compression still uses its own ledger entry when the remaining context requires it.

## Offline replay

All selected backend tests use local SQLite, mock models and transports, or test-only HTTP/MCP services. Use an isolated fixture database and check the Provider flags before running. On Windows, check hash-pinned evidence with the exact committed bytes when the checkout converts LF to CRLF.

| Coverage | Test selection |
| --- | --- |
| P0 Task isolation, current conditions, and review | `tests/test_p0_01_task_context.py`, `tests/test_p0_02_task_conditions.py`, `tests/test_p0_02_bridge.py` |
| AR-05 and business safety | `tests/test_ar05_s1_session_bridge_01.py`, `tests/test_ar05_s2_assistant_handoff_01.py`, `tests/test_d3_actions.py`, `tests/test_d4_recovery.py`, `tests/test_m1_event_process_recovery.py`, `tests/test_m4_01_dialogue_update_safety.py` |
| Personal memory and Provider boundary | `tests/test_c01_b_personal_memory.py`, `tests/test_c01_b2_a_personal_memory.py`, `tests/test_c01_b2_b_personal_memory_auto_consolidation.py`, `tests/test_c01_b2_live_01_hf02_memory.py`, `tests/test_c01_b2_live_01_hf02_stream.py`, `tests/test_live_02_fix_01_hf01_profile.py`, `tests/test_live_02_fix_01_memory.py`, `tests/test_product_01_runtime_grant_01_hf01.py`, and the C01 current-Run tool projection test |
| S3 historical sources and C01 Session behavior | `tests/test_live_02_fix_01_history.py` and the C01 pagination, transcript replay, and 40-turn Session tests |
| AR-04 compaction and recovery | `tests/test_ar04_live_summary_persist_hf_01.py`, `tests/test_ar04_summary_fact_retention_edges_hf_02.py`, `tests/test_ar04_summary_fact_retention_hf_01.py`, `tests/test_ar04_summary_persist_budget_hf_01.py`, `tests/test_ar04a_compression_cancel_hf_01.py`, `tests/test_r2_ar04_compaction_c06_hf_01.py` |
| Frontend | `node --experimental-transform-types --test frontend/test/*.test.ts` with `AR05_TRACE_PATH` from the local MCP/HTTP journey in `test_formal_worker_investigates_same_session_through_real_mcp_and_http`. `npm --prefix frontend run build` |

Run backend selections using `python -m pytest -vv --tb=short -p no:cacheprovider --basetemp=<new-fixture-directory>`. To save the P0 serialized SDK request and summary replay, set `OPSPILOT_BRIDGE_EVIDENCE` to a new local directory. The combined 24-turn replay recorded nine compressions. Before review, three of four strings appeared in the historical summary and the protocol condition was absent. After user confirmation, the SDK request carried all four source-linked conditions in the dedicated conditions block. The prior seven-generation RED and its original result remain unchanged.

The latest result for each selected test is 219 backend passes and 37 frontend passes, with zero failures or skips in those selections. The backend breakdown is 13 P0, 66 AR-05 and business safety, 94 memory and Provider boundary, 11 historical source and C01 Session, and 35 AR-04 compaction tests. A focused rerun of the five cancellation tests covers both outcomes after source invalidation. Initial failed runs are retained outside Git. The frontend type check and production build also passed.

Migration replay backed up two isolated and populated test databases. v19 preserved five condition review records and v24 preserved one active memory. Both reached v25 with a single review column, passed SQLite integrity checks, and preserved those records on a second initialization. Rollback to older binaries against a migrated database remains unverified.

## Limits

- Real Provider semantics, live rollout, browser acceptance and a whole-repository run were outside this trial. Paid Provider calls and external business writes were zero. AR-04B remains separately `HOLD / UNVERIFIED`. Older paid experiments remain bound to their frozen versions and authorizations.
- Natural-language condition discovery still uses the authorized legacy classifier route. A deployment with only a runtime grant receives `MODEL_CONFIGURATION_MISSING` for discovery. The confirmed-condition and ordinary Assistant paths remain available under their existing authorization.
- A Git merge preview of the separate `codex/r2-ar06-e11-d-readiness-01` branch found a conflict in `opspilot/assistant.py`. Its E03 experiment routing, observation guidance and later evaluation evidence remain in its own line, outside the memory integration.
