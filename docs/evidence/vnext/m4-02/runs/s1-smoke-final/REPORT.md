# OpsPilot D3 运行报告

**结果：** PASS

**运行时间：** 2026-10-22T18:43:14+00:00

**主提交：** 8aa3f6fca9f6b5aecc03a17b085611784f7b91c4

**范围：** D3 E01 真实模型 / MCP / LangGraph HITL / REPAIR / 在线验证 / 冻结报告 / DELIVER

## 环境与运行命令

- Python：`3.14.0`（Windows-11-10.0.26200-SP0）
- 模型：`deepseek-flash`（密钥不记录）
- 依赖：`{"langchain": "1.4.1", "langchain-openai": "1.7.2", "langgraph": "1.2.16", "langgraph-checkpoint-sqlite": "3.1.2", "mcp": "2.3.0", "pydantic": "2.14.1"}`
- 复现命令：`.venv\Scripts\python.exe -m opspilot.cli d3-smoke --db .runtime\d3-domain.sqlite3 --checkpoint-db .runtime\d3-checkpoints.sqlite3`
- 初始调查进程 PID：`28452`；独立审批与恢复进程 PID：`33228`
- 初始进程命令：`D:\学习\agent新项目\.venv\Scripts\python.exe -m opspilot.cli d3-start --actor support-a --executor executor-a --db D:\学习\agent新项目\.runtime\m4-02\s1-smoke-final.sqlite3 --checkpoint-db D:\学习\agent新项目\.runtime\m4-02\s1-smoke-final.checkpoints.sqlite3`
- 审批恢复命令：`D:\学习\agent新项目\.venv\Scripts\python.exe -m opspilot.cli d3-approve --actor approver-a --thread-id opspilot-f27e015c-9d02-4549-989b-8a3adbd2ff2c --plan-hash 48b78b3a323e29fe17fac46bb3438e476a874aac8c3c0a0c03d1d96a727264bf --decision APPROVED --executor executor-a --db D:\学习\agent新项目\.runtime\m4-02\s1-smoke-final.sqlite3 --checkpoint-db D:\学习\agent新项目\.runtime\m4-02\s1-smoke-final.checkpoints.sqlite3`
- 真实模型 Function Calling 选择：`probe_endpoint → get_principal_status → get_auth_policy → get_integration_config`；对应 MCP Client/Server 调用：`probe_endpoint → get_principal_status → get_auth_policy → get_integration_config`（完整 Observation/Evidence 在 TRACE.json）。

## 运行结果

- 初始真实业务 Probe：HTTP `401`，请求 `cfc9669640b9bf3a`，认证事件 `1`；Gate=`READY`。
- 审批前状态：`cred-v1` / config version `7`，工单处置条目 `0`；受限写入为零。
- LangGraph 在 Plan `48b78b3a323e29fe17fac46bb3438e476a874aac8c3c0a0c03d1d96a727264bf` 处等待人工审批；审批人为 `approver-a`，决定 `APPROVED`。
- 两种独立授权消费状态：`{'DELIVER': 'CONSUMED', 'REPAIR': 'CONSUMED'}`。持久 ActionIntent：`DELIVER=action-1b4150be-e874-495f-8218-5f9128fecfc5 / key=idem-fb785395-dc82-4b73-9de8-eae91ffe1611 / digest=fdf20b7cef96d1fbc0673577d5422b034f36ec68492e2441226e8bf0300231f0; REPAIR=action-570e4989-9faa-4b38-92f3-a0c036ce16a0 / key=idem-92daf23c-2dca-454e-95d9-639e2e1e738d / digest=672ec454da93357cb1ac0087361b37cc5050b441509b51c7f5bc056ac89b0a5c`。
- REPAIR ledger：`ledger-f6f66991-52da-4f55-9224-ab8602904abc`，状态 `COMMITTED`，配置版本 `7 → 8`。
- 在线验证：HTTP `200`，`order_id=demo-order`，`status=CONFIRMED`，同 service/integration/principal/route 断言 `True`；request `c6a73de021b6ac6c` / auth event `2`；VerificationReceipt=`verification-c1d51be8-6b00-47ef-8160-d09b8b203916`。
- 冻结报告：`report-87ea6d8f-518b-4d34-ab2c-1adda88fb8d0`，SHA-256=`1558207092e90f2fb851c1abcc2900d800884cd6de31bee0f394a4c91feb3e19`。
- 独立 DELIVER ledger：`ledger-6b014583-a28f-4815-8e7e-23a28ed5261c`，状态 `COMMITTED`；delivery receipt=`{'delivery_action_id': 'action-1b4150be-e874-495f-8218-5f9128fecfc5', 'report_digest': '1558207092e90f2fb851c1abcc2900d800884cd6de31bee0f394a4c91feb3e19', 'report_ref': 'report-87ea6d8f-518b-4d34-ab2c-1adda88fb8d0', 'report_version': 1, 'resolution_digest': '6e510b1e2085dbe9bb57776cbd7c4258e107b332d75874b6c5f6df55dfd52448', 'status': 'COMMITTED', 'ticket_entry_id': 'ticket-entry-2c495be6-04bf-4fc4-ad3b-0813294a7881', 'ticket_id': 'INC-A-001', 'verification_id': 'verification-c1d51be8-6b00-47ef-8160-d09b8b203916'}`；唯一工单处置条目数=`1`。
- 最终业务状态：`RECOVERED`；任务状态=`COMPLETED`。


完整脱敏轨迹见 [`TRACE.json`](TRACE.json)，两个 OS 子进程输出见 [`process_logs.json`](process_logs.json)。

## 已知限制

本轮验证的是本地 SQLite Demo Domain 与固定订单路由；跨进程 HITL 由两个独立 CLI 进程完成。D4 的崩溃窗口/并发响应丢失故障矩阵不在本轮验收范围，不能据此声称生产级 IAM 或分布式 exactly-once。
