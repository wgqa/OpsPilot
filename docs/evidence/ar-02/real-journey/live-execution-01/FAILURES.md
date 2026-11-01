# Failures and stop record

All entries are retained. Attempts 01 and 02 failed before Provider I/O; attempt 03 is the one and only live Provider dispatch. No prompt was resent.

| Attempt | Stage | Result | Classification | Evidence |
|---|---|---|---|---|
| 01 | Python runner import | `ModuleNotFoundError: No module named 'opspilot'` | Runner setup failure; no user message or Provider call | `runs/live.log`, `RESULTS.json` |
| 02 | Local fixture seeding | `sqlite3.IntegrityError: FOREIGN KEY constraint failed` because the fresh DB had not first been seeded with tenant rows | Fixture preparation failure; no user message or Provider call | `attempt-02/runs/live.log`, `attempt-02/RESULTS.json` |
| 03 | First S01 model dispatch | `OpenAIConnectionError: Connection error.` No HTTP response event or Usage was received | Live outcome UNKNOWN; hard stop | `attempt-03/PROVIDER_HTTP.jsonl`, `attempt-03/TRACE.jsonl`, `attempt-03/RESULTS.json`, `attempt-03/runs/live.log` |

## Attempt 03 details

- Exactly one user message was accepted: S01. Run `run-b5f22395-0792-47d1-857d-32525b5667e3` ended `FAILED`.
- The program persisted a `PROGRAM_LIMIT` connection-failure notice. This is not a DeepSeek answer and is not counted as task completion.
- One durable Provider dispatch was reserved: `ar02-live-dispatch-a8efc5d8-a9d3-4402-93f1-317beedac996`; status `UNKNOWN`, Usage `UNKNOWN`, retained reserve USD 0.645600.
- MCP calls: 0. No model tool decision or observation exists.
- The HTTP request path was `/v1/chat/completions`, whereas the previously successful CONN-02 request used `/chat/completions`. The body offered one Knowledge tool but omitted `tool_choice=auto`. These deviations were discovered from the actual wire capture and were not corrected because the task prohibits any second request after an unknown outcome.
- No HTTP response means no reliable HTTP status, Completion ID, fingerprint, Usage, or billed amount. Do not infer DNS, TCP, TLS, proxy, or server-side cause from the generic exception.
- The ledger closed to `BUDGET_BREACH`; it retained the full reservation. No later turn was submitted.

## Stop decision

Stop the whole experiment at S01. S02-1 through S02-5 remain `NOT_RUN`. No retry, alternate endpoint, alternate network, model switch, or new experiment identity was used.
