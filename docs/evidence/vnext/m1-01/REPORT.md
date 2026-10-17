# OpsPilot vNext M1-01 实施与运行报告

**结论：M1-01 实施和本轮验收项 PASS，等待主 Agent 审查。** 这不表示 M1 总体完成，不表示第三方重新批准 v0.3，也不授权启动 M1-02。

## 范围、版本与环境

- 分支：`main`，直接基于用户指定的 `a53e13a4243cc6c7fa545b3e3a92b838596b6242`；提交后的精确终点以 `git rev-parse HEAD` 和最终交付记录为准。
- 起始工作区：跟踪文件干净。`开发目录/` 中用户提供的原始材料保持未跟踪、未暂存、未修改；其归档副本位于 `docs/handoff/vnext/`。
- 范围：Task 终止、关键纠错、Message/Command/Run 原子受理，以及既有 D3 事务动作受 TaskControl 约束；未实施 M1-02、HTTP/API/SSE 聊天接入、后台 worker lease、S2、Memory、Skills 或 Multi-Agent。
- 环境：Windows 11，CPython 3.14.0，pytest 9.1.1；`pip check` 无依赖冲突。实际 smoke 依赖：`langchain 1.4.1`、`langchain-openai 1.7.2`、`langgraph 1.2.16`、`langgraph-checkpoint-sqlite 3.1.2`、`mcp 2.3.0`、`pydantic 2.14.1`。真实模型为 `deepseek-flash`；API key 未写入报告或证据。
- 合同状态：v1.0 基线继续管辖 D1–D7 历史功能；vNext 依据本地交接的 v0.3 合同和 M1-01 任务卡。v0.3 文本记载 v0.2 第三方结论为 `REVISE_AND_REVIEW`，v0.3 附录 B 尚未再次第三方复审。本报告不代表第三方签字。

## 实施摘要

在现有 SQLite Domain 中新增 `task_controls`、`sessions`、`session_task_links`、`commands`、`messages`、`task_runs`、`task_run_inputs`、`domain_outbox` 和 `d3_plan_control_bindings`。`database.initialize()` 在单一迁移事务内建表/索引并安全回填；未知旧历史不伪造 revision。重复迁移两次后原 Plan hash 不变。

新增 `opspilot/domain/task_control.py`：`create_session()`、`admit_task_message()`、`abort_task()`、`claim_task_run()`、`resume_task_run()`、`apply_pending_critical_inputs()`、`finish_task_run()` 和 `get_task_run()`。Message、幂等 Command、排队 TaskRun、control revision 与 outbox 在一个 `BEGIN IMMEDIATE` 中受理。Abort 与 correction 是独立命令；关键更正到达即提高 revision、登记 pending 消息高水位并使旧计划资格失效。新 Run 消费更正时以 `USER_INPUT_UNTRUSTED` 记录，Gate 仍要求当前 MCP Evidence。

`d3.py` 的 Plan、Approval/permission、ActionIntent 与 REPAIR/DELIVER 最终提交事务都核对 TaskControl 和 Plan binding；合法历史 Ledger 仍可按可信身份回查。`investigator.py::run_investigation()` 在入口、intake 和恢复前读取持久 Run/control 状态；各 Run 使用独立 checkpoint thread，且只在消费完整有效输入后将纠错作为未信任上下文交给模型。

主要文件与函数索引见 `TASKS.md` 与本仓库源码；新增定向测试位于 `tests/test_m1_task_control.py`，真实 TaskRun smoke 为 `opspilot/smokes/m1_task_run.py`。

## 新鲜运行命令与结果

以下命令均在本轮执行；完整全量 pytest stdout/stderr 见 [`logs/pytest-full.txt`](logs/pytest-full.txt)，逐项关键事件见 [`logs/n1-domain-and-process-events.jsonl`](logs/n1-domain-and-process-events.jsonl)。

```powershell
cd "D:\学习\agent新项目"
New-Item -ItemType Directory -Path .runtime -Force | Out-Null
.\.venv\Scripts\python.exe -m pytest -q -s tests/test_m1_task_control.py --basetemp=.runtime/m101-m1-focused-final
.\.venv\Scripts\python.exe -m pytest -q -s --basetemp=.runtime/m101-pytest-final
.\.venv\Scripts\python.exe -m compileall -q opspilot tests
.\.venv\Scripts\python.exe -m pip check
git diff --check
.\.venv\Scripts\python.exe -m opspilot.smokes.m1_task_run --db .runtime/m101-model-taskrun.sqlite3 --checkpoint-db .runtime/m101-model-taskrun-checkpoints.sqlite3
.\.venv\Scripts\python.exe -m opspilot.cli d3-smoke --db .runtime/m101-s1-domain.sqlite3 --checkpoint-db .runtime/m101-s1-checkpoints.sqlite3 --evidence-dir .runtime/m101-s1-evidence
```

- 全量 pytest：**73 passed / 73 collected，48.25s**。包括现有 D1–D7 回归和本轮 9 个 M1 定向用例，无 pytest 失败。
- M1 定向复跑：**9 passed / 9 collected，7.33s**；原始日志见 [`logs/pytest-m1-focused.txt`](logs/pytest-m1-focused.txt)。
- `compileall`：PASS；`pip check`：PASS，`No broken requirements found.`；`git diff --check`：PASS（退出码 0）。PowerShell 下 Git 曾提示 `d3.py` 工作副本 LF 将标准化为 CRLF；无 whitespace error，仓库已有 `.gitattributes` 约束；不涉及业务代码差异。
- 全量日志中有一条预期注入的 `d3_smoke_result FAIL` 事件：`tests/test_d6_smoke_evidence.py::test_d3_smoke_preserves_failed_start_process_without_crashing` 人为构造 `provider timeout`，断言失败轨迹被留存；该 pytest 用例通过。此行不是本轮真实模型 smoke 失败。
- 首次 M1 模型 smoke 的失败原因和采集限制见 [`ATTEMPT-01.md`](ATTEMPT-01.md)；经只修正 smoke fixture 票据后，独立数据重跑 PASS。失败保留在本报告，不从次数中删去。

## N1 验收结果

N1 测试在上述全量 pytest 新鲜运行中执行；命令可按表中 node ID 定向复现。原始 JSON 事件及进程 PID/状态见证据 JSONL。`tests/test_m1_task_control.py` 的 9 个测试均通过。

| Case | 本轮结果与因果事实 | 真实测试项 |
|---|---|---|
| N1-01/02 原子受理/重试 | **PASS**。Trigger 在 Run 插入处强制 SQL abort 后，Command/Message/Run/outbox/control 更新整体回滚；移除 failpoint 后同 key 重试返回原 `command_id/message_id/run_id`，revision 只增一次；同 key 异摘要为 `IDEMPOTENCY_CONFLICT`。 | `test_n1_01_02_admission_is_atomic_and_idempotent` |
| N1-05 单 Run claim | **PASS**。两个独立线程/SQLite connection 争用同 Run，只有一方 `CLAIMED/RUNNING`，另一方 `TASK_RUN_NOT_QUEUED`，Running count=1。 | `test_n1_05_one_worker_claims_the_durable_run` |
| N1-09 无 Plan 时 abort | **PASS，独立 OS 子进程**。父进程已持久化 checkpoint，abort 将控制 revision 置 1；子进程以 PID 34440 恢复旧 thread，在读取/推进前得到 `TASK_ABORTED`。Plan/Approval/Intent/Ledger 全为 0。 | `test_n1_09_abort_before_old_checkpoint_resume_is_enforced_in_another_process` |
| N1-10 correction 先于旧动作 | **PASS**。更正受理使旧 Intent 首次尝试为 `TASK_INPUT_PENDING`；新 Run 消费消息后旧 Plan 返回 `TASK_CONTROL_STALE`，旧路径没有配置副作用。新 Plan 绑定 revision 2/消息高水位并经新审批，唯一合法 REPAIR 使 config v7→v8，Repair Ledger=1。 | `test_n1_10_correction_invalidates_old_run_and_new_run_binds_fresh_plan` |
| N1-11 REPAIR 后 abort | **PASS，独立 OS 子进程**。REPAIR 已提交后 abort；配置 v8 与原 COMMITTED Ledger 保留且历史回执仍可读。子进程 PID 27196 恢复旧 checkpoint 得 `TASK_ABORTED`；DELIVER Ledger、DeliveryRecord、工单 entry 均为 0。 | `test_n1_11_repair_commit_survives_abort_and_old_checkpoint_cannot_deliver` |
| 权限/角色、终态与迁移回归 | **PASS**。owner scope 与已完成任务终态回归；pending correction 时禁止新审批；迁移重放两次，control ACTIVE/revision0，Plan binding 保留、Plan hash 不变。原 D1–D7 全套测试一并通过。 | 对应测试见 `tests/test_m1_task_control.py` 与历史回归测试 |

本轮新建的业务 Control 无未授权写入。N1-11 的 REPAIR 在 abort 前已经合法 COMMITTED，因此保留 v8 和一条历史 Ledger 是合同要求；abort 仅阻断尚未提交的 DELIVER，不伪称回滚。

## 真实模型/MCP 与业务回归

### TaskRun 调查 smoke

原始脱敏轨迹见 [`logs/real-model-task-run.jsonl`](logs/real-model-task-run.jsonl)：真实 `deepseek-flash` Function Calling 5/5 请求为 OK；MCP stdio Client/Server 的 `get_integration_config`、`get_auth_policy`、`get_principal_status`、`probe_endpoint` 四次调用均为 OK；12,792 tokens。Gate=`READY`，纠错消息作为未信任输入被新 Run 消费，Plan 绑定 `control_revision=2`、`consumed_message_seq=1` 与当前 Run。LangGraph 停在 `d3_human_approval`，Run 为 `WAITING_APPROVAL`；此时 config 仍是 v7，业务写入/ActionIntent/ActionLedger 为零。

这证明的是新 TaskRun 与真实调查链路，不表示人工已批准或动作已执行。模型 API 密钥未写入记录。

### S1 401→200 回归

本轮 fresh D3 smoke **13/13 checks PASS**，完整资料位于 [`s1-d3-smoke/`](s1-d3-smoke/)。初始业务 route `/api/orders/demo-order` 返回 HTTP 401；原受信 fixture 的 `approver-a` 模拟 CLI 审批后 config v7→v8；同 service/integration/principal/route 的在线业务验证返回 HTTP 200、`order_id=demo-order`、`status=CONFIRMED`。REPAIR 与 DELIVER 各一条 COMMITTED Ledger，工单 disposition entry=1。此程序化审批是 Demo 角色模拟，不是现实用户或第三方审批。

## 失败、边界与后续

- 保留一次真实模型/MCP smoke harness 失败：使用未注册票据时 Plan 被拒；首次终端原始 stderr 未落盘。修正 ticket fixture 后成功，失败记录明确见 `ATTEMPT-01.md`。
- pytest 的人为 provider timeout FAIL 事件是一个预期失败注入，且其断言通过；全量 73 个测试无失败。
- 当前实现是单机 SQLite Domain；本轮未交付后台 worker 的跨进程 lease/队列消费、Web/API/SSE、生产 IAM、跨主机锁或 exactly-once。N1-05 仅证明独立 SQLite connections 的单 Run 互斥，不能扩大解释为多进程 worker 调度。
- M1-02 尚未开始。下一步等待主 Agent 审查本轮源码和新鲜证据。
