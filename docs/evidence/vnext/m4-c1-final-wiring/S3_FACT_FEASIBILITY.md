# S3 Transport Attempt History — Read-Only Feasibility

## Finding

**Not currently supported as durable business history.** The existing S3 tables hold one current row per order: `s3_orders`, `s3_deliveries`, and `s3_receivers` use an order-scoped primary key (`opspilot/domain/s3.py:61-79`). The delivery row has an `event_id`, one `transport_request_id`, one HTTP status, an attempt counter, and one response JSON/digest. It cannot enumerate the individual requests or responses counted by `attempt_count`.

`prepare_s3_fixture()` creates one Event and one Transport Request ID, performs at most one real local receiver POST, and returns its `transport_trace` in the function result. The trace is not persisted. The fixture then uses `INSERT OR REPLACE` for all three order snapshots, so a later preparation replaces the current Event and response (`opspilot/domain/s3.py:305-408`). This is test setup, not an Agent tool or a production retry path.

The HTTP request history that does exist is different: `s3_http_observations` records authenticated order `GET` responses with request ID, authn event, status, body digest, and timestamp (`opspilot/domain/s3.py:81-89,411-423`). It does not record outbound callback `POST` attempts. MCP exposes current order, delivery, and receiver reads; it has no transport-attempt history query (`opspilot/domain/s3_mcp.py:39-56`). D2 attempts and tool observations record the Agent's MCP calls and their Run association, not the downstream callback transport itself (`opspilot/domain/database.py:343-422`).

## What can and cannot be answered

| Sample | Needed facts | Current ability |
|---|---|---|
| Same Event retry: Event `evt-842`, attempt 1 uses request `tr-001` and receives HTTP 503; attempt 2 reuses `evt-842`, uses `tr-002`, and receives HTTP 202. | Both request IDs, both responses, attempt order, timestamps, and source. | The current delivery snapshot could retain the latest `evt-842` / `tr-002` / 202 and `attempt_count=2`; it cannot prove the earlier 503 or its time/request ID. |
| Different Event: `evt-842` receives 503, then a new Event `evt-843` receives 202. | Whether the second send was a retry of the same Event or a new callback Event. | The latest snapshot shows only `evt-843` and its latest transport fields. The prior Event is overwritten by fixture preparation; the current API cannot distinguish the histories. |
| Historical question: “Did the receiver return 503 for the previous Event?” | The old Event and that attempt's response. | **Unknown from current business history.** A current 202 snapshot or an Agent's later MCP observation does not establish the older response. |

These are schema-backed examples of the distinction the next slice must test; the IDs and responses above are illustrative, not claimed production observations.

## Smallest missing responsibility

Add one append-only S3 transport-attempt fact record for each actual callback HTTP attempt, while retaining the existing delivery row as the current projection. Each record needs enough immutable correlation to identify tenant/service/order, stable Event ID, unique Transport Request ID, attempt sequence, request/response time, HTTP response or transport error, response digest/body, and the trusted source of the send. Retries of one Event must retain its Event ID and receive distinct transport request IDs. A new Event must have its own attempt sequence. No diagnosis or handoff authority needs to move into this history store.

After that business scope is approved, expose a bounded read-only MCP query that resolves the Task's immutable binding and current S3 authorization in Domain, then returns attempts only for that bound order (optionally one validated Event ID). The existing Domain Gate remains responsible for current diagnosis; the history is supporting evidence only. An unavailable or incomplete history must be reported as a gap, never inferred from the snapshot. This task does **not** implement the table, MCP query, or Gate changes.
