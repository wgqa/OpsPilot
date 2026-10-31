# Failures and preserved attempts

All logs below are append-only historical attempts. The later passing logs do not replace or hide them.

| Log | Observation | Classification / disposition |
|---|---|---|
| `runs/red-provider-wiring.log` | The first run used the machine-global Python without the locked project dependencies; most failures were `ModuleNotFoundError`, and the intended missing factory was also absent. | Test environment preparation failure plus expected implementation RED. Preserved. |
| `runs/red-provider-wiring-venv.log` | Under the project venv, all four new checks were red because the formal server did not inject a factory and no guarded factory existed. | Valid wiring RED. Fixed by the server injection and fail-closed factory. |
| `runs/green-provider-wiring.log` | One post-implementation test looked for `.timeout`; the pinned LangChain object exposes `request_timeout`. | Incorrect test assertion, not a product defect. Corrected and preserved. |
| `runs/red-provider-wire-mock-02.log` | Local wire capture showed `max_completion_tokens: 2048`; the test expected DeepSeek's documented `max_tokens`. | Valid protocol mismatch RED. Fixed for DeepSeek by setting the provider field through `extra_body` and removing the conflicting per-call alias. |
| `runs/green-provider-wire-mock-04.log` | The first attempt to replace the model's HTTP client with `model_copy()` did not replace its cached client. One request containing the test-only placeholder key reached DeepSeek and returned HTTP 401 (request ID recorded in the raw log). No successful completion or usage was returned. | Test harness isolation failure and accidental external auth request. The test was corrected to inject `MockTransport` at model construction. No further external request was made. Billing state was not independently checked, so this report does not claim verified zero billing. |
| `runs/ar02-regression.log` | The test runner's `--basetemp` parent did not exist; the run had 4 passes and 33 setup errors. | Local test-path preparation failure. Preserved. |
| `runs/ar02-regression-02.log` | Corrected isolated temp location; 37 related tests passed before the final wire correction. | Historical intermediate GREEN, not used as final regression evidence. |
| `runs/ar02-regression-06.log` | 38 related tests passed after the first local wire harness correction but before the final provider configuration checks. | Historical intermediate GREEN. |
| `runs/green-provider-wire-mock-03.log` | Initial wire-test iteration. | Preserved; superseded by final exact-body capture. |
| `runs/green-provider-wire-mock-05.log` | Final local MockTransport capture contains the exact serialized body with `max_tokens`, not `max_completion_tokens`. | Free local adapter verification. |
| `runs/green-provider-preflight-final.log` | 7 provider-factory and wire tests passed; exact body printed from MockTransport. | Final focused free GREEN. |
| `runs/ar02-related-regression-final.log` | 40 AR-02 runtime, Assistant, Knowledge, HF-01 and new adapter tests passed. | Final related free regression GREEN. |

The unexpected 401 is a material incident. It used only the literal test placeholder `test-only-not-a-real-key`; it produced no model answer or Usage record. The external account ledger was not accessible, so billing is **unverified**. The task remains blocked before any authorized model completion.
