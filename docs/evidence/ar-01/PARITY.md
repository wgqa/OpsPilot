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
