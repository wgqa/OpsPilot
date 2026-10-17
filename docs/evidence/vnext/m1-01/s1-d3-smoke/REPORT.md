# OpsPilot D3 运行报告

**结果：** PASS

**运行时间：** 2026-10-17T17:13:18+00:00

**主提交：** a53e13a4243cc6c7fa545b3e3a92b838596b6242

**范围：** D3 E01 真实模型 / MCP / LangGraph HITL / REPAIR / 在线验证 / 冻结报告 / DELIVER

## 环境与运行命令

- Python：`3.14.0`（Windows-11-10.0.26200-SP0）
- 模型：`deepseek-flash`（密钥不记录）
- 依赖：`{"langchain": "1.4.1", "langchain-openai": "1.7.2", "langgraph": "1.2.16", "langgraph-checkpoint-sqlite": "3.1.2", "mcp": "2.3.0", "pydantic": "2.14.1"}`
- 复现命令：`.venv\Scripts\python.exe -m opspilot.cli d3-smoke --db .runtime\d3-domain.sqlite3 --checkpoint-db .runtime\d3-checkpoints.sqlite3`
- 初始调查进程 PID：`35412`；独立审批与恢复进程 PID：`35656`
- 初始进程命令：`D:\学习\agent新项目\.venv\Scripts\python.exe -m opspilot.cli d3-start --actor support-a --executor executor-a --db D:\学习\agent新项目\.runtime\m101-s1-domain.sqlite3 --checkpoint-db D:\学习\agent新项目\.runtime\m101-s1-checkpoints.sqlite3`
- 审批恢复命令：`D:\学习\agent新项目\.venv\Scripts\python.exe -m opspilot.cli d3-approve --actor approver-a --thread-id opspilot-2b0ee3bf-04c8-4988-90f1-f369af6fc356 --plan-hash 8c8bcb09533d2d28d0342ca5ad557881700f5a4dbb6d40daef748690668a6b23 --decision APPROVED --executor executor-a --db D:\学习\agent新项目\.runtime\m101-s1-domain.sqlite3 --checkpoint-db D:\学习\agent新项目\.runtime\m101-s1-checkpoints.sqlite3`
- 真实模型 Function Calling 选择：`get_integration_config → get_auth_policy → get_principal_status → probe_endpoint`；对应 MCP Client/Server 调用：`get_integration_config → get_auth_policy → get_principal_status → probe_endpoint`（完整 Observation/Evidence 在 TRACE.json）。

## 运行结果

- 初始真实业务 Probe：HTTP `401`，请求 `e24d32fd540476b6`，认证事件 `1`；Gate=`READY`。
- 审批前状态：`cred-v1` / config version `7`，工单处置条目 `0`；受限写入为零。
- LangGraph 在 Plan `8c8bcb09533d2d28d0342ca5ad557881700f5a4dbb6d40daef748690668a6b23` 处等待人工审批；审批人为 `approver-a`，决定 `APPROVED`。
- 两种独立授权消费状态：`{'DELIVER': 'CONSUMED', 'REPAIR': 'CONSUMED'}`。持久 ActionIntent：`DELIVER=action-143b8b14-0e1c-407b-a484-49da109908fa / key=idem-2d6b6622-0fca-4c7c-996a-845f34ac1340 / digest=aefebc6d86afa96f99466090ad6f640643c92b2ef4ebaa8f7f84c35eac0a7522; REPAIR=action-065da62c-5673-4a9f-a38b-544f52f7c21c / key=idem-12c0e99f-1e74-4e70-84b2-7361b5a48886 / digest=ff72daad191dd67c01c80a802b72a0132f24acb41f07141890a969134297d51f`。
- REPAIR ledger：`ledger-09d9c884-3785-4a81-9fc8-a4a297d85989`，状态 `COMMITTED`，配置版本 `7 → 8`。
- 在线验证：HTTP `200`，`order_id=demo-order`，`status=CONFIRMED`，同 service/integration/principal/route 断言 `True`；request `891df6f71cd4f135` / auth event `2`；VerificationReceipt=`verification-7bf0c885-db14-4c55-9442-86718ef15fe5`。
- 冻结报告：`report-b2acd6a3-d5c7-45aa-bbd9-61536f4f084f`，SHA-256=`72f37f9fcf4291ace7d3b3299429566b2987e6e91ec3497d93d5ac358dc46c44`。
- 独立 DELIVER ledger：`ledger-9d79d460-f02c-43f4-b1aa-eda14926d7d2`，状态 `COMMITTED`；delivery receipt=`{'delivery_action_id': 'action-143b8b14-0e1c-407b-a484-49da109908fa', 'report_digest': '72f37f9fcf4291ace7d3b3299429566b2987e6e91ec3497d93d5ac358dc46c44', 'report_ref': 'report-b2acd6a3-d5c7-45aa-bbd9-61536f4f084f', 'report_version': 1, 'resolution_digest': '6e7a34efb6fe96968dbfda015777512f2d768e2db5e16b5a02e361e621bec3f2', 'status': 'COMMITTED', 'ticket_entry_id': 'ticket-entry-a89d1b3f-920a-4f2a-b187-5e109fb5ad87', 'ticket_id': 'INC-A-001', 'verification_id': 'verification-7bf0c885-db14-4c55-9442-86718ef15fe5'}`；唯一工单处置条目数=`1`。
- 最终业务状态：`RECOVERED`；任务状态=`COMPLETED`。


完整脱敏轨迹见 [`TRACE.json`](TRACE.json)，两个 OS 子进程输出见 [`process_logs.json`](process_logs.json)。

## 已知限制

本轮验证的是本地 SQLite Demo Domain 与固定订单路由；跨进程 HITL 由两个独立 CLI 进程完成。D4 的崩溃窗口/并发响应丢失故障矩阵不在本轮验收范围，不能据此声称生产级 IAM 或分布式 exactly-once。
