# R2-AR04-STOP-B-EVIDENCE-SCOPE-HF-02

## Status

`ACCEPTANCE_CANDIDATE` for independent review. The frozen-diff allowlist now includes only the approved Stop B execution-evidence directory in addition to the two original evidence roots and exact Adapter file. Mock and zero-cost Preflight pass on the updated Runner. No effective authorization was created and no Provider request was sent.

## Baseline and change

- Repository: `wgqa/OpsPilot`
- Branch: `codex/r2-ar04-live-admission-hf01`
- HF-02 Base: `d9d432a9de1c434ba8864d988b3047cd982f439b`
- Implementation commit: `cf46d6ffba872257124fc993c21ccd7a33b7435e`
- Original frozen Base: `fa4cd8a7ea6dd36babccbbfc5fcdb7a179729fd3`
- Authorization Task ID: `R2-AR04-REMAINING-LIVE-GATE-01`

The Preflight block was caused by `_task_assert_frozen()` allowing the gate evidence root, the HF-01 review evidence root, and one exact Adapter path, but not the already approved `docs/evidence/r2-ar04-remaining-live-exec-01/` root. The fix adds that exact trailing-slash prefix and leaves all prior conditions in place. `run_v2.py` and its `PROTECTED_DIFF_PATHS` were not changed.

The fixed Mock directory is now `mock_run_07`. Authorization validation, Preflight, Live and per-request validation continue to use the same fixed Mock path and digest. `mock_run_06` remains unchanged and is rejected as a stale path.

## Frozen check and Mock

- Candidate `_task_assert_frozen()` passed in the full regression suite.
- Injecting a changed path under an unrelated `docs/evidence/` directory still raises `TASK_DIFF_OUTSIDE_NEW_EVIDENCE`.
- Simulated production Chat Blob drift and simulated protected-history hash drift still stop in V2 freeze checks.
- `mock_run_07/MOCK_RESULTS.json` SHA-256: `84bdf25e883215cb059ab1f82681ff9a0a1b26a9d0ca1e3dcb52a85b95b3b94b`.
- Runner SHA-256 in the Mock and current Runner: `e31956fb0ec381458f5271d4ccbf580daf36a54c69737ee8fcd59eba65976a1e`.
- The Mock has Q02-B and Q06-B SUCCEEDED, four Mock summaries, two Mock answers, six Mock sends, zero Provider requests, USD 0.00, and zero external MCP calls.
- Q02-B `/callback` is visible with source sequence 3. Q06-B protocol and `max_attempts 3 -> 5` are visible with source sequence 11; the earlier sequence 3 remains `PARTIAL`.
- The Mock was generated from the modified Runner bytes immediately before the implementation commit; its Runner SHA exactly matches the committed Runner. Its `candidate_head_at_run` therefore records the parent HEAD `d9d432a...`. A post-commit regeneration attempt stopped at the existing-output guard (`FileExistsError`, exit 1) before writing; the artifact was left untouched. This does not affect Runner-byte binding.

## Preflight

Default-path and explicit same-path Preflight both returned `READY_FOR_NEW_LIVE_AUTHORIZATION` after the implementation commit. Both bind `docs/evidence/r2-ar04-remaining-live-gate-01/mock_run_07/MOCK_RESULTS.json` and the same Mock SHA. Runtime Grant binding and full Mock checks passed; historical authorization reuse remains blocked. The output records API-key presence only, not its value.

Two earlier exploratory Preflight outputs from the modified working tree before the implementation commit are also retained (`LIVE_PREFLIGHT_HF02_DEFAULT.json` and `LIVE_PREFLIGHT_HF02_EXPLICIT.json`). They passed with the same Runner bytes and Mock digest; the `*_CODE_*` files above are the authoritative post-implementation-commit Preflights.

No task-specific effective authorization directory existed before or after these checks. The existing Preflight reports zero Provider transport invocations, zero Provider requests/cost, zero external MCP calls, zero production database writes and no authorization creation. The only local DB work was isolated Mock/Preflight work.

## Limits

This candidate establishes the offline whitelist repair and Mock readiness only. The official price snapshot must be freshly rechecked and persisted, and the original one-time authorization must be used only after independent acceptance. No real Provider call or semantic score was attempted.

Exact commands and outcomes are in `SCOPE_HF02_TEST_RUN.txt`; machine results and artifact digests are in `SCOPE_HF02_RESULTS.json`.
