# AR-03-MATERIAL-LIVE-01 — Recovery 01 public summary

**Release status:** `ACCEPTANCE_CANDIDATE` — free offline recovery evidence only
**Release base:** `codex/ar03-material-01-public@69a1a1171b97849a6b5a77a7b8f8d03f263c95aa`
**Frozen recovery plan:** commit `5a16647e62abaafe8e4eb05bcbaca67f9b5f889b`
**Implementation:** commit `243f7d9f1eb6e97d6484e456c51c45b54a6dc53f`
**Sidecar refusal coverage:** commit `0369ecfd78bcd054744fa4da59e351c84ce8b85b`

## Result

The campaign runner previously initialized the SQLite schema but did not seed the trusted demo principals required by its isolated fixture. It now reuses the existing `reset_fixture(..., "S1_POS")` only for a demonstrably fresh campaign database. Existing database, `-wal`, or `-shm` artifacts are rejected before any reset can occur.

A fresh offline validation completed with **4 passed in 3.59s** after the publication-safety edits. It exercised the formal API/Worker/Assistant/MCP/Domain path with a deterministic fixture model. It verified trusted demo setup, authorized order binding, same-event `HTTP 202 / ACKNOWLEDGED` delivery and `QUEUED` receiver observations, current source validation, and zero business writes. The three refusal tests cover a pre-existing database and each SQLite sidecar.

This is a fixture-driven wiring and safety result. It is **not** evidence of real-model autonomy or a live customer outcome.

## Resource and side-effect accounting

- Real Provider HTTP requests: **0**; provider opt-in remained disabled.
- New paid one-shot execution claim: **not created or consumed**.
- MCP read calls in the preview: **2**; no business write tools were exposed.
- Business write records: **0**.
- Browser validation: **not run**.
- The fixture model's three internal dispatch reservations are test accounting only; they are not Provider requests, vendor Usage, or a real cost.
- The consumed claim, campaign ledger, results, trace, and Domain database included in the before/after digest check remained byte-identical. No new paid claim was created.

## Provider and budget preflight

No completion request was sent. The current [DeepSeek Chat Completions contract](https://api-docs.deepseek.com/api/create-chat-completion/) documents `deepseek-flash`, non-thinking mode, `max_tokens`, tool calling, and `tool_choice=auto`. The current [Models & Pricing page](https://api-docs.deepseek.com/quick_start/pricing/) lists DeepSeek-V4.1-Flash-1017 behind `deepseek-flash`, with peak cache-miss input at $0.30 / 1M tokens and output at $1.20 / 1M tokens (checked 2026-11-03).

At the frozen 12,000-input / 2,048-output caps, that listed peak rate gives an arithmetic request estimate of about **$0.006058** before any other billing adjustments. The frozen application reserve remains **$0.645600 per request**; 16 such reservations total **$10.329600**, below the unchanged $10.50 campaign ceiling. This is a preflight calculation, not a vendor invoice or a live request-body validation. Recheck prices and actual serialized payload before any separately authorized live campaign.

## Earlier attempts and retained evidence

The private evidence store retains all eight original preview logs and exit codes. The first three attempts exposed, respectively, an interpreter dependency mismatch and two incorrect test assumptions. Previews 04–07 passed the then-current two-test set while the test and capture were being completed. Preview 08 passed the final four-test set. A further sanitized-output run on this release tree passed all four tests in 3.59s. No prior failure record was overwritten.

Public test command (portable form):

```text
python -m pytest -q -s tests/test_ar03_material_live_recovery_01.py --basetemp <fresh-local-directory>
```

The detailed request/observation trace, database, raw stdout, failure logs, and their hashes remain in private local evidence storage. They are not included in this public release.

## Live execution status

The free preview is complete. A new real-model campaign has **not** started. It requires independent review and a new one-shot claim/authorization; this release does not enable, create, or spend one. No real Provider request, browser run, main-branch change, or business write was performed.
