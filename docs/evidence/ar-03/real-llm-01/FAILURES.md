# Failures and non-success evidence

All entries are retained as run logs. The first test preparation errors are not counted as business RED.

1. **Test import setup error — not business RED.** Initial `pytest` used the system interpreter without `PYTHONPATH=.` and failed to import `opspilot`. Log: `runs/budget-cap-red.log`.
2. **Environment dependency mismatch — not product regression.** A first corrected-PYTHONPATH run used `D:\python\python.exe`, whose environment lacked `langchain_core`; 16 tests passed and 11 failed during imports. No Provider call occurred. Log: `runs/budget-cap-green.log`.
3. **Valid budget RED before implementation.** With the project venv, the new half-allocation test reproduced that AR-03 initialized each isolated database at 16/12 rather than the required 8/6. Both focused assertions failed as expected. Log: `runs/budget-cap-red-corrected.log`.
4. **Initial safety-regression command typo — not a test result.** One named test path did not exist; pytest ran no tests. Log: `runs/ar03-safety-regression.log`.
5. **Transport preflight defect found before live use.** HTTPX URL in the installed version has no `is_https` property. The runner was corrected to compare `url.scheme`; an offline MockTransport test now exercises the recorder and pre-send wire check. No real Provider traffic was sent during this correction.

No previous UNKNOWN reservation, historical Gold, prior trace or old experiment database was modified. The live run's own failures, if any, are appended after execution; no quality reruns are permitted.
