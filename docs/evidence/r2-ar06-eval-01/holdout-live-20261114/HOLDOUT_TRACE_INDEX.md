# Holdout Trace Index — 2026-11-14

All H trace and Runner result files below are byte-for-byte copies of the single-session redacted exports in their original `.runtime` directories. Their SHA256 values were compared to the source files after graceful shutdown. The complete model answers are retained in each trace. D records remain at their original paths and are not duplicated or rewritten by this report.

## E01-D — historical first attempt, retained

- Runtime: `user-demo-r2-e01-1114a`
- Session: `session-57d5d0a8-bb16-4be9-ab6a-c58f18049976`
- Run: `run-7ff06937-6268-4fa3-a51e-4ce63100436e`; Provider response: `814c3218-c068-4aff-a0c4-2b55ac6a1ade`
- Frozen input SHA256: `bfc28bababb48805409563fd27a1911723781167a9aee76e994fa12dcfa6e3c4`
- Trace: [LIVE_E01-D_HISTORICAL_TRACE.json](../runs/LIVE_E01-D_HISTORICAL_TRACE.json), SHA256 `abdd1c66c9a8e33ee30e237131e2575a8ddad0e4b1866d453f65b694d7493688`
- Domain DB SHA256: `5d225e8bb0d5fdd0ab0cf27cf3cab28b05c04274b5923fc4c0e148212638cae5`; Checkpoint SHA256: `5507a716fdbf1c9d48a8e50700602bdac77f26c9ed9b935f55edd89f8f1c9b2b`
- Result record: [E01_CANDIDATE_SCORE.json](../E01_CANDIDATE_SCORE.json). This result was not re-run in this task.

## E05-D — prior development first attempt

- Runtime: `user-demo-r2-e05-live01`
- Session: `session-36f1742a-826c-4d25-9712-43fbe0037ff2`
- Run: `run-4b15215e-3f49-445d-be88-98999d85e63d`; Provider response: `527572e1-b29a-4c47-a809-8df1ee9347c7`
- Frozen input SHA256: `645d998ad89484df6119d20df0c61c46be87ece0915f425c227fd8823bc3af7f`
- Trace: [LIVE_E05-D_TRACE.json](../runs/LIVE_E05-D_TRACE.json), SHA256 `64bd52b76243ed0c51d6290f539e09a06a32ef0ac5b56dfa05f558ac973043cb`
- Runner result: [LIVE_E05-D_RUN_RESULT.json](../runs/LIVE_E05-D_RUN_RESULT.json), SHA256 `ed79247bdc7598ee2191387de354024e4943b67cb411e1d8e8b3ddfec33b5e62`
- Domain DB SHA256: `e1fc8f8ebfc7409b714a666098f4936c92ecda9a148003a81322256c3d6be70b`; Checkpoint SHA256: `a48cada6e30b2141eee421389338c835d1ea97c03c4b9e3ec7fb2dde94a3f687`

## E07-D — prior development first attempt

- Runtime: `user-demo-r2-e07-live01`
- Session: `session-300f9d82-85f7-4bff-a3d6-6da8d99324b3`
- TaskBinding: `task-73c28480-0392-47c4-866d-8a5e505ae619`
- Run: `run-c6be60b9-e6b0-4310-8c8f-853c00934d4f`; Provider responses: `377d6ab2-2aca-49d3-bd79-cd9e77008be5`, `c88b0aa9-67af-41a5-9f3d-ceab2b8035d1`
- Frozen input SHA256: `58a3fa04a1ff5197fb8ff6f604bfd8c5e4975a7fac202f5850f58ee37e6a9354`
- Trace: [LIVE_E07-D_TRACE.json](../runs/LIVE_E07-D_TRACE.json), SHA256 `aacf15bdb81a24461b612551a23800a12c86f54a275f95185a3d24cdb34ebb59`
- Runner result: [LIVE_E07-D_RUN_RESULT.json](../runs/LIVE_E07-D_RUN_RESULT.json), SHA256 `d31a82dd7f39e961a8b0398d6b554b40f6b5d609d8b66362989489cd0494ebd0`
- Domain DB SHA256: `31698951bf1987a26ba536c4dc8785bcdb9af08b718ea51638d7130f917ec8ce`; Checkpoint SHA256: `b93f063546e7edf8ae2ca47f06fda73b7f037eb5be7507c0debdcd193db9bf84`

## E02-H — authorized first holdout attempt

- Runtime: `user-demo-r2-e02h-live01`
- Session: `session-9bdec216-d146-41fa-85a4-b24d56ce1829`
- Run: `run-cb15aaf1-08ec-4e67-a1fa-bfebf1933955`
- Source Message: `message-83c4bc5f-2802-48cc-b1ac-9e8ab3a4263f`
- Provider Response ID (from spend `completion_id` and trace response metadata): `7b1c5afd-949a-4dc6-9a2a-7ccbc7618b51`
- Frozen prompt SHA256: `4cae1c272aa3dceb334728e3c49a31db4d01c381b6ed2a27d4c9915fc0abcb89`; Run status `SUCCEEDED`; 1 request; input/output 2,496/455; USD 0.001295; no TaskBinding, MCP, Observation, Evidence, UNKNOWN or retry.
- Original Trace: `.runtime/user-demo-r2-e02h-live01/evidence/E02-H.json`; source SHA256 `042F2C16076632AC40AAA67CB8A0E52DB27E300D0C364A0158106B8A57ECD770`.
- Review copy: [E02-H.trace.json](E02-H.trace.json), SHA256 `042F2C16076632AC40AAA67CB8A0E52DB27E300D0C364A0158106B8A57ECD770`.
- Runner result copy: [E02-H.runner-result.json](E02-H.runner-result.json), SHA256 `D305FD7E44FF996B48F3FE49B349681E879652654C9438579AC5D34E81B600FD`.
- Original Domain DB SHA256: `86A4DF3DA23704DEC688ADDC4D313B8046CAB84A438BAFD48BA450BBB70E9481`; Checkpoint SHA256: `473BD1BE276D821F3E168D2C1CE0A8D803866575B16026C80B0347A05167AA64`.

## E06-H — authorized first holdout attempt

- Runtime: `user-demo-r2-e06h-live01`
- Session: `session-8b59f364-989d-4320-bc11-b4d7ea65fa03`
- Run: `run-90ac6a92-39a9-4d5c-bd34-dcc69e52a0b1`
- Source Message: `message-15a4526c-5354-4b00-838e-c18d33ad86e4`
- Provider Response ID: `6c1c302d-343f-49f6-80a5-bb5fea006334`
- Frozen prompt SHA256: `af2123d4a2a3d459aa18d7805cbcb214d5d45f7ea6c4e3af690644f0414a7aa6`; Run status `SUCCEEDED`; 1 request; input/output 2,511/425; USD 0.001264; no TaskBinding, MCP, Observation, Evidence, UNKNOWN or retry.
- Original Trace: `.runtime/user-demo-r2-e06h-live01/evidence/E06-H.json`; source SHA256 `4C32C2C9721FBC7896756034FCCA8393CAB59683130A03B3CE9D00CAD785D0AF`.
- Review copy: [E06-H.trace.json](E06-H.trace.json), SHA256 `4C32C2C9721FBC7896756034FCCA8393CAB59683130A03B3CE9D00CAD785D0AF`.
- Runner result copy: [E06-H.runner-result.json](E06-H.runner-result.json), SHA256 `EE930BDDAAC5CB46720A0750A09325018EC5FBF6B8D91043034D47654FAC9630`.
- Original Domain DB SHA256: `A84AF4A5B314401FEADC66BC912A9294FF25D8E25B438FAFCAFCAD70775C198C`; Checkpoint SHA256: `07B23E89D3540FB73EA803F68E80612EAD0497E29F70A8107E2B07A02EF0B3B3`.

## Integrity note

The two H original export files and their repository copies were compared byte-for-byte by SHA256 after the services stopped. Runtime DB/Checkpoint digests above were computed after graceful stop. All source Runtime data remains in place.