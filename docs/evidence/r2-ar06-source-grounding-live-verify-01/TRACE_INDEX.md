# Trace index

The JSON files below are the full sanitized Runtime-scoped exports and unchanged Runner result files. The original files remain under each isolated Runtime's `.runtime/<runtime>/evidence/` directory.

| Case | Runtime | Run | Trace | Trace SHA256 | Runner result | Result SHA256 |
|---|---|---|---|---|---|---|
| E07-D QUEUED | `user-demo-r2-sg-live-queued01` | `run-49471cb5-314d-4f2e-b86f-1b0b2335a86b` | `E07-D.json` | `4335781b9df05dbe177e0a58f031ad562d67a5617fc082c4b8dd24d34b3ba72a` | `E07-D.result.json` | `01fa126c705d8ea7cbbf092f48ad0884906970db33126f9b3225008ee89300a4` |
| Exploratory PROCESSED | `user-demo-r2-sg-live-processed01` | `run-52c2442a-cf60-4dd1-8dfe-63ebb65860fc` | `OBSERVATION-CONTRAST-PROCESSED.json` | `e9e72759b5d13e2ed9afff0f264efafeaee4867c5f429d83790814168ef433c4` | `OBSERVATION-CONTRAST-PROCESSED.result.json` | `f67a182d25b3becdaa12d4c169acba429c384b357f79c349bab4c740ab41e9a4` |

`LIVE_RESULTS.json` is the combined index and keeps both runner assessments as `UNVERIFIED`. The exploratory run is explicitly labeled `EXPLORATORY_COUNTERFACTUAL_NOT_FROZEN_CASE`.
