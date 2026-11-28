# Diff review

## Changed files

- `opspilot/assistant.py`
  - Adds a user-facing program notice for `SUMMARY_SOURCE_EXCEEDS_COMPRESSION_BUDGET`.
  - Catches only `ContextBudgetExceeded` around the first `probe.context()` preflight, passes its stable code to the existing terminal failure closeout, and records required/input budget tokens plus the preflight phase in the trace.
  - Ordinary runtime errors keep the existing generic Worker classification.
- `tests/test_r2_ar04_compaction_c06_hf_01.py`
  - Adds offline T01–T06 and T08 coverage. It imports the frozen audit fixture/generator, verifies the exact original C06 message digest, checks the API notice and idempotent closeout, and observes actual local Domain state.
  - Existing tests provide T07 coverage.
- `docs/evidence/r2-ar04-compaction-c06-hf01/`
  - Adds this report, machine-readable results, actual test output, repair-before RED reproduction and RED test output. Earlier iteration logs remain in place for audit history.

## Invariants checked

- No compression budget, output reserve, recent-window size or strategy trigger was changed.
- No long User message is truncated, deleted, summarized, or rewritten by the patch. C06's first User body and digest match the frozen source.
- The budget error ends before a model dispatch, compression attempt, answer receipt, or delivery attempt.
- The notice uses the existing idempotent Domain closeout and is returned by the normal Run/messages API as `PROGRAM_LIMIT`.
- No authorization, TaskBinding, approval, intent, ledger or business-action rules changed.
- Frozen audit Trace and `RESULTS.json` were not edited. Repair-before RED and prior run logs are preserved as separate files.

## Evidence limits and remaining issue

T01–T08 evidence is offline and deterministic. Fixture MODEL counts are not real Provider calls; no external MCP or external business write was exercised. T08 uses an injected `RuntimeError`. The fix classifies and explains the failure; it does not make an individually oversized User message safely compressible. Full repository tests were not run.

Captured pytest display padding and Markdown hard-break spaces were trimmed at line ends for diff cleanliness; assertion text, ordering, and test outcomes are unchanged.
