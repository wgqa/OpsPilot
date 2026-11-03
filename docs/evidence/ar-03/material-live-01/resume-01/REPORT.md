# AR-03-MATERIAL-LIVE-01 Resume 01 — execution preparation report

Status: `ACCEPTANCE_CANDIDATE` / `PREFLIGHT_READY_AWAITING_PAID_AUTHORIZATION`

## What is ready

The accepted safe branch now has a new isolated campaign identity, a separate pending claim record, a dedicated future Domain/Checkpoint path, and a preflight entry point bound to the accepted base, the exact new branch, and the frozen MAT Cases blob. The preflight reuses the accepted `run_live.py`; it does not create a second live execution engine.

The pending record is not paid authorization and is not a consumed one-shot execution claim. The new Runner's `--execute-once` refuses before claim or database creation. `create_assistant_model()` independently refuses this prepared experiment ID even if global Provider opt-in and model configuration are present. A later paid task must explicitly enable a new one-shot dispatch and re-run the official price/wire preflight.

## User journey and free evidence

No new user-facing capability was added. The zero-cost preview used the formal API, Worker, `ASSISTANT_V1`, deterministic FixtureModel, MCP and Domain path with a fresh temporary database. The trusted API bound `ar03-order`; the current same-Event Delivery was `HTTP 202 / ACKNOWLEDGED` and the Receiver was `QUEUED`. The worker recorded two actual MCP observations and a current source response; protected business-write tables remained empty. The three FixtureModel calls are local deterministic dispatches, not Provider HTTP requests.

The new experiment ledger initialized independently at 16 Provider / 10 MCP with zero used, reserved, or settled budget. The real campaign runtime and checkpoint files remain absent, as required before the future one-shot execution. The old claim, ledger, result, trace, old runtime paths, and frozen Gold were not opened for writing; the previous claim digest is checked by the new preflight and the old artifact hashes matched before/after the formal preview.

## Changes

- `opspilot/domain/assistant_experiment.py`: add one explicitly named new campaign identity to the existing allowlist and fresh-schema constraint; assign the unchanged 16/10 and $10.50 caps.
- `opspilot/domain/assistant.py` and `opspilot/assistant.py`: scope the existing Run limit and Skill ON/OFF behavior to the new identity; fail closed on real Provider construction until separate paid authorization.
- Existing `run_live.py`: allow the untracked-run evidence prefix to follow its configured evidence directory, fixing stale path binding.
- New `resume-01/run_live.py`: bind the accepted Runner to the new branch, base, identity and isolated paths; report only sanitized preflight fields; block `--execute-once`.
- `PREPARED_CLAIM.json`: record the pending, unconsumed identity and frozen limits.

No Gold, business Gate, TaskControl contract, tool capability, approved budget, or main branch changed.

## Verification and limitations

- New focused preparation/recovery regression: 21 passed.
- Broader selected regression: 73 passed / 4 failed. The same four failures reproduced unchanged on the accepted safe base; see `FAILURES.md` and local private logs.
- Python `compileall` and `git diff --check`: passed.
- Zero-cost formal API/Worker/MCP preview: passed; Provider HTTP=0; business writes=0.
- Final preflight at implementation HEAD `9cca2504005aeb7bd4e7ad7ad69fb0f3ddfdd26c`: exit 0, `PREFLIGHT_READY_AWAITING_PAID_AUTHORIZATION`.
- Full pytest, browser, official price refresh, live Provider, and paid execution: not run.

The only appropriate next action is independent review and, if approved, a separate paid execution authorization. This report does not self-sign PASS.

## Six-question summary

1. **User change:** No live-model result yet; the next approved material campaign can reach its frozen preflight instead of failing on the old branch/claim binding.
2. **Agent decision:** Unchanged and not evaluated with a real model in this slice.
3. **Observation-driven:** The fixture preview proved that current same-Event 202/ACKNOWLEDGED and QUEUED facts traverse the formal read path; real model behavior remains unverified.
4. **Constraint:** The prepared identity cannot send Provider requests before separate authorization; the positive offline worker run proves legal trusted binding and read-only MCP remain available.
5. **Simplification:** Reused the prior runner and ledger, adding only identity/path binding and an authorization-pending refusal; no new runtime or budget service.
6. **Evidence and stop:** Exact preflight, 21 focused passes, 4 accepted-base failures, and zero paid requests are recorded. Stop here; do not consume a claim or send to Provider.
