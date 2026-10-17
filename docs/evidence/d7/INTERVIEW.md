# STAR 候选与源码追问

以下是项目事实的表达候选；使用者应先沿 CODE_READING_MAP 阅读并能解释关键事务和测试。数字只描述本地有限实验，不代表生产准确率、吞吐或个人独立编码工时。

## STAR 候选 1：可验证的 Agent 业务闭环

**S**：同一个订单接口的 HTTP 401 可能来自旧客户端凭证、停用主体或证据不足，直接让模型改配置会产生越权风险。**T**：在冻结的单一 S1 范围内，让真实模型通过 MCP 调查，只有当前证据支持且独立批准后才能修复，并用业务结果证明恢复。**A**：用 LangGraph 串接拆分只读工具、确定性 Evidence Gate、不可变 Plan/HITL；在 Domain 预登记 ActionIntent，再事务 CAS 更新配置；以同一 service/integration/principal/route 的实际 HTTP 验证生成冻结报告，使用独立授权动作写工单。**R**：D6 E01 真实链路通过，停用主体返回 NO_ACTION、缺证据返回 INCONCLUSIVE，均没有修复写入。D7 从新目录和锁定依赖复现的实际结果及失败见 REPORT；不把 D6 十个场景族说成十个独立模型样本。

可选简历表述：在本地 SQLite Demo 实现认证故障 Agent 的调查、证据门禁、人工批准、事务修复、同身份 HTTP 验证与幂等工单交付；保留真实模型/MCP 轨迹和分离的安全/恢复评测。

## STAR 候选 2：跨进程恢复与副作用去重

**S**：业务事务已经 COMMIT、进程却在响应或 checkpoint 写入前退出，会使重试误以为动作没执行。**T**：修复和工单交付各自保留稳定动作身份及可重放回执，计划取消/替换与动作提交有明确顺序。**A**：把 Intent、PlanAuthorization、Approval、分动作 Permission、Ledger 和业务 CAS/工单去重放在同一个 SQLite Domain；Graph 只保存引用。用真实 OS 子进程强制退出，覆盖 COMMIT 前后、旧 checkpoint、报告冻结及 DELIVER 丢响应；恢复回查相同 Ledger，无回执则 ACTION_OUTCOME_UNKNOWN 转人工。**R**：D6 全量控制回归通过，D7 独立环境再次运行既有崩溃恢复用例并保留原始 PID、exit code、action/ledger 与计数。结论限于本地单库事务，不宣称生产分布式 exactly-once。

## 十个追问（回答应能落到函数和运行证据）

1. **模型是否只是在按脚本顺序调用工具？** `investigator.build_investigation_graph` 的 `investigate` 接收真实 Function Calling 响应，`execute_read_tools` 派发选中的只读调用；次序看 D7 E01 `model_traces/mcp_observations`。工具种类和预算由程序限定，模型不决定策略或根本权限。
2. **为什么同样 401 会有不同结论？** `domain.d2.evaluate_evidence_gate` 对比当前主体、策略、配置与关联 Probe。D6 E02 DISABLED 的正确处理是 NO_ACTION；E03 缺证据是 INCONCLUSIVE；它们都不计 Actual Recovery。证据路径见 D6 RESULTS。
3. **如何证明恢复不是数据库造出来的 PASS？** `domain.d3.verify_repair_online` 调用 `domain.client.probe_orders`，由真实 HTTP 返回 200/`demo-order`/`CONFIRMED` 才写回执。D7 E01 的原始 401 Evidence、同身份 VerificationReceipt 和独立 DELIVER 回执可交叉核对；fixture reset 是测试准备，不是 REPAIR。
4. **为什么不把动作结果全放 checkpoint？** checkpoint 与业务事务没有跨层原子提交。`get_or_create_action_intent` 在首次动作前固定身份，`execute_repair/_prior_ledger` 以 Domain COMMITTED 回执重放。D7 `WORKERS.json` 展示 COMMIT 后 exit 75 与另一进程恢复，不靠模型重建 key。
5. **批准之后取消 Plan，动作是否还能提交？** `cancel_plan/_activate_plan_in_transaction` 和 `execute_repair/execute_deliver` 由 BEGIN IMMEDIATE 串行裁决。取消先提交则新动作拒绝；动作先提交则保留历史回执，不宣传回滚。对应 `test_d4_cancel_and_repair_are_serializable`、`test_d4_plan_replacement_races_repair_and_historical_receipt_replays`。
6. **为什么工单不重复？修复许可消费后还能交付吗？** `submit_plan_approval` 产生 REPAIR/DELIVER 两条许可；`execute_deliver` 校验固定报告、验证回执和票据归属，在同事务追加唯一条目、写 DeliveryRecord/Ledger、消费 DELIVER。`test_d4_langgraph_replays_committed_delivery_after_lost_response` 验证只写一次。
7. **跨租户与注入控制只写在 Prompt 吗？** `create_task_binding/authorize_thread_resume`、`mcp_server.build_task_server`、`_require_executor` 和作用域 SQL 真实校验；模型 Schema 不接受 tenant、actor、URL 或 Authorization。`test_d4_real_read_only_mcp_injection_cannot_create_action_intent` 即便结构化事实足以 READY，未批准写入仍为零。有限样本不证明抵抗所有注入。
8. **Memory 真正学到了什么？** `episodic_memory.MEMORY_SUMMARY` 是固定通用排查方法，与 Skill 重叠。已证明的是可信来源/人工确认、跨任务真实 Prompt 注入、撤销后跨进程不再加载；不是自动提取独特案例经验，也没有公平消融证明效果提升。D6 E10 原始失败仍为 PARTIAL。
9. **安全停止为什么不算业务恢复？** `VerificationReceipt.recovery_verified` 必须有业务 HTTP 和订单断言；NO_ACTION、INCONCLUSIVE、ACTION_OUTCOME_UNKNOWN 均不是 RECOVERED。D6 RESULTS 分开记录 Correct Handling、Actual Recovery、Control Safety，64/64 控制测试也不能替代模型 smoke 的 4/5 分母。
10. **独立复现实际发现过什么？** D7 初次源码导出受 Windows autocrlf 影响，Skill 正文摘要失败，E01 在模型/写入前停止、全量 61/64。最小修复 `.gitattributes` 将该正文固定 LF，完整保留失败后在新环境重跑。其余限制包括本地信任根、单机 SQLite、单一模型端点、未做生产分布式幂等与通用诊断；新鲜结果见 D7 REPORT，第三方尚未审查。
