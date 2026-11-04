# Free preflight record

## Status

`OFFLINE_CORE_PASSED`; the final clean-HEAD live preflight is intentionally run after the source commit is pushed. No paid claim has been consumed by the checks in this file.

## Formal API / Worker / MCP / Domain path

An isolated temporary Domain database was bootstrapped using the existing trusted demo bootstrap. The test prepared the frozen `ar03-order` fixture, changed only that fixture's target Event Receiver to `PROCESSED`, then created a trusted order binding through the existing API and ran `ASSISTANT_V1` through the formal Worker.

The deterministic model was connected to an explicit HTTPX `MockTransport`; the production ChatOpenAI serializer and persistent dispatch ledger were exercised. The mock made three sequential model responses: select `get_callback_delivery`, observe the result, select `get_receiver_processing`, then answer. The two successful MCP results were linked to the same Event and current Task/Run; Delivery was `HTTP 202 / ACKNOWLEDGED`, Receiver was `PROCESSED`, and the source audit was current.

The process sent 3 synthetic HTTP requests to MockTransport and 0 external Provider requests, performed 2 MCP dispatches with no count ceiling, and persisted a synthetic user-facing answer explicitly classified `DETERMINISTIC_MOCKTRANSPORT_NOT_REAL_PROVIDER`. All protected approval, plan, action, diagnosis, and handoff write-table counts were zero. The test did not create the paid runtime or consume a one-shot claim.

Private full output: `.runtime/ar03-material-remainder-live-01/raw/offline-preflight.json` (SHA-256 recorded in the private execution manifest). The output includes local fixture IDs and is intentionally not copied into the public repository.

## Automated checks

Python compilation succeeded for the changed implementation, runner, and test modules.

The final scoped regression command was:

```powershell
python -m pytest -q `
  tests/test_ar03_material_remainder_live_01.py `
  tests/test_ar03_material_remainder_01.py `
  tests/test_ar03_material_live_resume_02.py `
  tests/test_ar03_material_runner_recovery_02.py `
  tests/test_ar03_material_post_live_closeout.py `
  tests/test_ar02_assistant.py `
  --basetemp <private unique directory>
```

Result: **44 passed**. The exact process log and exit code are in the private runtime store. The earlier run's 3 test-fixture environment-leak failures and the corrected successful rerun are retained there; see `FAILURES.md`.

The historical setup RED remains unchanged: 2 failed, 1 passed, exit code 1. Its original local log was copied byte-for-byte to the private runtime store; the repository's existing ignore rule keeps raw `.log` files out of public commits.

## Provider price and request contract

On 2026-11-04 the official DeepSeek pricing page still showed `deepseek-flash` peak cache-miss input at USD 0.30 / 1M tokens and output at USD 1.20 / 1M tokens. Its model table showed 1M context and 384K maximum output. At the frozen request cap of 12,000 input and 2,048 output tokens, this pricing envelope is below the frozen USD 0.645600 reservation. Sixteen full reservations total USD 10.329600, below the USD 10.50 application limit. The local budget remains an application-side estimate, not a guarantee of the Provider invoice.

The offline wire test confirmed the actual serialized `deepseek-flash` request has `thinking.type=disabled`, `max_tokens=2048`, `stream=false`, `tool_choice=auto` and `parallel_tool_calls=false` when tools are supplied, and no `max_completion_tokens` alias. Zero automatic retries remain configured.

## Remaining gate

After the source commit is pushed, run the Runner's complete `--preflight-only` command from a clean checkout. It must confirm the frozen rule and Gold blobs, branch, remote `main`, model identity, current budget/price constants, 12,000-token context budget, and absence of the final runtime/claim before `AR-03-MATERIAL-REMAINDER-01` may consume its single paid claim.
