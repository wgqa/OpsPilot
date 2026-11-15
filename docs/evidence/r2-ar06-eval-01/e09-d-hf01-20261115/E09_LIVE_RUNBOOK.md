# E09-D first Live runbook after HF01

**Status:** Offline-prepared candidate only. This task created no Runtime Grant and sent no Provider request. Obtain independent acceptance, a fresh price check, and a separate explicit cost authorization before Live.

## Frozen input and execution shape

- Use `E09_TURN_SCRIPT.json` without edits; required SHA256: `744abd7ae909b4e4bac02b2b9fa389a98a0ba8a1450d75f735199d5856da99cc`.
- It contains ten ordered Taskless user turns. Submit one turn, wait for its Run to reach a terminal success, then continue.
- After turn 10 only, create the `async-order` TaskBinding through the trusted order-binding UI/API and submit `trusted_task_binding.initial_message` as that binding Run. This is Run 11; do not send an additional follow-up.
- The profile is `r2-e07-queued`. Verify the actual TaskBinding and same-Event Delivery/Receiver association before interpreting status.

## Existing Runner support

`run_r2_ar06_case.py` currently supports one-turn `run-live` cases and does not list E09-D. No multi-turn Runner was added in this HF01. The existing User Demo UI calls the formal Assistant message and order-binding APIs. `frontend/src/assistant-entry.ts::beginAssistantOperation` persists the operation ID and request digest in `sessionStorage`, and `frontend/src/api.ts` sends that ID as `Idempotency-Key`. Preserve this behavior; do not resubmit if acceptance is ambiguous. Inspect the Session and Run status first, and stop if the request cannot be reconciled.

## Local setup after separate authorization

Choose a never-used runtime name. If it exists, choose another name; do not reset it.

```powershell
$RuntimeName = 'user-demo-r2-e09-hf01-live01'
.\scripts\user-demo\Initialize-UserDemo.ps1 -RuntimeName $RuntimeName -S3FixtureProfile r2-e07-queued
python scripts/user-demo/runtime_admin.py --runtime-name $RuntimeName configure
python scripts/user-demo/runtime_admin.py --runtime-name $RuntimeName preflight
.\scripts\user-demo\Start-UserDemo.ps1 -Profile S1 -Mode Live -RuntimeName $RuntimeName
```

The `configure` command must use the existing interactive confirmation. This HF01 did not run it. Before Live, verify the selected Runtime is fresh, the Support identity is `tenant-a/support-a`, the Provider/model/endpoint are correct, Runtime Grant is active, and the current balance covers the authorized plan. Do not print passwords, API keys, cookies, or authorization headers.

Open the local Web UI. Create one Session. Copy each turn body exactly from the frozen script, send it once, and wait for `SUCCEEDED` before sending the next. If a Run fails, remains UNKNOWN, a submit response is ambiguous, or compression/provenance fails, stop immediately; preserve all prior evidence and do not retry or skip ahead.

After turn 10, inspect the current Taskless Summary, source IDs and digests, and the actual turn-10 model input. Then select `async-order` from the server-filtered order list and submit the exact trusted binding initial message. Confirm the binding response, Task ID, Run ID, and current Event identity. No write, approval, repair, or handoff is part of this journey.

Export and stop:

```powershell
python scripts/user-demo/export_live_evidence.py --runtime-name $RuntimeName --session-id <SESSION_ID> --actor-id support-a --output ".runtime/$RuntimeName/evidence/e09-live-trace.json"
.\scripts\user-demo\Stop-UserDemo.ps1 -RuntimeName $RuntimeName
```

Verify the export belongs only to the selected Runtime and Session. Keep the Domain database, Checkpoint database, Grant, Spend ledger, Trace, Run results, and failed attempts intact.

## Dispatch and cost bound

There are 11 independent Runs. `opspilot/domain/chat.py` sets `MAX_CHAT_ATTEMPTS = 3`; `_chat_attempt_counts` includes both `chat_attempts` and `context_compression_attempts`, and compression reserves the next shared attempt number. The safe planning ceiling is therefore **33 total Provider dispatches**, with compression inside that count. Do not increase the per-Run budget.

The current source caps each dispatch at 12,000 input and 2,048 output tokens. Using the previous runbook's peak planning rates (USD 0.30/M input cache-miss and USD 1.20/M output), the worst-case estimate is USD 0.0060576 per dispatch and **USD 0.1999008** for 33 dispatches. The previous **USD 0.22** pool was a planning suggestion only, not approval. This HF01 did not recheck DeepSeek's current official prices; recheck the official page, local rates, model configuration, and actual Runtime Preflight immediately before Live. Do not assume cache discounts.

## Stop conditions and evidence

Stop on an invalid/expired Grant, Runtime mismatch, changed price configuration, insufficient balance, Run not terminal-success, compression failure, source digest change, TaskBinding/Event mismatch, UNKNOWN, ambiguous acceptance, or any unexpected MCP result. Do not automatically retry, replay, extend the Grant, or continue to later turns after a stop condition.

Record the exact script hash, each accepted user-message ID, Run ID/status, Summary version and source dependencies, model input/output, compression and answer attempts, Provider response IDs, actual token usage, application spend, MCP observations, TaskBinding/Event association, export digest, and shutdown result. Application spend is not the vendor's final invoice.
