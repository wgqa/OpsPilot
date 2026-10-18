# M1-03 current evidence version guard

- Base: `main@64f8510ab03a9d8516c4a27f606b93b7aa818f0c`
- Scope: trusted Domain version validation in `opspilot/domain/chat.py::_current_evidence()` and focused regression coverage in `tests/test_m1_chat.py`.
- Result: current evidence is admitted only when its typed observed version and facts match the live Config, Principal, and AuthPolicy rows for the task binding. An Endpoint Probe additionally requires complete `before` and `after` snapshots to match all three current versions, to be equal, and to report a stable probe using the current credential reference. Evidence rows remain stored for audit. Stale evidence is excluded from model context with `EVIDENCE_RESOURCE_VERSION_MISMATCH`; assistant messages whose recorded sources include such evidence inherit the same exclusion reason.

## Fresh validation

The regression creates a task-bound v7 investigation with real Domain reads and a real loopback HTTP 401 probe. It confirms that v7/401 evidence is initially included, then creates and approves a Plan, persists a REPAIR ActionIntent, and commits the controlled repair from config v7 to v8. On the next chat, the old credential reference, HTTP 401 result, and assistant answer based on that evidence are absent from model context. The ContextManifest excludes the stale config and probe evidence and the dependent answer with `EVIDENCE_RESOURCE_VERSION_MISMATCH`; the historical evidence rows remain in SQLite.

- `python -m pytest tests/test_m1_chat.py tests/test_d3_actions.py -q` — **20 passed**.
- `python -m pytest -q` — **102 passed** in 63.65s.
- `git diff --cached --check -- opspilot/domain/chat.py tests/test_m1_chat.py docs/evidence/vnext/m1-03/logs/VERSION_GUARD_FIX.md` — **passed**. Raw pytest failure captures are preserved verbatim and contain pytest-rendered trailing whitespace, so the same check over all evidence logs reports those lines.

Raw logs are retained alongside this note: `version-guard-red-pre-fix.txt` is the pre-fix functional failure showing `cred-v1` and the old 401 still in the next context; `version-guard-green.txt` records the focused fixed test; `version-guard-targeted-pass.txt` and `version-guard-full.txt` record the final targeted and complete runs. The earlier `version-guard-red.txt` and `version-guard-red-baseline.txt` are test setup attempts corrected before the functional red run (a non-seeded ticket and an incorrect expected result-key name). The first two broader targeted runs also exposed the inspector fixture's now-invalid empty version metadata and its old hard-coded credential expectation; the fixture was updated to reflect the live seeded Domain state. These are retained as test harness corrections, not implementation failures. The full suite prints a `d3_smoke_result: FAIL` record from `test_d3_smoke_preserves_failed_start_process_without_crashing`, which deliberately injects a provider timeout and asserts that the failure is preserved; pytest itself passed.

No D1-D7 or other M1 functionality was changed, and M1-04 was not started.
