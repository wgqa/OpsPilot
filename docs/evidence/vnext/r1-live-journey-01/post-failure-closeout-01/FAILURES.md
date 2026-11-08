# Failures and limits

## Original live failure

The original private database confirms four failed Runs, four `assistant_calls=UNKNOWN`, and four Runtime spends=`RESPONSE_STORED` with Completion IDs and valid Usage. Historical protocol/receiver MCP count is zero. The assistant-call result contains `runtime_dispatch_state=RESPONSE_STORED`, but the original exception type and cause chain were not persisted. Therefore:

- **Confirmed:** Assistant status handling incorrectly treated a saved response with known Usage as UNKNOWN. That produced the wrong user-facing fee uncertainty message.
- **Not confirmed:** Why the original ChatOpenAI/Agent execution did not return the four captured `tool_calls` to ToolNode. The capture omitted `Content-Encoding`; it also did not save the original exception cause chain. No root cause is inferred from HTTP 200 alone.
- **New evidence:** Two exact captured responses (single-tool J1-01 and three-tool J2-01) now pass the current formal local path under MockTransport, with the proposed MCP calls executed and response messages included in the next model input. This establishes that these captured tool payloads are accepted by the current path; it does not prove the historical failure has one specific cause.

## Closeout test attempts

1. An initial invocation placed the pytest log inside the `--basetemp` directory. Pytest's temporary-directory cleanup then raised Windows `PermissionError`; this was a test invocation error, not a product failure.
2. The next run correctly isolated the log but exposed one overly strict assertion requiring the literal `系统不会自动重试`; the actual Usage-violation notice says `且不会自动重试`. The assertion was narrowed to the actual shared semantic phrase `不会自动重试`.
3. Final targeted run: 9/9 passed. Runtime Grant plus R1 J1/J2 regression: 44/44 passed.

The original R1 live `PARTIAL` result and private logs remain unchanged. There were no new Provider requests, no external business writes, and no browser runs in this closeout. Full repository pytest was not run.
