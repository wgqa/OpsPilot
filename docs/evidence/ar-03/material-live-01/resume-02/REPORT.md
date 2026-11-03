# AR-03-MATERIAL-LIVE-01-RESUME-02 — Candidate report

**Status:** implementation is being prepared for submission. The authorized paid campaign has not started; a clean-worktree preflight is still required.

## User-facing result

No user has received a new live model answer yet. The first preflight attempt was blocked because authorized implementation changes were still uncommitted. All seven cases remain `NOT_RUN` pending the required clean-worktree preflight; this is not a model-quality or business-capability result.

## What changed

- Added the exact RESUME-02 experiment ID to the existing experiment budget schema, authorization-required set, and fixed 16 Provider / 10 MCP policy.
- Added a separate exact one-shot authorization and claim identity. The API key or experiment allowlist alone cannot construct a Provider client. The one-shot token is not passed to the MCP child.
- Replaced the Runner's “non-empty answer means real Provider” label with evidence-based classification using Run state, typed answer kind, source Run/message IDs, model call status, Completion ID, call and campaign dispatch Usage, and persisted answer content.
- Kept old RESUME-01 authorization and historical records unchanged.

## Evidence

The formal FastAPI/Worker/ASSISTANT_V1 path passed with explicit HTTPX MockTransport. The test observed that the persistent Provider reservation was already `RESERVED` before the mock handler returned a synthetic completion; response parsing, exact-source answer persistence, completion/Usage audit and zero business writes passed. A separate failure path retains the UNKNOWN status/reservation and classifies a program notification as such, not as a model answer.

Focused offline regression: 41 passed, 0 failed across the RESUME-02 tests, Runner Recovery 02, live recovery, live execution-prep and frozen material business tests. These are deterministic/local tests and do not demonstrate real DeepSeek behavior.

Official DeepSeek pricing was checked on 2026-11-04. The current peak input/output prices preserve the frozen per-request reserve and total application cap. The exact live request contract is unchanged.

## Paid execution status

The first formal preflight returned `WORKTREE_OR_INDEX_NOT_CLEAN`. The configured shared environment file was then checked at its correct parent-workspace path; presence-only checks confirmed the Provider key, frozen model and official host configuration, while Provider opt-in, experiment ID and one-shot token were absent. No credential value was read or displayed. The RESUME-02 one-shot claim remains uncreated and unconsumed. There have been zero real Provider requests, zero live MCP calls and zero external business writes. The RESUME-01 claim and root historical claim remain unchanged by SHA verification. The clean-worktree preflight is still required before any paid send.

The next step is to commit the reviewed candidate, re-run the exact preflight, and execute the single authorized campaign only if it returns READY. Do not place secrets in Git or chat.

## Six review questions

1. **User change:** No new live investigation result was delivered; the Runner is now ready to distinguish real model delivery from program notices when execution can start.
2. **Agent decision:** No live model decision occurred. MockTransport tests only verified the execution and audit path.
3. **Observation-driven:** No live business Observation occurred; QUEUED/PROCESSED Gold conditions remain untested in this experiment.
4. **New constraints:** The new experiment requires an exact, isolated one-shot claim. Legitimate RESUME-02 execution is covered by a MockTransport positive case; missing/wrong claim is refused. Business authorization and write rules are unchanged.
5. **Simplification:** Reused the existing Assistant, Runner, budget tables and claim pattern. No new runtime, budget service, Agent, or Domain state table was added.
6. **Evidence and stop line:** 41 local tests passed. The first preflight stopped before claim creation on dirty worktree. No live model or Gold result is claimed yet; main was not modified.
