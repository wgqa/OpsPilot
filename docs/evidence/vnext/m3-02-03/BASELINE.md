# M3-02 / M3-03 开工基线

- Verified starting commit and initial `origin/main`: `5ade2b5deedbb3704b09e9d6fbbfbffa3ab8deb8`.
- Frozen acceptance commit: `3cb826d0d41984c898aefa5081d347d94a7c9c21`.
- Baseline test code SHA: `3cb826d0d41984c898aefa5081d347d94a7c9c21`; production code was unchanged from the starting baseline.
- Domain SQLite schema observed in source: `user_version=9` (the task card's v8 reference is stale).
- Fresh command: `.venv\Scripts\python.exe -m pytest -q --basetemp=.runtime\pytest-m302m303-baseline-01`.
- Result: **204 passed in 152.38s**, process exit code 0. Raw stdout/stderr capture: [`runs/baseline-01/pytest.log`](runs/baseline-01/pytest.log); exact exit code: [`runs/baseline-01/exit-code.txt`](runs/baseline-01/exit-code.txt).
- Historical M3-01/HF-01 outcomes and files were not rewritten. No pre-existing user files were staged.
