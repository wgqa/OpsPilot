# M3-01 面试追问与回答

### 为什么复用 D5，而不建新的向量记忆服务？

本阶段只需要少量结构化且可审批的案例事实。D5 已有 SQLite 生命周期、来源检查、撤销和 Provenance，复用它更容易保持 Task/租户权限权威，也避免把模糊的相似度结果误当成授权。M3-01 没有做向量检索或通用资产后台。

### 一个经历如何成为可用案例？

由 Domain 从已经提交且可核验的业务事实创建 Candidate。S1 需要真实 REPAIR Ledger、在线恢复 VerificationReceipt、冻结 Report 和 Evidence；S2 需要可信 DiagnosisReceipt，若声明真实交接还需要真实 HandoffReceipt。候选只能由可信 APPROVER 激活，不能由模型回答直接激活。

### 为什么不让用户说“之前就是 Scope 问题”来选 S2 Memory？

用户输入是不可信线索。`_current_evidence_memory_problem_type()` 只接受当前 Run 的受信 MCP Probe 与 Domain 决策关联来选择案例类型；没有匹配事实就不加载。Prompt 中历史经验只给调查方法，当前 Evidence 和 Domain Gate 决定事实及 Outcome。

### 如何避免 ON/OFF 评估偏袒 ON？

每一对臂从同一目标 Domain 快照独立复制；除是否注入可用案例 Memory 外，身份、初始状态、模型、工具、Skill、Knowledge、预算和提示主版本相同。Gold 在实现前冻结，所有 16 臂都保留。实际结果包括 ON/OFF token、MCP、耗时、Outcome 和执行错误。

### 如果撤销发生在模型 Prompt 构建之后呢？

Memory 内容不会由 Checkpoint 当成长期授权缓存。每次调用在出站前重读 SQLite 并检查状态/有效期/来源；独立 Worker 恢复也会重建上下文。撤销前 Provenance 保留以便审计，新上下文不再包含该 Memory。当前跨进程 Smoke 证明了暂停、审批撤销、新进程恢复和空的新 Context。

### P03/P04 为什么记录成失败？

两个 S2 正例在 ON/OFF 都真实运行完成，但模型把业务 Outcome 推进到 `HANDOFF_READY`，冻结 Gold 只允许 `DIAGNOSED` / `INCONCLUSIVE`。即使这只是草稿且没有真实 HandoffReceipt，也不能改 Gold 或把它算作通过。结果保留并供主 Agent判断是否是产品/模型行为问题。

### Memory 是否带来效果？

目前无法证明。P01/P02 和 P07 的 ON 选入了跨 Task Memory，但对应 ON/OFF 的冻结 Outcome 没有显示效用改善；多个场景因当前事实而正确排除了 Memory。样本只有 8 对，不能声称统计显著或因果收益，因此结论是 `UTILITY_NOT_PROVEN`。

### 费用是多少？

Provider 返回 tokens，但没有向这次请求返回账单价格。评测记录了 ON `101,582`、OFF `88,495` tokens 和每臂耗时/MCP 数，不按外部或可变单价估算费用；成本字段明确为 `NOT_REPORTED`。

### 这能用于生产吗？

不能据此作此声明。当前证据来自本地 SQLite Demo、固定订单 API/Route、有限案例和演示用身份。任务证明的是现阶段的来源审核、跨 Task 注入、撤销和调查边界，不等于生产 IAM、跨实例高可用或通用经验平台。
