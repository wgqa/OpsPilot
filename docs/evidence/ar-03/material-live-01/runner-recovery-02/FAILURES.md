# Failure record — Runner Recovery 02

All original logs remain in the private evidence store; SHA-256 values are listed in `RESULTS.json`. No earlier failure log was overwritten.

| Stage | Result | Classification | Resolution |
|---|---|---|---|
| First RED attempt | 3 failed, 1 passed | Test harness setup: loading the base runner without the resume wrapper's experiment identity caused scope mismatch before the target code path. Not treated as product evidence. | Rebuilt the isolated harness with the same bound experiment identity; kept the original log. |
| Valid RED | 3 failed, 1 passed | Product defects reproduced: `PRICE_VERSION` was undefined in `_CampaignState.begin()`; `_audit_case()` raised `KeyError: error_code` on success and failure rows because the column is absent from the actual schema. | Fixed both directly in the existing runner responsibilities. |
| First GREEN | 2 failed, 2 passed | Test expectation mistakes: audit status was in a different result location, and the program fallback is intentionally non-empty on a failed Run. | Corrected assertions to check the real audit contract and explicit program message. |
| GREEN rerun | 1 failed, 3 passed | Exception assertion expected an SDK wrapper name different from the actual `OpenAIConnectionError`. | Updated the assertion to preserve the observed wrapper name. |
| Final focused run | 4 passed | No failures. | Complete. |
| First related regression | 27 passed, 1 failed | Stale test assumption: a prior authorized run had already created the historical runtime DB/checkpoint, so asserting non-existence was incorrect. | Replaced absence assertions with before/after hashes covering DB, checkpoint, WAL, and SHM. The prior artifacts are protected, not deleted. |
| Final related regression | 28 passed | No failures. | Complete. |

No real Provider call was made. The synthetic connection failure is a local MockTransport injection and is not evidence about live network connectivity.
