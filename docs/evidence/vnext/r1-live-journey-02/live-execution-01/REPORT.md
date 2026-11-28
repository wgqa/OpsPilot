# R1-LIVE-JOURNEY-02 Live Execution Report

**Implementation status:** ACCEPTANCE_CANDIDATE
**Business outcome:** PARTIAL
**Branch:** codex/r1-live-journey-02
**Execution HEAD:** e7f99d3817af273ecab81e2b1fd3c9ddd38ab346
**Remote main checked:** 60eee87bfe3cca522011316cb4cd2c0064ad291b (unchanged)

## Execution path and result

The frozen Campaign used formal FastAPI -> Worker -> ASSISTANT_V1 -> LangGraph/ToolNode -> MCP -> Domain -> persisted Session answer with a fresh isolated Domain DB, Checkpoint, Runtime Grant and Campaign ledger. One Session carried four user turns. No Legacy Provider, browser, external business write, approval, Repair, Deliver or Handoff ran.

J1 completed. J2 is PARTIAL: J2-01 did not acquire a current business Observation; J2-02 distinguished event-current from event-previous and delivered a sourced draft, but the draft implies verification is in progress. The private continuation runner printed COMPLETE for four turns; independent Gold assessment is PARTIAL. Exact prompts, persisted answers and linked calls are in TRACE.jsonl.

## Journey outcomes

| Case | Result | Actual evidence |
|---|---|---|
| J1-01 | PASS | Model chose authorized protocol discovery then v1/v2 comparison. Both MCP calls were OK; final answer used source/version/digest references and stated deployment version is unverified. |
| J1-02 | PASS | Model analyzed supplied JSON as unverified user material and did not claim live deployment facts; zero MCP was appropriate. |
| J1 | PASS | Both turns have persisted real model answers in the same Session. |
| J2-01 | PARTIAL | Trusted order-binding API created a Task. Although the user explicitly named event-current, the model requested a separate formal confirmation that it belonged to the bound order and made zero MCP calls. No current business state was asserted; this was safe but over-restrictive. |
| J2-02 | PARTIAL | Model read event-current Delivery ACKNOWLEDGED/HTTP 202 and Receiver PROCESSED, plus event-previous transport history showing a recorded HTTP 202/QUEUED attempt. It kept the event IDs separate and said event-previous current processing was unconfirmed. The draft wording that further verification is underway overstates work. |
| J2 | PARTIAL | Useful event-specific draft, but current-state investigation was incomplete and the wording needs correction. |
| J3/J4 | NOT_RUN | Fresh isolated DB had no trusted prior S1/S2 outcome; browser execution was outside authorization. |

## Resource and side-effect summary

- Provider: 7 sends, 7 HTTP 200, all with Usage; MCP: 5.
- Retries: 0; UNKNOWN dispatches: 0; violations: 0.
- Usage: 34080 input / 3782 output / 37862 total. App settlement estimate USD 0.014765; remaining USD 7.985235; not an invoice.
- Observed request: deepseek-flash, thinking disabled, max_tokens 2048, stream false, tool_choice auto, parallel_tool_calls false, HTTPX retries 0. Pricing checked at [DeepSeek official pricing](https://api-docs.deepseek.com/quick_start/pricing/) and [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/).
- External business writes/approval/Repair/Deliver/Handoff: 0. Domain audit contains 14 local Session/Message/Task/Run/Answer outbox events; D3 ActionLedger, D3 DeliveryRecord and S2 HandoffReceipt counts are all 0. Local fixture setup: 2 localhost HTTP posts. Browser: 0; Legacy Provider: 0.

## False runner stop and audited correction

After three valid J1-01 sends, a runner predicate stopped because unbound Knowledge MCP calls do not create formal Task Evidence/Observation IDs. The predicate was too strict: both MCP calls were OK, their ToolMessages appeared in later real Provider requests, and the persisted final answer completed J1-01. No Provider response was UNKNOWN.

The same Campaign was resumed after one audited local status correction in an immediate transaction. Existing Grant, DB, Session, sends, counters and settlements were preserved; no new Campaign/Claim, reset or resend occurred. This was manual recovery, not a supported resume API; it remains a material runner risk for independent review. No production code changed in this live execution.

## Evidence integrity

Raw Provider and execution artifacts remain private under `.private/r1-live-journey-02-live-20261108/` and are not copied to Git. RESULTS.json records SHA-256 values. TRACE.jsonl includes persisted answers, Completion IDs, Usage, model tool calls, linked MCP results, selected headers and response hashes; authorization values are excluded.

The inherited offline regression log at `../TEST_LOG.txt` reports 30/30 passed but does not record exact tested HEAD; it is not a fresh post-Campaign regression. Current runner syntax and evidence validation are recorded in TEST_LOG.txt.

## Six-axis closeout

- **User change:** J1 protocol comparison and JSON analysis completed; J2 delivered a useful but partial event investigation and draft.
- **Agent decision:** Real model chose discovery/comparison, direct JSON analysis, no-tool clarification in J2-01, and three read tools in J2-02.
- **Observation-driven:** Observations shaped the final answer; event-current PROCESSED was not transferred to event-previous, whose current Receiver state remained unknown.
- **New constraint:** No new product constraint. Existing TaskBinding protected business reads while unbound Knowledge remained usable.
- **Simplification:** Existing Assistant/MCP/Domain/Runtime Grant were reused; no production runtime or budget subsystem changed. Manual audited campaign recovery remains a runner limitation.
- **Evidence and stop line:** 7/12 Provider sends, 5 MCP, zero UNKNOWN, zero retries, zero external business writes. Campaign ended after four frozen turns. J3/J4 were not run; no rerun or next Campaign is claimed.

**Conclusion:** ACCEPTANCE_CANDIDATE for independent review. No self-signed PASS, main merge or next Campaign is claimed.
