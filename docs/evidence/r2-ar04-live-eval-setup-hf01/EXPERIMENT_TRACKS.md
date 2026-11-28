# Live semantic evaluation tracks

## Shared frozen inputs

Both tracks use the same 29-row synthetic history from `r2-ar04-long-context-journey-01/HISTORY_SNAPSHOT.json`, the same frozen question text and actual Assistant tool schema. A, B and C map to `HYBRID`, `ROLLING_SUMMARY` and `RECENT_WINDOW`. All three use a configured 12,000-token input limit and a temporary Grant capped at 12,000 input / 512 output tokens. Each case starts from its own temporary Domain database and checkpoint. Gold answers and scoring rules are read by the offline harness only; the Assistant receives only the fixed question text, selected context and the same tool schema.

The production Runtime reserves trusted system/context/tool overhead before selecting history. Therefore the effective available history budget is lower than the configured 12,000-token cap and may vary slightly with the strategy's context payload. Both exact values and each actual Mock request estimate are recorded. Strategy comparisons must use the same configured cap and report those effective values; they must not claim that every group received exactly 12,000 history tokens.

## Track 1 — history recall

Question set: `Q02`, `Q03`, `Q06`, `Q07`, `Q08`, `Q10`, `Q12` for all three strategies. The request carries the same tools and schemas as the other track, but the Assistant Runtime receives the explicit evaluation-only `tool_choice_override="none"`. All observed answer requests must serialize `tool_choice: "none"`; no tool call is produced or executed.

This isolates what the model can answer or abstain from using the selected history. The previous `tool_choice=auto` live results remain a separate experiment and are not mixed into Track 1. Fixture responses prove request construction and execution only; they do not establish semantic recall accuracy.

## Track 2 — agent investigation

The offline path keeps the Assistant Runtime default (`tool_choice=auto`). Q06 is used as the local integration smoke for each strategy: the Mock Provider proposes the known read-only `list_scoped_protocol_documents` tool, and the application's local stdio Assistant MCP serves that request from the isolated test Domain. No remote/external MCP, search/fetch service or business action is called. Tool proposal and local tool observation are retained in the mock trace.

This smoke confirms the `auto` choice and the legal read-only call path. It does not score whether a real model would choose the right tool, and does not substitute for the seven-question live investigation track. In a later authorized run, preserve `auto`, record any proposed calls, and never execute an external MCP call unless separately permitted.

## Offline evidence

`test_offline_harness.py` performs 24 separate question/strategy/track runs: 21 Track 1 runs and 3 Q06 Track 2 runs. It persists the actual Domain Context Manifest and actual outbound Mock request payloads. The deterministic checks validate Grant binding, summary creation/no-summary behavior, configured and effective budgets, tool choice, source/schema digest consistency, Gold/scoring-rule separation and no cross-question answer contamination. Mock-generated natural-language answers are marked `NOT_SCORED_MOCK_OUTPUT`.

The only product-code compatibility addition is the optional `run_assistant(..., tool_choice_override=...)` argument for `none` or `auto`. The default remains unset, so normal Assistant Runtime requests keep the existing automatic tool choice. Compression behavior, Grant validation and provider dispatch are unchanged.
