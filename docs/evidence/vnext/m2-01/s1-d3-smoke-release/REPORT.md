# OpsPilot D3 运行报告

**结果：** PASS

**运行时间：** 2026-10-18T17:16:38+00:00

**主提交：** d32e5c77fa675e12219446c07e1867b194a917d7

**范围：** D3 E01 真实模型 / MCP / LangGraph HITL / REPAIR / 在线验证 / 冻结报告 / DELIVER

## 环境与运行命令

- Python：`3.14.0`（Windows-11-10.0.26200-SP0）
- 模型：`deepseek-flash`（密钥不记录）
- 依赖：`{"langchain": "1.4.1", "langchain-openai": "1.7.2", "langgraph": "1.2.16", "langgraph-checkpoint-sqlite": "3.1.2", "mcp": "2.3.0", "pydantic": "2.14.1"}`
- 复现命令：`.venv\Scripts\python.exe -m opspilot.cli d3-smoke --db .runtime\d3-domain.sqlite3 --checkpoint-db .runtime\d3-checkpoints.sqlite3`
- 初始调查进程 PID：`26800`；独立审批与恢复进程 PID：`30772`
- 初始进程命令：`D:\学习\agent新项目\.venv\Scripts\python.exe -m opspilot.cli d3-start --actor support-a --executor executor-a --db D:\学习\agent新项目\.runtime\m2-01\s1-d3-release-20261019\domain.sqlite3 --checkpoint-db D:\学习\agent新项目\.runtime\m2-01\s1-d3-release-20261019\checkpoints.sqlite3`
- 审批恢复命令：`D:\学习\agent新项目\.venv\Scripts\python.exe -m opspilot.cli d3-approve --actor approver-a --thread-id opspilot-8426bcb7-7e34-46c2-a8b3-9bb05c147359 --plan-hash 3bc163e3c3e0c5d6dde77d614811994ddb4184e02a5618db64e3f9468e6a4ff3 --decision APPROVED --executor executor-a --db D:\学习\agent新项目\.runtime\m2-01\s1-d3-release-20261019\domain.sqlite3 --checkpoint-db D:\学习\agent新项目\.runtime\m2-01\s1-d3-release-20261019\checkpoints.sqlite3`
- 真实模型 Function Calling 选择：`get_integration_config → get_principal_status → get_auth_policy → probe_endpoint`；对应 MCP Client/Server 调用：`get_integration_config → get_principal_status → get_auth_policy → probe_endpoint`（完整 Observation/Evidence 在 TRACE.json）。

## 运行结果

- 初始真实业务 Probe：HTTP `401`，请求 `81189a707b1fdf7e`，认证事件 `1`；Gate=`READY`。
- 审批前状态：`cred-v1` / config version `7`，工单处置条目 `0`；受限写入为零。
- LangGraph 在 Plan `3bc163e3c3e0c5d6dde77d614811994ddb4184e02a5618db64e3f9468e6a4ff3` 处等待人工审批；审批人为 `approver-a`，决定 `APPROVED`。
- 两种独立授权消费状态：`{'DELIVER': 'CONSUMED', 'REPAIR': 'CONSUMED'}`。持久 ActionIntent：`DELIVER=action-179ebc39-bc78-4e7c-9de0-45328b1e9514 / key=idem-839ed520-aa20-4cc9-bb74-9cdc943f0921 / digest=37d678f520e33bcf23df0f901c482b89dc2debadc4cc51411a4eb3f1ef65e5e4; REPAIR=action-1bae6d42-546d-4499-a2d2-d376b5b3a87d / key=idem-7c334f76-8164-4fe6-8368-1f212bf0214e / digest=4e93803cdefb4b76e534d951313991330a889efffdb8d7257e3879fb67141917`。
- REPAIR ledger：`ledger-f8a179d5-e960-432b-a30b-53b4e049e467`，状态 `COMMITTED`，配置版本 `7 → 8`。
- 在线验证：HTTP `200`，`order_id=demo-order`，`status=CONFIRMED`，同 service/integration/principal/route 断言 `True`；request `df09194ecc1a07f9` / auth event `2`；VerificationReceipt=`verification-4712f23d-5ed8-4941-9045-d3473974a0e5`。
- 冻结报告：`report-7317c9b2-8f2e-428e-be08-951479ee522d`，SHA-256=`8f54377a9a0c1a48c91b8cd4b58b289f74c500320e2a0dea5fb638850b55dfd1`。
- 独立 DELIVER ledger：`ledger-c61ea719-ec1a-4847-b48f-948aa652d75c`，状态 `COMMITTED`；delivery receipt=`{'delivery_action_id': 'action-179ebc39-bc78-4e7c-9de0-45328b1e9514', 'report_digest': '8f54377a9a0c1a48c91b8cd4b58b289f74c500320e2a0dea5fb638850b55dfd1', 'report_ref': 'report-7317c9b2-8f2e-428e-be08-951479ee522d', 'report_version': 1, 'resolution_digest': '2f7f9b82589380d2010893d45d8448346972b44dd9bc30ee34222a0486dc6f9c', 'status': 'COMMITTED', 'ticket_entry_id': 'ticket-entry-89354743-db33-46e3-ba0f-995860dfb2f8', 'ticket_id': 'INC-A-001', 'verification_id': 'verification-4712f23d-5ed8-4941-9045-d3473974a0e5'}`；唯一工单处置条目数=`1`。
- 最终业务状态：`RECOVERED`；任务状态=`COMPLETED`。


完整脱敏轨迹见 [`TRACE.json`](TRACE.json)，两个 OS 子进程输出见 [`process_logs.json`](process_logs.json)。

## 已知限制

本轮验证的是本地 SQLite Demo Domain 与固定订单路由；跨进程 HITL 由两个独立 CLI 进程完成。D4 的崩溃窗口/并发响应丢失故障矩阵不在本轮验收范围，不能据此声称生产级 IAM 或分布式 exactly-once。
