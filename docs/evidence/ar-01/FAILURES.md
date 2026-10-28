# AR-01 development attempts and limits

All attempts are retained under runs/. No historic evidence or CASES.json was rewritten.

| Attempt | Actual result | Cause / treatment |
|---|---|---|
| local-01 | exit 1 | Candidate stored Run ID as self.run, shadowing its run() method. Renamed to run_id. Not a valid comparison. |
| local-02 | exit 1 | Strict schema byte equality detected BaseTool title metadata stripping. schema-diff-01.json preserves actual difference. Constraints checked separately; original raw A specs now exposed at actual B model boundary. No permission/schema constraint relaxation. |
| local-03 | exit 1 | tools() method conflicted with AgentMiddleware.tools list attribute. Renamed make_tools(). Not a valid comparison. |
| local-04 | exit 0 pipeline, NOT rubric PASS | All pairs ran, but AR01-03 failed variant stopped PARTIAL/TypeError in both groups: the deterministic model helper parameter name conflicted with the Skill's name argument. The early runner only checked parity/immutability, so its LOCAL_IMPLEMENTATION_READY label is insufficient and is retained as a reporting failure. Fixed helper and added offline assertions for the unchanged frozen expectations. |
| local-05 | exit 0, 9 pairs met frozen local assertions | Actual MCP/HTTP, deterministic model. Valid local mechanics, not intelligence. |
| local-06 | exit 0, 9 pairs met frozen local assertions | Rechecked after Context Provenance lifecycle completion changes. |
| local-07 | 9 pairs met local assertions; Trace-quality failure | Explicit normal/fallback stop reasons were present, but final audit found the shared string redaction pattern matched sk- inside task-UUID. Earlier Trace task_id values were obscured. Do not treat these as complete identity-correlation evidence. |
| local-08 | final execution; see RESULTS.json | Experimental redactor now distinguishes opaque task IDs from standalone secret prefixes; original redacted records remain. |
| pytest-01 | 15 passed | Initial test set, retained. |
| pytest-02/03/04 | 19 passed each | Added revoked/reauthorized source and history isolation paths; later export includes actual unit Trace/ledger rows. |
| pytest-05 | 20 passed | Added repeated-asset audit semantics: call counts but no fabricated new semantic progress. |
| pytest-06 | 20 passed | Before the new task-ID preservation redaction assertion. |
| pytest-07 | final execution; see RESULTS.json | Includes opaque identity preservation and standalone secret redaction. |
| safety-01 | 72 passed | S1 business/D3, S2 facts/diagnosis, S3 HF01/HF02 and TTL integrity. Not full pytest. |

Expected MCP denials appear in logs for cross-order Event and forged resource
arguments. They are successful safety tests, not hidden tool successes.

All pre-local-08 Trace files retain the original over-redaction. Loop/permission
observations are still historical facts, but final correlation proof uses local-08
and unit-traces-07. No old Trace was repaired in place. The Git raw artifacts keep
their original CRLF/LF bytes; whitespace checks exclude raw runs, while content
hashes are checked against the exact staged Git blobs.

Known limits: no real Provider, Usage/cost effect, browser, full pytest, production
Worker recovery, or cross-Run goal management. Native-history restoration is
same-instance only. A production report path is intentionally outside the policy
comparison. No architecture superiority or formal Stage B PASS follows from
these results. Real-model authorization and finite cost preflight remain pending.
