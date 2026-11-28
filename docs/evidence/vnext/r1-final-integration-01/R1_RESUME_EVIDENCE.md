# R1 简历与面试证据清单

本文提供可核对的项目事实，不代替用户最终简历措辞。

## 可表述的工程实现

- 基于 LangChain/LangGraph 的连续 Assistant 对话，结合可信 Context、会话历史与调用预算。
- 通过 MCP 将模型选择的只读调查连接到受 TaskBinding 限定的 Domain 工具；工具参数中的用户文本或 Task ID 不会自动变成授权。
- 普通 Assistant 可按需提出 S1/S2 受控调查建议；用户经现有确认入口创建 Task 后，旧 Investigator 执行专业调查，Domain 保存 Plan、Approval、ActionIntent、Ledger、Receipt 与 Handoff 状态。
- S1 隔离 Demo 具备从 401 证据、独立审批、当前性复核、CAS、同一 service/integration/principal/route HTTP 200，到 VerificationReceipt、冻结报告与独立 DELIVER 的可追踪因果链。
- S2 隔离 Demo 可从匹配的 403/Authz DENY 形成未提交草稿；显式提交后取得本地 Queue、不可变 HandoffReceipt 与 Outbox，明确停在等待人工审查，不声称已获新权限或恢复业务。
- Assistant 对历史来源、当前 Observation、用户材料、Knowledge 文档版本和可信业务结果采用不同来源语义。

工程表述的证据来自 [Final Bridge 报告](../product-01-final-bridge-01/REPORT.md)、[Bridge Closeout 报告](../product-01-bridge-closeout-01/REPORT.md) 和本轮 77/77 定向回归。它们证明隔离确定性链路及安全边界，不证明生产环境部署。

## 可量化真实模型运行

1. **PRODUCT-01 Slice 02：** 同一 Session 四轮真实 DeepSeek；8 个 Provider 请求、9 次 MCP 调用。模型实际发现并比较协议、分析用户 JSON、绑定后读取当前订单回调、纠正 Event 并给出说明草稿。总体 PARTIAL：配置适用性推断超出可见证据，草稿需人工校稿。详见 [真实旅程报告](../product-01-slice-02-live/REPORT.md)。
2. **AR-04C Memory OFF/ON：** 两组共 8 个真实 Provider 请求、14 次 MCP 调用。首轮业务解释总体有用；ON J4 在零 MCP、零新 Observation 时仍称本轮重新读取，G7 ON FAIL。不能宣称 Memory 提升质量。详见 [真实 OFF/ON 报告](../../ar-04c/live-exec-01/REPORT.md)。
3. **F01 定向真实复验：** 8 个真实 Provider 请求、10 次 MCP 调用。模型取得同 Event QUEUED 与 PROCESSED 观察；由于第 9 次 Provider 请求被硬上限拒绝，PROCESSED 观察未进入后续模型结论，用户收到程序生成的 PROGRAM_LIMIT 通知。结论 PARTIAL_STOPPED_PROVIDER_LIMIT；不能说模型根据 PROCESSED 完成判断。详见 [F01 复验报告](../../ar-04c/f01-recheck-01/REPORT.md)。

费用均以各自原报告中的应用账本估算为准，不称为供应商发票。本轮没有启动任何新真实 Provider。

## 暂不应宣称

- 真实模型已自主完成全部 S1/S2 修复或交接。
- 已接入企业生产系统、生产级 IAM 或生产级分布式可靠性。
- 浏览器端到端体验已通过。
- Agent 自动消除了所有用户故障。
- Memory 已被证明普遍提高决策质量；Skill 已被证明改善结果。
- R3 日志/Trace 平台、通用 API 联调平台或生产工作流已实现。
- 历史全量 pytest 在本次候选 SHA 上全绿；本轮只执行适用定向范围。

## 面试讲解路线

建议从“用户在同一 Session 中提出问题 → 模型看到什么来源/上下文 → 模型选择工具或直接回答 → MCP/Domain 产生何种 Observation → 结果如何关联回原问题”展开，再用一次真实失败解释边界：

- Slice 02：模型有用，但仍将两个配置值不一致过度解释为配置未生效。
- AR-04C ON J4：Context 保留了有效历史来源，却不能将其说成当前 Run 已重新读取；真实回答与零 MCP 轨迹冲突。
- F01：本地 MCP 已取得 PROCESSED，但 Provider 预算阻止下一次模型读取，所以程序通知不能当成模型结论。
- AR-03 Runner：保护历史工具合同的拒绝逻辑挡住了旧 Runner 新接入工具 Schema；不应通过放宽安全门禁制造绿灯。

这些失败体现了可追查的来源关联、预算和实验边界，也限制了对自主性与业务效果的宣称。
