# User Demo Windows lifecycle fix

This isolated candidate is based on `6faca90f5600181972aa2d61cba1df19ae734c07` and includes the SSE shutdown change from `01a8d94cfe5705d095c3fb8c31e791a48ab637f2` as commit `55ec66f`.

## Cause and change

- `Start-UserDemo.ps1` already redirected child stdout/stderr, but left stdin inherited. Hidden API and Vite children could retain the parent console input handle. Both now receive a dedicated empty stdin file, and the existing hidden-process log redirection remains.
- Vite treats stdin EOF as a shutdown signal. A small User Demo launcher sets `CI=true` in its own process before creating Vite, then watches the existing `shutdown.request` and calls `server.close()`. The API and Vite still use one shutdown file; no second process-control channel was added.
- `Stop-UserDemo.ps1` now requests shutdown for either managed child and waits up to 30 seconds for the API/Worker and Vite independently. A timeout leaves the process and manifest in place for diagnosis; the previous `Stop-Process -Force` path is removed.
- The existing API SSE shutdown fix was reused. `Start-UserDemo.ps1` also uses `Invoke-WebRequest -UseBasicParsing` so Windows PowerShell 5.1 does not pause for the first-run IE parsing confirmation.

## Windows acceptance

Run logs under `runs/` were captured in Windows PowerShell 5.1.26100.8655 in the isolated `windows-user-demo-lifecycle-01` worktree. User and machine names are redacted in the committed transcript copies. The test data lives only under that worktree's ignored `.runtime/user-demo`; startup used `-Mode Offline`, with Provider and legacy Provider paths disabled.

The same-window commands were:

```powershell
.\scripts\user-demo\Start-UserDemo.ps1 -Profile S1 -Mode Offline
Write-Host 'INPUT_OK'
.\scripts\user-demo\Stop-UserDemo.ps1
```

- `same-shell-acceptance-01.redacted.txt`: start in one PowerShell window, run `Write-Host 'INPUT_OK'`, hold a real Edge EventSource open, stop from that same window, then restart and verify the Session remains visible.
- `same-shell-acceptance-02.redacted.txt`: repeat after strengthening the browser probe to wait for its first `SESSION_CREATED` event. The event stream reports closed during Stop; the same Session is visible after restart; another same-window `INPUT_OK` and stop succeeds.
- `browser-sse-acceptance-01.log` and `browser-session-restart-02.log`: browser markers include `BROWSER_SSE_FIRST_EVENT`, `BROWSER_SSE_OPEN`, and `BROWSER_SSE_CLOSED`.
- `sqlite-retention-01.log`: the isolated Domain DB contains exactly one row for the tested Session; the Checkpoint DB remains present at 20,480 bytes. Both 8000 and 5173 are unbound after Stop, and the process manifest is removed.
- `launcher-lifecycle-01.log`: the Vite launcher independently stayed ready with empty stdin and closed from `shutdown.request` on a free local test port.

One early restart probe ended in a 35-second browser timeout because it called the stream open as soon as response headers arrived, without waiting for an SSE frame. That attempt is retained in `browser-session-restart-01.stderr.log`; the probe now requires the first `SESSION_CREATED` frame before declaring the stream open, and the corrected immediate-stop rerun passed.

One two-second API readiness poll timed out while the Worker was starting during a restart. The bounded readiness loop retried and reported API and Worker ready; the same-window startup completed. No lockfile or dependency version changed.

## Regression checks

- `sse-regression-final.log`: `D:\学习\agent新项目\.venv\Scripts\python.exe -m pytest tests/test_r1_user_demo_hf02_sse.py -q --basetemp docs/evidence/vnext/user-demo-windows-lifecycle-01/runs/pytest-sse-final` — 2 passed.
- `frontend-build-final.log`: `npm run build` — passed.
- `static-validation-final.log`: PowerShell parsing, Node syntax checks, and `git diff --check` — passed.

No migration, real Provider call, Runtime Grant change, business action, or non-isolated Demo database change was made.
