# M3-01 Web API 合同（冻结版）

所有路由使用现有 FastAPI Session 身份、tenant/task reader 检查、Origin/CSRF、严格 schema 和 Domain 最终校验。路径可在实现中作内部调整，但外部语义不能放宽。写操作均需 Idempotency-Key；身份和 receipt/source 不从请求体信任。

## SUPPORT

- GET /api/tasks/{task_id}/memories：仅 Task owner/reader；返回适用 Active Memory 的 id、version、digest、历史 outcome/source summary、过期时间，以及最近 ContextManifest 的 selected/excluded reason。
- POST /api/tasks/{task_id}/memories/candidates：只有可信 SUPPORT owner；用 Task A 的当前可信 Domain 收据生成或幂等回查 Candidate。请求不得提交 source outcome、receipt ID、当前 facts 或可信 summary。

## APPROVER

- GET /api/memories：同租户 APPROVER；按状态列举最小脱敏条目。
- GET /api/memories/{memory_id}：同租户 APPROVER 可读候选/详情和 source refs；不读无权源 Task 正文。
- POST /api/memories/{memory_id}/confirm：同租户 APPROVER；Domain 复核 source/digest/expiry 后 CANDIDATE→ACTIVE。
- POST /api/memories/{memory_id}/revoke：同租户 APPROVER；ACTIVE→REVOKED；后续 prompt admission 会排除。

Candidate 建立和生命周期操作经既有 commands 事务记录 Request digest。相同 actor/key/command/target/digest 回放相同结果；同 key 跨 target 或同 target 异 digest 返回幂等冲突。失败无状态副作用。

## UI 表现

Task A 显示真实 source outcome、source refs、case-specific facts/method/limitations 和“历史方法提示，不是当前事实”警告。APPROVER 显示独立审核和撤销按钮。Task B 显示本次模型 Context 的 Memory id/version/digest/source Task/outcome、采用或排除原因，以及当前真实 MCP 调用。任何页面不得显示由 Memory 直接决定的 Gate/授权/业务成功。
