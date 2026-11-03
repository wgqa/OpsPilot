# Public release manifest — Recovery 01

This release is based on the already public recovery candidate base `69a1a1171b97849a6b5a77a7b8f8d03f263c95aa`. This manifest reviews the new branch delta only; files already present on that public base are unchanged.

| Path | Purpose | Publication review |
|---|---|---|
| `docs/evidence/ar-03/material-live-01/recovery-01/ACCEPTANCE_PLAN.md` | Frozen free-recovery scope and acceptance criteria | Uses synthetic demo tenant/principal/order labels from the project fixture; contains no personal or credential data. |
| `docs/evidence/ar-03/material-live-01/run_live.py` | Fresh-database bootstrap fix | Only the changed source diff is new relative to the public base. No key, token, cookie, local database, or environment file is added. |
| `tests/test_ar03_material_live_recovery_01.py` | Offline refusal and formal-path regression coverage | Contains synthetic fixture identifiers and a disposable in-process test password (`offline-test-only`); no real credential or external endpoint. Detailed runtime trace output is not printed. |
| `docs/evidence/ar-03/material-live-01/recovery-01/PUBLIC_SUMMARY.md` | Redacted result and failure summary | Aggregate outcomes only; omits private run IDs, event IDs, database values, raw messages, and workstation paths. |
| `docs/evidence/ar-03/material-live-01/recovery-01/PUBLIC_RELEASE_MANIFEST.md` | File-by-file publication review | This manifest. |

## Excluded private artifacts

The new recovery delta does not add raw pytest stdout, recovery JSONL traces, SQLite databases or sidecars, one-shot claim files, budget ledgers, credentials, cookies, environment configuration, screenshots, or private execution paths. These newly generated raw recovery artifacts remain in the original local recovery candidate and are indexed there outside the published change. Earlier material-live-01 artifacts already present on the public base are unchanged by this release.

No claim is made that synthetic fixture identifiers are production customer data. No new raw browser state or personal information is added. No commit is pushed to `main`.
