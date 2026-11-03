# AR-03-MATERIAL-LIVE-01 — Recovery 01 public summary

**Release status:** `ACCEPTANCE_CANDIDATE` — free offline recovery evidence only
**Release base:** `codex/ar03-material-01-public@69a1a1171b97849a6b5a77a7b8f8d03f263c95aa`
**Frozen recovery plan:** commit `7f5fc65b27e03cba8bd95c8b8f38096c333db12f`
**Implementation:** commit `84c8656a8de67ec85ef74be6353d64cc5f4bc9ee`
**Sidecar refusal coverage:** commit `e9a87384a0eec01e000043fa75e2ab877acf6119`

## Start-of-work verification

- Remote recovery base: `69a1a1171b97849a6b5a77a7b8f8d03f263c95aa`; remote `main`: `ec8c3582f6d145eec9979c43607302731411ead8`.
- Local recovery candidate observed at start: `36ac4fee8643a036097c4b79b4110b3c68a6b231`; it was not remotely verified or pushed.
- `PROJECT_NORTH_STAR.md` blob: `1f737712c7a36ceb34433ac09c3fbba3c3305542`.
- `AGENTS.md` blob: `32c45506cceeaa8c76a5c56bf8360ff476b58856`.
- Project review Skill blob: `d405c8d413d633824b279202cc1503dab4cf0b03`.
- Frozen `CASES.json` blob: `faf16fbb857278e98f8afbe179fe327855132967`. Gold is embedded in `CASES.json` and the acceptance plan; there is no separate `GOLD.md` for this slice.

The original local candidate was left intact. The public branch was rebuilt from the verified remote base and contains only selected safe changes plus the redacted summary/manifest.

## Result

The campaign runner previously initialized the SQLite schema but did not seed the trusted demo principals required by its isolated fixture. It now reuses the existing `reset_fixture(..., "S1_POS")` only for a demonstrably fresh campaign database. Existing database, `-wal`, or `-shm` artifacts are rejected before any reset can occur.

A fresh offline validation completed with **4 passed in 3.58s** after the publication-safety and seed-assertion edits. It exercised the formal API/Worker/Assistant/MCP/Domain path with a deterministic fixture model. It verified tenant, active SUPPORT principal, current credential reference, bound S3 order, same-event `HTTP 202 / ACKNOWLEDGED` delivery and `QUEUED` receiver observations, current source validation, and zero business writes. The three refusal tests cover a pre-existing database and each SQLite sidecar.

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

The frozen configuration remains `max_tokens=2048`, `thinking=disabled`, `tool_choice=auto` when tools are supplied, `parallel_tool_calls=false`, `stream=false`, 30-second timeout, and zero retries. The campaign cap is 16 Provider requests / 10 MCP calls, with a $10.50 application ceiling, $0.645600 per-request reservation, and 12,000 input-token limit. The offline test confirms that the isolated campaign and Task budgets initialize to 16/10; it does not send or validate a real Provider payload.

At the frozen 12,000-input / 2,048-output caps, that listed peak rate gives an arithmetic request estimate of about **$0.006058** before any other billing adjustments. The frozen application reserve remains **$0.645600 per request**; 16 such reservations total **$10.329600**, below the unchanged $10.50 campaign ceiling. This is a preflight calculation, not a vendor invoice or a live request-body validation. Recheck prices and actual serialized payload before any separately authorized live campaign.

## Earlier attempts and retained evidence

The private evidence store retains all eight original preview logs and exit codes. The first three attempts exposed, respectively, an interpreter dependency mismatch and two incorrect test assumptions. Previews 04–07 passed the then-current two-test set while the test and capture were being completed; preview 08 passed the original final four-test set. During publication hardening, a supplemental assertion initially queried the S1 `orders` table instead of S3's `s3_orders`; that test-only failure was retained, the assertion was corrected, and the final sanitized release-tree run passed all four tests in 3.58s. No prior failure record was overwritten.

Public test command (portable form):

```text
python -m pytest -q -s tests/test_ar03_material_live_recovery_01.py --basetemp <fresh-local-directory>
```

The detailed artifacts generated by this recovery run (request/observation trace, isolated database, raw stdout, failure logs, and their hashes) remain in private local evidence storage and are not added in this branch delta. Earlier material-live-01 files already present on the public base are unchanged.

## Live execution status

The free preview is complete. A new real-model campaign has **not** started. It requires independent review and a new one-shot claim/authorization; this release does not enable, create, or spend one. No real Provider request, browser run, main-branch change, or business write was performed.
