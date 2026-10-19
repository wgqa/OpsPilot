# M2-03 权限矩阵（冻结）

可信身份从服务端 Web Session 解析。请求体中的身份、租户、角色、队列接收者均无权威性；未知字段必须拒绝。读写接口均按 tenant+task 进行范围限制，未授权和不存在资源按现有策略返回一致的拒绝响应，不泄漏跨租户资源是否存在。

| 主体 / 条件 | 查询当前 Draft/Receipt | 提交 SCOPE_REVIEW | 产生 Queue/Receipt/Outbox | 授予 Scope/Policy/Grant | 说明 |
|---|---:|---:|---:|---:|---|
| 当前 Task 的可信 SUPPORT owner，认证、Origin、CSRF 有效，显示 Draft 并明确点击确认 | 允许 | 允许，Domain 最终裁决 | 仅当前 Draft 已提交事务成功时各一条 | 禁止 | 唯一提交者；Queue 仅为本地人工审查接收 |
| 同租户但非 Task owner 的 SUPPORT | 按现有 Task reader 范围拒绝 | 禁止 | 禁止 | 禁止 | 不拥有该 Task |
| APPROVER，即使同租户 | 按现有 reader 策略 | 禁止 | 禁止 | 禁止 | M2-03 的提交不是审批操作；不能代替 owner 提交 |
| 其他 tenant 用户 | 禁止且不泄漏存在性 | 禁止 | 禁止 | 禁止 | 租户隔离 |
| 未认证用户 | 禁止 | 禁止 | 禁止 | 禁止 | 返回认证错误 |
| Session 无效、Origin 不匹配或 CSRF 无效 | 可按当前只读/写守卫策略处理 | 禁止 | 禁止 | 禁止 | 所有写请求均过 `write_user` |
| 用户聊天文本或模型回答 | 可作为只读解释 | 禁止 | 禁止 | 禁止 | 文字“同意/提交”不是业务确认 |
| 浏览器脚本/Body 提供 actor、tenant、receiver、role、任意队列 | 不提供这些参数 | 禁止 | 禁止 | 禁止 | 服务端忽略不得发生；必须拒绝额外字段 |
| 本地队列接收记录 | 可查脱敏摘要 | 不审批/不授权 | 已存在的 Entry/Receipt | 禁止 | 接收者固定为服务端本地 Demo 配置 |

## 写操作前的 Domain 必检

1. 可信 actor tenant/role 与 Task owner 完全一致，且为 SUPPORT。
2. Idempotency-Key 与 body `operation_id` 一致并符合长度/字符限制；同身份 key 不可异正文复用。
3. TaskControl 为 ACTIVE、revision 等于请求预期、无待应用 Critical Correction、未 Abort、未完成；没有 queued/running/waiting/interrupted 的业务 Run。
4. 请求引用与最新适用的同 Task Draft 完全一致：draft ID、digest、version、DiagnosisReceipt、Run、Request ID；Draft 仍是冻结状态且未被更正取代。
5. 在本次 `BEGIN IMMEDIATE` 的同一个连接上重算/复核受信 S2 Gate：Evidence 属同 tenant/task/Run/request、未过期、Request/Authz event 关联一致、Policy/Grant/Principal 当前版本相符，结论仍为可诊断的 Scope 不足。
6. 确认 `(tenant_id, task_id, handoff_kind)` 尚无冲突业务接收；已有同一兼容结果只允许返回原 Receipt，不新增任何业务记录；不兼容 Draft 必须拒绝。

任何一步失败时不得新增 Queue、Receipt、接受 Outbox 或将 Task 投影成已交接。
