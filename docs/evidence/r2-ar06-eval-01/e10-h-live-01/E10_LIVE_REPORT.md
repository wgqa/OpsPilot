# E10-H First Live Run Report

- **Status:** `ACCEPTANCE_CANDIDATE`; executor evidence only, independent M1-M6 scoring pending.
- **Frozen score ceiling:** `PARTIAL` under the existing E10 contract.
- **Base / execution HEAD:** `d9913167b611f1c4f319238f368f334db7fb4814`.
- **Branch / Runtime:** `codex/r2-ar06-e10-h-readiness-01` / `user-demo-r2-e10h-readiness-02`.
- **Run:** `run-e6cc2bf6-fda6-4348-9870-5f95028571f8` (`SUCCEEDED`), one prompt submission, no retry.
- **Session / Task:** `session-7899ecb6-1ca8-486a-bbc5-5d47a3e4a75c` / `task-a69bfb83-d3d8-4457-9f2b-50afb78dfc58`.
- **Frozen input SHA-256:** `117780889e83ce54db5f98ebd2925a476b26196ed00e53790a5f61af03538d1f`.

## Outcome

The real model selected Memory A as non-authoritative project method guidance. It excluded Memory B (revoked version 2) and C (source digest invalid). B/C bodies were absent from actual Provider inputs; their IDs and machine-readable exclusion reasons were present as provenance metadata. These are project Semantic Memories, not Personal Memory.

The model made three read-only MCP calls and obtained three current observations linked to the same tenant, task and run. The order observation reports `COMPLETED` but has no callback `event_id`; `authn_event_id=1` is not a callback Event ID. Delivery and Receiver report the same target Event `event-00000000-0000-4000-8000-000000000001`: Delivery `ACKNOWLEDGED / HTTP 202`, Receiver `QUEUED`. At observation time the receiver had been queued for 16,557 seconds, exceeding the 300-second SLA by 16,257 seconds. No business write was made.

The final answer correctly distinguishes order completion from callback processing and reports the Receiver as queued/overdue. It also says “I have no record in this session of any revocation of that memory,” instead of explicitly explaining that B was excluded. This wording is retained for independent scoring; no PASS is assigned here.

## Provider and cost

- Real Provider dispatches: **2**; responses: `1b2fefc8-7ac4-46ae-ae36-d7d1a3ea7f7e, ee6a9c78-7d1d-4524-b829-2ffbab6c147c`.
- Usage: **8,735 input + 976 output = 9,711 tokens**.
- Application ledger settlement: **USD 0.003793**; UNKNOWN: **0**; retry: **0**.
- MCP / Observation / Evidence: **3 / 3 / 3**.
- Grant: USD 0.05, remaining USD 0.046207, expiry `2026-11-16T13:12:28Z`. Services were gracefully stopped; do not use the remaining Grant.
- Current DeepSeek Flash V4.1 peak cache-miss input price USD 0.30/M and output USD 1.20/M were checked against the [official pricing page](https://api-docs.deepseek.com/quick_start/pricing/). At 12,000 input / 2,048 output per request, the eight-dispatch worst-case reservation is USD 0.048464. Application settlement is not the supplier invoice.

## Final persisted Assistant answer

```text
Here's what this session's fresh observations show for the bound order `async-order` (service `orders-async-demo`, tenant-a), all read at 2026-11-16T11:38:01Z:

**Order level** (`get_order_status`, HTTP 200)
- `order_id`: async-order, `order_version`: 2, `status`: **COMPLETED**
- `authn_event_id`: 1 — note this is an authentication event identifier, not a callback business Event ID, so it can't be used to correlate with the Delivery/Receiver rows.

**Delivery** (`get_callback_delivery`, delivery_version 2)
- `event_id`: `event-00000000-0000-4000-8000-000000000001`
- `status`: ACKNOWLEDGED, `receiver_http_status`: 202, `attempt_count`: 0, `max_attempts`: 3, `retry_state`: NOT_APPLICABLE, `failure_code`: null
- The embedded transport response records `receiver_state: QUEUED` at acceptance time 2026-11-16T07:02:04.832095Z.

**Receiver** (`get_receiver_processing`, receiver_version 2)
- `event_id`: `event-00000000-0000-4000-8000-000000000001` — **matches** the Delivery's event_id, so these two observations do refer to the same Event.
- `status`: **QUEUED**, `accepted_at`: 2026-11-16T07:02:04.832095Z, `processing_sla_seconds`: 300
- SLA assessment: **OVERDUE** — deadline 2026-11-16T07:07:04.832095Z, elapsed ~16,557 s (≈4.6 h) at observation time.

**Interpretation**
- The callback was accepted at the transport layer (HTTP 202 / ACKNOWLEDGED), but that is transport acceptance only — it does not confirm business processing.
- The Receiver for this same Event is still QUEUED and has exceeded its 300-second processing SLA. So processing is **not confirmed**, and it is overdue.
- There is no Delivery failure and no exhausted retry (`attempt_count` 0, `retry_state` NOT_APPLICABLE), so this is not a "transport failed / retries exhausted" case — it's a stuck/queued receiver case.
- The order-level status COMPLETED comes from the order service's own record; it is a separate order-level field and does not by itself prove the callback Event was processed by the receiver.

**On the cross-session memory guidance**
The stored project-context note (check current Receiver for the trusted binding, correlate with Delivery for the same Event, treat HTTP 202 as transport acceptance only) is consistent with what I observed this run, so I used it only as a method hint — the conclusions above rest on this run's observations. I have no record in this session of any revocation of that memory, so I'm not treating it as revoked; if you know it has been revoked, tell me and I'll disregard it going forward.

**Suggested next steps (not performed — no action has been taken)**
- Escalate to the receiver/consumer team for `orders-async-demo` about Event `event-00000000-0000-4000-8000-000000000001` remaining QUEUED past SLA.
- If you want, I can pull the transport history for this Event to see the recorded attempts, or draft a handoff note. Any actual re-send, retry, or ticket creation would have to go through the normal domain process — I can't initiate it here.
```

## Evidence

`E10_LIVE_TRACE.json` contains actual persisted model requests and responses, tool calls, observations, evidence, context manifests, spend rows and the final chat answer. `E10_EVIDENCE_INDEX.json` records artifact and retained Runtime hashes. No production code, Gold, Rubric, business state or historical readiness evidence was modified by this execution.
