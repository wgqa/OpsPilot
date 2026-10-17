# OpsPilot D3 运行报告

**结果：** PASS

**运行时间：** 2026-10-17T09:55:35+00:00

**主提交：** f2c940316644e1429734065107c3fc317984ddfa

**范围：** D3 E01 真实模型 / MCP / LangGraph HITL / REPAIR / 在线验证 / 冻结报告 / DELIVER

## 环境与运行命令

- Python：`3.14.0`（Windows-11-10.0.26200-SP0）
- 模型：`deepseek-flash`（密钥不记录）
- 依赖：`{"langchain": "1.4.1", "langchain-openai": "1.7.2", "langgraph": "1.2.16", "langgraph-checkpoint-sqlite": "3.1.2", "mcp": "2.3.0", "pydantic": "2.14.1"}`
- 复现命令：`.venv\Scripts\python.exe -m opspilot.cli d3-smoke --db .runtime\d3-domain.sqlite3 --checkpoint-db .runtime\d3-checkpoints.sqlite3`
- 初始调查进程 PID：`27836`；独立审批与恢复进程 PID：`31148`
- 初始进程命令：`D:\学习\agent新项目\.venv\Scripts\python.exe -m opspilot.cli d3-start --actor support-a --executor executor-a --db D:\学习\agent新项目\.runtime\d6-e10-retry.sqlite3 --checkpoint-db D:\学习\agent新项目\.runtime\d6-e10-retry-checkpoints-d5-smoke-work\task-a-checkpoints.sqlite3`
- 审批恢复命令：`D:\学习\agent新项目\.venv\Scripts\python.exe -m opspilot.cli d3-approve --actor approver-a --thread-id opspilot-23e4dc41-2aab-41ce-93d0-b572b9810db3 --plan-hash b3afabf0466dad4b8e04ba3b224d377e9aa42eec9b0d1a829796ae27ff0798cf --decision APPROVED --executor executor-a --db D:\学习\agent新项目\.runtime\d6-e10-retry.sqlite3 --checkpoint-db D:\学习\agent新项目\.runtime\d6-e10-retry-checkpoints-d5-smoke-work\task-a-checkpoints.sqlite3`
- 真实模型 Function Calling 选择：`get_integration_config → get_auth_policy → get_principal_status → probe_endpoint`；对应 MCP Client/Server 调用：`get_integration_config → get_auth_policy → get_principal_status → probe_endpoint`（完整 Observation/Evidence 在 TRACE.json）。

## 运行结果

- 初始真实业务 Probe：HTTP `401`，请求 `ff2fcc2edb0c12b2`，认证事件 `1`；Gate=`READY`。
- 审批前状态：`cred-v1` / config version `7`，工单处置条目 `0`；受限写入为零。
- LangGraph 在 Plan `b3afabf0466dad4b8e04ba3b224d377e9aa42eec9b0d1a829796ae27ff0798cf` 处等待人工审批；审批人为 `approver-a`，决定 `APPROVED`。
- 两种独立授权消费状态：`{'DELIVER': 'CONSUMED', 'REPAIR': 'CONSUMED'}`。持久 ActionIntent：`DELIVER=action-3a40e2d1-b741-422f-ae03-591057228729 / key=idem-d7259a62-3309-4c0a-a3c2-e64a83cac062 / digest=2878215b49ba8e591feafeb792b42adc79d291af93e46505e7d324a613c0d103; REPAIR=action-674abd82-1dd0-45cb-abc7-05dc55904c0a / key=idem-b893349a-8aef-43e3-9bbb-69d2131d8dd6 / digest=4d1062e967ff8a92d1b62d3ff5d46a628002ba8b3c64bfd5ea7564136a29f04c`。
- REPAIR ledger：`ledger-29bf5cc0-affb-46c0-8b32-546a0e8bf940`，状态 `COMMITTED`，配置版本 `7 → 8`。
- 在线验证：HTTP `200`，`order_id=demo-order`，`status=CONFIRMED`，同 service/integration/principal/route 断言 `True`；request `439625c2167036dc` / auth event `2`；VerificationReceipt=`verification-6df28663-01cc-4a46-8baa-aa63449c66d4`。
- 冻结报告：`report-845db9b9-0963-40c7-90c9-1429903f4464`，SHA-256=`1581b64d0b86810ee078e3487ac0f345bfc78be9065a14dd81ca35c2863ce863`。
- 独立 DELIVER ledger：`ledger-48fa3df5-2524-4b89-bc26-37591f8cf894`，状态 `COMMITTED`；delivery receipt=`{'delivery_action_id': 'action-3a40e2d1-b741-422f-ae03-591057228729', 'report_digest': '1581b64d0b86810ee078e3487ac0f345bfc78be9065a14dd81ca35c2863ce863', 'report_ref': 'report-845db9b9-0963-40c7-90c9-1429903f4464', 'report_version': 1, 'resolution_digest': 'a10d15e0228f5d247bff695d904d1086aef0f035d88003e7f9ec4d37e75efda0', 'status': 'COMMITTED', 'ticket_entry_id': 'ticket-entry-79ec827f-d16c-42c2-9a90-76ed35c1b6f5', 'ticket_id': 'INC-A-001', 'verification_id': 'verification-6df28663-01cc-4a46-8baa-aa63449c66d4'}`；唯一工单处置条目数=`1`。
- 最终业务状态：`RECOVERED`；任务状态=`COMPLETED`。


完整脱敏轨迹见 [`TRACE.json`](TRACE.json)，两个 OS 子进程输出见 [`process_logs.json`](process_logs.json)。

## 已知限制

本轮验证的是本地 SQLite Demo Domain 与固定订单路由；跨进程 HITL 由两个独立 CLI 进程完成。D4 的崩溃窗口/并发响应丢失故障矩阵不在本轮验收范围，不能据此声称生产级 IAM 或分布式 exactly-once。
