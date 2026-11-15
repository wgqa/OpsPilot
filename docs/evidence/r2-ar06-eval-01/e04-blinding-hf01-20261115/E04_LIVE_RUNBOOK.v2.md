# E04-H first Live Runbook — blinded fixture v2

Use only after independent acceptance of HF01 and a separate explicit user authorization for the E04-H Live cost. This Runbook does not authorize a Provider request or create a Runtime Grant. Suggested application budget ceiling: **USD 0.06 for one first Run**; confirm the official current price, local rate configuration, token limits, and worst-case reserve at execution time.

The frozen question is submitted by the Runner directly from `CASES.json`. Do not add a prompt hint, manually rewrite the question, or expose expected outcomes to the model.

## 1. Create a new Runtime

Run in PowerShell from the repository root. Choose a name that has never existed; if the suggested name already exists, choose a new suffix. Never reset or reuse a prior Runtime.

```powershell
$runtime = 'user-demo-r2-e04-h-live02'
if (Test-Path ".runtime/$runtime") { throw "Runtime already exists; choose a new name." }
python scripts/user-demo/run_r2_ar06_case.py prepare --case-id E04-H --runtime-name $runtime
python scripts/user-demo/run_r2_ar06_case.py preflight --case-id E04-H --runtime-name $runtime --mode offline
```

Confirm the selected isolated project is `orders-protocol-review`, with exactly `callback-retry-contract` v1.0.0 and `callback-retry-contract-v2` v2.0.0. The registry's post-freeze manifest status is operator metadata; it must not appear in model messages or tool schemas. Confirm the Runtime is fresh, has no Grant, no Session/Run, no Provider requests, and no UNKNOWN request.

## 2. Configure cost authorization only after approval

After a separate user authorization, verify the local DeepSeek model, endpoint, official current pricing, configured rates, per-request token caps, and the existing maximum of eight model dispatches per Run. Configure a dedicated Grant for this Runtime only, with a ceiling no higher than the approved amount. Do not reuse another case's Grant, copy its ledger, lower configured rates, or automatically extend a pool.

```powershell
python scripts/user-demo/runtime_admin.py configure --runtime-name $runtime
python scripts/user-demo/runtime_admin.py preflight --runtime-name $runtime
```

If the eight-dispatch worst-case reserve exceeds the approved cap, stop and obtain a new budget decision. Do not send a request until Live Preflight confirms the Grant, remaining budget, model and selected Runtime all match.

## 3. Start and preflight Live services

```powershell
./scripts/user-demo/Start-UserDemo.ps1 -Mode Live -RuntimeName $runtime
python scripts/user-demo/run_r2_ar06_case.py preflight --case-id E04-H --runtime-name $runtime --mode live --authorized-max-cost-usd 0.06
```

Continue only if the process is local, API and Worker are ready, the selected Domain and Checkpoint belong to this Runtime, the neutral project authorization contains only the two listed protocol documents, and there is no prior Provider activity or UNKNOWN request.

## 4. Submit the frozen question once

```powershell
python scripts/user-demo/run_r2_ar06_case.py run-live --case-id E04-H --runtime-name $runtime --authorized-case-id E04-H --authorized-max-cost-usd 0.06
```

The model can choose among authorized discovery, comparison, source excerpt reading, asking for missing materials, or stopping. No tool order is required. Stop on Preflight failure, budget mismatch, UNKNOWN, unclear submission status, timeout, or incomplete evidence association. Never retry or resubmit this first Run.

## 5. Stop and preserve evidence

```powershell
./scripts/user-demo/Stop-UserDemo.ps1 -RuntimeName $runtime
python scripts/user-demo/runtime_admin.py summary --runtime-name $runtime
$sessionId = '<RUNNER_OUTPUT_SESSION_ID>'
python scripts/user-demo/export_live_evidence.py --runtime-name $runtime --session-id $sessionId --actor-id support-a --output ".runtime/$runtime/evidence/E04-H.live.trace.json"
```

Keep the original database, Checkpoint, Grant, ledger, Runner result, and exported trace. Review the actual persisted model request payloads for the neutral project ID and absence of evaluation labels; inspect Provider usage, spend, UNKNOWN, MCP results, and source digests. Application-ledger settlement is not the provider invoice. `SUCCEEDED` is not a Rubric PASS; the main Agent scores the frozen Rubric independently.
