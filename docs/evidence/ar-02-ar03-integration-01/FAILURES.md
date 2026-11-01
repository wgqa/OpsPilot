# Failures and Corrections

This file preserves the implementation attempts in chronological order. No frozen Gold, previous reports, or historical AR-02/AR-03 evidence was edited.

| Log | Observation | Classification | Resolution / final meaning |
|---|---|---|---|
| `RED-01-protocol-primitives.log` | pytest could not create the requested temporary base because its parent directory did not exist. | Test preparation failure; not product evidence. | Created the test-owned temp parent and reran. Preserved this log. |
| `RED-02-protocol-primitives.log` | Three tests failed because the AR-02 branch had no protocol comparison implementation and no source revalidation. | Valid RED for the frozen gap. | Added the comparison engine, scoped MCP bridge, and current-source checks. |
| `GREEN-01-domain-primitives.log` | Two assertions incorrectly assumed the fixture version string had a particular suffix; one test passed. | Test design error. | Asserted semantic versions from the trusted catalog instead. No production behavior was changed to satisfy the assumption. |
| `GREEN-02-domain-primitives.log` | Three focused domain tests passed. | GREEN. | Confirmed discovery/comparison source checks and bounded history primitive. |
| `GREEN-03-integration-e2e.log` | Collection used the system Python, which did not have the repository's `langchain_core` dependency. | Environment/interpreter selection error. | Used the repository's existing `.venv`; no dependency installation or network access. |
| `GREEN-04-integration-e2e.log` | Two bound journey cases exhausted the existing auxiliary Provider-call budget during fixture setup. The budget guard refused further work. | Test setup interacted with a real product budget; safe refusal, not a reason to raise limits. | Adjusted fixture setup to avoid spending a model call before the journey under test. Frozen budget code and limits were unchanged. |
| `GREEN-05-integration-e2e.log` | Two assertions read SQLite rows by an unstable positional index. | Test assertion bug. | Queried rows by named fields/meaning and reran. |
| `GREEN-06-integration-e2e.log` | Six end-to-end integration tests passed. | GREEN. | Formal API/Worker/Assistant/local MCP path passed for the first six cases. |
| `GREEN-07-integration-e2e-trace.log` | Six tests passed while appending real persisted test observations to `TRACE.jsonl`. | GREEN with evidence capture. | Retained the trace; later added the unauthorized MCP case. |
| `GREEN-08-protocol-and-integration-regression.log` | 49 AR-03 protocol tests plus the initial integration set passed. | GREEN. | Selective comparison/scoped-protocol regression. |
| `GREEN-09-ar02-regression.log` | 84 relevant AR-02 regression tests passed. | GREEN. | AR-02 Knowledge, TaskBinding, MCP, source revalidation, continuity and security regressions. |
| `GREEN-10-integration-positive-negative.log` | Seven integration tests passed. | GREEN. | Positive and negative integration set. |
| `GREEN-11-unauthorized-mcp-trace.log` | The explicit unauthorized comparison tool call was refused; one test passed. | GREEN. | Added the denial to the persisted trace; denial is not represented as a protocol fact. |
| `GREEN-12-final-protocol-integration-regression.log` | 50 protocol and integration tests passed. | Final targeted GREEN. | Final AR-03 comparison/scoping plus all seven integration tests. |
| `GREEN-13-final-protocol-integration-command.log` | Re-ran the final protocol/scoped-source/integration command with its command and exit code captured; 50 tests passed. | Final fresh GREEN. | Command: `D:\学习\agent新项目\.venv\Scripts\python.exe -m pytest tests/test_ar03_protocol_comparison.py tests/test_ar03_02_scoped_protocol_comparison.py tests/test_ar02_ar03_integration_01.py -q --basetemp=.pytest-temp/ar02-ar03-final-confirm`. |
| `STATIC-diff-check-first-attempt.log` | The first staged check found Markdown hard-break trailing spaces and extra blank lines at three copied test-file EOFs. After those were fixed, including verbatim pytest logs exposed whitespace emitted by pytest's failure renderer. | Packaging hygiene issue plus raw-log formatting. | Fixed only Markdown/test-file formatting. Kept raw pytest logs byte-for-byte; the final check excludes only those immutable `runs/*.log` files and checks every source, test, trace, and report file. |
| `STATIC-final-source-and-trace-failure.log` | The initial secret scan matched its own log label (`Bearer credential`) rather than any request or trace value. | Scanner self-match; no credential content was found. | Preserved the false-positive output, changed the scan description to avoid matching its own pattern name, and reran against the trace and all logs. |

`STATIC-compileall.log`, `STATIC-diff-check-final.log`, and `STATIC-final-source-and-trace.log` all have exit code 0. The final diff check excludes only verbatim pytest `runs/*.log` files because their renderer emits trailing spaces; all source, test, trace, and report files pass. The source/trace check parses the 74-row JSONL and `RESULTS.json`, compiles the eight changed Python modules without generating bytecode, and found zero bearer credentials/API key assignments/provider host markers. The complete repository pytest suite was not run; this task's relevant suites are listed in `RESULTS.json`.

`PUSH-01.log` records the remote connectivity blocker. The source/evidence commit exists locally, but no successful push or remote branch SHA was verified. The scanner false positive is retained separately and does not indicate a credential in request or trace content.

No real Provider request, browser session, business write, main-branch update, or historical budget/ledger mutation occurred.
