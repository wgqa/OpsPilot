# AR-03-REAL-LLM-01 Preparation Report

**Status:** `READY_FOR_LIVE_AUTHORIZATION` — local offline preparation candidate only; not a live-call authorization.

## User journey frozen

The two frozen cases use the same request: “我们最近升级了回调协议，客户反馈重试行为和以前不一样。请查一下有权限访问的旧版、新版协议，分析具体变化，再结合这个订单的回调情况判断影响，最后整理一份处理说明草稿。不能确认的地方请明确告诉我。”

Both cases use an isolated trusted binding for `ar02-order`, the same target Event, same protocol documents and `HTTP 202 / ACKNOWLEDGED`. The current same-Event Receiver state is the paired variable:

- `QUEUED`: report transport acceptance, say business processing is not confirmed, and suggest a reasonable next check.
- `PROCESSED`: may confirm only this Event was processed.

In both cases, protocol documents do not prove deployment, other Events cannot prove this Event, and the support note must be explicitly unsubmitted. The model is not required to use a fixed tool order or call every tool.

## What was prepared and verified

The formal FastAPI → Worker → `ASSISTANT_V1` path was exercised once with `ChatOpenAI` backed exclusively by explicit HTTPX `MockTransport`. The serialized request reached the mock at the official-style `/v1/chat/completions` URL, used the frozen model and wire fields, included the authorized protocol tools, excluded business tools without TaskBinding, and stayed inside the current 12,000-token estimate. The deterministic answer was persisted against its original user Message. The temporary experiment ledger recorded one synthetic dispatch and synthetic Usage; it did not touch any old experiment database or ledger.

The existing formal Worker/MCP integration regression exercised two isolated cases using the same order and fixed Event ID. Each investigation run executed five MCP calls: protocol discovery, protocol comparison, order, delivery and receiver. The stored business observations included same-Event delivery HTTP 202/ACKNOWLEDGED and Receiver QUEUED or PROCESSED. The answers differed accordingly. The model used in this regression is a deterministic fixture whose tool choices are scripted by test code; this proves route/Domain wiring, not real LLM autonomy.

The fixture POST and TaskBinding are confined to temporary test databases and a local loopback receiver. No diagnosis, approval, action permission, action intent/ledger, handoff receipt, external ticket, or production business write was created. No real Provider or browser was used. The AR-02-REAL-JOURNEY-03 S02-4 `PARTIAL` report remains untouched.

## Minimal code change

The existing isolated Assistant experiment ledger previously allowlisted only AR-02 IDs. This slice adds `AR-03-REAL-LLM-01` to its Python allowlist and new-database SQLite CHECK constraint. No budget limit, retry behavior, provider factory, Assistant loop, MCP interface, Gate, or business permission was changed. An older database schema rejects the new ID fail-closed; there is no automatic table rebuild or migration. Existing experiment rows remain separate by primary key and experiment ID.

The paired regression fixture now gives both isolated cases the same Event and Transport Request IDs during setup. This resolves a trace-detected test parity gap without changing any frozen user text or Gold.

## Evidence and results

- Frozen criteria were committed first: `6f9074e84c185553cfeab0f225e81640b8b525f0`.
- Offline implementation/tests were committed second: `1f557ecd124a6ae9ac1ff9ccdba1dad0b4cc9284`.
- New preparation tests: 4 passed.
- Protocol discovery/comparison and formal Worker regression: 50 passed.
- Provider factory, budget, scope, previous journey prep and Knowledge regression: 42 passed.
- Same-event QUEUED/PROCESSED rerun after fixture alignment: 2 passed.
- Python compile check: exit 0.
- Full `pytest`: not run.
- Real DeepSeek requests: 0. MockTransport requests: 1.
- Isolated candidate branch push: succeeded at `ead1fc8d9fadeb70e8ff5ff29d9dc822ae3ea18c`. A subsequent read-only check of remote `main` failed to connect to GitHub port 443; current `main` SHA is `UNVERIFIED`. No main update was attempted.

The initial valid RED had 3 failures and 1 pass because the new experiment ID was absent from the allowlist/schema. It passed after the minimal ID wiring. A first test invocation also used a nonexistent worktree-local Python path and did not start pytest. Both records are preserved in `FAILURES.md` and `runs/`.

## Live authorization gates still open

This report does not assert model quality, successful autonomous tool selection, cost, or a completed user journey. Before any paid run, the Main Agent and user must separately authorize it; current official price and request compatibility must be rechecked; and the isolated run database/checkpoint/ledger and stop conditions must be confirmed. No provider switch was enabled outside the test process.

The proposed cap remains 16 Provider requests, 12 MCP calls, USD 10.50 app budget, USD 0.645600 reservation/request, zero retries, one in-flight request, 30-second timeout and 12,000 input tokens. The dated cost basis was not revalidated in this offline task.

## North Star six questions

1. **User change:** No live user capability was added. The preparation now has a frozen paired journey and verified offline product route ready for separately authorized testing.
2. **Agent decision:** Real model decisions were not tested. The deterministic pair verifies that the existing Assistant can expose legal choices and persist local outcomes.
3. **Observation-driven:** The fixed Event’s QUEUED versus PROCESSED observation changes the deterministic answer from “not confirmed complete” to “this Event processed”; a real model response remains unverified.
4. **Constraints:** The new ID is isolated in the existing experiment allowlist/schema; provider remains default-off and key presence alone does not enable it. Fresh and stale schema tests verify new use and fail-closed legacy behavior.
5. **Simplification:** The existing budget ledger, formal Assistant, Worker and MCP are reused. No new runtime, loop, guard or budget service was added.
6. **Evidence and stop:** Freeze, RED/GREEN logs, local MockTransport request, local MCP/HTTP traces and selected regressions are available. Real provider, browser, full pytest, live pricing and remote push are unverified. Stop here pending Main Agent review and separate live authorization.
