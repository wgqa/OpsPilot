# Resume 01 preparation failures and limitations

No historical failure or Gold was overwritten. Full raw console logs are kept in the local private evidence directory; this file contains only a review-safe summary.

## New failures observed and resolved

- Initial RED on the project virtual environment: the new experiment ID was absent from the campaign allowlist and schema; the prepared Provider guard returned the generic invalid-scope refusal; and the new isolated Runner did not yet exist. These failures established the required implementation gap. The environment was corrected to the repository `.venv`; an earlier system-Python run lacked `langchain` and is classified as a test-environment selection error, not product evidence.
- Early GREEN attempts exposed test-only setup mistakes (missing temporary Runtime parent, assuming the fixture returned an Event ID, and a missing `json` import). Each raw failed run is retained; the tests were corrected without changing product expectations.
- One attempted regression command named a nonexistent test file and exited 4 with `no tests ran`; the corrected command used existing repository test paths. Its log is retained.

## Existing failures reproduced on the accepted base

The broader AR-03 material run reported 73 passed and 4 failed. Running `tests/test_ar03_material_01.py` unchanged on the accepted safe base `ff956ea71b90448d40229c57b8f8619c997b5cbd` reproduced the same 4 failures (6 passed / 4 failed):

1. `test_protocol_upgrade_skill_is_integrity_checked_and_only_loaded_on_demand`: protocol Skill body digest does not match its manifest.
2. `test_formal_assistant_reads_authorized_text_and_keeps_pasted_material_untrusted`: deterministic formal Assistant Run returned `FAILED`.
3. `test_trusted_order_material_investigation_uses_current_same_event_and_keeps_draft_unsubmitted[QUEUED]`: deterministic formal Assistant Run returned `FAILED`.
4. The same test for `[PROCESSED]`: deterministic formal Assistant Run returned `FAILED`.

These failures pre-exist this candidate, were not changed, and were not attributed to a specific shared root cause in this task. The new execution-preparation tests, recovery test, and compatible material tests passed. No full pytest run was performed.

## Not run by authorization

- Any real Provider request or paid MAT case.
- Browser automation.
- Business writes or approvals.
- Full pytest.
- A new one-shot paid claim; it remains unconsumed until separate authorization.
