# C01-B2-A Verification Record

**Base:** `1c48f365c93fcef1b7e97cfe4941f6bb83a0a9de`

**Branch:** `codex/c01-b2a-default-personal-memory`

**Scope:** offline candidate validation only; no production database, real Provider, real external MCP service, or external business write was used.

## Candidate behavior exercised

- A Fixture Model called the real local `memory_remember` tool for an explicit save. The tool derived tenant, owner, and source message from the active Run; the persisted record was `USER_EXPLICIT`, and its receipt contained no memory content.
- A second Session received the PINNED preference in the actual recorded model request without lexical overlap. The completed Run's LangGraph thread was removed after its answer committed.
- A project background was selected for a related query and excluded from an unrelated query. PINNED selection stayed within three items and the 250-token estimate budget.
- One-shot, quoted/log-derived, and secret-like save attempts did not create memories. A later explicit correction created a checked next version; revoke removed the memory from subsequent Provider input; a fresh explicit save after revoke succeeded.
- The recall setting defaulted on, persisted per trusted tenant/owner, disabled later request injection without deleting memory, and allowed recall after re-enabling.
- The v21-to-v22 isolated migration preserved events, foreign keys, candidate state, and prior confirmation semantics; repeated initialization passed.
- Memory lookup failure degraded to ordinary chat without injecting memory. Existing C01-B source/currentness, actor/tenant isolation, Context, compaction, D5, and Runtime Grant regressions passed.

## Commands and results

| Command | Result |
|---|---:|
| `python -m compileall -q opspilot tests/test_c01_b2_a_personal_memory.py` | PASS |
| `python -m pytest -q --basetemp=.pytest-c01b2a-final-04 tests/test_c01_b2_a_personal_memory.py` | 6 passed in 17.14s |
| `python -m pytest -q --basetemp=.pytest-c01b2a-final-05 tests/test_c01_a_session_context.py tests/test_c01_b_personal_memory.py tests/test_c01_b2_a_personal_memory.py tests/test_m303_semantic_memory.py tests/test_ar04a_context_journey_01.py tests/test_ar04b_memory_journey_01.py tests/test_d5_context.py tests/test_product_01_runtime_grant_01.py tests/test_product_01_runtime_grant_01_hf01.py` | 81 passed in 218.62s |
| `python -m pytest -q --basetemp=.pytest-c01b2a-business-03 tests/test_d2_investigation.py tests/test_d3_actions.py tests/test_ar05_s1_session_bridge_01.py tests/test_ar05_s2_assistant_handoff_01.py tests/test_m4_02_s3.py tests/test_m4_03_s3.py` | 67 passed in 80.43s |
| `npm run build` (in `frontend/`) | PASS; `vue-tsc --noEmit` and Vite build |
| `npm run test:e2e:c01-a` (in `frontend/`) | PASS; Session restore, pagination, refresh, reopen, multi-Session isolation |
| `npm run test:e2e:c01-b` (in `frontend/`) | PASS; candidate preview, owner scope, confirmation, persistent toggle, TTL disclosure, revoke refresh |
| `git diff --check` | PASS |

Pre-implementation baseline at the base SHA was **37 passed** across C01-A/C01-B, M3, AR04B, and D5. An initial comprehensive run was started alongside the business regression and stopped after no progress; the same comprehensive suite was then rerun sequentially and passed as recorded above. This was an interrupted test run, not an assertion failure.

`npm ci --cache .npm-cache-c01b2a` completed using an isolated cache after a shared-cache `EPERM` on the first attempt. No dependency manifest or lockfile changed. npm reported 10 moderate advisories for the existing dependency tree.

## Cost and side-effect boundary

The model tests use a local Fixture Model with synthetic usage metadata. No real Provider was called or charged. Runtime Grant and S1/S2/S3 tests use isolated temporary databases, where fixture records and domain transitions are permitted; no existing ledger or external business system was touched. The new local tool is not an MCP call and does not consume the MCP attempt budget.

## Data and implementation footprint

- Schema user_version advances to 22. Existing `personal_memories` gains `memory_mode` and `creation_source`; its event check accepts `USER_EXPLICIT_CREATED`; one minimal `personal_memory_settings` table stores an owner-scoped recall toggle.
- No new dependency, Memory framework, Context manager, Agent Runtime, EventBus, worker, queue, or vector store was added.
- The existing personal-memory source, version, idempotency, confirmation, revocation, expiry, audit, and Context Builder paths are reused. Business Semantic/Episodic approval rules are unchanged.
- Completed Runs that sent personal memory or called the save tool delete their Checkpoint thread only after the final answer is durable. The source Session message and the personal-memory source record remain intact.
