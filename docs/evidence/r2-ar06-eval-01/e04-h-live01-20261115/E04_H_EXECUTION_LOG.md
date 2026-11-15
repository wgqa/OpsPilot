# E04-H first Live execution log

**Candidate:** `codex/r2-ar06-e04-eval-blinding-hf01@5650653638fa2b4b7ea37290f3367a6a8f9da122`
**Runtime:** `user-demo-r2-e04-h-live02`

## Authorization and configuration

- User approved one first E04-H DeepSeek Agent Run with a USD 0.06 application cap.
- The user entered the `runtime_admin.py configure` program's exact confirmation for USD 0.060000. Grant expiry: `2026-11-15T10:30:00Z`.
- Local config: `deepseek-flash`, `https://api.deepseek.com`, model version `deepseek-v4.1-flash-1017`, price version `DEEPSEEK_FLASH_PEAK_2026-11-14`. API key was present; its value was neither printed nor saved.
- Official DeepSeek peak cache-miss input/output prices were USD 0.30 / USD 1.20 per million tokens; configured rates matched. Request caps: 12,000 input and 2,048 output tokens. One maximum request reserve was USD 0.006058; eight-dispatch worst-case was USD 0.048464, below the approved ceiling. See `E04_H_PRICE_PRECHECK.json` and [official pricing](https://api-docs.deepseek.com/quick_start/pricing/).
- Offline Preflight and Runtime Grant Preflight passed. Before Live, the Grant showed USD 0.060000 available, Provider sends 0, UNKNOWN 0, and the new Runtime had no Session or Run.

## Commands executed

```powershell
python scripts/user-demo/run_r2_ar06_case.py prepare --case-id E04-H --runtime-name user-demo-r2-e04-h-live02
python scripts/user-demo/run_r2_ar06_case.py preflight --case-id E04-H --runtime-name user-demo-r2-e04-h-live02 --mode offline
python scripts/user-demo/runtime_admin.py configure --runtime-name user-demo-r2-e04-h-live02
python scripts/user-demo/runtime_admin.py preflight --runtime-name user-demo-r2-e04-h-live02
./scripts/user-demo/Start-UserDemo.ps1 -Mode Live -RuntimeName user-demo-r2-e04-h-live02
python scripts/user-demo/run_r2_ar06_case.py preflight --case-id E04-H --runtime-name user-demo-r2-e04-h-live02 --mode live --authorized-max-cost-usd 0.06
python scripts/user-demo/run_r2_ar06_case.py run-live --case-id E04-H --runtime-name user-demo-r2-e04-h-live02 --authorized-case-id E04-H --authorized-max-cost-usd 0.06
./scripts/user-demo/Stop-UserDemo.ps1 -RuntimeName user-demo-r2-e04-h-live02
python scripts/user-demo/runtime_admin.py summary --runtime-name user-demo-r2-e04-h-live02
python scripts/user-demo/export_live_evidence.py --runtime-name user-demo-r2-e04-h-live02 --session-id session-593885d5-4e12-45dd-85bf-03d33660d1e1 --actor-id support-a --output .runtime/user-demo-r2-e04-h-live02/evidence/E04-H.live.trace.json
```

The Runner submitted the frozen question once. Result: Session `session-593885d5-4e12-45dd-85bf-03d33660d1e1`, Run `run-e294b7cd-dc04-4d95-b54e-3e949d59fb18`, `SUCCEEDED`, 3 Provider responses, 4 MCP calls, no UNKNOWN. The spend summary after shutdown shows USD 0.005776 settled and USD 0.054224 remaining.

## Shutdown and evidence preservation

The Stop script printed that API, Worker and local frontend completed graceful shutdown and that Session, messages, Domain DB, Checkpoint DB and logs were retained. A PowerShell wrapper then raised because it checked `$LASTEXITCODE` after invoking a PowerShell script. Independent post-checks found no Runtime `processes.json` and no listener on `127.0.0.1:8000` or `127.0.0.1:5173`; no restart was attempted. The runtime files remain in `.runtime/user-demo-r2-e04-h-live02/`.

The exporter reported 2 messages, 1 Run, 7 calls, 0 observations and 0 evidence. It confirmed the export was redacted and that secret values and authorization material were omitted. No Gold, Rubric, shared authorization, production code, or historical Trace was modified in this Live execution. No browser automation or external business write occurred.
