# AR-04C-PRELIVE-HF-01 — Free pre-live gate evidence

**Status:** `ACCEPTANCE_CANDIDATE`
**Base:** `codex/ar04c-real-journey-01@d99843b501df10a4411b44f43d900f7b997e8ab2`
**Scope:** Offline authorization/claim verification and a test-only shutdown lifecycle correction.

## Frozen scope

- Preserve AR-04C `PLAN.md`, `GOLD.md`, `CASES.json`, `BUDGET.md`, and `PAID_EXECUTION_CONTRACT.md` unchanged.
- Do not create or consume a real paid authorization, one-shot claim, or token.
- Use only temporary authorization/claim files, isolated SQLite files, and explicit HTTPX `MockTransport` in tests.
- Keep production Worker shutdown behavior unchanged; fix the AR-04C test harness ordering only.
- Do not run DeepSeek, browser automation, external business writes, merge `main`, or start LIVE.

## Checks

1. Bind an authorization to the exact branch, execution HEAD, frozen contract digest, model parameters, and budget.
2. Verify atomic claim creation, one-process capability, fresh-process replay rejection, and persistent stop on unknown dispatch.
3. Exercise the official FastAPI/Worker/ASSISTANT_V1 path with MockTransport and verify persisted claim consumption and campaign DB identity pinning before transport.
4. Reproduce the observed `TestClient.wait_shutdown` stall, then wait for the final Worker dispatch and empty queue before closing the test client.

Full pytest and real Provider behavior are outside this task. No real DeepSeek or business write is authorized here.
