# Frozen A/B parity and declared differences

| Dimension | Shared condition / difference |
|---|---|
| Model | Same injected model/config per pair; independent instances. Local deterministic model only. No real model effect claims. |
| Tools | Exactly six names from existing s3_mcp; same description/input schema. Compare native B tool conversions to A specs; fail readiness if not equal. |
| Authorization | Same trusted TaskBinding/current Scope/Principal/Grant checks on the existing server; no direct fact SQL/HTTP in B tools. |
| Facts | Prepare once with existing fixture (real local HTTP), clone SQLite before creating independent Tasks. Initial business snapshot digests must match. |
| Budget | Both initial Runs use current 8/6, cumulative Task24/18, same context profile/timeouts. No automatic reset or retry. |
| Prompt | A PROMPT unchanged and structured current evidence/context. B shorter instruction plus native full message/tool history. Not strict prompt equality. |
| Loop | A existing candidates->one tool->gate->next_step. B create_agent model/tool edges, sequential tool graph invocation. No planner/reviewer. |
| Context | A reconstructs current JSON; B validates retained current sources before dispatch. Invalidated sources cause explicit safe partial stop in first candidate, not a new Context framework. This may reduce legal continuation and is reported as a candidate limitation. |
| Assets | Same versioned search/load MCP, no initial approved Memory. A extra method catalog/labels remain visible; B tool descriptions supply catalog. |
| Final delivery | Shared existing S3 response support/currentness checks; no Domain diagnosis/report/handoff commit. A production report writer omitted explicitly; this is decision-policy comparison only. |
| Continuity | Small in-experiment message history tests only; not product cross-Run goals or new persistent conversation implementation. |

Readiness requires actual protocol checks and initial-state/schema equality. Deterministic runs prove loop mechanics and safety, not comparative autonomy. Paid trials remain NOT_RUN.

## Observed implementation details (do not alter frozen Gold)

LangChain's BaseTool converter strips display-only `title` metadata. The initial
strict check rejected this difference (local-02, schema-diff-01.json). B now checks
native execution constraints excluding titles, then passes the original A raw
specs at the actual model boundary. The runner verifies the actual model's bound
schemas are identical in every final pair; parameters/descriptions were not reduced.

Both request parallel_tool_calls=false. If a model violates that setting, standard
B receives a native tool batch and executes it serially under a lock; A retains its
existing first-tool/reconsider-candidates behavior. This is a declared loop-policy
difference, not an extra B tool or permission. The local normal cases use single
proposals; a separate negative test proves a batch cannot overrun remaining slots.

Only fresh initial Run equivalence is claimed. The B experiment's default 8/6
limit argument caps cumulative experiment usage as well as the existing Domain
Run caps. Full CONT-UX 24/18 Task allocation across multiple Runs is NOT matched
or evaluated. Re-entry on the same Run retains spent attempts; unverified or
restarted native history is explicitly refused. Neither adapter runs production
Worker heartbeat/Checkpoint recovery or formal completion writes.

B rejects structured fake Receipt/result fields and uses existing typed processing
support checks. Natural-language truth remains unverified; an authority label
cannot establish semantic correctness. A's extra structured Context/catalog and
B's native retained messages may affect real-model results and cost.
