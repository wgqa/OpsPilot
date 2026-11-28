# Failure Analysis

## Stop cause

The stop happened before the first Provider request. After loading the normal local environment source, `OPSPILOT_MODEL_API_KEY` was absent; the worktree had no `.env`, and the model ID, endpoint, model-config version, price version, and Assistant service identity were also absent. Without the local credential and matching runtime identity, no isolated live Runtime Grant could be bound and validated. The task card explicitly requires `BLOCKED_BEFORE_PROVIDER_SEND` in that state. No key was requested or exposed.

No live temporary Grant was created, no runtime database was opened, and no dispatch was attempted. This is a missing local prerequisite, not a denial emitted by the Runtime Grant implementation and not a provider/model failure.

## What this does and does not show

- It does not show whether a real HYBRID or ROLLING_SUMMARY model call would preserve `/callback`, `req-483`, or `v1.2 → v1.3`.
- It does not show whether RECENT_WINDOW can answer those questions from its selected raw messages.
- It does not provide live Summary JSON, final prompt evidence, Provider Usage, L2 availability, or L3 answer quality.
- It does not demonstrate information loss, model misunderstanding, or a production compression defect.
- Historical Setup-HF01 Fixture/Mock summaries show the Assistant path and context manifests can be constructed; those fixture results are not a substitute for real summaries or answers.

## Schema drift found during preflight

The Phase A tool digest (`f6c75eaa…`) and current Assistant Runtime digest (`555cd385…`) differ because actual JSON Schema fields differ, not only because of encoding. The tool set and names are the same. Current A/B/C Mock payloads for Q02/Q03/Q06 have equal current schema digests, equal trusted system-prompt-prefix digests, and `tool_choice=none`. Thus no within-group mismatch was found. The historical-to-current schema change remains a comparability limitation, especially the omitted `additionalProperties:false` in the memory tool schema; no production tool definition was altered to chase the older digest.

## Preserved prior live evidence

The previous `R2-AR04-LIVE-SEMANTIC-PILOT-01` remains separate and unchanged: its three D reference requests included correct supported Q02, Q03 with a false source-location claim, and an unexpected Q06 `list_scoped_protocol_documents` tool call that stopped that run. Those outcomes do not count toward this nine-slot A/B/C experiment and do not remove this task's zero-send stop.

## Failure category and next trigger

This is an **environmental execution block**. Reopen a separately authorized live run only after a credential is available through the approved local secret mechanism and the model, endpoint, price/config versions, and service identity can be verified. Do not paste a key into chat, check it into Git, reuse prior D responses, or treat this record as an A/B/C result.
