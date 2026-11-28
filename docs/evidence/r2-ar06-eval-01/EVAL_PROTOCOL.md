# R2-AR06-EVAL-01 Evaluation Protocol

## Freeze and scope

- Base: `27c11fa341717f462286da1dd92568e7dce59469`.
- `CASES.json` and `RUBRIC.json` are frozen before case execution. Their SHA-256 values are recorded in `FROZEN_HASHES.json` and repeated in the report.
- The twelve cases are six work types × one development (`D`) and one held-out (`H`) case. Four security negatives remain a separate denominator.
- Gold and expected outcomes are offline evaluator data. Do not pass them to the Assistant, prompt, MCP, Knowledge, Evidence, or Gate.
- The case set uses only synthetic fixture data. The protected user Demo database/checkpoint, `.env`, historical spend ledger, Sessions and Memory are out of scope and must not be opened/reset.

## Execution and scoring

1. Reuse the formal API/Worker/Assistant/MCP/Domain tests at the Base. Every pytest invocation uses its own temporary Domain and checkpoint SQLite files under a task-specific temporary directory.
2. Use Fixture Models and local Mock MCP/HTTP only. Record actual fixture dispatches separately from paid Provider requests; fixture `usage_metadata` is never reported as Provider tokens or cost.
3. Keep each test's first result and log. No retries to turn a failure into a pass. A re-run caused by infrastructure/setup failure is a new attempt, not a replacement.
4. Assign `PASS`, `PARTIAL`, `FAIL`, `NOT_RUN`, or `UNVERIFIED` from the frozen outcome and evidence. Never infer a business outcome from `Run=SUCCEEDED`.
5. Retain `NOT_RUN` and `UNVERIFIED` cases in the frozen denominator. Do not use the R2-AR03 J1 composite trace as two independent samples; any multi-objective reuse is disclosed and does not increase independent `n`.
6. Score source correctness, decision quality, Domain outcome, actual Provider cost/performance and safety independently. No weighted aggregate score or significance claim.

## R/H/A comparison plan

M2-02's R/H/A protocol is retained as a reference, not copied as current results. Its 16-case S2 diagnosis/deferred-handoff task, real-model requirements and older runtime are not directly comparable to these six R2 work types. The current Base has one formal Assistant path; it does not contain a separate, equivalent rule-only (`R`) and model-normalization-plus-rule (`H`) runtime that shares the exact current tools, prompts, policy, budgets and evaluator. This task will not build a second runtime or rule engine.

For a later authorized comparison: freeze a matched subset first; run R as a competent conditional policy over the same trusted observations/tools; run H with model-produced untrusted intent normalization but the same R decision policy; run A with free legal tool/clarify/stop choice. Use independent isolated Domain/checkpoint instances, identical facts, budgets, model/prompt/schema where applicable, and the same evaluator. Keep the first failure. If these controls cannot be met, report a case study and the mismatch rather than a comparative claim.

## Historical live evidence separation

The historical evidence index in `EVAL_REPORT.md` retains each experiment's own Base, model request count, result and limits. None of those real Provider calls are included in the current Phase A totals. Historical responses, tokens, costs or PASS counts must not be combined with fixture results or with one another.

## Phase B handoff

Phase B requires separate user authorization for each paid Provider campaign, budget/grant, provider settings and any real-browser journey. The planned first campaign is at most six first-attempt samples selected from E01, E03, E05, E07, E08 and E09, one run each. Preserve failures; do not selectively repeat. E10 Memory ON/OFF and E11/E12 controlled handling are later authorized, isolated specials. Before sending, verify effective grant, available spend, provider-call count, unknown requests, and the explicitly approved hard budget. No such call is authorized by Phase A.
