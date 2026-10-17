# OpsPilot D3 运行报告

**结果：** FAIL

**运行时间：** 2026-10-17T10:19:08+00:00

**主提交：** 

**范围：** D3 E01 真实模型 / MCP / LangGraph HITL / REPAIR / 在线验证 / 冻结报告 / DELIVER

## 环境与运行命令

- Python：`3.14.0`（Windows-11-10.0.26200-SP0）
- 模型：`deepseek-flash`（密钥不记录）
- 依赖：`{"langchain": "1.4.1", "langchain-openai": "1.7.2", "langgraph": "1.2.16", "langgraph-checkpoint-sqlite": "3.1.2", "mcp": "2.3.0", "pydantic": "2.14.1"}`
- 复现命令：`.venv\Scripts\python.exe -m opspilot.cli d3-smoke --db .runtime\d3-domain.sqlite3 --checkpoint-db .runtime\d3-checkpoints.sqlite3`
- 初始调查进程 PID：`24940`；独立审批与恢复进程 PID：`None`
- 初始进程命令：`D:\学习\OpsPilot-D7-repro-20261017T101609Z\.venv\Scripts\python.exe -m opspilot.cli d3-start --actor support-a --executor executor-a --db D:\学习\OpsPilot-D7-repro-20261017T101609Z\.runtime\d7-e01.sqlite3 --checkpoint-db D:\学习\OpsPilot-D7-repro-20261017T101609Z\.runtime\d7-e01-checkpoints.sqlite3`
- 审批恢复命令：``
- 真实模型 Function Calling 选择：``；对应 MCP Client/Server 调用：``（完整 Observation/Evidence 在 TRACE.json）。

## 运行结果

- 初始真实业务 Probe：HTTP `None`，请求 `None`，认证事件 `None`；Gate=`None`。
- 审批前状态：`cred-v1` / config version `7`，工单处置条目 `0`；受限写入为零。
- LangGraph 在 Plan `None` 处等待人工审批；审批人为 `None`，决定 `None`。
- 两种独立授权消费状态：`{}`。持久 ActionIntent：``。
- REPAIR ledger：`None`，状态 `None`，配置版本 `None → None`。
- 在线验证：HTTP `None`，`order_id=None`，`status=None`，同 service/integration/principal/route 断言 `False`；request `None` / auth event `None`；VerificationReceipt=`None`。
- 冻结报告：`None`，SHA-256=`None`。
- 独立 DELIVER ledger：`None`，状态 `None`；delivery receipt=`{}`；唯一工单处置条目数=`0`。
- 最终业务状态：`None`；任务状态=`None`。
- 失败原因：real_initial_401_evidence, gate_ready_and_plan_hash, graph_checkpoint_stores_references_only, processes_are_distinct, independent_approver, repair_committed_once, same_identity_online_200, frozen_report_before_delivery, independent_deliver_committed_once, both_action_intents_persisted, business_outcome_recovered, model_and_mcp_trajectory_present

完整脱敏轨迹见 [`TRACE.json`](TRACE.json)，两个 OS 子进程输出见 [`process_logs.json`](process_logs.json)。

## 已知限制

本轮验证的是本地 SQLite Demo Domain 与固定订单路由；跨进程 HITL 由两个独立 CLI 进程完成。D4 的崩溃窗口/并发响应丢失故障矩阵不在本轮验收范围，不能据此声称生产级 IAM 或分布式 exactly-once。
