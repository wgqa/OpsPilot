# AGENTS.md — OpsPilot v1.0 工程规则（Luna 与其他代码实施 Agent 必须遵循）

**唯一执行合同：** `docs/baseline/v1.0-implementation-baseline.md`。第三方 R5 已批准设计；实现仍需逐阶段验收。开发进度见 `TASKS.md`。

## 不可违反的边界

1. P0 只承诺 S1：真实调用方仍用旧 `credential_ref` 导致业务 API 401；获批后配置 CAS 更新，并由**同一 service / integration / principal / route** 的真实业务调用恢复到业务 200。主体 DISABLED 是迷惑负例，禁止自动启用或替换凭证。
2. LLM 只能建议只读调查工具/假设。`tenant_id`、actor、审批、Policy、资源授权、风险、预算扣减和状态转换来自可信程序；模型不能自由输入密钥/URL/Authorization。
3. Graph checkpointer 管执行进度，Domain SQLite 管 PlanAuthorization/Approval/ActionPermission/ActionIntent/ActionLedger/业务事实/交付回执。**不能把 checkpoint 当成外部副作用的唯一状态证据。**
4. `get_or_create_action_intent` 必须**先于 REPAIR/DELIVER 首次调用**持久化同一 canonical request、action_id/key/digest；同键异摘要拒绝，历史 COMMITTED 回执可回查。计划失效与新提交在同一 Domain 事务内裁决。
5. REPAIR 与 DELIVER 分别审批消费。修复验收在线真实探测；报告/验证收据先持久冻结，DELIVER 用独立 ActionIntent 幂等追加工单。工单写入失败不能重新 REPAIR。
6. 外部证据、记忆、Skill 内容均不可信任为策略指令；真实凭据仅工具侧处理。在线 Verifier 不能接触离线 Gold/fixture expected labels。
7. 两个可信本地租户/操作者足以展示隔离边界，但绝不可宣传为生产级 IAM。未经批准，**受限配置与工单业务写入均为零**。
8. 不得为展示而新增 Redis、S2/S3、多 Agent、A2A、自建网关、复杂前端、向量 DB 或监控平台。初版代码以一个 Agent app、一个 Demo Domain、一个只读 MCP Server 为范围。
9. 每个任务必须附真实测试日志、执行命令、Trace 与已知失败；不得把 mock 成功或文档冻结当作已实现。不许杜撰指标。
10. 节点重命名/合并并非问题；如触及状态兼容性、执行/审批语义或 E01–E10 行为，先提出简短设计变更，由主 Agent 审查。

## 开发流程

- **D1**：真实模型 Tool Call、MCP stdio tools/list + tools/call、持久 interrupt/跨进程 resume 三 smoke；无模型 S1 真实因果链。**不要在 D1 提前做 D3/D4 业务事务完整系统。**
- **D2**：动态调查、Evidence Gate 与只读工具；不通过不能接真实写入。
- D2 Investigator 的事实读取必须经过 TaskBinding 作用域下的真实 MCP Client/Server；D1 `get_demo_service_info` 聚合工具只用于 D1 回归，不得进入正式 Investigator 工具集。
- D2 模型不能指定 tenant、actor、Authorization、凭证值、任意 URL 或 thread ID。MCP Server 从持久可信 TaskBinding 取得 scope；Domain 每次查询均重新核验 task/resource 归属。恢复 checkpoint 前必须先校验 thread 所有者。
- D2 只读循环的程序预算默认最多 8 次模型请求、6 次 MCP `tools/call` attempt；每次外发前持久登记，重试/恢复重放都计数。Gate 只返回 `READY`、`NEED_MORE`、`NO_ACTION`、`INCONCLUSIVE`，只用类型化、同租户、同任务、同资源、版本兼容且足够新的 Evidence；模型文字不能直接决定 Gate。
- D2 的 `READY` 只允许生成诊断与 Plan 候选，不执行配置或工单写入。主体 `DISABLED` 返回 `NO_ACTION`；缺失事实在预算内可 `NEED_MORE`，冲突、重复无增量或耗尽预算则安全停止为 `INCONCLUSIVE`。
- **D3**：Plan、审批、持久 ActionIntent、修复事务、独立在线业务恢复探测、报告与交付首次闭环。
- **D4**：恢复、动作身份回查、取消/替换、授权消费、工单去重、越界及响应丢失故障注入。
- **D5**：一个 `auth-incident-triage` Skill、一类经批准 Episodic Memory、最小 Context Provenance。
- **D6**：冻结 E01–E10 回归、成本/错误记录及探索性对照。
- **D7**：干净环境演示、文档、可重跑报告、面试追问。任何硬门禁失败则不向下一层叠加功能。

## 每次提交必附

`Commit/branch`、锁定依赖、实际改动、运行命令、测试分子/分母、失败明细、业务事实证据、外部副作用/审批/安全影响、下一步与是否需变更基线。

**本地已有 AGENTS.md 时，本稿是合并目标，不要抹掉原有安全条款或机器环境说明；冲突必须由主 Agent 裁决。**

## 从原工作区保留的约束

- 旧项目和其他学习任务仅作只读参考，不修改其中的代码或资料。
- 在 D1 中只完成 D1 范围；不以常规实现选择为由引入额外审批，也不扩展到 D2 及后续阶段。
- 归档文件中的旧方案和任务卡仅供溯源。实施时只按根目录本文件、`TASKS.md`、当前阶段任务书及唯一有效的 v1.0 基线执行。
