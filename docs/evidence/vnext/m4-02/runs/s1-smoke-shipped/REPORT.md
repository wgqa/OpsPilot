# OpsPilot D3 运行报告

**结果：** PASS

**运行时间：** 2026-10-22T19:02:54+00:00

**主提交：** a3ef416f325dca3ffe18aad1fa837e4ce8612589

**范围：** D3 E01 真实模型 / MCP / LangGraph HITL / REPAIR / 在线验证 / 冻结报告 / DELIVER

## 环境与运行命令

- Python：`3.14.0`（Windows-11-10.0.26200-SP0）
- 模型：`deepseek-flash`（密钥不记录）
- 依赖：`{"langchain": "1.4.1", "langchain-openai": "1.7.2", "langgraph": "1.2.16", "langgraph-checkpoint-sqlite": "3.1.2", "mcp": "2.3.0", "pydantic": "2.14.1"}`
- 复现命令：`.venv\Scripts\python.exe -m opspilot.cli d3-smoke --db .runtime\d3-domain.sqlite3 --checkpoint-db .runtime\d3-checkpoints.sqlite3`
- 初始调查进程 PID：`17080`；独立审批与恢复进程 PID：`32180`
- 初始进程命令：`D:\学习\agent新项目\.venv\Scripts\python.exe -m opspilot.cli d3-start --actor support-a --executor executor-a --db D:\学习\agent新项目\.runtime\m4-02\s1-smoke-shipped.sqlite3 --checkpoint-db D:\学习\agent新项目\.runtime\m4-02\s1-smoke-shipped.checkpoints.sqlite3`
- 审批恢复命令：`D:\学习\agent新项目\.venv\Scripts\python.exe -m opspilot.cli d3-approve --actor approver-a --thread-id opspilot-eb24e118-d99a-48a1-bf70-d5e1a71b1f29 --plan-hash a6ec64386817b4b44ca2c5bb9849c4b7115a9152f1685f1a0c3530c8f94fd59b --decision APPROVED --executor executor-a --db D:\学习\agent新项目\.runtime\m4-02\s1-smoke-shipped.sqlite3 --checkpoint-db D:\学习\agent新项目\.runtime\m4-02\s1-smoke-shipped.checkpoints.sqlite3`
- 真实模型 Function Calling 选择：`probe_endpoint → get_auth_policy → get_integration_config → get_principal_status`；对应 MCP Client/Server 调用：`probe_endpoint → get_auth_policy → get_integration_config → get_principal_status`（完整 Observation/Evidence 在 TRACE.json）。

## 运行结果

- 初始真实业务 Probe：HTTP `401`，请求 `4e18ed7b255a3921`，认证事件 `1`；Gate=`READY`。
- 审批前状态：`cred-v1` / config version `7`，工单处置条目 `0`；受限写入为零。
- LangGraph 在 Plan `a6ec64386817b4b44ca2c5bb9849c4b7115a9152f1685f1a0c3530c8f94fd59b` 处等待人工审批；审批人为 `approver-a`，决定 `APPROVED`。
- 两种独立授权消费状态：`{'DELIVER': 'CONSUMED', 'REPAIR': 'CONSUMED'}`。持久 ActionIntent：`DELIVER=action-262e68a3-bf92-45fd-8ce2-365b9af15fc4 / key=idem-f92b0911-1375-4511-be7a-a556f6b77964 / digest=66524e585b06f40db786161ae77ab471aa437e7a443c71dc4dcafe27dc8bed48; REPAIR=action-2ce582cf-af21-4f59-bd9a-88637d514339 / key=idem-02b9da39-3e32-4a21-90c9-3e7b7be946e2 / digest=b1de58431e86ab255b190038963e20b7215a5a030dbe1fbcfbdac789a801b3e0`。
- REPAIR ledger：`ledger-66cfb625-8c35-4fab-bc95-64f2eb3244b1`，状态 `COMMITTED`，配置版本 `7 → 8`。
- 在线验证：HTTP `200`，`order_id=demo-order`，`status=CONFIRMED`，同 service/integration/principal/route 断言 `True`；request `136ab694e5a2ef40` / auth event `2`；VerificationReceipt=`verification-c2a355f8-97c8-4b3d-9d1b-606600557952`。
- 冻结报告：`report-149e0f19-ec6c-47fc-8c04-d1ac9c58aee4`，SHA-256=`ae6608a9d84b81d1fe4bbc9c33d13fdcbaa1ce595cad7eba09061a1b5f660e21`。
- 独立 DELIVER ledger：`ledger-8a2509d6-3b50-4f95-9cef-099481d489ec`，状态 `COMMITTED`；delivery receipt=`{'delivery_action_id': 'action-262e68a3-bf92-45fd-8ce2-365b9af15fc4', 'report_digest': 'ae6608a9d84b81d1fe4bbc9c33d13fdcbaa1ce595cad7eba09061a1b5f660e21', 'report_ref': 'report-149e0f19-ec6c-47fc-8c04-d1ac9c58aee4', 'report_version': 1, 'resolution_digest': '7b31ac0105de8032612bb20c5aae694d063fce322a2bd2bde061d66ada7e90bb', 'status': 'COMMITTED', 'ticket_entry_id': 'ticket-entry-f0712722-da38-4644-b896-81b33a138eb2', 'ticket_id': 'INC-A-001', 'verification_id': 'verification-c2a355f8-97c8-4b3d-9d1b-606600557952'}`；唯一工单处置条目数=`1`。
- 最终业务状态：`RECOVERED`；任务状态=`COMPLETED`。


完整脱敏轨迹见 [`TRACE.json`](TRACE.json)，两个 OS 子进程输出见 [`process_logs.json`](process_logs.json)。

## 已知限制

本轮验证的是本地 SQLite Demo Domain 与固定订单路由；跨进程 HITL 由两个独立 CLI 进程完成。D4 的崩溃窗口/并发响应丢失故障矩阵不在本轮验收范围，不能据此声称生产级 IAM 或分布式 exactly-once。
