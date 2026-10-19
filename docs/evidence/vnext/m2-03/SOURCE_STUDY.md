# M2-03 源码学习笔记

## 业务交接执行路径

1. [frontend/src/App.vue](../../../../frontend/src/App.vue) 只在可信 SUPPORT 工作区显示交接按钮。用户确认后，页面重新读取当前 Draft 与控制版本，再提交精确的 `draft_id`、摘要、版本和 operation ID。operation ID 按 Task/Draft 写入 `localStorage`；请求异常时先 GET 回查 HandoffReceipt，不生成新意图。
2. [frontend/src/api.ts](../../../../frontend/src/api.ts) 将同一个 operation ID 同时放入 JSON 和 `Idempotency-Key` 请求头。
3. [opspilot/web/app.py](../../../../opspilot/web/app.py) 通过已登录 Web Session 建立可信身份，应用 Origin/CSRF 和严格 Schema 校验，然后才调用 Domain。请求正文不能指定 tenant、actor、角色或接收队列。
4. [opspilot/domain/s2_handoff.py](../../../../opspilot/domain/s2_handoff.py) 在一个 `BEGIN IMMEDIATE` 事务内核验 SUPPORT owner、TaskControl、活动 Run、最新 Draft/DiagnosisReceipt、证据与授权事实；其后写 Command、Queue Entry、HandoffReceipt、Task 投影和 Domain Outbox。唯一索引保护 `(tenant_id, task_id, handoff_kind)`。同 operation 的重放返回原 Receipt；异正文冲突或业务唯一项冲突不会新增队列项。
5. [opspilot/domain/s2_diagnosis.py](../../../../opspilot/domain/s2_diagnosis.py) 提供只读 Evidence Gate。提交时它与授权事实查询复用写事务的 SQLite Connection，避免并发版本更新导致“先检查、后写入”的 TOCTOU。已提交 Receipt 是不可变历史事实；后来证据失效不会抹掉接收回执。
6. [opspilot/domain/d2.py](../../../../opspilot/domain/d2.py) 和只读 MCP Server 提供绑定范围内的 Probe 与 Authz Decision。403 是响应事实；缺少 Scope 的业务根因由服务端 Authz Decision、请求关联和当前 Policy/Grant/Principal 版本确定。M2-03 不写这些授权对象。
7. [opspilot/domain/database.py](../../../../opspilot/domain/database.py) 从 v7 增量迁移到 v8，建立 Queue/Receipt 表、业务唯一约束和不可变 Receipt 触发器。测试 fixture 清理仅由 `reset_fixture` 在测试准备时使用。

## 关键实现原则

- **模型和聊天不授权：** 模型回答、自然语言“提交吧”和冻结 Draft 都不能创建 Queue Entry。只有 Web 中明确的 SUPPORT owner 操作通过 Domain 最终检查后才可提交。
- **去重有两层：** operation ID 解决同一 Web 意图的响应丢失与重复点击；SQLite 业务唯一键解决不同标签页、不同请求 ID 或不同进程竞争同一 Task 的问题。
- **同事务重核验：** 当前 Evidence Gate、TaskControl 和写入操作在同一个 SQLite 写事务连接内执行。任何版本变化或竞争提交会整体拒绝或回查既有回执。
- **Outbox 与业务事实同生共死：** Queue、Receipt、Command、Task 投影和 Outbox 一起提交或一起回滚；SSE/客户端事件不是业务状态权威。
- **业务完成不等于业务恢复：** 工作流 Task 可结束，但只有成功接收的不可变回执可推出 `SCOPE_ESCALATED`。它只表示进入本地待人工审查队列；没有自动授权、没有人工审批结果、API 没有恢复。

## 易错边界

- `submitted` 是事实字段，不能由 Draft 存在与否或模型回答推导。
- 相同 operation ID 配不同摘要必须拒绝；不同 operation ID 也不能创建第二个同 Task/类型的交接。
- 重试的 `200` 表示读到已接受回执，不表示再次执行写入；首次提交为 `202`。
- 72 小时超期是只读投影，不能触发授权、自动审批、删除或重新投递。
- Provider/MCP 轨迹用于证明调查发生；授权能力仍来自 Domain 和固定业务绑定，而非 Trace 文本。
