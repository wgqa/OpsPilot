# OpsPilot D3 运行报告

**结果：** PASS

**运行时间：** 2026-10-18T17:10:35+00:00

**主提交：** 832dd632dd0ed27201015a4e66f50e1a4771fec1

**范围：** D3 E01 真实模型 / MCP / LangGraph HITL / REPAIR / 在线验证 / 冻结报告 / DELIVER

## 环境与运行命令

- Python：`3.14.0`（Windows-11-10.0.26200-SP0）
- 模型：`deepseek-flash`（密钥不记录）
- 依赖：`{"langchain": "1.4.1", "langchain-openai": "1.7.2", "langgraph": "1.2.16", "langgraph-checkpoint-sqlite": "3.1.2", "mcp": "2.3.0", "pydantic": "2.14.1"}`
- 复现命令：`.venv\Scripts\python.exe -m opspilot.cli d3-smoke --db .runtime\d3-domain.sqlite3 --checkpoint-db .runtime\d3-checkpoints.sqlite3`
- 初始调查进程 PID：`17936`；独立审批与恢复进程 PID：`23876`
- 初始进程命令：`D:\学习\agent新项目\.venv\Scripts\python.exe -m opspilot.cli d3-start --actor support-a --executor executor-a --db D:\学习\agent新项目\.runtime\m2-01\s1-d3-20261019-final\domain.sqlite3 --checkpoint-db D:\学习\agent新项目\.runtime\m2-01\s1-d3-20261019-final\checkpoints.sqlite3`
- 审批恢复命令：`D:\学习\agent新项目\.venv\Scripts\python.exe -m opspilot.cli d3-approve --actor approver-a --thread-id opspilot-edaba2da-1a0c-4799-bed1-f062a78b5540 --plan-hash e2656750215568e3a320570c8d6cb27ecead9db1ea82ff6fb66148d5d225d586 --decision APPROVED --executor executor-a --db D:\学习\agent新项目\.runtime\m2-01\s1-d3-20261019-final\domain.sqlite3 --checkpoint-db D:\学习\agent新项目\.runtime\m2-01\s1-d3-20261019-final\checkpoints.sqlite3`
- 真实模型 Function Calling 选择：`get_integration_config → get_auth_policy → get_principal_status → probe_endpoint`；对应 MCP Client/Server 调用：`get_integration_config → get_auth_policy → get_principal_status → probe_endpoint`（完整 Observation/Evidence 在 TRACE.json）。

## 运行结果

- 初始真实业务 Probe：HTTP `401`，请求 `203c229cd6f5d393`，认证事件 `1`；Gate=`READY`。
- 审批前状态：`cred-v1` / config version `7`，工单处置条目 `0`；受限写入为零。
- LangGraph 在 Plan `e2656750215568e3a320570c8d6cb27ecead9db1ea82ff6fb66148d5d225d586` 处等待人工审批；审批人为 `approver-a`，决定 `APPROVED`。
- 两种独立授权消费状态：`{'DELIVER': 'CONSUMED', 'REPAIR': 'CONSUMED'}`。持久 ActionIntent：`DELIVER=action-badd3012-69bd-4bea-afb8-544cded41cd8 / key=idem-aa9cca6a-f7e1-45cb-bc47-e84ef09b1fba / digest=8c2d682332f7d62e7cd5a2cfddb5c98ef725a30c1e5931e03883c2c8c4f68051; REPAIR=action-dea8ace9-d222-4d93-9e30-1bd49218a2e4 / key=idem-27d19167-5d09-4882-a42c-b7c227685ee3 / digest=e151ae1a2ccb9f0d026a302d7f4b6507a1461add66f42086a71cda5080def107`。
- REPAIR ledger：`ledger-44ddc1b2-b2b9-43ab-a278-7c52c11176df`，状态 `COMMITTED`，配置版本 `7 → 8`。
- 在线验证：HTTP `200`，`order_id=demo-order`，`status=CONFIRMED`，同 service/integration/principal/route 断言 `True`；request `99105137cb2ec4cb` / auth event `2`；VerificationReceipt=`verification-56a205bd-670a-4d39-926c-5b5f3a32277f`。
- 冻结报告：`report-affa171f-c215-4052-bc98-91d9a3d4b57b`，SHA-256=`cc09b6994015418d56e3c1e87bce8ac23c71eb7324d1cc8263429afbe8f289f4`。
- 独立 DELIVER ledger：`ledger-a6afec5c-3285-4816-9308-70b752625c17`，状态 `COMMITTED`；delivery receipt=`{'delivery_action_id': 'action-badd3012-69bd-4bea-afb8-544cded41cd8', 'report_digest': 'cc09b6994015418d56e3c1e87bce8ac23c71eb7324d1cc8263429afbe8f289f4', 'report_ref': 'report-affa171f-c215-4052-bc98-91d9a3d4b57b', 'report_version': 1, 'resolution_digest': '8d27320f030b819fad4db832fa42936cea66bbef8d09edb077e01b0605da4cf6', 'status': 'COMMITTED', 'ticket_entry_id': 'ticket-entry-2b3cb089-393f-4593-93a3-345b4d39d911', 'ticket_id': 'INC-A-001', 'verification_id': 'verification-56a205bd-670a-4d39-926c-5b5f3a32277f'}`；唯一工单处置条目数=`1`。
- 最终业务状态：`RECOVERED`；任务状态=`COMPLETED`。


完整脱敏轨迹见 [`TRACE.json`](TRACE.json)，两个 OS 子进程输出见 [`process_logs.json`](process_logs.json)。

## 已知限制

本轮验证的是本地 SQLite Demo Domain 与固定订单路由；跨进程 HITL 由两个独立 CLI 进程完成。D4 的崩溃窗口/并发响应丢失故障矩阵不在本轮验收范围，不能据此声称生产级 IAM 或分布式 exactly-once。
