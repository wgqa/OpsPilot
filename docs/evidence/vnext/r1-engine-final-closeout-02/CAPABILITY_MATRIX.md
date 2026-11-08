# R1-ENGINE 能力与证据矩阵

本矩阵只汇总可追溯的实现和历史执行结果。状态表示证据范围，不是验收签字。

| 用户能力 | 代码入口 | 确定性本地业务证明 | 真实 Provider 证明 | Web / 生产证明 | 状态与边界 |
|---|---|---|---|---|---|
| 连续 Assistant、Context 与模型调用保障 | [`assistant.py`](../../../../opspilot/assistant.py#L931)；[`Loop.context`](../../../../opspilot/assistant.py#L1244)；[`Loop.awrap_model_call`](../../../../opspilot/assistant.py#L1401)；[`runtime_provider.py`](../../../../opspilot/runtime_provider.py#L17)；[`reserve_dispatch`](../../../../opspilot/domain/assistant_runtime_grant.py#L1133)；[`run_worker`](../../../../opspilot/web/worker.py#L583) | Assistant、Runtime Grant、Context 与调用账本的离线定向回归；R1 集成候选记录了 77/77 定向后端结果 | 最新 J1/J2 Campaign 用真实 DeepSeek，9 次请求，Usage 全部有效 | 本地 API/Worker 有历史 health 证明；无浏览器验收或生产部署证明 | 代码及有限真实运行成立；不代表生产可靠性或全量 pytest 全绿 |
| 授权协议发现、比较与原文解释 | Assistant 工具由 [`assistant_mcp.py`](../../../../opspilot/assistant_mcp.py#L25) 注册；协议比较 Domain 实现见 [`scoped_protocol_comparison.py`](../../../../opspilot/domain/scoped_protocol_comparison.py) | 权限、版本、来源/Digest、合法查询和拒绝有定向离线覆盖 | PRODUCT-01 Slice 02 与 R1 J1-01 中模型自主发现/比较 v1/v2；J1-01 PASS | 正式浏览器旅程未运行 | 真实模型曾完成协议任务；静态文档不证明线上部署版本 |
| 用户 JSON/日志材料分析 | [`chat.py`](../../../../opspilot/domain/chat.py#L1050)；Assistant Context 入口见 [`assistant.py`](../../../../opspilot/assistant.py#L1883) | 正式 API/Worker/Assistant 离线材料路径有回归 | PRODUCT-01 Slice 02 与 R1 J1-02：同 Session 使用配置材料，不经 MCP；R1 J1-02 PASS | 页面连续体验未验证 | 用户材料一直是未验证输入；历史模型曾对配置适用性作超证据推断，当前 R1 J1-02 结果只支持该次样本 |
| 同订单 Event 的只读查询与纠错 | S3 MCP/Domain：[`s3_mcp.py`](../../../../opspilot/domain/s3_mcp.py)、[`s3.py`](../../../../opspilot/domain/s3.py)；可信 Task 创建：[`create_task_with_initial_run`](../../../../opspilot/domain/task_control.py#L976) | QUEUED/PROCESSED、TaskBinding、跨 Event/越权正反路径有离线证据 | R1 J2-01 查询 `event-current` 且正确限定到该 Event；J2-02 查询 `event-previous` 并将当前状态说明为未知；但客户草稿含未执行后续承诺，J2-02 PARTIAL | 浏览器未运行 | 可信观察能区分不同 Event；不代表 `event-previous` 已处理或已实时查询 Receiver |
| S1 401 受控修复闭环 | [`submit_web_plan_approval`](../../../../opspilot/domain/task_control.py#L353)；[`get_or_create_action_intent`](../../../../opspilot/domain/d3.py#L932)；[`revalidate_approved_plan`](../../../../opspilot/domain/d3.py#L1170)；[`execute_repair`](../../../../opspilot/domain/d3.py#L1525) | 隔离 Demo 完成当前事实复核、独立审批、CAS、同一身份本地 HTTP 401→200、VerificationReceipt、冻结报告及独立 DELIVER | 没有真实 LLM 自主完成统一 Bridge S1 的证据 | 浏览器 STOP；生产系统未连接 | 本地确定性闭环成立；不是生产恢复或真实模型端到端证明 |
| S2 403 诊断、交接和 Session 回读 | [`freeze_handoff_draft`](../../../../opspilot/domain/s2_diagnosis.py#L621)；[`submit_s2_handoff`](../../../../opspilot/domain/s2_handoff.py#L243)；[`get_s2_handoff_outcome`](../../../../opspilot/domain/s2_handoff.py#L440)；Assistant 结果读取 [`read_session_professional_outcomes`](../../../../opspilot/domain/assistant.py#L519) | 同 Session 本地 API/Worker/MCP/SQLite 形成 403/Authz DENY 草稿；用户确认后 Queue/Receipt/Outbox 各一并回读 | 没有真实 LLM 自主完成统一 Bridge S2 的证据 | 浏览器 STOP；无企业队列写入 | 终态 `SCOPE_ESCALATED / PENDING_REVIEW`；无新 Scope，403 未恢复 |
| 普通 Assistant 提议进入专业调查并读回结果 | [`propose_controlled_auth_investigation`](../../../../opspilot/domain/assistant.py#L308)；[`read_session_professional_outcomes`](../../../../opspilot/domain/assistant.py#L519)；API [`app.py`](../../../../opspilot/web/app.py#L692) | R1 Final Bridge 有正式 API/Worker/Domain 定向覆盖、权限反例和历史 77/77 结果 | 真实模型对新 Bridge 提议/读回 S1/S2 结果尚未运行 | 无浏览器 CTA、刷新恢复验收 | 接线/确定性路径有证据；真实 Agent 选择和用户端 Web 连续性未证明 |
| Context、Memory、Skill 与来源时态 | [`assistant.py`](../../../../opspilot/assistant.py#L1244)；[`episodic_memory.py`](../../../../opspilot/domain/episodic_memory.py#L1271)；Skill loader/审计在对应 Assistant 路径 | Context 12K、来源 TTL/撤权、历史投影、Memory ON/OFF 安全测试有离线证据 | AR-04C Memory ON/OFF 曾有真实调用，但 ON J4 对当前重查作错误陈述并 G7 FAIL；F01 定向复验因预算停止；Skill 实际未加载的样本不证明 Skill 效果 | 不推定浏览器或生产效果 | 能力实现存在，效果证据有限且混合；不能声称 Memory 或 Skill 普遍提高质量 |

## 证据来源

- [R1-J2-LIVE-RECHECK-02 真实结果](../r1-j2-live-recheck-02/LIVE_REPORT.md)、[机器结果](../r1-j2-live-recheck-02/LIVE_RESULTS.json)、[费用账本](../r1-j2-live-recheck-02/LIVE_COST_LEDGER.md)。
- [PRODUCT-01 Slice 02 真实四轮旅程](../product-01-slice-02-live/REPORT.md)。
- [S1 本地闭环报告与结果](../../ar-05/s1-d3-close-01/REPORT.md)、[S1 Results](../../ar-05/s1-d3-close-01/RESULTS.json)。
- [S2 本地交接报告与结果](../../ar-05/s2-assistant-handoff-01/REPORT.md)、[S2 Results](../../ar-05/s2-assistant-handoff-01/RESULTS.json)。
- [R1 集成报告](../r1-final-integration-01/INTEGRATION_REPORT.md)、[历史能力矩阵](../r1-final-integration-01/R1_ENGINE_ACCEPTANCE_MATRIX.md)。
- [真实 J2-02 复现性限制](../r1-j2-02-repeat-01/REPORT.md)、[Wire replay 阻断](../r1-j2-02-wire-replay-01/REPORT.md)。
