# E11-D contract audit

- Base: `c960becd81c277e6fae9b2f1c4b8a5691ebcbb62`; branch: `codex/r2-ar06-e11-d-readiness-01`.
- Frozen prompt SHA256: `721177e0c907421ab13927c9ac10bb23ba5b568c365d4ff58ef33ad2887a39be`; loaded directly from frozen CASES.json and asserted in the test.
- Frozen CASES, RUBRIC, EVAL_PROTOCOL, and FROZEN_HASHES were not modified. Source Git Blob IDs are listed in `E11_EVIDENCE_INDEX.json`.
- Required business distinction: HTTP 403 is a symptom; DIAGNOSED requires current matching Probe/Authz; HANDOFF_READY is only a draft; SCOPE_ESCALATED means locally accepted pending review; this test cannot produce SCOPE_AUTHORIZED or RECOVERED.
- Historical ordinary Assistant Run failure is preserved in `E11_BASELINE_FAILURE_TRACE.json`; the new exact-prompt RED is in `E11_RED_RESULT.json`. Its fixture lacked `bind_tools`, causing a persisted FAILED CHAT_READONLY Run.
- The checkout E10 live report is an executor candidate, while the readiness report retains a PARTIAL ceiling; no independently signed verdict was found in the inspected evidence. Therefore the task card's stated independent E10 PARTIAL verdict provenance is `UNVERIFIED`; no E10 runtime/data was used.
- The legacy Provider gate is in `opspilot/config.py:17`; Worker paths call it at `opspilot/web/worker.py:147` and `:337`, and Investigator calls it at `opspilot/investigator.py:2450`. These paths instantiate ChatOpenAI without a demonstrated durable Runtime Grant/Spend integration for this use.
- This is offline Fixture/Domain evidence, not a real-model semantic result.
