# M2-03 Web API 合同（冻结）

接口路径采用任务卡建议路径；实现可调整内部函数名称，但外部业务语义、授权、稳定幂等和回执结果不得改变。

## `GET /api/tasks/{task_id}/handoff`

- 使用认证 Session 与当前 reader scope；不写 Domain。
- 没有当前有效提交时，返回 `business_outcome`（`NO_S2_DIAGNOSIS`、`DIAGNOSED` 或 `HANDOFF_READY`）、`currentness`、当前 Draft 预览和 `submitted=false`。不得把模型回答作为当前 outcome。
- 已有 Receipt 时优先返回 immutable receipt 摘要、Queue Entry、`business_outcome=SCOPE_ESCALATED`、`submitted=true`、handoff 状态；`scope_authorized=false`、`recovered=false` 恒为 false。
- Queue `PENDING_REVIEW` 到 72h 期限时，可只读派生 `OVERDUE`；读取不改 Receipt、不重投、不触发 Worker。
- 不返回凭证、Secret、完整 Prompt、他人 Task 内容或未脱敏授权明细。

## `POST /api/tasks/{task_id}/handoff/submit`

Headers: `Idempotency-Key`, `X-CSRF-Token`, `Origin`, `Content-Type: application/json`。通过既有 `write_user` 认证、Origin 和 CSRF 检查。

请求严格只接受以下字段：

```json
{
  "operation_id": "<stable client-generated operation id>",
  "draft_id": "<current frozen draft id>",
  "draft_digest": "<frozen digest>",
  "expected_control_revision": 2,
  "handoff_kind": "SCOPE_REVIEW"
}
```

Header key 必须等于 `operation_id`。不接受 `actor_id`、`tenant_id`、`role`、`receiver`、`queue_id`、`scope` 或任何额外 body 字段。服务器由 Session 得到身份，由固定配置决定本地 receiver。

Canonical request digest 使用版本化 JSON，至少包含 method/route、trusted tenant/actor、task ID、operation ID、draft ID/digest、预期 control revision 与 handoff kind；JSON 使用 UTF-8、键排序、紧凑分隔，SHA-256。服务端按既有 `commands` 查询 tenant+actor+key：完全相同 request 返回已持久结果；同 key 不同 command/target/digest 返回幂等冲突。操作 key 不替代业务唯一键。

首次成功返回 `202`；相同幂等请求/业务兼容回查返回 `200`。成功 DTO：

```json
{
  "status": "ACCEPTED",
  "business_outcome": "SCOPE_ESCALATED",
  "operation_id": "...",
  "receipt_id": "...",
  "queue_entry_id": "...",
  "draft_id": "...",
  "draft_digest": "...",
  "receiver_label": "本地受控审查队列",
  "received_at": "...",
  "handoff_status": "PENDING_REVIEW",
  "submitted": true,
  "scope_authorized": false,
  "recovered": false,
  "replayed": false
}
```

Replay 仅将 `replayed=true`、status/HTTP 更新为回放语义；Receipt/Entry identity 必须相同。成功响应缺失或连接中断后，前端用相同 operation ID 先 GET 回查，再可用相同请求重试；不可生成新 ID 掩盖未知结果。

## 错误映射

错误码稳定、无副作用、不得泄漏跨租户资源：

| 情形 | 建议 HTTP | 错误码 |
|---|---:|---|
| 未登录/Session 失效 | 401 | `AUTH_REQUIRED` |
| Origin/CSRF 无效 | 403 | 既有 CSRF/Origin code |
| 非 SUPPORT owner / reader scope 不匹配 | 403 或统一 404 | `TASK_OWNER_REQUIRED` / `TASK_SCOPE_DENIED` |
| JSON 未知字段、Key 与 operation 不同、格式错误 | 422 | `INVALID_REQUEST` / `IDEMPOTENCY_KEY_MISMATCH` |
| 同 key 异正文 | 409 | `IDEMPOTENCY_CONFLICT` |
| 预期 Control Revision 过期 / pending correction / abort | 409 | `TASK_CONTROL_STALE` / `TASK_INPUT_PENDING` / `TASK_ABORTED` |
| Draft 不再最新或当前 Gate/Evidence 变化 | 409 | `DRAFT_STALE` |
| 不兼容业务唯一身份已有接收 | 409 | `QUEUE_ALREADY_ACCEPTED` |
| 完全相同业务接收已存在 | 200 | 现有 Receipt 回查，不新增记录 |

## 自然语言及事件

聊天 POST 仍按 CHAT_READONLY 处理，任何模型文本不得自动调用交接 POST。`S2_HANDOFF_ACCEPTED` Domain Outbox 用 session/task 关联形成持久事件；SSE 断线后事件历史可重放。事件只通告结果，不是提交依据。只读追问必须明确“已被本地队列接收，等待人工处理；尚未批准、尚未授权 Scope、API 未恢复；无需重复提交”。
