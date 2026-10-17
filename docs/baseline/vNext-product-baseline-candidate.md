# OpsPilot vNext 产品基线候选（M1-01 实施快照）

**状态：候选实现基线，等待主 Agent 审核。** 它记录本轮按用户授权执行的范围，不表示整个 vNext 架构、M1 或 G0 已通过第三方评审。

## 来源与优先级

- v1.0 的 D1–D7 安全基线继续适用于历史功能，见 [v1.0 implementation baseline](v1.0-implementation-baseline.md)。S1、F1–F3、D1–D7 数据与证据不被本文件覆盖。
- vNext 产品/架构输入为 [v0.3 用户提供合同](../handoff/vnext/OpsPilot-vNext-v0.3-product-architecture-contract.md)；N1 的最高优先级规则在其附录 B。
- 本轮执行范围由 [M1-01 任务卡](../handoff/vnext/Luna-M1-01-implementation-task-card.md)收窄。任务卡与当前用户消息授权了 M1-01；M1-02 和之后的工作仍需主 Agent 验收后另行启动。
- v0.3 文本记载：第三方对 v0.2 的最近结论为 `REVISE_AND_REVIEW`，v0.3 附录 B 尚未再次第三方复审。**本文件和本轮测试均不构成第三方签字。**

## 本轮冻结的执行边界

1. 在现有 Domain SQLite 中持久化 TaskControl、Session、Message、Command、TaskRun 与事务 outbox。
2. `abort_task` 和 `CORRECT_TASK_INPUT` 是不同控制命令。它们的受理、版本更新、Plan/permission 失效与事件记录在 `BEGIN IMMEDIATE` 内提交。
3. 旧 D3 入口只允许 revision 0、无 pending correction 的窄兼容路径。新 Run 从持久 Run 读取预期 revision；关键输入必须先以 `USER_INPUT_UNTRUSTED` 消费，不能成为 Evidence 或授权。
4. 每个不可变 Plan 在独立表中绑定 Task revision、已消费消息高水位和可选 Run ID；不修改 v1.0 canonical Plan、历史 hash、ActionIntent、Ledger 或回执。
5. abort/correction 与 REPAIR/DELIVER 通过同一个 Domain 数据库的写事务排序。先提交的事实决定后续资格；已提交 REPAIR 不能被伪装回滚，未提交 DELIVER 可被阻止。
6. SQLite/本地受信 operator registry 是当前演示边界，不代表生产 IAM、分布式锁或 exactly-once。

## 当前实现状态

M1-01 新增 TaskControl Domain API、迁移、事务守卫、Run-specific LangGraph checkpoint 路径和真实模型/MCP smoke。详细接口与状态见同目录的 `STATE_TRANSITIONS.md`、`API_CONTRACT.md`、`ACCESS_MATRIX.md` 与 `EVENT_RECOVERY.md`。

M1-01 **不交付** Web/FastAPI 聊天界面、HTTP 202/读 API、SSE projector、后台多进程 Run lease、S2/403、Memory/Knowledge 变更或 M1-02 的其他内容。它提供后续任务可复用的持久 Domain 记录，但不宣称完整多轮对话已经完成。

## 后续待决范围

按合同记录，S2 的 P0 本地受控接收队列/HandoffReceipt 决策以及后续阶段路线，不由 M1-01 代替决策或实现。S2 结果边界见 [`S2_OUTCOMES.md`](S2_OUTCOMES.md)。本候选文件须经主 Agent 审查后才能提升为 vNext 已验收基线。
