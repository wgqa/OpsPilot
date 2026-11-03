# AR-03-MATERIAL-LIVE-01 technical debt ledger

This list tracks follow-up work only. No item authorizes expansion in the current slice.

| Item | Current impact | Trigger for follow-up | Scope deferred |
|---|---|---|---|
| Fixed per-Run and per-experiment caps | The campaign has hard 16 Provider / 10 MCP limits, with 16/10 per-Run limits only for this experiment ID. This is a safety envelope, not adaptive allocation. | A completed trace shows a legitimate task stopped only because the per-Run allocation was exhausted while aggregate budget remained. | Do not build a generic budget service or change this experiment's frozen limits. |
| Repeated MCP reads | Repeated legal reads can consume scarce campaign attempts and reduce remaining case coverage. No measured live frequency is claimed yet. | The real trace contains duplicate or low-information calls, assessed against the user's goal and returned observations. | Record as strategy cost; do not add a fixed tool sequence or hard ban. |
| Budget-exhaustion partial delivery | The runtime must not turn unexecuted tool requests into successful observations or invent a final answer. A useful deterministic partial summary may not be available for every stop reason. | A legal case reaches a cap with valid current evidence that could safely be summarized, or an existing stop leaves the user without a clear reason. | No new workflow/platform in this slice; report actual behavior and unknowns. |
| P2/P3 non-blocking issues | Track only issues that do not permit unauthorized reads/writes or false current facts. | A repeatable product impact is demonstrated in a preserved trace or test. | Do not repair unrelated issues during the paid run. |
