# Failures and remaining limits

## Product RED reproduced and closed

On the unchanged Base implementation, the isolated C02→C03 journey ended with the same-Task `CHAT_READONLY` Run `FAILED / TASK_INPUT_PENDING` before any Assistant call. See `RED_TEST_LOG.txt` and `RED_STATE.json`. The correction remained durably pending and the formal Investigator was stopped by the Legacy Provider authorization gate. The final isolated journey now succeeds through the read-only Assistant and two current MCP observations; see `GREEN_STATE.json`.

## Test/tooling failures preserved

- The first RED pytest setup attempt could not create a temp directory under the Windows user temp root (`WinError 5`). This was a local pytest temp-root permission issue, not an application failure. The reproduction was rerun using `--basetemp` inside this isolated worktree and reached the application RED.
- One intermediate GREEN run showed a second real gate at `d2.reserve_attempt()`; after that direct D2 TaskControl check received the same narrow read-only condition, the dedicated tests passed.
- Intermediate test assertions were corrected to match the actual Assistant answer and persisted schema. These were test-harness expectation mistakes, not converted into product results. The complete final outputs are retained in `FINAL_TEST_LOG.txt`.
- One focused regression remains failed: `tests/test_m1_task_control.py::test_schema_migration_is_idempotent_and_preserves_frozen_plan_hash` expects `user_version == 18`. The unchanged Base migration source already adds versions 19 and 20. No schema code or this historical assertion was changed.
- Frontend typecheck remains unverified because this isolated worktree has no installed `vue-tsc`; offline `npm ci` could not find the locked `yocto-queue@0.1.0` tarball in the local cache. No network install was attempted.

## Not run

- No real Provider request, real DeepSeek experiment, browser automation, Live demo interaction, or external business write.
- No full-repository pytest run. The focused regression suite, dedicated journey tests, and ordinary Assistant/Runtime Grant suites are recorded in `FINAL_TEST_LOG.txt`.
- No main merge.
