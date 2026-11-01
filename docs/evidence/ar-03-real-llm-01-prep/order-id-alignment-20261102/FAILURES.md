# Failure and correction record

All records below are from this order-ID alignment run. Historical prep logs and traces were not edited.

1. **System interpreter collection failure — exit 2.** `python -m pytest ...` resolved to `D:\python\python.exe`, which did not have `langchain_core`; pytest stopped at module collection and ran no cases. Raw output: `runs/queued-processed-pair.log`. Switched to the existing repo environment at `D:\学习\agent新项目\.venv\Scripts\python.exe`; no dependency was installed or changed.
2. **First virtualenv invocation setup failure — exit 1, 2 setup errors.** The requested `--basetemp` child directory did not exist under the D-drive `.tmp` parent. Pytest never reached either test body. Raw output: `runs/queued-processed-pair-venv.log`. Created a new uniquely named D-drive basetemp and reran.
3. **Initial aligned pair — 2 passed.** The fixture and trusted API binding were switched to `ar03-order`; the original business pair passed. Raw output and trace: `runs/queued-processed-pair-venv-run3.log`, `TRACE.jsonl`.
4. **Stricter authorization and no-write assertion pass exposed a test expectation mismatch — 2 failed.** The new test expected principal status `ACTIVE`, while the current trusted Domain row correctly reported `ENABLED`. This was a test assertion error, not an authorization defect. Raw failure: `runs/queued-processed-pair-verified.log`. The assertion was corrected to the persisted enum value `ENABLED`; no production authorization logic changed.
5. **Final focused rerun — 2 passed, 5 deselected, exit 0.** Raw output: `runs/queued-processed-pair-accepted.log`. The final trace files are `TRACE-accepted.jsonl` and `DOMAIN-CHECKS-accepted.jsonl`.

No real Provider call, browser action, or Agent business write occurred in any attempt.
