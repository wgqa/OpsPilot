# E08-H First Live Runbook

Status: **not authorized for Provider spending by this task**. Do not create a Runtime Grant or run Live until the user separately authorizes a specific budget.

## Prepared isolated Runtime

This worktree has an isolated, primed candidate Runtime:

```powershell
$runtime = 'user-demo-r2-e08h-live-prime-20261115'
```

Its files are under `.runtime/$runtime/`. The Runtime contains one Fixture Model history Run, a new SUPPORT Session, and the trusted `async-order` TaskBinding. Target Event `...0101` is now `PROCESSED`; decoy Event `...0102` remains `QUEUED`. The historical answer's source is invalidated by the target version change. It has no Grant, no spend pool, no Provider sends, no UNKNOWN requests, and no running managed processes.

Verify before any future authorization:

```powershell
python scripts/user-demo/run_r2_ar06_case.py preflight --case-id E08-H --runtime-name $runtime --mode offline
python scripts/user-demo/runtime_admin.py summary --runtime-name $runtime
```

Expected: `OFFLINE_HISTORY_PRIMED`; Runtime Grant not configured; no fee pool. If the Runtime is missing or its state differs, use a **new name** and run the initialization/priming sequence below. Never reset or reuse a different case Runtime.

## Rebuild an isolated primed Runtime if needed

The commands below create a new runtime and refuse an existing directory:

```powershell
$runtime = 'user-demo-r2-e08-h-live01'
python scripts/user-demo/run_r2_ar06_case.py prepare --case-id E08-H --runtime-name $runtime
python scripts/user-demo/run_r2_ar06_case.py preflight --case-id E08-H --runtime-name $runtime --mode offline
```

Configure `OPSPILOT_WEB_SUPPORT_PASSWORD` locally through the worktree `.env` or the process environment. Do not print it or place it in command history. Then seed the history using only the local Fixture Model; this command stops before submitting the frozen question:

```powershell
python scripts/user-demo/run_r2_ar06_case.py prime-history --case-id E08-H --runtime-name $runtime
python scripts/user-demo/run_r2_ar06_case.py preflight --case-id E08-H --runtime-name $runtime --mode offline
```

The second preflight must return `OFFLINE_HISTORY_PRIMED`. Repeating `prime-history` on a populated Runtime is rejected. No API/Worker service should be running while `prime-history` uses its embedded TestClient/Worker.

## Authorization and price checks (future Live only)

On 2026-11-15 the local configuration reported model `deepseek-flash`, endpoint `https://api.deepseek.com`, config version `deepseek-v4.1-flash-1017`, price version `DEEPSEEK_FLASH_PEAK_2026-11-14`, peak input rate USD 0.30 / million tokens, and peak output rate USD 1.20 / million tokens. These matched the current [official DeepSeek pricing page](https://api-docs.deepseek.com/quick_start/pricing/), which also lists lower off-peak and cache-hit rates. Recheck the official page and this worktree's local settings immediately before any future Grant; provider prices can change.

The existing Runtime contract bounds each request at 12,000 input and 2,048 output tokens and a Run at 8 model dispatches. At peak cache-miss input/output rates, the conservative 8-dispatch reservation is:

`8 × ((12,000 × $0.30 / 1,000,000) + (2,048 × $1.20 / 1,000,000)) = $0.0484608`

The prior readiness plan suggested USD 0.06 for a single Run; this is only a recommendation, not authorization. If separately authorized, use a **new E08-specific Runtime Grant** whose application budget does not exceed the approved amount. Never reuse another case's Grant. Use the existing interactive flow, which requires the operator to confirm the exact amount:

```powershell
python scripts/user-demo/runtime_admin.py configure --runtime-name $runtime
python scripts/user-demo/runtime_admin.py preflight --runtime-name $runtime
```

Do not bypass its confirmation. This task did not execute either command.

## Single first Live Run (after separate authorization)

Set only this worktree's local provider credentials in `.env`; do not log or commit them. Start the existing local services:

```powershell
.\scripts\user-demo\Start-UserDemo.ps1 -Profile S1 -Mode Live -RuntimeName $runtime
python scripts/user-demo/run_r2_ar06_case.py preflight --case-id E08-H --runtime-name $runtime --mode live --authorized-max-cost-usd 0.06
```

Proceed only if the preflight verifies the matching Runtime, Grant, zero prior Provider sends/UNKNOWN, target/decoy fixture, managed loopback services, and enough unused pool for the Run's worst-case reservation. Submit the frozen question once:

```powershell
python scripts/user-demo/run_r2_ar06_case.py run-live --case-id E08-H --runtime-name $runtime --authorized-case-id E08-H --authorized-max-cost-usd 0.06
```

Do not retry or resubmit after any ambiguous submission, timeout, UNKNOWN request, insufficient balance, source mismatch, or service error. Inspect the existing result and ledger instead. Stop gracefully and retain all data:

```powershell
.\scripts\user-demo\Stop-UserDemo.ps1 -RuntimeName $runtime
python scripts/user-demo/runtime_admin.py summary --runtime-name $runtime
```

The Runner writes the trace and result under `.runtime/$runtime/evidence/E08-H.json` and `.runtime/$runtime/evidence/E08-H.result.json`. Preserve the first response, Provider Response ID, MCP calls, Observation/Evidence IDs, input/output tokens, settled amount, UNKNOWN count, and source links for independent M1–M6 scoring. Runner success is not a Gold PASS.
