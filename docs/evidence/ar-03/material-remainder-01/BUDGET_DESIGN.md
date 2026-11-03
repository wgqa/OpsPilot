# Budget design and capacity rationale

## Effective gates inspected

| Layer | Before this slice | New remainder experiment only | Other identities |
|---|---|---|---|
| Campaign ledger | 16 Provider / 10 MCP for the prior material campaign; $10.50; $0.645600 Provider reserve | 16 Provider / no MCP count ceiling; same persisted counters, spend cap and UNKNOWN stop | Unchanged |
| Assistant Run ledger | 8 MODEL / 6 MCP ordinarily; 16/10 for prior material IDs | 16 MODEL / no MCP count ceiling | Ordinary 8/6 and prior 16/10 unchanged |
| Task/D2 | Existing LEGACY 8/6 or versioned CONTUX policy | Version `AR03_MATERIAL_REMAINDER_01_V1`: 16 MODEL / no MCP count ceiling, only on an untouched `orders-async-demo` bound Task in the matching open campaign | No global Task migration or default change |
| Time / graph | Provider request 30s; MCP handler 12s; Assistant Run max 60s; Task active deadline 300,000ms where applicable; recursion limit 36; max graph concurrency 1 | Preserved | Preserved |

The Task table historically has a NOT NULL `mcp_limit`. To avoid schema migration, the new policy stores `0` only as a version-scoped sentinel and maps it to `None` in trusted Python budget projections. All other policy versions continue to require their existing positive fixed limits. Campaign and Run ledgers store `NULL` for this new identity's MCP count limit. No ordinary Task receives this policy through an API; configuration is an internal trusted setup operation, checks the exact experiment ID, matching open campaign row, bound service, tenant, and absence of prior attempts/active time.

## Why remove the low MCP count gate

The saved RESUME-02 trace used all 10 campaign MCP attempts by MAT-04. Each call was a distinct successful read: target Event Delivery, target Event Receiver, scoped protocol discovery, two versioned excerpts, and transport history. The first response proposed three calls and the next response proposed three more, despite `parallel_tool_calls=false`; therefore a “one tool per Provider response” estimate is unsupported. The prior run ended with an audit defect, so those ten calls do not establish that a complete user goal necessarily needs ten, but they do show why an arbitrary smaller cap would truncate plausible work.

This slice retains durable MCP attempt/dispatch records and removes only the low **count-based** stop for the isolated new experiment. It does not reject a call because its tool name repeated or because an earlier call produced no new Evidence. In the local capacity probe, 11 repeated same-Event reads completed: all 11 calls, Attempts and Observations were recorded; they reused one Evidence ID and only the first added progress. That is capacity evidence, not evidence that repeating reads improves answers.

## Hard stops kept

- Shared experiment DB: max 16 Provider reservations; each pre-reserves 645,600 micro-USD. Sixteen reserves total 10,329,600 micro-USD, below the 10,500,000 micro-USD application cap. A 17th reserve is refused before dispatch.
- The independent fee check refuses a reserve that would cross the persisted application cap.
- Missing/invalid Usage or UNKNOWN dispatch closes the campaign to subsequent requests; the UNKNOWN reserve remains held.
- Each Run remains limited by 60 seconds, the Task active-time deadline remains 300 seconds, each Provider call remains 30 seconds, each MCP handler remains 12 seconds, and LangGraph keeps recursion limit 36. Retries remain disabled by the existing Provider configuration.
- Domain authorization, source-currentness, TaskBinding, same-Event correlation and read-only tools are unchanged.

No separate campaign timer was added to the Domain ledger. The next one-shot launcher must continue to enforce the existing campaign wall-clock contract (36,000 seconds) across all three conditions, with one shared Domain/campaign ledger and no retry. The durable Task clock, per-Run deadline and campaign runner deadline are different bounds; they must not be conflated.

## Remaining risks

- No real LLM was used, so the slice does not show whether a model will stop after redundant calls or how many MCP reads the user task needs.
- `parallel_tool_calls=false` is sent, but this local test does not establish how a live Provider behaves if it returns several calls in one response.
- The existing 36-step LangGraph recursion guard remains a finite graph-execution bound; this slice does not tune it.
- The fixed cost reserve is inherited from the prior freeze and must be revalidated against official price/model parameters before any new paid authorization is exercised.
