# OpsPilot D3 运行报告

**结果：** PASS

**运行时间：** 2026-10-17T07:53:19+00:00

**主提交：** 42b6d74eeee706d69905ed364aa001e42219241d

**范围：** D3 E01 真实模型 / MCP / LangGraph HITL / REPAIR / 在线验证 / 冻结报告 / DELIVER

## 环境与运行命令

- Python：`3.14.0`（Windows-11-10.0.26200-SP0）
- 模型：`deepseek-flash`（密钥不记录）
- 依赖：`{"langchain": "1.4.1", "langchain-openai": "1.7.2", "langgraph": "1.2.16", "langgraph-checkpoint-sqlite": "3.1.2", "mcp": "2.3.0", "pydantic": "2.14.1"}`
- 复现命令：`.venv\Scripts\python.exe -m opspilot.cli d3-smoke --db .runtime\d3-domain.sqlite3 --checkpoint-db .runtime\d3-checkpoints.sqlite3`
- 初始调查进程 PID：`12520`；独立审批与恢复进程 PID：`20596`
- 初始进程命令：`D:\学习\agent新项目\.venv\Scripts\python.exe -m opspilot.cli d3-start --actor support-a --executor executor-a --db D:\学习\agent新项目\.runtime\d4-e01.sqlite3 --checkpoint-db D:\学习\agent新项目\.runtime\d4-e01-checkpoints.sqlite3`
- 审批恢复命令：`D:\学习\agent新项目\.venv\Scripts\python.exe -m opspilot.cli d3-approve --actor approver-a --thread-id opspilot-ad145813-4aa2-483d-af26-c4ac90dfff0d --plan-hash 4e2df6d0f62c2eeeb8fb7a8fbd28488bd98ca24322e70420fcae189b7958c3d3 --decision APPROVED --executor executor-a --db D:\学习\agent新项目\.runtime\d4-e01.sqlite3 --checkpoint-db D:\学习\agent新项目\.runtime\d4-e01-checkpoints.sqlite3`
- 真实模型 Function Calling 选择：`get_auth_policy → get_integration_config → probe_endpoint → get_principal_status`；对应 MCP Client/Server 调用：`get_auth_policy → get_integration_config → probe_endpoint → get_principal_status`（完整 Observation/Evidence 在 TRACE.json）。

## 运行结果

- 初始真实业务 Probe：HTTP `401`，请求 `78783c26d54c50da`，认证事件 `1`；Gate=`READY`。
- 审批前状态：`cred-v1` / config version `7`，工单处置条目 `0`；受限写入为零。
- LangGraph 在 Plan `4e2df6d0f62c2eeeb8fb7a8fbd28488bd98ca24322e70420fcae189b7958c3d3` 处等待人工审批；审批人为 `approver-a`，决定 `APPROVED`。
- 两种独立授权消费状态：`{'DELIVER': 'CONSUMED', 'REPAIR': 'CONSUMED'}`。持久 ActionIntent：`DELIVER=action-439de612-b450-4645-8dd4-ccaeca6e1ad3 / key=idem-c2fc5b1a-f545-4700-bebf-f9f715328e9c / digest=39d24d84ff8f7c87f20ad12de11c09794b3d9bf0a67527417c472d69785535d1; REPAIR=action-730ea9b3-a408-4dba-a6b6-61e07eeeda77 / key=idem-8ef93437-5278-4c48-8f69-b3977a7739a9 / digest=9db3492e095e48ff3483cc517ca5e153c5c9078f1b6d65a29e1f9429df41d20d`。
- REPAIR ledger：`ledger-1ff03171-6d65-4430-8bcd-f601703dbf40`，状态 `COMMITTED`，配置版本 `7 → 8`。
- 在线验证：HTTP `200`，`order_id=demo-order`，`status=CONFIRMED`，同 service/integration/principal/route 断言 `True`；request `8bb30bd545de3c1b` / auth event `2`；VerificationReceipt=`verification-1e5ad31a-4a8d-4ff4-ba8b-924d977c916e`。
- 冻结报告：`report-f506b89f-6138-4643-8836-527fe8e3439d`，SHA-256=`8ba5d4f4b649ae6b447c97984bd5df3ef215cce2b69a776abb477a7091760b02`。
- 独立 DELIVER ledger：`ledger-3a00f0f7-2b56-484c-982a-47c8ff18b9d2`，状态 `COMMITTED`；delivery receipt=`{'delivery_action_id': 'action-439de612-b450-4645-8dd4-ccaeca6e1ad3', 'report_digest': '8ba5d4f4b649ae6b447c97984bd5df3ef215cce2b69a776abb477a7091760b02', 'report_ref': 'report-f506b89f-6138-4643-8836-527fe8e3439d', 'report_version': 1, 'resolution_digest': '8c7785be8963c9073a219fddd47a2fe0314989db5127071b5f217ec96515fd69', 'status': 'COMMITTED', 'ticket_entry_id': 'ticket-entry-03680db1-afcd-4c84-8351-6be01ec585d4', 'ticket_id': 'INC-A-001', 'verification_id': 'verification-1e5ad31a-4a8d-4ff4-ba8b-924d977c916e'}`；唯一工单处置条目数=`1`。
- 最终业务状态：`RECOVERED`；任务状态=`COMPLETED`。


完整脱敏轨迹见 [`TRACE.json`](TRACE.json)，两个 OS 子进程输出见 [`process_logs.json`](process_logs.json)。

## 已知限制

本轮验证的是本地 SQLite Demo Domain 与固定订单路由；跨进程 HITL 由两个独立 CLI 进程完成。D4 的崩溃窗口/并发响应丢失故障矩阵不在本轮验收范围，不能据此声称生产级 IAM 或分布式 exactly-once。
