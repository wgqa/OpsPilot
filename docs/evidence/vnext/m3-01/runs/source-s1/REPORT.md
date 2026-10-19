# OpsPilot D3 运行报告

**结果：** PASS

**运行时间：** 2026-10-19T16:03:20+00:00

**主提交：** c419e59507c7f7f3863b4e265c7bd10bc4c50c5c

**范围：** D3 E01 真实模型 / MCP / LangGraph HITL / REPAIR / 在线验证 / 冻结报告 / DELIVER

## 环境与运行命令

- Python：`3.14.0`（Windows-11-10.0.26200-SP0）
- 模型：`deepseek-flash`（密钥不记录）
- 依赖：`{"langchain": "1.4.1", "langchain-openai": "1.7.2", "langgraph": "1.2.16", "langgraph-checkpoint-sqlite": "3.1.2", "mcp": "2.3.0", "pydantic": "2.14.1"}`
- 复现命令：`.venv\Scripts\python.exe -m opspilot.cli d3-smoke --db .runtime\d3-domain.sqlite3 --checkpoint-db .runtime\d3-checkpoints.sqlite3`
- 初始调查进程 PID：`7988`；独立审批与恢复进程 PID：`15800`
- 初始进程命令：`D:\学习\agent新项目\.venv\Scripts\python.exe -m opspilot.cli d3-start --actor support-a --executor executor-a --db D:\学习\agent新项目\.runtime\m301-source-s1.sqlite3 --checkpoint-db D:\学习\agent新项目\.runtime\m301-source-s1-checkpoints.sqlite3`
- 审批恢复命令：`D:\学习\agent新项目\.venv\Scripts\python.exe -m opspilot.cli d3-approve --actor approver-a --thread-id opspilot-23742ab6-043a-4b1e-871a-fdcf8873606b --plan-hash 5ae53e36ad311af8b5637bbf17d2648cc252db0865e41753bde6cf56a459020a --decision APPROVED --executor executor-a --db D:\学习\agent新项目\.runtime\m301-source-s1.sqlite3 --checkpoint-db D:\学习\agent新项目\.runtime\m301-source-s1-checkpoints.sqlite3`
- 真实模型 Function Calling 选择：`probe_endpoint → get_principal_status → get_auth_policy → get_integration_config`；对应 MCP Client/Server 调用：`probe_endpoint → get_principal_status → get_auth_policy → get_integration_config`（完整 Observation/Evidence 在 TRACE.json）。

## 运行结果

- 初始真实业务 Probe：HTTP `401`，请求 `84fbc3fe42dfeaf8`，认证事件 `1`；Gate=`READY`。
- 审批前状态：`cred-v1` / config version `7`，工单处置条目 `0`；受限写入为零。
- LangGraph 在 Plan `5ae53e36ad311af8b5637bbf17d2648cc252db0865e41753bde6cf56a459020a` 处等待人工审批；审批人为 `approver-a`，决定 `APPROVED`。
- 两种独立授权消费状态：`{'DELIVER': 'CONSUMED', 'REPAIR': 'CONSUMED'}`。持久 ActionIntent：`DELIVER=action-5d53b4b8-10f5-42b5-a2ba-8af66c572fae / key=idem-f48e2dd8-1a8f-4427-aadc-48bfbb541a14 / digest=f0bd55d70eb6f5d0d39c7881f305932f9ad03aac496c84a0893dfdac93e01648; REPAIR=action-f1d79947-bfd8-420f-b8b0-3c97df1a51cb / key=idem-d97c1a40-dab3-4fcd-acd5-66a024fe0dbf / digest=1ea5308ab6b3448c7b26b85ecb0d61925880af51c628f966df92ec13a31b05aa`。
- REPAIR ledger：`ledger-152633ec-89aa-4d7e-aeea-b6c0a42fdfe3`，状态 `COMMITTED`，配置版本 `7 → 8`。
- 在线验证：HTTP `200`，`order_id=demo-order`，`status=CONFIRMED`，同 service/integration/principal/route 断言 `True`；request `a9a9e1da33c52938` / auth event `2`；VerificationReceipt=`verification-11130c26-463a-4393-89d0-fa180bdfad98`。
- 冻结报告：`report-8a38cdb1-fab3-4443-9cf5-b153865aa069`，SHA-256=`5554c9964d6cb5b7f59f450de84cd60f22ef1386f3084642929082db4d3dcad8`。
- 独立 DELIVER ledger：`ledger-f0edb9a9-e6ef-4754-827d-c21c8b5f25a4`，状态 `COMMITTED`；delivery receipt=`{'delivery_action_id': 'action-5d53b4b8-10f5-42b5-a2ba-8af66c572fae', 'report_digest': '5554c9964d6cb5b7f59f450de84cd60f22ef1386f3084642929082db4d3dcad8', 'report_ref': 'report-8a38cdb1-fab3-4443-9cf5-b153865aa069', 'report_version': 1, 'resolution_digest': 'd01e03af98b3425b9a1faeb70898d923e61862ece41d7a1f96c9afa86d34ff65', 'status': 'COMMITTED', 'ticket_entry_id': 'ticket-entry-b0c07885-47dc-4120-ba72-70f6aa6672f0', 'ticket_id': 'INC-A-001', 'verification_id': 'verification-11130c26-463a-4393-89d0-fa180bdfad98'}`；唯一工单处置条目数=`1`。
- 最终业务状态：`RECOVERED`；任务状态=`COMPLETED`。


完整脱敏轨迹见 [`TRACE.json`](TRACE.json)，两个 OS 子进程输出见 [`process_logs.json`](process_logs.json)。

## 已知限制

本轮验证的是本地 SQLite Demo Domain 与固定订单路由；跨进程 HITL 由两个独立 CLI 进程完成。D4 的崩溃窗口/并发响应丢失故障矩阵不在本轮验收范围，不能据此声称生产级 IAM 或分布式 exactly-once。
