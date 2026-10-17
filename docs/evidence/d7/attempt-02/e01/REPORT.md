# OpsPilot D3 运行报告

**结果：** PASS

**运行时间：** 2026-10-17T10:22:01+00:00

**主提交：** 

**范围：** D3 E01 真实模型 / MCP / LangGraph HITL / REPAIR / 在线验证 / 冻结报告 / DELIVER

## 环境与运行命令

- Python：`3.14.0`（Windows-11-10.0.26200-SP0）
- 模型：`deepseek-flash`（密钥不记录）
- 依赖：`{"langchain": "1.4.1", "langchain-openai": "1.7.2", "langgraph": "1.2.16", "langgraph-checkpoint-sqlite": "3.1.2", "mcp": "2.3.0", "pydantic": "2.14.1"}`
- 复现命令：`.venv\Scripts\python.exe -m opspilot.cli d3-smoke --db .runtime\d3-domain.sqlite3 --checkpoint-db .runtime\d3-checkpoints.sqlite3`
- 初始调查进程 PID：`27704`；独立审批与恢复进程 PID：`9112`
- 初始进程命令：`D:\学习\OpsPilot-D7-repro-20261017T102036Z\.venv\Scripts\python.exe -m opspilot.cli d3-start --actor support-a --executor executor-a --db D:\学习\OpsPilot-D7-repro-20261017T102036Z\.runtime\d7-e01.sqlite3 --checkpoint-db D:\学习\OpsPilot-D7-repro-20261017T102036Z\.runtime\d7-e01-checkpoints.sqlite3`
- 审批恢复命令：`D:\学习\OpsPilot-D7-repro-20261017T102036Z\.venv\Scripts\python.exe -m opspilot.cli d3-approve --actor approver-a --thread-id opspilot-07e4503d-2be5-49aa-a5e1-3de61308fcb2 --plan-hash a50d0de299d38ca04774fc6f66f5eb8980457ecb7fbcfdf16bf9137c2c6d8c81 --decision APPROVED --executor executor-a --db D:\学习\OpsPilot-D7-repro-20261017T102036Z\.runtime\d7-e01.sqlite3 --checkpoint-db D:\学习\OpsPilot-D7-repro-20261017T102036Z\.runtime\d7-e01-checkpoints.sqlite3`
- 真实模型 Function Calling 选择：`get_principal_status → get_auth_policy → get_integration_config → probe_endpoint → get_principal_status → get_principal_status`；对应 MCP Client/Server 调用：`get_principal_status → get_auth_policy → get_integration_config → probe_endpoint → get_principal_status → get_principal_status`（完整 Observation/Evidence 在 TRACE.json）。

## 运行结果

- 初始真实业务 Probe：HTTP `401`，请求 `3d345804f43cc16f`，认证事件 `1`；Gate=`READY`。
- 审批前状态：`cred-v1` / config version `7`，工单处置条目 `0`；受限写入为零。
- LangGraph 在 Plan `a50d0de299d38ca04774fc6f66f5eb8980457ecb7fbcfdf16bf9137c2c6d8c81` 处等待人工审批；审批人为 `approver-a`，决定 `APPROVED`。
- 两种独立授权消费状态：`{'DELIVER': 'CONSUMED', 'REPAIR': 'CONSUMED'}`。持久 ActionIntent：`DELIVER=action-6dcc1200-3457-4188-83a4-f0bc747752f2 / key=idem-8b26f49a-9934-4ffb-9832-0a6c40538f30 / digest=c8d11715c3623dac3d8c1df2f31144ef1ea0eee8f8193e36fb842420af0486c7; REPAIR=action-829acbaa-f8bf-4e27-b623-b44ae8b45bfb / key=idem-270f4161-bacb-4a87-a8f4-396a36b3b1ae / digest=8ae11a664b1158c11da7a630c2a50f79261faca8b5945d2c3a7f7c10f1a47076`。
- REPAIR ledger：`ledger-1452d727-ce5c-45cc-a1c6-1d32e651c1cd`，状态 `COMMITTED`，配置版本 `7 → 8`。
- 在线验证：HTTP `200`，`order_id=demo-order`，`status=CONFIRMED`，同 service/integration/principal/route 断言 `True`；request `b156ff38eac440b1` / auth event `2`；VerificationReceipt=`verification-16d97f92-45a9-4db7-94ca-ca732498f547`。
- 冻结报告：`report-dad6c81f-2da3-4a1f-bdaf-905c3211bba8`，SHA-256=`d598f377628a70ac39bcc22ad4ce51f561612531f88d88d88e3b17ab81dfb1c9`。
- 独立 DELIVER ledger：`ledger-a807829b-e634-4d94-b54c-e07355d10fbb`，状态 `COMMITTED`；delivery receipt=`{'delivery_action_id': 'action-6dcc1200-3457-4188-83a4-f0bc747752f2', 'report_digest': 'd598f377628a70ac39bcc22ad4ce51f561612531f88d88d88e3b17ab81dfb1c9', 'report_ref': 'report-dad6c81f-2da3-4a1f-bdaf-905c3211bba8', 'report_version': 1, 'resolution_digest': '46f7fa62d2d2fdffe9e6945855c96e71375294dae2db7f89964f0f9a740e2cf8', 'status': 'COMMITTED', 'ticket_entry_id': 'ticket-entry-95d49a85-6fa7-49c8-a8ec-f345e6fe9553', 'ticket_id': 'INC-A-001', 'verification_id': 'verification-16d97f92-45a9-4db7-94ca-ca732498f547'}`；唯一工单处置条目数=`1`。
- 最终业务状态：`RECOVERED`；任务状态=`COMPLETED`。


完整脱敏轨迹见 [`TRACE.json`](TRACE.json)，两个 OS 子进程输出见 [`process_logs.json`](process_logs.json)。

## 已知限制

本轮验证的是本地 SQLite Demo Domain 与固定订单路由；跨进程 HITL 由两个独立 CLI 进程完成。D4 的崩溃窗口/并发响应丢失故障矩阵不在本轮验收范围，不能据此声称生产级 IAM 或分布式 exactly-once。
