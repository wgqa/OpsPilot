# E11-D Live Runbook and gate

## Status: NOT_READY_FOR_LIVE

This task is OFFLINE ONLY. Do not create a Runtime Grant or start a paid Provider Run from this runbook.

Current blocker: the Worker CHAT_READONLY path and Professional Investigator path call `require_legacy_provider_authorization()` and `ChatOpenAI`. `opspilot/config.py` documents that these legacy paths predate Runtime Grant; the Investigator does not inherit Assistant V1 Runtime Grant. The test enables both legacy opt-in variables only with an offline monkeypatched Fixture. There is no demonstrated durable RuntimeGrant/Spend enforcement for this E11 Investigator path. Enabling legacy switches would bypass the intended cost gate and is not authorized.

Before any future Live proposal, a separate owner must establish a supported persistent Grant/Spend path for both relevant model paths, then independently validate request counts, budget pre-reservation, UNKNOWN behavior, and stop behavior. Until that review and explicit user authorization, real provider requests remain 0.

No grant command, live start command, or message submission is provided here because the path is not safely executable under the current contract. Offline evidence: `E11_ASSISTANT_AND_TASK_TRACE.json`, `E11_NEGATIVE_BOUNDARY_RESULT.json`, and source references in the readiness report.
