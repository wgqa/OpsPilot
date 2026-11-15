# R2-AR06 E09-D HF01 report

**Status:** `ACCEPTANCE_CANDIDATE` for independent review. Offline only; no Live authorization is implied.

## Baseline and scope

- Base: `321e6a5d450dbe15c44aa227286de51000d92017`
- Branch: `codex/r2-ar06-e09-d-hf01`
- Worktree: `D:\OpsPilot-LIVE-02-FIX-01-HF02` (reused; no new worktree)
- Frozen turn script SHA256: `744abd7ae909b4e4bac02b2b9fa389a98a0ba8a1450d75f735199d5856da99cc` (unchanged)
- Production Assistant, Context Builder, Memory, Domain, Schema, Gold, Rubric, and prior v3 evidence are unchanged.

The only code change is in `tests/test_r2_ar06_e09_readiness.py`. The Fixture reply now derives its displayed `max_attempts` and claimed version only from currently visible `HumanMessage` content. Summary assertions retain their first source unless an explicit user correction is present; corrections cite the correction turn sequence and preserve the prior claim source.

## Evidence

- RED: `E09_HF01_RED_LOG.txt`; previous v3 summary source drift is separately detailed in `E09_HF01_SOURCE_AUDIT.json`.
- GREEN: `E09_HF01_FINAL_REGRESSION_LOG.txt` — E09 module **5/5**.
- Context regressions: `AR04A_CONTEXT_COMPRESSION_REGRESSION_LOG.txt` — **14/14**.
- Latest isolated Assistant/API Fixture trace and actual model inputs: `E09_OFFLINE_TRACE.json`, `E09_MODEL_INPUT_AUDIT.json`, `E09_SUMMARY_PROVENANCE_AUDIT.json`, `E09_RUNNER_RESULT.json`.
- Offline Live-plan verification: `E09_LIVE_PREFLIGHT.json`; manual execution instructions: `E09_LIVE_RUNBOOK.md`.

The latest Fixture journey completed **11/11 Runs**, with **16 Fixture dispatches**, **3 persisted summaries**, and **13 summary dependencies**. Turn 1's actual model input and answer do not contain the future `max_attempts=5` value, the `syn-send-001` log marker, or the claimed v1 statement. After turn 2 supplies that material, the response labels those values as unverified user assertions.

The current Taskless Summary's `user_assertions` reference the original turn-2 message ID and its digest. The direct `MESSAGE` dependency digest matches the persisted message digest. A later repetition does not change that reference. The explicit-correction path is verified with a synthetic correction fixture (sequence 9); its summary retains original sequence 3 and records correction sequence 9. The frozen E09 script itself contains no correction turn.

Summary scope remains unchanged: later Taskless model input can see a current Taskless Summary; the Task-bound Run does not receive that Summary. The selected recent pre-binding goal/source review remains visible. No change was made to production Summary selection or cross-Task scope.

## Test commands and results

```powershell
python -m pytest tests/test_r2_ar06_e09_readiness.py -q --tb=short --basetemp <new-isolated-path>
python -m pytest tests/test_ar04a_context_journey_01.py tests/test_ar04a_compression_cancel_hf_01.py tests/test_ar04a_compression_budget_hf_01.py -q --tb=short --basetemp <new-isolated-path>
```

The final E09 run passed **5/5** in 33.27s. AR04A Context/Compression passed **14/14** in 149.93s. Initial RED and the corrected test assertion are retained in this directory. No all-repository suite was run.

## Live readiness and limits

The frozen script hash and all ten turn hashes pass. The offline plan verifies ten sequential Taskless Runs followed by one trusted order-binding/current-query Run. `MAX_CHAT_ATTEMPTS=3` counts answer and compression attempts together; the conservative ceiling is 11 × 3 = 33 Provider dispatches. Under the previous runbook's peak planning rates and 12,000/2,048 token caps, the planning bound is USD 0.1999008; USD 0.22 was the previously proposed pool ceiling, not an authorization. Recheck official price and local configuration before any future Live run.

`run_r2_ar06_case.py run-live` does not support E09-D multi-turn execution. No wrapper was added in this fixture-only HF01; the current documented path is the existing User Demo UI and formal Assistant API, with the UI's persisted operation ID. A separate E09 automation wrapper remains unimplemented. No Live Preflight, Runtime Grant, Provider call, browser automation, or business write was performed here.

**Recorded activity:** real Provider requests 0; Grants created 0; UNKNOWN 0; external business writes 0; browser Live `NOT_RUN`; all-repository tests `NOT_RUN`.

## Known limitation

This is deterministic Fixture evidence for message visibility and source-sequence behavior, not proof that a real model will produce a faithful summary. The Taskless Summary remains deliberately unavailable to the subsequent Task-bound model call; this HF01 does not change that scope contract.
