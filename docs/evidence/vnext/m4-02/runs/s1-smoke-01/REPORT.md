# OpsPilot D3 运行报告

**结果：** PASS

**运行时间：** 2026-10-22T18:18:57+00:00

**主提交：** 23c6c1c2345506c4d19b5cfc1c43c85e245c6843

**范围：** D3 E01 真实模型 / MCP / LangGraph HITL / REPAIR / 在线验证 / 冻结报告 / DELIVER

## 环境与运行命令

- Python：`3.14.0`（Windows-11-10.0.26200-SP0）
- 模型：`deepseek-flash`（密钥不记录）
- 依赖：`{"langchain": "1.4.1", "langchain-openai": "1.7.2", "langgraph": "1.2.16", "langgraph-checkpoint-sqlite": "3.1.2", "mcp": "2.3.0", "pydantic": "2.14.1"}`
- 复现命令：`.venv\Scripts\python.exe -m opspilot.cli d3-smoke --db .runtime\d3-domain.sqlite3 --checkpoint-db .runtime\d3-checkpoints.sqlite3`
- 初始调查进程 PID：`36152`；独立审批与恢复进程 PID：`29256`
- 初始进程命令：`D:\学习\agent新项目\.venv\Scripts\python.exe -m opspilot.cli d3-start --actor support-a --executor executor-a --db D:\学习\agent新项目\.runtime\m4-02\s1-smoke-01.sqlite3 --checkpoint-db D:\学习\agent新项目\.runtime\m4-02\s1-smoke-01.checkpoints.sqlite3`
- 审批恢复命令：`D:\学习\agent新项目\.venv\Scripts\python.exe -m opspilot.cli d3-approve --actor approver-a --thread-id opspilot-c8ef1ea6-9ecb-49eb-90d6-f83bbae0d738 --plan-hash 0f79ff7db0a0662c7de19ff81be92d57e2772dc666dc3292ba1f808a9bf8d866 --decision APPROVED --executor executor-a --db D:\学习\agent新项目\.runtime\m4-02\s1-smoke-01.sqlite3 --checkpoint-db D:\学习\agent新项目\.runtime\m4-02\s1-smoke-01.checkpoints.sqlite3`
- 真实模型 Function Calling 选择：`probe_endpoint → get_auth_policy → get_principal_status → get_integration_config`；对应 MCP Client/Server 调用：`probe_endpoint → get_auth_policy → get_principal_status → get_integration_config`（完整 Observation/Evidence 在 TRACE.json）。

## 运行结果

- 初始真实业务 Probe：HTTP `401`，请求 `6340147e21386aeb`，认证事件 `1`；Gate=`READY`。
- 审批前状态：`cred-v1` / config version `7`，工单处置条目 `0`；受限写入为零。
- LangGraph 在 Plan `0f79ff7db0a0662c7de19ff81be92d57e2772dc666dc3292ba1f808a9bf8d866` 处等待人工审批；审批人为 `approver-a`，决定 `APPROVED`。
- 两种独立授权消费状态：`{'DELIVER': 'CONSUMED', 'REPAIR': 'CONSUMED'}`。持久 ActionIntent：`DELIVER=action-b0ce13bb-f900-497a-9434-689e4c8221dd / key=idem-361e47cb-9328-447d-b970-b0a064a7d9ee / digest=c369193d02aaae0f1b9b3e6bf7853385e0b6d1879ce09f4537ad5c54828c6fa5; REPAIR=action-af902426-354b-47d2-aad4-fe83b05bbf7c / key=idem-2be1e5dc-a54e-40b8-84bd-fc6a6934362c / digest=c26f9706b7ae340e1aa132e72c0046fbdbdce8bafad6071f12efe9645bf6dd7f`。
- REPAIR ledger：`ledger-0e65a94c-3dd3-4b0c-bab7-25655e940f5e`，状态 `COMMITTED`，配置版本 `7 → 8`。
- 在线验证：HTTP `200`，`order_id=demo-order`，`status=CONFIRMED`，同 service/integration/principal/route 断言 `True`；request `b46df13dc52d5aae` / auth event `2`；VerificationReceipt=`verification-56e7a049-d885-455c-a40e-afa257460596`。
- 冻结报告：`report-dfbdb7fe-458f-4e06-8073-28c41eaa6d4f`，SHA-256=`6bf8b9c12c5a5533e6cc8ed12a6c36b70f3e9f2d8d46256b047400ac19a9b691`。
- 独立 DELIVER ledger：`ledger-09432861-2c37-410f-b275-054b82fc0011`，状态 `COMMITTED`；delivery receipt=`{'delivery_action_id': 'action-b0ce13bb-f900-497a-9434-689e4c8221dd', 'report_digest': '6bf8b9c12c5a5533e6cc8ed12a6c36b70f3e9f2d8d46256b047400ac19a9b691', 'report_ref': 'report-dfbdb7fe-458f-4e06-8073-28c41eaa6d4f', 'report_version': 1, 'resolution_digest': '090d2d1f9de9d219d7fd1a6d8bd793040ab0e3098733399b642db0691aadbf9e', 'status': 'COMMITTED', 'ticket_entry_id': 'ticket-entry-d945637f-5cbf-477e-bbf0-096e5706c0a6', 'ticket_id': 'INC-A-001', 'verification_id': 'verification-56e7a049-d885-455c-a40e-afa257460596'}`；唯一工单处置条目数=`1`。
- 最终业务状态：`RECOVERED`；任务状态=`COMPLETED`。


完整脱敏轨迹见 [`TRACE.json`](TRACE.json)，两个 OS 子进程输出见 [`process_logs.json`](process_logs.json)。

## 已知限制

本轮验证的是本地 SQLite Demo Domain 与固定订单路由；跨进程 HITL 由两个独立 CLI 进程完成。D4 的崩溃窗口/并发响应丢失故障矩阵不在本轮验收范围，不能据此声称生产级 IAM 或分布式 exactly-once。
