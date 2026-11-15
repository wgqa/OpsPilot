# E04-H blinding HF01 offline execution report

**Base:** `4e23e229cea3e42d61ebb2bc49f25a0e37bf5f1c`
**Branch:** `codex/r2-ar06-e04-eval-blinding-hf01`
**Runtime:** `user-demo-r2-e04-h-blind-20261115-01`

## Result

The revised E04-H fixture completed through the formal Assistant API and local Worker using a fresh, isolated Runtime. Run `run-7c9dab6e-a8ab-459e-a64a-d21e20c794bd` ended `SUCCEEDED`; Session `session-268d7776-34a8-40d4-9c1f-f3eed86f19d6` has no TaskBinding. The model chose scoped discovery, protocol comparison, source excerpt reading, and then an answer. The separate test path also verifies a legal discovery-only response that asks for missing materials.

The Fixture output distinguishes the authorized v1.0.0/v2.0.0 documents from the user's unverified claim about two migration notes. It limits the v1.4 statement to the authorized project directory and does not claim to know the deployed version. The fixture result is `UNVERIFIED`; Fixture success does not establish real-model quality or a Gold PASS.

## Isolation and source checks

- Project ID: `orders-protocol-review`.
- Authorized documents: `callback-retry-contract` v1.0.0 and `callback-retry-contract-v2` v2.0.0.
- No v1.4 document or migration-note source is registered in this Runtime.
- Document IDs, versions, source labels, file bytes, and SHA256 digests are unchanged from the previous fixture.
- No TaskBinding, Domain Observation, or Evidence was created.
- E03 continues using the separate `orders-async-demo` Runtime grant.
- Cross-tenant access, unauthorized document access, revocation, digest invalidation, and E03 regression tests passed.

The fixture scope is post-freeze and is not represented as an original frozen test artifact. Gold, Rubric, and EVAL_PROTOCOL were not modified.

## Model-visible label audit

`E04_MODEL_INPUT_AUDIT.json` records the scan of all four persisted model requests' messages and tool schemas. There were no matches for the former project name or the checked evaluation-only markers. The ordinary `deployment_version_verified=false` boundary remains present in the MCP result. This is a check of the persisted request payloads, not an inference from the final answer.

## Validation

| Check | Result |
| --- | --- |
| Python compile | PASS |
| E03 and E04 targeted suite | 14/14 PASS (E03 6/6, E04 8/8) |
| Frozen CASES hash and exact E04 input | PASS |
| Original E04 Manifest/Trace/Result hashes retained | PASS |
| New formal Assistant API Fixture run | SUCCEEDED, Fixture only |
| Provider sends / responses / UNKNOWN | 0 / 0 / 0 |
| Runtime Grant | none |
| External business writes | 0 |

The first regression attempt was RED: 6 failures and 8 passes because Fixture schema inspection called `model_json_schema()` on a dictionary returned by the installed LangChain tool wrapper; two E03 assertions cascaded from that Fixture-model error. A small Fixture-only schema snapshot helper now handles both schema objects and dictionaries. The GREEN rerun passed all 14 tests. No E03 business code, project ID, shared authorization, or evaluated Trace was changed.

## Live readiness

The revised fixture is ready for independent review before any first E04-H Live run. Live execution remains unauthorized. The separate Runbook requires a new Runtime, a separate explicit USD 0.06-or-lower budget decision, official current price and Grant preflight, one frozen submission, and no retry.
