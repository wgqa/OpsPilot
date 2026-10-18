# OpsPilot D3 运行报告

**结果：** PASS

**运行时间：** 2026-10-18T17:07:32+00:00

**主提交：** 832dd632dd0ed27201015a4e66f50e1a4771fec1

**范围：** D3 E01 真实模型 / MCP / LangGraph HITL / REPAIR / 在线验证 / 冻结报告 / DELIVER

## 环境与运行命令

- Python：`3.14.0`（Windows-11-10.0.26200-SP0）
- 模型：`deepseek-flash`（密钥不记录）
- 依赖：`{"langchain": "1.4.1", "langchain-openai": "1.7.2", "langgraph": "1.2.16", "langgraph-checkpoint-sqlite": "3.1.2", "mcp": "2.3.0", "pydantic": "2.14.1"}`
- 复现命令：`.venv\Scripts\python.exe -m opspilot.cli d3-smoke --db .runtime\d3-domain.sqlite3 --checkpoint-db .runtime\d3-checkpoints.sqlite3`
- 初始调查进程 PID：`29068`；独立审批与恢复进程 PID：`33604`
- 初始进程命令：`D:\学习\agent新项目\.venv\Scripts\python.exe -m opspilot.cli d3-start --actor support-a --executor executor-a --db D:\学习\agent新项目\.runtime\m2-01\s1-d3-20261019\domain.sqlite3 --checkpoint-db D:\学习\agent新项目\.runtime\m2-01\s1-d3-20261019\checkpoints.sqlite3`
- 审批恢复命令：`D:\学习\agent新项目\.venv\Scripts\python.exe -m opspilot.cli d3-approve --actor approver-a --thread-id opspilot-17174bdd-d1b7-431d-b368-6db3eb0f9e7d --plan-hash b393510dc965d68e3273488b56e9e8b452a9247e5e2ab355d89510f26ec8c021 --decision APPROVED --executor executor-a --db D:\学习\agent新项目\.runtime\m2-01\s1-d3-20261019\domain.sqlite3 --checkpoint-db D:\学习\agent新项目\.runtime\m2-01\s1-d3-20261019\checkpoints.sqlite3`
- 真实模型 Function Calling 选择：`get_integration_config → get_principal_status → get_auth_policy → probe_endpoint`；对应 MCP Client/Server 调用：`get_integration_config → get_principal_status → get_auth_policy → probe_endpoint`（完整 Observation/Evidence 在 TRACE.json）。

## 运行结果

- 初始真实业务 Probe：HTTP `401`，请求 `81663801db01db0a`，认证事件 `1`；Gate=`READY`。
- 审批前状态：`cred-v1` / config version `7`，工单处置条目 `0`；受限写入为零。
- LangGraph 在 Plan `b393510dc965d68e3273488b56e9e8b452a9247e5e2ab355d89510f26ec8c021` 处等待人工审批；审批人为 `approver-a`，决定 `APPROVED`。
- 两种独立授权消费状态：`{'DELIVER': 'CONSUMED', 'REPAIR': 'CONSUMED'}`。持久 ActionIntent：`DELIVER=action-c11c7cba-0dd6-4bd9-9963-d6634021a292 / key=idem-b51c4aa2-01e0-4291-926a-b69a082aa90d / digest=b6f6b47dfe78fa5c66139c54c50c3136bba1c83e6c3256ecaec4be715390623f; REPAIR=action-01297b3e-dff7-4bdf-a7fa-e27523c3a805 / key=idem-63db0558-300a-48d7-864b-029a35c41d1f / digest=882361c2425a0bc524a0935ee837121b602f94216a071c87bd7e171fc98110c5`。
- REPAIR ledger：`ledger-ff6b52f8-a62a-47f5-aa0c-47804b70b020`，状态 `COMMITTED`，配置版本 `7 → 8`。
- 在线验证：HTTP `200`，`order_id=demo-order`，`status=CONFIRMED`，同 service/integration/principal/route 断言 `True`；request `873e4abea6b39c41` / auth event `2`；VerificationReceipt=`verification-27ca7ded-6861-4913-a313-1941f778dfe2`。
- 冻结报告：`report-0bc0bf81-a91a-437b-8754-2a5bb1cfcb49`，SHA-256=`09794fdd1f791775de7b5eee8aa95e38a6abaea1b234e59105896f6f21df9e11`。
- 独立 DELIVER ledger：`ledger-f2859e5b-3d04-4a78-a4bb-f972ad7e03b2`，状态 `COMMITTED`；delivery receipt=`{'delivery_action_id': 'action-c11c7cba-0dd6-4bd9-9963-d6634021a292', 'report_digest': '09794fdd1f791775de7b5eee8aa95e38a6abaea1b234e59105896f6f21df9e11', 'report_ref': 'report-0bc0bf81-a91a-437b-8754-2a5bb1cfcb49', 'report_version': 1, 'resolution_digest': '9df36b333d2c75945eaaa1ef943325f1d4ac679bcfa113bbacc7433343b23f82', 'status': 'COMMITTED', 'ticket_entry_id': 'ticket-entry-d5bb4c5a-529d-4265-9475-8f1c361bfaca', 'ticket_id': 'INC-A-001', 'verification_id': 'verification-27ca7ded-6861-4913-a313-1941f778dfe2'}`；唯一工单处置条目数=`1`。
- 最终业务状态：`RECOVERED`；任务状态=`COMPLETED`。


完整脱敏轨迹见 [`TRACE.json`](TRACE.json)，两个 OS 子进程输出见 [`process_logs.json`](process_logs.json)。

## 已知限制

本轮验证的是本地 SQLite Demo Domain 与固定订单路由；跨进程 HITL 由两个独立 CLI 进程完成。D4 的崩溃窗口/并发响应丢失故障矩阵不在本轮验收范围，不能据此声称生产级 IAM 或分布式 exactly-once。
