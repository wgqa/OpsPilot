# E09-D first Live runbook

**Status:** Offline-ready candidate only. No Runtime Grant was created and no real Provider request was sent. Obtain independent acceptance and a separate user cost authorization before any Live setup.

## Proposed isolated journey

Use a new Runtime name, for example `user-demo-r2-e09-live01`; if its directory exists, choose another name and never reset it. It must be separate from the pytest Fixture runtime and all earlier User Demo databases.

1. Initialize a fresh database with the existing S3 fixture:

   ```powershell
   .\scripts\user-demo\Initialize-UserDemo.ps1 -RuntimeName user-demo-r2-e09-live01 -S3FixtureProfile r2-e07-queued
   ```

2. After a future explicit cost authorization, inspect local Provider configuration without printing its key, and configure only this Runtime through the existing interactive procedure:

   ```powershell
   python scripts/user-demo/runtime_admin.py --runtime-name user-demo-r2-e09-live01 configure
   python scripts/user-demo/runtime_admin.py --runtime-name user-demo-r2-e09-live01 preflight
   ```

   The existing configuration flow asks for a pool limit and expiry and then requires its exact confirmation phrase. Do not bypass that confirmation. The proposed ceiling below is an estimate for later review, not an authorization.

3. Start the matching Live API/Worker and Web app:

   ```powershell
   .\scripts\user-demo\Start-UserDemo.ps1 -Profile S1 -Mode Live -RuntimeName user-demo-r2-e09-live01
   ```

   The script checks the Grant and binds both Domain and Checkpoint databases to the selected Runtime. Confirm the API health/Worker readiness and that the browser is using this Runtime before the first message.

4. Submit the ten messages from `E09_TURN_SCRIPT.json` in order, one per completed Run, with no edits and no retries. After turn 10, inspect the persisted summary, its source dependencies, and that turn 10's actual model request contains the prior current Taskless Summary.

5. Use the normal trusted order-binding interaction for `async-order`, with the script's `trusted_task_binding.initial_message` as the binding request. This creates the TaskBinding and asks for the current Delivery/Receiver in the same Run. Do not inject a Taskless Summary into this Run. Verify new observations are linked to this Run, Task, and Event.

6. Export the Session evidence and stop cleanly:

   ```powershell
   python scripts/user-demo/export_live_evidence.py --runtime-name user-demo-r2-e09-live01 --session-id <SESSION_ID> --actor-id support-a --output .runtime/user-demo-r2-e09-live01/evidence/e09-live-trace.json
   .\scripts\user-demo\Stop-UserDemo.ps1 -RuntimeName user-demo-r2-e09-live01
   ```

   Check the exporter's current `--help` before use. Keep the Domain, Checkpoint, Grant, spend ledger, and trace intact.

The current `run_r2_ar06_case.py` does not support a multi-turn `E09-D` Live command. The offline test harness is not a paid Live runner. The sequence above uses the established User Demo and trusted Assistant API/UI path; no new Runner was added in this readiness task.

## Run and request budget

The fixture journey uses **11 independent Runs**: ten Taskless chat Runs, then one order-binding/current-query Run. `opspilot/domain/chat.py` currently sets `MAX_CHAT_ATTEMPTS = 3`; answer and compression attempts share that per-Run limit. Thus the conservative ceiling is **33 Provider dispatches total**, with compression included, not added on top. A successful Run needs a final answer, so compression consumes some of those same slots and can reduce room for tool/answer calls. Do not increase the limit for this evaluation.

The Runtime Grant's product caps are currently 12,000 input and 2,048 output tokens per dispatch. At the peak cache-miss/output rates currently recorded in source (`DEEPSEEK_FLASH_PEAK_2026-11-08`: USD 0.30 / 1M input and USD 1.20 / 1M output), one worst-case dispatch reserves:

- Input: 12,000 × USD 0.30 / 1,000,000 = USD 0.0036000.
- Output: 2,048 × USD 1.20 / 1,000,000 = USD 0.0024576.
- Total: USD 0.0060576.

At 33 dispatches, the token-bound peak ceiling is **396,000 input tokens + 67,584 output tokens = USD 0.1999008**. A later isolated Spend Pool ceiling of **USD 0.22** is proposed to allow rounding/headroom, subject to a fresh official-price check and exact local Preflight. This is a planning figure only. It is not an authorization and no Grant exists from this task.

The official [DeepSeek Models & Pricing page](https://api-docs.deepseek.com/quick_start/pricing/) was checked on 2026-11-15. It currently lists `deepseek-flash` served by DeepSeek-V4.1-Flash-1017 at USD 0.30/M peak cache-miss input and USD 1.20/M peak output, and states prices may change. The local rates and price version must match the official page at Live time; otherwise stop and request a separately reviewed price update. This runbook assumes no cache discount.

## Stop and evidence rules

- Stop before sending if Runtime identity, endpoint/model, price version/rates, token limits, Grant, Worker, or current balances do not match.
- Stop immediately on UNKNOWN, unclear submission state, missing/invalidated Summary provenance, failed compression, `CHAT_ATTEMPTS_EXHAUSTED`, missing TaskBinding, mismatched Event, or budget exhaustion. Do not retry or resubmit; preserve partial data and evidence.
- Stop after the planned binding/query Run. No extra turns or cases.
- Separate actual Provider calls, per-call Usage, compression requests, estimated input sizes, and application Spend. Application Spend is not the supplier invoice.
- Preserve unsuccessful Runs and export the first result; do not revise the script or prompt after seeing Live answers.
