# RED-01 原始复现

- Freeze commit: 76aead4248cdf63c1d59e914c4c99a37c1b68141
- Pre-RED HEAD: 76aead4248cdf63c1d59e914c4c99a37c1b68141
- Command: .venv\Scripts\python.exe -X utf8 -m pytest tests/test_m301_red.py -q --tb=short --basetemp=docs/evidence/vnext/m3-01/runs/red/red-01/pytest-basetemp
- Exit code: 1
- Result: 4 failed in 2.22s. The unmodified implementation returned no case schema for S1, rejected a Task with a real local HTTP 403 and DiagnosisReceipt because it only recognizes S1 repair sources, omitted S2 memory from Investigator context, and returned 404 for the candidate-creation Web route.
- Evidence boundary: this RED run uses a fixture-seeded S1 source and the existing local HTTP/Domain S2 receipt helper. It did not run a real model or MCP stdio process and is not counted as final real-model evidence.
- Raw output: pytest.log. The four per-test assertions and original failure text are retained unchanged.
- No product source files were modified before this run.
