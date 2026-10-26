# Stage B failures and retained deviations

All listed raw output remains under `runs/`; no failure was removed from the record.

## Frozen RED

- `red-01/api-pytest.log` — invocation did not put the repository on `PYTHONPATH`; collection failed before exercising the API. Environment/setup failure, not product evidence.
- `red-01/projection-node-test.log` — `frontend/src/conversation.ts` did not yet exist; expected pre-implementation module-not-found RED.
- `red-02/api-pytest.log` — pytest's default temp discovery selected an inaccessible user temp directory. Environment/setup failure.
- `red-03/api-pytest.log` — effective product RED: both deterministic API tests reached assertions and failed because exact `answer_run_id`, `answer_source_message_id`, and `answer_kind` were absent. The S3 case also required source metadata to be redacted with the answer after current Scope revocation.

## Implementation iterations

- `green-01/` retained an early API error and TypeScript/projection failures: the API selection did not include the persisted message command ID needed to resolve durable limit notices; the frontend projection also had type/association issues. These were corrected in the same bounded implementation.
- `green-02/` retained the first projection assertion failures; exact-source grouping and fixture expectations were corrected without changing the frozen product expectation.
- `green-03/` and `green-04/` retain subsequent successful focused runs. `green-04/eslint.log` is an invocation failure because it included a test path without a repository ESLint configuration. The corrected changed-file command passed (`eslint-corrected.log`).
- `regression-01/pytest.log` records collection blocked by system Python missing locked project dependencies (`mcp`, `langchain_core`). Testing then moved to a private worktree `.venv-stageb` installed from `requirements.lock.txt`; no system Python or primary checkout was changed.
- `historical-c1-red-01/pytest.log` records the expected failure of a legacy C1 test still sending retired `READONLY_FOLLOWUP`; current routing requires `FOLLOW_UP + readonly_action=INVESTIGATE`. The historical case remains unchanged and was explicitly deselected from the full run. The test appended to two old C1 traces; because both were clean before that run, only those two side-effect paths were restored to HEAD. The fresh failing log remains preserved.

## Current final runs

- `final-01/`: API tests 2 passed; projection tests 4 passed; build/typecheck and changed-file ESLint all exit 0.
- `regression-02/pytest.log`: 149 passed.
- `full-01/pytest.log`: 401 passed, 1 historical case deselected.

Browser work was explicitly stopped by the current execution instruction. Browser evidence is `NOT_RUN / BLOCKED_BY_TOOL_ENVIRONMENT`, not a failure repaired by test substitution.
