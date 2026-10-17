# OpsPilot D3 运行报告

**结果：** PASS

**运行时间：** 2026-10-17T09:25:44+00:00

**主提交：** b744e280d8dfdbf685f02d14908bc2d7fc372cc6

**范围：** D3 E01 真实模型 / MCP / LangGraph HITL / REPAIR / 在线验证 / 冻结报告 / DELIVER

## 环境与运行命令

- Python：`3.14.0`（Windows-11-10.0.26200-SP0）
- 模型：`deepseek-flash`（密钥不记录）
- 依赖：`{"langchain": "1.4.1", "langchain-openai": "1.7.2", "langgraph": "1.2.16", "langgraph-checkpoint-sqlite": "3.1.2", "mcp": "2.3.0", "pydantic": "2.14.1"}`
- 复现命令：`.venv\Scripts\python.exe -m opspilot.cli d3-smoke --db .runtime\d3-domain.sqlite3 --checkpoint-db .runtime\d3-checkpoints.sqlite3`
- 初始调查进程 PID：`27900`；独立审批与恢复进程 PID：`30408`
- 初始进程命令：`D:\学习\agent新项目\.venv\Scripts\python.exe -m opspilot.cli d3-start --actor support-a --executor executor-a --db D:\学习\agent新项目\.runtime\d5-domain.sqlite3 --checkpoint-db D:\学习\agent新项目\.runtime\d5-smoke-work\task-a-checkpoints.sqlite3`
- 审批恢复命令：`D:\学习\agent新项目\.venv\Scripts\python.exe -m opspilot.cli d3-approve --actor approver-a --thread-id opspilot-3cbb0ae1-bc5f-4130-9800-d0ac8b87eb4f --plan-hash ff08c7307cf7aaefece6dd39c24c4184b8ca5281642f398e6272c713d9cbf0c3 --decision APPROVED --executor executor-a --db D:\学习\agent新项目\.runtime\d5-domain.sqlite3 --checkpoint-db D:\学习\agent新项目\.runtime\d5-smoke-work\task-a-checkpoints.sqlite3`
- 真实模型 Function Calling 选择：`get_integration_config → get_principal_status → get_auth_policy → probe_endpoint`；对应 MCP Client/Server 调用：`get_integration_config → get_principal_status → get_auth_policy → probe_endpoint`（完整 Observation/Evidence 在 TRACE.json）。

## 运行结果

- 初始真实业务 Probe：HTTP `401`，请求 `fe929031640fbb20`，认证事件 `13`；Gate=`READY`。
- 审批前状态：`cred-v1` / config version `7`，工单处置条目 `0`；受限写入为零。
- LangGraph 在 Plan `ff08c7307cf7aaefece6dd39c24c4184b8ca5281642f398e6272c713d9cbf0c3` 处等待人工审批；审批人为 `approver-a`，决定 `APPROVED`。
- 两种独立授权消费状态：`{'DELIVER': 'CONSUMED', 'REPAIR': 'CONSUMED'}`。持久 ActionIntent：`DELIVER=action-50df75e5-87a8-4056-9194-e2f7ad60a71b / key=idem-d7a9fb51-9f37-4f9e-9678-2e31bb703ee0 / digest=23eed6ffd920195fbd50147cffbb447396fcf673f9f890d0df5569cb2791c9a3; REPAIR=action-2decb388-fcfe-4f64-8805-5bb16fcb1355 / key=idem-d1afb1ae-9e80-4500-a3d8-d87201baba5e / digest=0e4eff5c0b4f10e4d76b4e664d5cb4e436621646cdf09ec79ad9277927512482`。
- REPAIR ledger：`ledger-e2de3b8f-580d-499a-9582-701e7d429467`，状态 `COMMITTED`，配置版本 `7 → 8`。
- 在线验证：HTTP `200`，`order_id=demo-order`，`status=CONFIRMED`，同 service/integration/principal/route 断言 `True`；request `f693496506679d10` / auth event `14`；VerificationReceipt=`verification-3f2ea5a4-4f68-4bf3-b8ef-68311d8bb00f`。
- 冻结报告：`report-12618b97-f6c6-4c12-b683-5716c6b3f73f`，SHA-256=`93a41660627c46fc0781e7970f8765145823daa058fc879c2bdf08adb0b9e079`。
- 独立 DELIVER ledger：`ledger-5a66ca09-caf7-4b8e-a3a8-eb7f7d6ad705`，状态 `COMMITTED`；delivery receipt=`{'delivery_action_id': 'action-50df75e5-87a8-4056-9194-e2f7ad60a71b', 'report_digest': '93a41660627c46fc0781e7970f8765145823daa058fc879c2bdf08adb0b9e079', 'report_ref': 'report-12618b97-f6c6-4c12-b683-5716c6b3f73f', 'report_version': 1, 'resolution_digest': '1bee9a40eb66ef4908d74985b57290a679f12527f987b836162f02cf5f0d48f7', 'status': 'COMMITTED', 'ticket_entry_id': 'ticket-entry-090377bc-5408-4fee-83a0-96ec0e8a9e62', 'ticket_id': 'INC-A-001', 'verification_id': 'verification-3f2ea5a4-4f68-4bf3-b8ef-68311d8bb00f'}`；唯一工单处置条目数=`1`。
- 最终业务状态：`RECOVERED`；任务状态=`COMPLETED`。


完整脱敏轨迹见 [`TRACE.json`](TRACE.json)，两个 OS 子进程输出见 [`process_logs.json`](process_logs.json)。

## 已知限制

本轮验证的是本地 SQLite Demo Domain 与固定订单路由；跨进程 HITL 由两个独立 CLI 进程完成。D4 的崩溃窗口/并发响应丢失故障矩阵不在本轮验收范围，不能据此声称生产级 IAM 或分布式 exactly-once。
