# AR-02-REAL-JOURNEY-02 Report

**Status: `FAIL_STOPPED_AFTER_S02_4_CONTEXT_BUDGET`**
This is an incomplete real journey, not a PASS. The single frozen run stopped at S02-4. No turn was retried, S02-5 was not submitted, and no additional model request was made after the stop.

## What the user actually received

| Turn | Result | User-visible outcome |
| --- | --- | --- |
| S01 | `SUCCEEDED` | A direct model answer explained that HTTP 202 means accepted for processing, not processed. No business Task was bound, no current order/Event/Receiver state was claimed, and the model chose zero tools. It did make a broad comparison to 200/204 that should be read as a general synchronous convention, not a universal business-completion guarantee. |
| S02-1 | `SUCCEEDED` | The model called `search_project_knowledge` twice. It cited `receiver-ack-contract-v2` v2.1.0 and `callback-retry-contract-v2` v2.0.0, marked them as method-only references, and treated the user's E1/202 text as unverified. |
| S02-2 | `SUCCEEDED` | The model searched Knowledge twice again and explained the applicable v2 protocol: 202 proves durable acceptance into the receiver queue only; it does not prove processing. It correctly said the user-provided E1 example lacked a delivery version and was not current business evidence. The repeated searches were redundant. |
| S02-3 | `SUCCEEDED` | The trusted SUPPORT API returned HTTP 200 and registered/read-authorized `ar02-order` under service `orders-async-demo`, integration `async-integration-a`, principal `async-principal-a`, route `/api/async-orders/async-order`. The model then called Knowledge, Delivery, and Receiver tools. It saw the same actual Event and delivery version in the two business observations: Delivery `202/ACKNOWLEDGED`; Receiver `QUEUED`; acceptance time `2026-11-01T10:51:49.953668Z`; SLA 300 seconds; observation at about `10:53:15Z`, before the derived `10:56:49Z` deadline. Its answer said the delivery was accepted but processing was not yet proven complete, and the then-current direction was to continue observing. |
| S02-4 | `FAILED` | No Provider or MCP dispatch occurred. The formal Assistant returned a program-generated limit notice: `ContextBudgetExceeded: INVESTIGATOR_CONTEXT_EXCEEDS_BUDGET (12029 > 12000 tokens)`. This was not a model answer and did not re-query current facts. The runner stopped immediately. |
| S02-5 | `NOT_RUN` | No processing-note draft was produced. |

The S02 fixture was prepared in the new local test database through the existing fixture/HTTP path. The observations are genuine reads through the formal Assistant MCP/Domain path, but the underlying order/Event is isolated demo data, not a production order or external customer system.

## Run and source association

| Turn | Session | Task | User Message | Run |
| --- | --- | --- | --- | --- |
| S01 | `session-a6c584dc-4ce2-4614-b4cf-fbfcbc7d90c9` | — | `message-04ded2a4-cb4f-43eb-9c26-85c27e6300d6` | `run-c8dbbd8a-9ee3-43fd-9f41-c445b64f8bbe` |
| S02-1 | `session-d62af2b8-5401-4466-a33c-e842cc3c666c` | — | `message-fc1231ca-de7c-40fa-820a-5816ba024c41` | `run-2d3748e9-bac4-4e3c-accd-3f4302ba8da0` |
| S02-2 | same S02 Session | — | `message-f7dfccd9-0226-4ac1-95ea-788fe32ee5f4` | `run-30b9bc9f-ce11-4472-9c63-6e183d38dc82` |
| S02-3 | same S02 Session | `task-8d551cf3-686e-490e-96bf-84ced0cfa094` | `message-0ed788fb-ab62-4bdc-88fc-b78ca04a4f04` | `run-76fbaf0f-a98c-49ea-8af3-df14b6152674` |
| S02-4 | same S02 Session | same S02 Task | `message-1ec2f643-46bc-4dab-bc6a-e5dd0972fbe5` | `run-36c7d0a2-21d6-4de4-8429-04afa4e6ab13` |

## Real Provider and MCP evidence

- Formal path: FastAPI → one Worker → `ASSISTANT_V1` → `ChatOpenAI`/HTTPX → existing MCP/Domain.
- Provider: `deepseek-flash`; 7 actual HTTP POSTs and 7 HTTP 200 responses, each with validated Usage. Completion IDs, actual response model identifier, `system_fingerprint`, finish reason, Usage, request body and tool calls are in `PROVIDER_HTTP.jsonl`.
- Every request went to `https://api.deepseek.com/chat/completions`. The common fingerprint was `bc19ba97cbe016479903222bb1578db6`.
- Provider Usage total: 30,883 prompt tokens + 3,862 completion tokens = 34,745 tokens. Seven model dispatches settled to USD 0.013902 by the campaign's ceiling-rounded peak-rate calculation. This is the application ledger estimate, not the provider invoice.
- Campaign ledger: 7/16 Provider dispatches, 7/12 MCP attempts; USD 0.013902 settled, USD 0 reserved, USD 10.486098 remaining; status `OPEN`. All successful dispatches had known Usage. No retry or UNKNOWN result occurred.
- The model's actual MCP selections were: S02-1 two `search_project_knowledge` calls; S02-2 two `search_project_knowledge` calls; S02-3 one `search_project_knowledge`, one `get_callback_delivery`, and one `get_receiver_processing`. S01 used zero tools. All seven calls were actually dispatched and returned successfully.

The report does not equate the model's tool proposals with executions: request Tool Calls are captured in `PROVIDER_HTTP.jsonl`; executed MCP calls and returned observations are captured in `RESULTS.json` and `TRACE.jsonl`.

## Stop reason and safety outcome

The S02-4 context estimator reported 12,029 input tokens against a 12,000 configured limit (`tiktoken:cl100k_base:0.14.0`, fail-closed, no history compression). This limit notice occurred before any model request or MCP attempt, so it added no dispatch and no Usage. The existing runner's stop rule treated the failed Run as terminal; it did not restart the Worker or submit S02-5.

Final business write counters were all zero: `s3_diagnoses`, `d3_approvals`, `d3_action_intents`, `d3_action_ledgers`, `s3_handoff_queue`, and `s3_handoff_receipts`. The only trusted scope change was the requested API registration/authorization of the isolated demo order. No Repair, Approval, Deliver, ticket write, or external business write occurred.

The old `AR-02-REAL-JOURNEY-01` UNKNOWN reservation and all other historical experiment records were not opened by this runner; it used `.runtime/ar02-real-journey-02-20261101/domain.sqlite3` and `checkpoints.sqlite3`. `main` and the AR-03 branch were not changed. No browser automation was used.

## Evidence index and limits

- `PLAN.md`: frozen journey and budget.
- `PREFLIGHT.md`, `PREFLIGHT.json`: offline checks, checkout/model configuration, isolated initial ledger.
- `PREPARATION.json`: isolated fixture setup, separate from Agent evidence.
- `RESULTS.json`: per-turn Session/Task/Message/Run, persisted answers, MCP observations, ledger, and write counts.
- `TRACE.jsonl`: authenticated API/Worker journey events and turn associations.
- `PROVIDER_HTTP.jsonl`: seven real request/response pairs with secrets excluded.
- `runs/live.log`: original execution log and stop reason.
- `FAILURES.md`: retained offline REDs and this journey's stopping failure.

Browser experience is `NOT_RUN` as explicitly required. The run did not complete S02-4 or S02-5, so no sourced processing-note draft exists. This experiment therefore provides real model and read-only investigation evidence, but does not satisfy the full frozen S01/S02 user journey.

## North Star review summary

- **User change:** the user received a correct protocol explanation, two sourced protocol answers, and a current same-Event `202/QUEUED` interpretation; the final draft was not delivered.
- **Agent decision:** the real model directly answered S01, selected Knowledge searches, then selected Knowledge plus the two current read tools after binding.
- **Observation-driven:** actual same-Event delivery/receiver observations supported “accepted, still queued, not proven complete”; no action was taken from the untrusted E1 example.
- **New constraint:** the existing 12,000-token context ceiling prevented an over-budget model request; legal continuation in the same Session was not preserved at S02-4. The constraint prevented an over-limit send but also blocked the frozen user goal.
- **Simplification:** no new runtime or decision workflow was introduced; only the experiment ID was added to the existing budget allowlist/schema.
- **Evidence and stop:** one real run, 7 known-Usage Provider requests, 7 successful MCP calls, S02-4 context-limit failure, S02-5 not run. No PASS or main merge is claimed.
