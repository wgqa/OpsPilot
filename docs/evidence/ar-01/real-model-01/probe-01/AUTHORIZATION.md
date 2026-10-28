# PROBE-01 execution authorization

Direct current user instruction, 2026-10-28: AUTHORIZED_FOR_ONE_PROBE.
Approved source `6c61a5cc5f19800b10d10bb50e23a2dfce49f243`, branch codex/ar01-free-agent.
This document records the authorization; it is not approval for any subsequent run.

Exactly one DeepSeek Flash POST, non-thinking, max_tokens 512, original six schemas,
no MCP execution, no retries, 30s. REQUEST_WIRE_V1 reserve USD 0.315188, cap USD 0.50.
Provider contract violation may exceed the reserve/cap on the already-sent request.
Failure, unknown result or incompatibility stops; no parameter repair/retry.
P1/P2, main merge, browser and production changes remain unauthorized.

Frozen body blob `71854592cc914d080fc2a61053818defdbeb2c86`;
semantic digest `e9f088776d73e414238fc393c9d06659fa029280c064bac4c2d2361955521f8f`.
Current official prices rechecked: peak no-cache input 0.30 USD/M, output 1.20 USD/M.
No key, Authorization or Cookie is retained in evidence.

Skill A/B preflight: same approved HEAD, tracked tree clean; main ec8c358 unchanged.
North Star / AGENTS / Skill actual read blobs: 1f737712c7a36ceb34433ac09c3fbba3c3305542 /
32c45506cceeaa8c76a5c56bf8360ff476b58856 / d405c8d413d633824b279202cc1503dab4cf0b03.
User change: obtain one actual protocol observation. Agent decision: one response
or tool proposal only, no tool loop. Observation-driven comparison: not evaluated.
Constraints: preserve frozen body, one request and durable unknown exposure.
Simplicity: use existing authorized-probe adapter/ledger, no production changes.
Evidence/stop: record actual HTTP/Usage/IDs/failure, commit branch, then stop.
