# OpsPilot

面向客户 API 接入故障的智能调查与受控处置 Agent，使用 Python、LangChain 和 LangGraph。首周唯一业务场景是 S1：客户端凭证引用过旧导致业务 API 返回 401。

**设计状态：** R5 · DESIGN APPROVED
**D1 状态：** D1 技术 smoke、S1 业务闭环与 8 项自动化测试已通过主 Agent 审查。
**D2 状态：** 只读动态调查、真实模型 + MCP 链路、Evidence Gate 与三种 401 场景已通过主 Agent 验收，PR #2 已合入 `main@171f028`。
**D3 状态：** WP-01–05、真实端到端运行与全套回归已通过；提交主 Agent 源码与证据复核（29 项 pytest、13 项 D3 smoke 检查）。
**唯一有效架构与验收规范：** [v1.0 实施基线](docs/baseline/v1.0-implementation-baseline.md)
**当前实施任务：** [Luna D3 任务卡](docs/handoff/Luna-D3-implementation-brief.md)
**逐项进度与测试结论：** [TASKS.md](TASKS.md)
**D1 执行日志与报告：** [D1 报告](docs/evidence/d1/REPORT.md)
**D2 任务卡与执行报告：** [D2 任务卡](docs/handoff/Luna-D2-implementation-brief.md) · [D2 报告](docs/evidence/d2/REPORT.md)
**D3 真实运行轨迹与报告：** [D3 报告](docs/evidence/d3/REPORT.md) · [脱敏轨迹](docs/evidence/d3/TRACE.json) · [进程与测试日志](docs/evidence/d3/)
**工程边界：** [AGENTS.md](AGENTS.md)

## 产品目标与边界

S1-POS fixture 将 `integration-a` 设为旧凭证引用，访问固定订单业务路由会得到真实 HTTP 401。D3 只有在独立 approver 批准不可变 Plan 后，才由持久 ActionIntent 驱动事务 REPAIR；同一 service、integration、principal 和路由随后必须通过真实 HTTP 200，且响应包含 `order_id=demo-order`、`status=CONFIRMED`。S1-DISABLED 验证主体停用时不能通过切换凭证恢复。

D1 的 MCP 工具只读，服务端启动时绑定租户作用域。checkpoint smoke 用 SQLite 持久化，在进程 A 退出后由另一进程以同一 thread ID 恢复；越权操作者在读取 checkpoint 前被拒绝。fixture 凭证、SQLite 数据库和响应只用于本地演示，不代表生产系统或生产级身份管理。

## 环境和安装

已在 Windows CPython 3.14.0 上验证；`pyproject.toml` 声明最低 Python 3.11。依赖和传递版本锁在 [requirements.lock.txt](requirements.lock.txt)，直接依赖约束见 [requirements.in](requirements.in)。

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.lock.txt
Copy-Item .env.example .env
```

需要真实模型 Function Calling 时，在本机编辑 `.env`，填写 `OPSPILOT_MODEL_API_KEY` 和 `OPSPILOT_MODEL_NAME`；使用自定义 OpenAI-compatible Chat Completions 端点时再填写 `OPSPILOT_MODEL_BASE_URL`。不要把密钥放进 Git、命令历史或测试日志。未配置必需值时，真实模型 smoke 会明确返回 `BLOCKED`，不会调用模型。D1 已用模型 `deepseek-flash` 实际完成一次工具调用。

## 运行命令

复位正例 fixture：

```powershell
.\.venv\Scripts\python -m opspilot.cli reset --scenario S1_POS --db .runtime\opspilot.sqlite3
```

在第一个终端启动固定绑定 `tenant-a`、仅监听 loopback 的业务 API：

```powershell
.\.venv\Scripts\python -m opspilot.cli serve --db .runtime\opspilot.sqlite3 --host 127.0.0.1 --port 8000
```

在第二个终端让同一调用方真实请求业务端点：

```powershell
.\.venv\Scripts\python -m opspilot.cli probe --db .runtime\opspilot.sqlite3 --base-url http://127.0.0.1:8000
```

D1 正例、MCP、checkpoint 和真实模型命令：

```powershell
.\.venv\Scripts\python -m opspilot.cli smoke s1
.\.venv\Scripts\python -m opspilot.cli smoke mcp
.\.venv\Scripts\python -m opspilot.cli smoke checkpoint
.\.venv\Scripts\python -m opspilot.cli smoke tool-call
```

D2 真实模型调查命令（每个 `d2-smoke` 都会重置 `--db` 指定的本地演示数据；模型凭证只从被忽略的 `.env` 读取）：

```powershell
.\.venv\Scripts\python -m opspilot.cli d2-smoke --scenario POS --db .runtime\d2-pos.sqlite3 --checkpoint-db .runtime\d2-pos-checkpoints.sqlite3
.\.venv\Scripts\python -m opspilot.cli d2-smoke --scenario DISABLED --db .runtime\d2-disabled.sqlite3 --checkpoint-db .runtime\d2-disabled-checkpoints.sqlite3
.\.venv\Scripts\python -m opspilot.cli d2-smoke --scenario INSUFFICIENT --db .runtime\d2-insufficient.sqlite3 --checkpoint-db .runtime\d2-insufficient-checkpoints.sqlite3
```

D3 手动流程分两个 OS 进程运行。先执行 `d3-start`；它在 Plan 后通过 LangGraph `interrupt` 挂起并输出 `thread_id` 与 `plan_hash`。再从另一个进程以可信 approver 身份批准或拒绝，恢复同一 checkpoint。首次 `REPAIR` 和 `DELIVER` 之前都会先持久化各自的 ActionIntent：

```powershell
.\.venv\Scripts\python -m opspilot.cli d3-start --actor support-a --executor executor-a --db .runtime\d3.sqlite3 --checkpoint-db .runtime\d3-checkpoints.sqlite3
.\.venv\Scripts\python -m opspilot.cli d3-approve --actor approver-a --thread-id <d3-start 输出的 thread_id> --plan-hash <d3-start 输出的 plan_hash> --decision APPROVED --executor executor-a --db .runtime\d3.sqlite3 --checkpoint-db .runtime\d3-checkpoints.sqlite3
```

跨进程中断后可从持久化 Domain 回执恢复。恢复命令会先核对操作者和已存审批；无法由业务回执确认的终态会阻断并报告 `ACTION_OUTCOME_UNKNOWN`：

```powershell
.\.venv\Scripts\python -m opspilot.cli d3-resume --actor support-a --thread-id <task thread_id> --executor executor-a --db .runtime\d3.sqlite3 --checkpoint-db .runtime\d3-checkpoints.sqlite3
```

一条命令会复现真实模型、MCP Client/Server、独立进程审批恢复、真实业务验证与工单追加。该命令会重置指定的本地演示数据库：

```powershell
.\.venv\Scripts\python -m opspilot.cli d3-smoke --db .runtime\d3-smoke.sqlite3 --checkpoint-db .runtime\d3-smoke-checkpoints.sqlite3 --evidence-dir docs/evidence/d3
```

正式调查入口从可信本地操作者注册表创建 TaskBinding；需要先用 `reset` 初始化演示数据。D2 Investigator 通过真实 MCP stdio Server 选择只读查询，Graph checkpointer 与 Domain 数据库存放在不同 SQLite 文件中：

```powershell
.\.venv\Scripts\python -m opspilot.cli investigate --actor support-a
.\.venv\Scripts\python -m opspilot.cli resume --actor support-a --thread-id <task_binding_created 输出的 thread_id>
.\.venv\Scripts\python -m opspilot.smokes.d2_mcp
.\.venv\Scripts\python -m opspilot.smokes.d2_budget --db .runtime\d2-budget.sqlite3
```

D2 Investigator 只暴露四个拆分工具：`get_integration_config`、`get_principal_status`、`get_auth_policy`、`probe_endpoint`；D1 聚合工具仅保留在 D1 回归。每个模型请求最多 8 次，每个模型选择的 MCP `tools/call` 最多 6 次；attempt 在外发前写入 Domain 台账。`d2-smoke INSUFFICIENT` 使用测试专用证据源故障注入，业务端点仍实际返回 401，Gate 必须安全停止，不能进入 READY。

运行全套测试；给 pytest 指定仓库内临时目录，可避开 Windows 共享 Temp 目录的权限问题。D4 故障测试会启动真实 OS 子进程，并在事务或 Graph checkpoint 边界强制退出：

```powershell
New-Item -ItemType Directory -Path .runtime -Force | Out-Null
.\.venv\Scripts\python -m pytest -q -s --basetemp=.runtime\pytest-d4
.\.venv\Scripts\python -m pytest -q -s --basetemp=.runtime\pytest-d4-focused tests\test_d4_recovery.py
```

各命令的脱敏输出、失败尝试和解释见 [D1 evidence](docs/evidence/d1/) 与 [D1 报告](docs/evidence/d1/REPORT.md)、[D2 evidence](docs/evidence/d2/) 与 [D2 报告](docs/evidence/d2/REPORT.md)、[D3 evidence](docs/evidence/d3/) 与 [D3 报告](docs/evidence/d3/REPORT.md)，以及 [D4 报告](docs/evidence/d4/REPORT.md)。D4 包含 D2 三场景模型/MCP 复测、D3 业务闭环 smoke、D1–D4 全套测试和崩溃/丢响应/并发/Checkpoint 恢复轨迹。pytest 在 Windows 上请使用仓库内 `.runtime` 临时目录。

## 当前已知问题

- Function Calling 和 D2 Investigator 目前只验证了已配置的 `deepseek-flash` OpenAI-compatible Chat Completions 端点；其他提供商和模型尚未验证。模型偶尔会返回并行调用；Dispatcher 只发出第一个，其他调用留痕为未发送，再让模型依据结果选择下一步。
- 本地可信操作者注册表、业务 API、fixture 与 SQLite 仅用于演示，不代表生产 IAM 或客户系统。D3 通过本地事务与跨进程 CLI 演示首次正确闭环。
- D4 已用真实 OS 子进程验证 ActionIntent、REPAIR、冻结报告和 DELIVER 在提交/检查点边界进程退出后的幂等恢复，并覆盖计划取消/替换竞争、并发重复提交和未知终态阻断；这仍是本地 SQLite Demo Domain 的可靠性证据，不代表生产 IAM 或分布式存储保证。Memory、Skills、多 Agent、Redis、S2/S3 与前端也不在当前实现范围。

## 文档与评审历史

- [冻结基线](docs/baseline/v1.0-implementation-baseline.md) 是唯一有效的架构与验收合同。
- [R1–R5 评审记录](docs/reviews/) 用于追溯设计放行过程，不构成并行需求。
- [历史方案资料](框架规划文档/) 保留早期构思及任务记录，现已归档，不作为当前实现依据。
- [v1.0 交接原件](开发目录/) 保留本地交付包。
