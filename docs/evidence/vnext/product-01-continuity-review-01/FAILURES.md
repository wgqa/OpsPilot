# Failures and limits

## Newly reproduced RED

The new expectation that valid same-Run observations could be shown after a terminal model-budget stop initially failed for both fixture states (`QUEUED`, `PROCESSED`). The API returned `current=false` / `BUSINESS_SOURCE_INVALIDATED`. Underlying inspection showed the source was rejected because `_observation_scope()` accepted only `RUNNING` or `SUCCEEDED` Runs. The observations had been successfully obtained in the failed `CHAT_READONLY` Run, but the user could not inspect them. The original RED is preserved in `TEST_LOG_RED.txt`.

The narrow fix permits an explicit source-detail-only path for failed `CHAT_READONLY` `ASSISTANT_V1` Runs. The default `sources_current()` and `current_s3_evidence()` paths remain closed for failed Runs. The source endpoint revalidates the exact same Run, TaskBinding, Domain versions and TTL; the tests prove a Receiver version change makes the saved observation unavailable. No model answer is fabricated.

## Non-code execution issue

The first pytest invocation used the Windows default C: temporary directory and failed during fixture setup with `PermissionError: [WinError 5] Access is denied` while creating pytest's temporary directory. No test body ran in that attempt. The tests were rerun with `--basetemp` under `D:\Temp\OpsPilot-product-01-continuity-review-01` and then passed. This is retained as an environment limitation; it is not counted as a code failure or as a pass.

## Historical model observations (not newly reproduced)

- F01 turn 2: the model misstated whether a prior Run had used tools. This is a historical model phrasing/reasoning error (Type C); no guard or prompt change was made.
- F01 terminal turn: the program-generated budget notice said no business fact had been reacquired despite successful current-Run observations. This is the deterministic Type B defect fixed here. The run still had no model-final answer.
- Product-01 Slice 02 final turn: the model said follow-up verification was in progress without an actual follow-up execution. This remains a historical model phrasing issue; no new task scheduler or answer validator was added.
- Historical live model performance is not re-evaluated by the deterministic fixture tests.

## Unverified / not run

- No new real Provider request; ordinary non-experiment Provider operation remains unverified and is blocked by the current factory's requirement for a supported experiment identity when Provider mode is enabled.
- No browser automation or visual verification.
- No full repository pytest run.
- No conclusion on whether new prompt phrasing would change real-model behavior.
- No external business writes.
