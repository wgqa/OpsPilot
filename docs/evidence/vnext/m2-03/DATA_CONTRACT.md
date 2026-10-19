# M2-03 SQLite 数据与原子提交合同（冻结）

基线 Domain `PRAGMA user_version=7`。增量实现目标 `user_version=8`；不得删除现存业务事实，初始化和迁移需可重复、安全升级旧 S1/S2 文件，并有迁移前后回归。

## 新增业务表（逻辑 DDL）

字段类型与唯一性在冻结后不得弱化；可补充索引或等价 FK 以符合实际 schema 风格。

```sql
CREATE TABLE s2_handoff_queue_entries (
  entry_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  task_id TEXT NOT NULL,
  handoff_kind TEXT NOT NULL CHECK (handoff_kind = 'SCOPE_REVIEW'),
  receiver_queue_id TEXT NOT NULL,       -- server-fixed local queue only
  receiver_identity_ref TEXT NOT NULL,   -- fixed local demo receiver reference
  draft_id TEXT NOT NULL,
  draft_version INTEGER NOT NULL CHECK (draft_version > 0),
  draft_digest TEXT NOT NULL,
  received_at TEXT NOT NULL,
  review_due_at TEXT NOT NULL,
  queue_status TEXT NOT NULL CHECK (queue_status IN ('PENDING_REVIEW', 'REVIEWED')),
  UNIQUE (tenant_id, task_id, handoff_kind),
  UNIQUE (entry_id, tenant_id, task_id),
  FOREIGN KEY (task_id, tenant_id) REFERENCES task_bindings(task_id, tenant_id),
  FOREIGN KEY (draft_id) REFERENCES s2_handoff_drafts(draft_id)
);

CREATE TABLE s2_handoff_receipts (
  receipt_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  task_id TEXT NOT NULL,
  handoff_kind TEXT NOT NULL CHECK (handoff_kind = 'SCOPE_REVIEW'),
  entry_id TEXT NOT NULL UNIQUE,
  draft_id TEXT NOT NULL,
  draft_version INTEGER NOT NULL,
  draft_digest TEXT NOT NULL,
  operation_id TEXT NOT NULL,
  canonical_request_digest TEXT NOT NULL,
  accepted_by_receiver_ref TEXT NOT NULL,
  accepted_by_actor_id TEXT NOT NULL,
  accepted_at TEXT NOT NULL,
  receipt_digest TEXT NOT NULL,
  control_revision INTEGER NOT NULL,
  request_id TEXT NOT NULL,
  decision_id INTEGER NOT NULL,
  credential_policy_version INTEGER NOT NULL,
  scope_policy_version INTEGER NOT NULL,
  grant_version INTEGER NOT NULL,
  UNIQUE (tenant_id, task_id, handoff_kind),
  FOREIGN KEY (entry_id, tenant_id, task_id)
    REFERENCES s2_handoff_queue_entries(entry_id, tenant_id, task_id)
);
```

Existing `commands` is the durable operation/idempotency ledger. A `S2_HANDOFF_SUBMIT` command row uses trusted tenant/actor, `target_ref=task_id:SCOPE_REVIEW`, `idempotency_key=operation_id`, canonical `request_digest`, accepted state and a result JSON that points to the immutable Receipt. Existing Domain Outbox stores exactly one `S2_HANDOFF_ACCEPTED` event with `source_kind=S2_HANDOFF_RECEIPT`, `source_id=receipt_id`; schema unique source/event prevents duplicate event. No second operation table or general workflow platform is introduced.

The S2 task projection is updated to Task status `COMPLETED` in the same transaction as receipt acceptance; business outcome is derived from the immutable receipt as `SCOPE_ESCALATED`. Receipt fields are immutable; later queue review lifecycle must not rewrite Receipt. The 72h `OVERDUE` display is derived read-only from `review_due_at` and a trusted clock.

## Canonical receipt digest

`receipt_digest = SHA-256(canonical_json(receipt_payload))`. Payload binds schema version, tenant/task, handoff kind, Queue Entry ID, draft ID/version/digest, operation ID and request digest, trusted accepted actor, fixed receiver identity, accepted timestamp, control revision, Request/Decision IDs, and credential/scope policy plus Grant versions. Do not include secrets. All IDs are created before insert within the transaction and persisted once.

## Sole commit protocol

All steps use one connection and one `BEGIN IMMEDIATE` transaction:

1. Resolve trusted identity; verify SUPPORT role and Task ownership.
2. Canonicalize request and inspect existing `commands`. Exact key/payload replay returns stored Receipt; same key/different payload rejects. Do not require a new control revision for replay of a committed operation.
3. Check existing `(tenant, task, handoff_kind)`. An identical compatible handoff returns its Receipt (and records the newly accepted command alias if safe); conflicting Draft/digest rejects. Never insert a second Queue or Receipt.
4. Assert TaskControl ACTIVE, no pending correction, expected revision equal current, task nonterminal, Task workflow still `WAITING_HANDOFF`, and no active/unresolved business Run.
5. Query latest applicable frozen Draft and DiagnosisReceipt by trusted Task scope. Bind exact request draft ID/digest/version to it. Re-evaluate the existing S2 Evidence Gate through a same-connection function; compare current `DIAGNOSED` request/decision/evidence digests and current authority versions. No nested Domain connection and no weaker duplicate Gate.
6. Insert Queue Entry, immutable Receipt, accepted `commands` row, update Task projection, and insert Outbox. Any pre-commit failpoint exception rolls all of them back.
7. Commit once. A post-commit HTTP failure is resolved only by querying command/Receipt using the same trusted scope and replaying the same result.

TaskControl correction/Abort and Handoff serialize via `BEGIN IMMEDIATE`: whichever transaction commits first governs. If correction/Abort commits first, old revision/draft fails; if Handoff commits first, receipt remains an immutable accepted fact and cannot be represented as never submitted.

## Constraints and prohibitions

- Business uniqueness is enforced by SQLite, not process-local locks.
- Scope, Policy, Principal Grant tables are read only in M2-03. Write-count delta must remain zero.
- No external network, MCP, LLM, worker, or callback inside this Domain transaction.
- No queue transmission to remote systems; local SQLite Queue Entry is the receiver-owned record in this demo.
- No mutable Receipt status, automatic review, authorization, retry/re-delivery, or repair operation.
