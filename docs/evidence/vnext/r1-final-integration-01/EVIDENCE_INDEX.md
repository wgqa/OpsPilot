# Evidence Index

## Current run private logs

Raw output remains under the local ignored directory .private-evidence/r1-final-integration-01/. It is not committed. The digests below allow the reviewer to distinguish the preserved logs without publishing databases, sessions, credentials or full runtime state.

| Local private file | Result | SHA-256 |
|---|---|---|
| ar03-mocktransport-targets-20261107.log | Current candidate 0/3; root failure assertions | F8E8457473F2DECC0115B99942118DD63118D0133EA09F2B03931F139D085DB7 |
| focused-product-s1-s2-20261107.log | Current candidate targeted Python 77/77 | 948EA236588EDE9D85AD434E180DB93E22EAE94FA25885A0969833DDC5A7A8EE |
| frontend-assistant-entry-test-20261107.log | 8/8 | BCE2EC43260165C955CE1BA140A60213E3C483028D3AC5D6BD086F05F3EFA980 |
| frontend-typecheck-20261107.log | Passed | ACC8B34F1216A35E180BA6C131BF81C217A6DA08FF881C2AA37EFFB228AC86F2 |
| frontend-build-20261107.log | Passed | F69AFFEE4A853BC4B35758820C4B4809E82C555001C63FE7C08EAC8595D2E22F |
| frontend-eslint-20261107.log | Passed | 03F21F7520DDEA2EA2C0578207FC8EBC5E7E430235798E09CABFBE5448F9EEBE |
| npm-ci-20261107.log | Lockfile install, private cache | 2A7147D14A34B4E58D13C93C52819D6CB22B9BF4C394DB4C02D976018606314E |
| cli-reset-demo-20261107.log | S1_POS fresh temp DB, exit 0 | EAF7856659C130C373F1751B67783C621FE9A2549B080977AAC07F5516DC4D70 |
| server-health-graceful-20261107.log | Health 200, Worker ready, lifespan shutdown complete | B8DEFCE2D3CCE680A4ABE41C8942FED0FE958ABD834A215DCDC62FD9BAA2BFC9 |
| python-compile-20261107.log | compileall, exit 0, no stdout | 5C5F1EDD3830579A499D347576CC82DEFC723FAA66620B5B4BB8F2DC94E08D94 |
| pip-check-20261107.log | Environment version mismatch, exit 1 | 47BDD0B2C9FD8447C1DFC6CD47F69E7C8BE57ED9F4F04DA5B26A01EF21766B4A |

Python compileall ran successfully with exit 0; it emitted no stdout. A zero-output log will be recorded after final checks.

## Baseline comparison logs

| Local private file | Result | SHA-256 |
|---|---|---|
| ../r1-final-integration-01-baseline-d4/.private-evidence/r1-final-integration-01/ar03-baseline-d4-targets-20261107.log | Two extant target tests passed 2/2 on d4addd403ba0722d4acb4c1a33d1cd655599c97c | 8E648DD3021056C6C5DCF36331FC2FE639ED86A98A96C5F378CC8F793CE1C5FC |
| ../r1-final-integration-01-baseline-8df/.private-evidence/r1-final-integration-01/ar03-baseline-8df-targets-20261107.log | All three targets passed 3/3 on 8df557dabb6f7440b371828c39974239363ee6d9 | 5E05AF3C616CF0BD781CE3DEC8611520227C4911013AEF701A28A6D81892013F |

The detached baseline worktrees and their databases/logs were preserved. No historical claim, budget or data was reset.

## Commands

Focused Python regression:

    python -m pytest tests/test_product_01_bridge_closeout_01.py tests/test_product_01_final_bridge_01.py tests/test_ar05_s1_session_bridge_01.py tests/test_ar05_s2_assistant_handoff_01.py tests/test_d3_actions.py tests/test_ar02_runtime.py tests/test_ar02_assistant.py tests/test_ar02_smoke_provider_factory.py tests/test_ar02_ar03_integration_01.py -vv -s --basetemp %TEMP%\r1-final-integration-focused-20261107

AR-03 MockTransport targets:

    python -m pytest tests/test_ar03_material_live_resume_02.py::test_resume02_formal_worker_persists_reservation_and_classifies_mock_completion tests/test_ar03_material_runner_recovery_02.py::test_formal_worker_mocktransport_accepts_reserved_request_and_persists_mat01_answer tests/test_ar03_material_runner_recovery_02.py::test_formal_worker_failed_mock_request_is_auditable_without_overwriting_run_reason -vv -s --basetemp %TEMP%\r1-final-integration-ar03-targets-20261107

Frontend:

    npm ci --cache %TEMP%\npm-cache-r1-final-integration-20261107 --no-audit --no-fund
    node --experimental-transform-types --test test/assistant-entry.test.ts
    npm run typecheck
    npm run build
    npx eslint src/App.vue src/assistant-entry.ts test/assistant-entry.test.ts

Python:

    python -m compileall -q opspilot
    python -m opspilot.cli reset --scenario S1_POS --db <new-private-temp-db>
    python -m opspilot.web.server --host 127.0.0.1 --port <local-port> --workers 1
    Invoke-RestMethod http://127.0.0.1:<local-port>/api/health

No full pytest was run on this candidate SHA. Do not interpret the predecessor's 741/757 as this branch's run.

## Final governance blobs

| File | Blob |
|---|---|
| PROJECT_NORTH_STAR.md | 43dabda468506717c6956e676dfad4304c4f38e6 |
| AGENTS.md | 807b928686a4dd2cac7b15b3c354b9943c93c910 |
| TASKS.md | 1f08ee3a8e538d7ece4d2b2841c7c53e25737b7c |
| README.md | 9302b85b0bb7ce6ede7662e129a5e7b2dc06c408 |
| .agents/skills/opspilot-slice-review/SKILL.md | d405c8d413d633824b279202cc1503dab4cf0b03 |

Final SHA values were obtained with git hash-object after the document changes. The project review Skill was unchanged from the baseline Blob. The Markdown link scan checked 100 local links in the four governance files and this evidence package; none were missing. git diff --check passed.
