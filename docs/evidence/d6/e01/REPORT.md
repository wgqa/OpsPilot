# OpsPilot D3 运行报告

**结果：** PASS

**运行时间：** 2026-10-17T09:51:08+00:00

**主提交：** 151a1cea2ea23fa7413abbbd89d5ed6fd173da9c

**范围：** D3 E01 真实模型 / MCP / LangGraph HITL / REPAIR / 在线验证 / 冻结报告 / DELIVER

## 环境与运行命令

- Python：`3.14.0`（Windows-11-10.0.26200-SP0）
- 模型：`deepseek-flash`（密钥不记录）
- 依赖：`{"langchain": "1.4.1", "langchain-openai": "1.7.2", "langgraph": "1.2.16", "langgraph-checkpoint-sqlite": "3.1.2", "mcp": "2.3.0", "pydantic": "2.14.1"}`
- 复现命令：`.venv\Scripts\python.exe -m opspilot.cli d3-smoke --db .runtime\d3-domain.sqlite3 --checkpoint-db .runtime\d3-checkpoints.sqlite3`
- 初始调查进程 PID：`35560`；独立审批与恢复进程 PID：`11868`
- 初始进程命令：`D:\学习\agent新项目\.venv\Scripts\python.exe -m opspilot.cli d3-start --actor support-a --executor executor-a --db D:\学习\agent新项目\.runtime\d6-e01.sqlite3 --checkpoint-db D:\学习\agent新项目\.runtime\d6-e01-checkpoints.sqlite3`
- 审批恢复命令：`D:\学习\agent新项目\.venv\Scripts\python.exe -m opspilot.cli d3-approve --actor approver-a --thread-id opspilot-1d68b570-42dd-475b-b8f8-28977395a7a0 --plan-hash 7335abd485430b4468acde45f7ca5ca1b7d3e71d198568bdd06832529263e764 --decision APPROVED --executor executor-a --db D:\学习\agent新项目\.runtime\d6-e01.sqlite3 --checkpoint-db D:\学习\agent新项目\.runtime\d6-e01-checkpoints.sqlite3`
- 真实模型 Function Calling 选择：`get_integration_config → get_principal_status → get_auth_policy → probe_endpoint`；对应 MCP Client/Server 调用：`get_integration_config → get_principal_status → get_auth_policy → probe_endpoint`（完整 Observation/Evidence 在 TRACE.json）。

## 运行结果

- 初始真实业务 Probe：HTTP `401`，请求 `4fc8e68ba5953454`，认证事件 `1`；Gate=`READY`。
- 审批前状态：`cred-v1` / config version `7`，工单处置条目 `0`；受限写入为零。
- LangGraph 在 Plan `7335abd485430b4468acde45f7ca5ca1b7d3e71d198568bdd06832529263e764` 处等待人工审批；审批人为 `approver-a`，决定 `APPROVED`。
- 两种独立授权消费状态：`{'DELIVER': 'CONSUMED', 'REPAIR': 'CONSUMED'}`。持久 ActionIntent：`DELIVER=action-c8609e83-a16f-4a51-9fb6-dee05f564e0e / key=idem-7366429e-7d80-43e0-8ad3-8d98311b0504 / digest=708c1ea3ca4a4b00aaae84bccd5ed0bff108b4755988ee18a288c0498a38fcf7; REPAIR=action-eec0312d-0781-4fa6-8581-fc0edb6fc108 / key=idem-ea0a0410-b267-4636-9bb4-e26d643d7320 / digest=725e5952e756e38c628c63c6278f6124b1554aae490ff45ff00af276ef252936`。
- REPAIR ledger：`ledger-b61025eb-ab9d-4d95-990d-c81c3d10252d`，状态 `COMMITTED`，配置版本 `7 → 8`。
- 在线验证：HTTP `200`，`order_id=demo-order`，`status=CONFIRMED`，同 service/integration/principal/route 断言 `True`；request `c29baa12ef847f37` / auth event `2`；VerificationReceipt=`verification-cba94895-81af-48a0-9f80-c3e7aff3581f`。
- 冻结报告：`report-59f934fa-f2f7-4b02-96c9-431f79bfd47d`，SHA-256=`486f75f7bc57d488efb85b782536b8479f461a1aac90a2394a5dca8e54d8c183`。
- 独立 DELIVER ledger：`ledger-0882ffcf-cb47-4f10-92c8-cf1df8db25b9`，状态 `COMMITTED`；delivery receipt=`{'delivery_action_id': 'action-c8609e83-a16f-4a51-9fb6-dee05f564e0e', 'report_digest': '486f75f7bc57d488efb85b782536b8479f461a1aac90a2394a5dca8e54d8c183', 'report_ref': 'report-59f934fa-f2f7-4b02-96c9-431f79bfd47d', 'report_version': 1, 'resolution_digest': '6a6c731e363590001d97c4f56d0e66309d6f006ffeb09ed3b17c26d536d49aec', 'status': 'COMMITTED', 'ticket_entry_id': 'ticket-entry-06b5126b-be46-4a77-a4d2-693d45aac23a', 'ticket_id': 'INC-A-001', 'verification_id': 'verification-cba94895-81af-48a0-9f80-c3e7aff3581f'}`；唯一工单处置条目数=`1`。
- 最终业务状态：`RECOVERED`；任务状态=`COMPLETED`。


完整脱敏轨迹见 [`TRACE.json`](TRACE.json)，两个 OS 子进程输出见 [`process_logs.json`](process_logs.json)。

## 已知限制

本轮验证的是本地 SQLite Demo Domain 与固定订单路由；跨进程 HITL 由两个独立 CLI 进程完成。D4 的崩溃窗口/并发响应丢失故障矩阵不在本轮验收范围，不能据此声称生产级 IAM 或分布式 exactly-once。
