# Follow-up experiment discussion — MAT-05 and MAT-06

This is a planning suggestion only. No budget constant was changed and no paid request was made.

## What the real trace says

The completed conditions used 10 MCP calls: MAT-01 used 2, MAT-02 used 0, MAT-03 used 2, and MAT-04 used 6. MAT-04's six calls were all successful and materially different: three distinct current business facts (delivery, receiver, transport history), one scoped document discovery, and two reads of different protocol documents. There was no repeated same-tool call in that Run. The MCP counter reached 10/10, while Provider usage was 9/16. The recorded campaign stop was the Runner's audit `KeyError`, not a model-request failure; the exhausted MCP allowance independently meant no further MCP call was available.

The trace therefore does not support treating 10 MCP calls as a generous campaign allowance for a research task, nor does it support blocking repeated tool names categorically. A tool count alone cannot distinguish useful evidence discovery from an unproductive repetition.

## Suggested budget discussion

- Keep authorization, total application spend, wall-clock duration, context size, and no-retry behavior as hard safety boundaries.
- Do not carry a low, per-Run MCP ceiling into the next experiment by default. Prefer to instrument and charge every actual MCP attempt to the experiment's shared durable ledger while letting the model continue within the authorized task and financial/time envelope.
- If a finite call-count ceiling is required by the execution substrate, derive it from the remaining frozen work plus slack. As a discussion estimate, MAT-05 may consume a similar 2–6 calls to MAT-04, and MAT-06 OFF/ON may consume 0–3 calls per condition depending on whether the model chooses to load the Skill and whether additional sources are useful. That implies roughly 4–12 further calls, or 14–22 cumulatively from the observed 10. Treat this range as a planning estimate, not a recommended hard cap; pre-authorize a comfortably higher contingency or use spend/time limits with an operational alert instead of stopping at the estimate.
- Preserve per-call audit fields: Case/Run, tool, sanitized arguments, attempt status, observation/evidence IDs, digest/version, and whether the call added new authoritative evidence. Use these fields after the run to discuss efficiency; do not make “new evidence every call” a runtime gate.
- When the agent has no safe next action or relevant source, let it stop/clarify. A context, authorization, money, or time boundary should still stop it explicitly and report the actual reason.

Before any later paid run, freeze its independent identity, cases, expense envelope and stop behavior with the reviewer. This proposal does not resume or reuse RESUME-02's consumed claim.
