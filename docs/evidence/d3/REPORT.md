# OpsPilot D3 运行报告

**结果：** PASS

**运行时间：** 2026-10-17T07:21:02+00:00

**验证基线：** `171f028d6db1f36df087d62be06c255d09c7e138`

**D3 实现提交：** `5529990c7e180aacdfead723967b07cbcb538e77`（已在 `main`；代码和原始运行轨迹已提交，测试摘要与此 SHA 在本次证据更新中补录）

**范围：** D3 E01 真实模型 / MCP / LangGraph HITL / REPAIR / 在线验证 / 冻结报告 / DELIVER

## 环境与运行命令

- Python：`3.14.0`（Windows-11-10.0.26200-SP0）
- 模型：`deepseek-flash`（密钥不记录）
- 依赖：`{"langchain": "1.4.1", "langchain-openai": "1.7.2", "langgraph": "1.2.16", "langgraph-checkpoint-sqlite": "3.1.2", "mcp": "2.3.0", "pydantic": "2.14.1"}`
- 复现命令：`.venv\Scripts\python.exe -m opspilot.cli d3-smoke --db .runtime\d3-final-refs.sqlite3 --checkpoint-db .runtime\d3-final-refs-checkpoints.sqlite3 --evidence-dir docs/evidence/d3`
- 初始调查进程 PID：`21820`；独立审批与恢复进程 PID：`17088`
- 初始进程命令：`D:\学习\agent新项目\.venv\Scripts\python.exe -m opspilot.cli d3-start --actor support-a --executor executor-a --db D:\学习\agent新项目\.runtime\d3-final-refs.sqlite3 --checkpoint-db D:\学习\agent新项目\.runtime\d3-final-refs-checkpoints.sqlite3`
- 审批恢复命令：`D:\学习\agent新项目\.venv\Scripts\python.exe -m opspilot.cli d3-approve --actor approver-a --thread-id opspilot-c0d84f7c-c8b6-4549-bd69-8358176c27e5 --plan-hash 20b2924664b96c2c59e0adb7134197cac10f8f0bdc29bc5394808ee5d7d33ae5 --decision APPROVED --executor executor-a --db D:\学习\agent新项目\.runtime\d3-final-refs.sqlite3 --checkpoint-db D:\学习\agent新项目\.runtime\d3-final-refs-checkpoints.sqlite3`
- 真实模型 Function Calling 选择：`get_auth_policy → get_integration_config → get_principal_status → probe_endpoint`；对应 MCP Client/Server 调用：`get_auth_policy → get_integration_config → get_principal_status → probe_endpoint`（完整 Observation/Evidence 在 TRACE.json）。

## 运行结果

- 初始真实业务 Probe：HTTP `401`，请求 `b3e93477b3610b09`，认证事件 `1`；Gate=`READY`。
- 审批前状态：`cred-v1` / config version `7`，工单处置条目 `0`；受限写入为零。
- LangGraph 在 Plan `20b2924664b96c2c59e0adb7134197cac10f8f0bdc29bc5394808ee5d7d33ae5` 处等待人工审批；审批人为 `approver-a`，决定 `APPROVED`。
- 两种独立授权消费状态：`{'DELIVER': 'CONSUMED', 'REPAIR': 'CONSUMED'}`。持久 ActionIntent：`DELIVER=action-1d2514de-2c4c-47c8-b3e2-31c10efbc1fb / key=idem-b0d472e1-9a29-4162-beea-ad70e63bd5ec / digest=96072c8c8b2a9a1da6dd19eade51deeda21d2ceb0a20cef87f0b3de955e85772; REPAIR=action-fdd16964-647c-45fa-a7e4-da2c5113c0f9 / key=idem-81df17c8-de08-46c5-b0b4-f5f1a7b9c5f3 / digest=c8c7736932a62a0a724b46362e35c1647bce34f0849c77bcb1a548cd746ae521`。
- REPAIR ledger：`ledger-ea76792f-6343-4a00-8525-dba8dda8d601`，状态 `COMMITTED`，配置版本 `7 → 8`。
- 在线验证：HTTP `200`，`order_id=demo-order`，`status=CONFIRMED`，同 service/integration/principal/route 断言 `True`；request `a0b639313a2c83b8` / auth event `2`；VerificationReceipt=`verification-d720c028-c812-46cf-845c-6163aec381ae`。
- 冻结报告：`report-77ca4773-f02e-4fdb-a393-b1ed24fe76e8`，SHA-256=`e92cd4ba0a2d2dbfd97852e4e52e2deba530bdcf4c256be835151b7e60a9cd0e`。
- 独立 DELIVER ledger：`ledger-c5103b56-9713-4c7d-ab44-b06164a9e2c4`，状态 `COMMITTED`；delivery receipt=`{'delivery_action_id': 'action-1d2514de-2c4c-47c8-b3e2-31c10efbc1fb', 'report_digest': 'e92cd4ba0a2d2dbfd97852e4e52e2deba530bdcf4c256be835151b7e60a9cd0e', 'report_ref': 'report-77ca4773-f02e-4fdb-a393-b1ed24fe76e8', 'report_version': 1, 'resolution_digest': 'c439e48b9d1555863ff6b1e062b0bd229897ba8f2f72bac7797016b382248fea', 'status': 'COMMITTED', 'ticket_entry_id': 'ticket-entry-00ea1066-5859-47bf-a556-7398405bb3ee', 'ticket_id': 'INC-A-001', 'verification_id': 'verification-d720c028-c812-46cf-845c-6163aec381ae'}`；唯一工单处置条目数=`1`。
- 最终业务状态：`RECOVERED`；任务状态=`COMPLETED`。


完整脱敏轨迹见 [`TRACE.json`](TRACE.json)，两个 OS 子进程输出见 [`process_logs.json`](process_logs.json)。

## 自动化与回归结果

- 全量命令：`.venv\Scripts\python.exe -m pytest -q -s --basetemp=.runtime\pytest-d3`；结果 `29 passed in 17.18s`，原始输出见 [`pytest.log`](pytest.log)。覆盖 D1/D2/D3；其中重复 Probe 定向回归确认仅 request/auth-event ID 变化时仍为 `READY`，稳定诊断事实变化时为 `INCONCLUSIVE`。
- 静态检查：`python -m compileall -q opspilot tests`、`python -m pip check` 与 `git diff --check` 均通过；pip 输出为 `No broken requirements found.`。
- D2 真实模型 + MCP 回归命令和脱敏原始日志：
  - `.venv\Scripts\python.exe -m opspilot.cli d2-smoke --scenario POS --db .runtime\d3-d2-pos.sqlite3 --checkpoint-db .runtime\d3-d2-pos-cp.sqlite3` → `READY` (`config_version=7`, unchanged)，日志 [`d2-pos.log`](d2-pos.log)。
  - `.venv\Scripts\python.exe -m opspilot.cli d2-smoke --scenario DISABLED --db .runtime\d3-d2-disabled.sqlite3 --checkpoint-db .runtime\d3-d2-disabled-cp.sqlite3` → `NO_ACTION` (`config_version=7`, unchanged)，日志 [`d2-disabled.log`](d2-disabled.log)。
  - `.venv\Scripts\python.exe -m opspilot.cli d2-smoke --scenario INSUFFICIENT --db .runtime\d3-d2-insufficient.sqlite3 --checkpoint-db .runtime\d3-d2-insufficient-cp.sqlite3` → `INCONCLUSIVE` (`config_version=7`, unchanged)，日志 [`d2-insufficient.log`](d2-insufficient.log)。
- D3 smoke 的 13 项机器断言全部为真：真实模型与 MCP 轨迹、审批前零写入、独立进程恢复、checkpoint 只存引用、独立审批、REPAIR 单次提交、同身份在线 200、冻结报告先于 DELIVER、两类 Intent 均持久化、单条工单回执。详见 `TRACE.json` 的 `checks`。

## 保留的失败尝试

第一次集成 smoke 已保留在 [`TRACE-attempt-01.json`](TRACE-attempt-01.json) 和 [`process_logs-attempt-01.json`](process_logs-attempt-01.json)，结果为 FAIL：真实调查、独立审批、REPAIR 与相同身份的 HTTP 200 已完成，但 Graph `TypedDict` 漏声明恢复完成标志，导致后续节点未冻结报告，也未执行 DELIVER。实现随后改为从持久化 VerificationReceipt 按引用读取恢复事实，并以引用形式保存 Graph 状态；复跑的 `TRACE.json` 中 13 项断言全部通过。该失败未被计入测试通过数。

## 已知限制

本轮验证的是本地 SQLite Demo Domain 与固定订单路由；跨进程 HITL 由两个独立 CLI 进程完成。D4 的崩溃窗口/并发响应丢失故障矩阵不在本轮验收范围，不能据此声称生产级 IAM 或分布式 exactly-once。
