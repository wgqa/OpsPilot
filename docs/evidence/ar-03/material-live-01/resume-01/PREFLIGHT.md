# Resume 01 zero-cost preflight

Status: `PREFLIGHT_READY_AWAITING_PAID_AUTHORIZATION`

## Identity check

- Preflight implementation HEAD: `9cca2504005aeb7bd4e7ad7ad69fb0f3ddfdd26c`.
- Branch: `codex/ar03-material-live-01-exec-prep`.
- Accepted base: `ff956ea71b90448d40229c57b8f8619c997b5cbd`.
- Frozen Cases blob: `faf16fbb857278e98f8afbe179fe327855132967`.
- Freeze commit: `434a8b027f0072036b46bc624d1defab8703b775`.
- Remote `main` observed by the preflight: `ec8c3582f6d145eec9979c43607302731411ead8`.
- Old claim SHA-256 was verified as `db65416c9e361a064fe2bf29b0864793343e81d0d38edb637b89b4b8069d1e3a`; the old claim remains consumed and is not reused.

## Frozen request and caps

The accepted runner preflight verified `deepseek-flash`, `thinking=disabled`, `max_tokens=2048`, `tool_choice=auto` when tools are present, `parallel_tool_calls=false`, `stream=false`, 30-second timeout, zero SDK/HTTP retries, and single-flight Provider execution. It verified the existing `DEEPSEEK_FLASH_PEAK_2026-11-01` reservation contract: 16 Provider calls, 10 MCP `tools/call` attempts, USD 10.50 application cap, USD 0.645600 reserved per Provider request, 12,000 context input tokens, and a 60-minute stop. Maximum reservations are USD 10.329600. No cap or price constant was increased.

The existing frozen price version was checked for internal consistency with the campaign ledger, not refreshed against live pricing in this offline-preparation task. A future paid authorization must recheck official price and the serialized request before dispatch.

## Preparation outcome

- New identity: `AR-03-MATERIAL-LIVE-01-RESUME-01`.
- Prepared claim: `WAITING_FOR_EXPLICIT_PAID_AUTHORIZATION`; `paid_dispatch_authorized=false`; `one_shot_consumed=false`.
- Dedicated future runtime paths are `domain.sqlite3` and `checkpoints.sqlite3` under `.runtime/ar03-material-live-01-resume-01/`; neither path exists yet. The offline formal preview used separate disposable Domain and Checkpoint files and did not create these campaign paths.
- Local credential presence was detected but its value was neither printed nor copied. Provider opt-in was false.
- Formal preflight result on implementation HEAD `9cca2504005aeb7bd4e7ad7ad69fb0f3ddfdd26c`: exit 0, `PREFLIGHT_READY_AWAITING_PAID_AUTHORIZATION`; provider HTTP=0, MCP campaign calls=0.
- The new Runner's `--execute-once` is deliberately blocked before claim or runtime creation until a separate authorization task changes this state.

The raw machine output and full command log stay in the local private evidence directory. This public summary excludes the shared environment-file location, API-key value, absolute local paths, and raw DB contents.
