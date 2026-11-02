# Live execution process record

- Command: `D:\学习\agent新项目\.venv\Scripts\python.exe docs/evidence/ar-03/real-llm-02/run_live.py --execute-once`
- Started under the authorized elevated network path after offline preflight; no provider ping or separate probe was run.
- Persisted one-shot claim: `CLAIMED_NO_RETRY`, experiment `AR-03-REAL-LLM-02`, claim time `2026-11-02T14:07:15.554983+00:00`, execution HEAD `91205b0049fdaa68d369fa123c2361cb890db97f`.
- The shell session disappeared before its terminal exit code and full stdout could be retrieved. The exit code is therefore `UNRECOVERABLE`, not inferred.
- Persisted artifacts agree: two scenarios completed processing; 5 Provider HTTP 200 responses with known Usage; 11 actual MCP dispatches; no in-flight or unknown Provider result; no business writes; overall result `PARTIAL` because the B run ended at `ASSISTANT_RUN_MCP_LIMIT`.
- No rerun was attempted. `EXECUTION_CLAIM.json` remains a one-shot no-retry claim.
