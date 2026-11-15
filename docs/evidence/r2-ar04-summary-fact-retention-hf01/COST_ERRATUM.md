# Cost terminology erratum — ABC-LIVE-ENV-UNBLOCK-01

The prior frozen report used “actual cost” / “实付 USD 0.032708” for a locally computed estimate. That wording overstated what the evidence establishes. This erratum clarifies the accounting labels without changing the prior report, Trace, results or ledger.

| Field | Correct value | Evidence |
|---|---:|---|
| `provider_usage_tokens.input` | 82,563 | Frozen provider Usage records in `live_run_02/LIVE_REQUESTS.jsonl.gz` |
| `provider_usage_tokens.output` | 6,609 | Frozen provider Usage records in `live_run_02/LIVE_REQUESTS.jsonl.gz` |
| `conservative_peak_cost_estimate_usd` | 0.032708 | Per-request upward-rounded estimate using the prior report's peak uncached rates: $0.30/M input and $1.20/M output. The sum of unrounded token arithmetic is $0.0326997; rounding each request upward to micro-dollars produces the ledger total 32,708 micro-USD. |
| `provider_actual_billed_usd` | `UNVERIFIED` | No account invoice/usage-billing record was captured. Provider token usage and the local price model do not prove account billing. |

The frozen ledger remains unchanged and continues to record its calculated `settled_usd_micro`; that field is a local estimate derived from token usage and configured rates, not a verified DeepSeek account debit. This erratum does not authorize or motivate another paid experiment. This task itself made zero Provider requests and incurred USD 0.

The prior report SHA-256 is `2f2c05d7aa114c5b965c80921e90d64abbae8b7a5954c697f4fe69bc1f116e2a`. Protected original hashes are asserted by `tests/test_ar04_summary_fact_retention_hf_01.py::test_frozen_provider_trace_results_ledger_and_c06_red_are_unchanged`.
