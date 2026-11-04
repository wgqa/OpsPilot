# Campaign failures and limits

## Runtime result

- Campaign stop reason: none. Three authorized conditions executed; all 8 Provider requests returned HTTP 200 with known Usage, and all 12 MCP calls returned OK.
- No provider retry, UNKNOWN dispatch, budget violation, authorization anomaly, or protected business write was observed.
- Campaign runner exit code: `0`.

## Product result limits

- `MAT-06-SKILL-ON` loaded the real Skill, but the model stopped after document listing and Skill loading. It did not call protocol comparison or excerpt tools in that run. Its method-level explanation is not evidence that it completed the same substantive comparison as OFF.
- Only one fixed-order OFF→ON pair ran. The observed tool-choice difference cannot establish that Skill availability caused a quality difference.
- Mutated Skill source was not injected into the paid campaign. Its rejection was verified by the separate offline integrity test (`1 passed`), not by live execution.
- Full pytest, real browser experience, and additional Skill-effect samples were not run.

## Preserved prior failures

- The original preparation RED (2 failed, 1 passed, exit code 1) is preserved byte-for-byte in the private evidence store and hash-listed in `PRIVATE_EVIDENCE_SHA256.json`; it was a missing live-entry/claim setup test before implementation, not a live-business failure.
- The earlier free-test fixture failures and corrected 44-pass run remain in private evidence storage and are summarized in the parent `FAILURES.md`. They have not been deleted or relabeled.
- Historical RESUME-01/02 UNKNOWN states and their reservations were not reused or modified by this campaign.
