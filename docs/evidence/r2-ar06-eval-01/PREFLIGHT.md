# R2-AR06-EVAL-01 Preflight

## Baseline and isolation

- Repository: `wgqa/OpsPilot`.
- Reused worktree: `D:\OpsPilot-LIVE-02-FIX-01-HF02`; no new worktree created. Inventory count before/after branch creation: 76 / 76.
- Base: `codex/r2-ar03-user-test-ready-01@27c11fa341717f462286da1dd92568e7dce59469`.
- Candidate branch: `codex/r2-ar06-eval-01`; branch was created in the reused clean worktree. The target Demo directory `.runtime\user-demo` was inventoried without opening its SQLite files; its Domain/checkpoint and lock remain untouched.
- Before switch: clean worktree, expected branch/HEAD, no listener on ports 8000/5173/5174/8080. After branch creation: HEAD unchanged and worktree count unchanged.
- `origin` read at start was attempted; the remote lookup was unavailable because the connection reset. Cached local tracking refs showed the Base branch at the requested SHA. Remote freshness remains UNVERIFIED until a later push/read succeeds.

## Files actually read at the Base

| File | Git blob | Finding/use |
|---|---|---|
| `PROJECT_NORTH_STAR.md` | `43dabda468506717c6956e676dfad4304c4f38e6` | User outcome and Agent decision first; six work types and 12 representative cases remain R2 scope; model authority remains bounded; §8 evidence and failure preservation. |
| `AGENTS.md` | `807b928686a4dd2cac7b15b3c354b9943c93c910` | Trusted bindings and Domain contracts remain authoritative; no bypass of approvals/action ledger; mock is not real-model evidence; preserve historical failures. |
| `TASKS.md` | `1f08ee3a8e538d7ece4d2b2841c7c53e25737b7c` | R2 requires six work types, Context/Memory/Skill, S1/S2, 12 cases and interview/source material. |
| `.agents/skills/opspilot-slice-review/SKILL.md` | `d405c8d413d633824b279202cc1503dab4cf0b03` | Actually read and applied its A opening checks; North Star §8 governs. |
| User task card | attached text in this request | Phase A offline assets only; no paid Provider, browser automation, external business write, main merge or Demo reset. |

## Reused artifacts and evidence

| Existing source at Base | Blob / identity | Reuse boundary |
|---|---|---|
| `docs/evidence/vnext/m2-02/EVAL_PROTOCOL.md` | `65e50256a7ed42d303efbba153bb711bd3542777` | Reuses oracle separation, explicit NOT_RUN handling, real-vs-fixture usage and non-weighted R/H/A framing; old 16-case scope is not this case set. |
| `docs/evidence/vnext/m2-02/GOLD.json` | `25b4371fc40bcc76f09c0b7f8fd633c3356382ab` | Historical 8 development + 16 holdout S2 cases; not relabeled as the new 12. |
| `docs/evidence/vnext/m2-02/RUBRIC.json` | `ee0f85cacc43d0736a69d592c33df9e5bb66e8ec` | Reuses PASS/PARTIAL/FAIL/NOT_RUN/UNVERIFIED and separate fact/source, outcome, cost, safety dimensions. |
| `docs/evidence/vnext/product-01-slice-02-live/CASES.json` | `0e2216f3a407b512200c8b1df3a823f8fb743ef4` | Historical four-turn materials/current-event/correction journey; separate live evidence only. |
| `docs/evidence/vnext/product-01-slice-02-live/RESULTS.json` | `1a4e3fdac75867574500263d98fde2d394d3e094` | Historical PARTIAL result; not an AR06 trial. |
| `docs/evidence/ar-03/real-llm-02/REPORT.md`, `RESULTS.json` | `bbece22b33deccc6e6b2adc5a9760fccca99d7e9`, `4a09f624cf54437c10e6414e0f9b540a4ab00d68` | Historical two-case live comparison: 5 provider requests, 11 MCP calls, paired user outcome PARTIAL because PROCESSED case lacked a final answer. |
| `docs/evidence/ar-04c/live-exec-01/REPORT.md`, `RESULTS.json` | `5517f5ce51a954caa822bf711a64de128f9c26fd`, `352c600de2eba7ad6ebe79e9406428f7ca6c5e92` | Historical Memory OFF/ON live journey: 8 provider requests, 14 MCP calls, 47,088 input / 4,883 output tokens, business evaluation PARTIAL; ON produced a false current-read claim. |
| `docs/evidence/r2-ar03-integrated-journey-01/GOLD.md`, `REPORT.md`, fixture trace | `6ebadab468d26a55aa39756155f930d37eb112fc`, `01562b9db497acc2382638e47b31d181ec4c8c3a`, `3cb7949d78234e54e7f03df20b54f90f7ad9fd5d` | Reuses synthetic J1/J2/J3 inputs, current Same-Event assertions, and local formal API/Worker/MCP trace. It records no real Provider calls. |

Relevant Base tests read: `tests/test_r2_ar03_integrated_journey_01.py` (J1, same-Event QUEUED/PROCESSED, cross-Tenant denial, held-out/simple answer, history no-current-read), `tests/test_ar04a_context_journey_01.py` (long-session summary in actual Fixture Model input and source invalidation), `tests/test_ar04b_memory_journey_01.py` (cross-task selection, Owner/Tenant isolation and revocation), `tests/test_ar05_s2_assistant_handoff_01.py` (draft vs explicit local receipt), `tests/test_ar05_s1_session_bridge_01.py` (independent approvals, revalidation, local verification and delivery), and `tests/test_ar03_material_01.py` (authorized source excerpts and user material provenance).

## Six scope checks

1. **User outcome:** a frozen, reproducible evaluation set and interview report, not a production Agent change.
2. **Agent decisions:** direct answer, document/Skill choice, current scoped observation, clarification, or safe stop remain valid choices; no fixed tool order is added.
3. **Trusted observations:** current business states/outcomes are scored from Domain/MCP/receipt evidence, not the model's sentence or Run status.
4. **New hard restriction:** none. Evaluator rules prevent outcome inflation and preserve safety findings.
5. **Simpler implementation:** reuse existing tests and evidence; add only frozen case/rubric files and a task-specific JSONL aggregator, not a runtime/harness/platform.
6. **Acceptance/stop:** offline fixture regressions, JSONL aggregation, accurate report and interview brief; stop before paid model, browser, external business action or main merge.

## Contracts and deferred gates

The M2-01/M2-02 deferred gates were read. Scope/Grant/Policy writes, S2 `SCOPE_ESCALATED` outside its separately authorized local test, S1 repair without independent approval/revalidation, and production claims unsupported by live evidence remain prohibited. The current evaluation does not widen those contracts. S1/S2 fixture tests use temporary local Domain/Checkpoint only; any local test receipt is not an external business write.
