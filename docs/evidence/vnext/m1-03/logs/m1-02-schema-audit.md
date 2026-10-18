# M1-02 schema metadata check (M1-03 handoff item)

Checked against the existing files; no correction to historical M1-02 evidence was made.

- `docs/evidence/vnext/m1-02/RESULTS.json` has top-level `schema_version: 1`; it describes that JSON result document. It is not a SQLite `PRAGMA user_version` field.
- M1-02 historical test output `logs/pytest-m1-02.txt` records the migration case's SQLite `user_version: 2`; `logs/attempts.md` independently documents the M1-02 schema migration from 1 to 2.
- The current M1-03 Domain migration adds chat persistence and advances SQLite `user_version` to 3. The fresh migration test in `tests/test_m1_task_control.py::test_schema_migration_is_idempotent_and_preserves_frozen_plan_hash` now asserts 3, and the M1-03 live smoke records the fresh DB's value in `RESULTS.json`.

These values use different names and refer to different schemas. The original M1-02 RESULTS file and its raw logs remain unchanged.
