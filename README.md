# OpsPilot

面向客户 API 接入故障的智能调查与受控处置 Agent，使用 Python、LangChain 和 LangGraph。首周唯一业务场景是 S1：客户端凭证引用过旧导致业务 API 返回 401。

**设计状态：** R5 · DESIGN APPROVED
**D1 状态：** D1 技术 smoke、S1 业务闭环与 8 项自动化测试通过；等待主 Agent 复核。D2 尚未开始。
**唯一有效架构与验收规范：** [v1.0 实施基线](docs/baseline/v1.0-implementation-baseline.md)
**当前实施任务：** [Luna D1 任务书](docs/handoff/Luna-D1-implementation-brief.md)
**逐项进度与测试结论：** [TASKS.md](TASKS.md)
**D1 执行日志与报告：** [D1 报告](docs/evidence/d1/REPORT.md)
**工程边界：** [AGENTS.md](AGENTS.md)

## 产品目标与边界

S1-POS 中，`integration-a` 用旧凭证引用访问固定订单业务路由，收到真实 HTTP 401；仅测试 fixture 驱动可以把配置切至服务端接受的凭证引用。随后同一 integration、principal 和路由必须得到业务 HTTP 200，且响应包含 `order_id=demo-order`、`status=CONFIRMED`。S1-DISABLED 验证主体停用时切换凭证仍然返回 401。

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

运行全套测试；给 pytest 指定仓库内临时目录，可避开 Windows 共享 Temp 目录的权限问题：

```powershell
New-Item -ItemType Directory -Path .runtime -Force | Out-Null
.\.venv\Scripts\python -m pytest -q -s --basetemp=.runtime\pytest-d1
```

各命令的脱敏输出、失败尝试和解释见 [D1 evidence](docs/evidence/d1/) 与 [执行报告](docs/evidence/d1/REPORT.md)。最新干净环境测试为 **8 passed**，`pip check` 无依赖冲突。此前 pytest 默认临时目录遇到 Windows `PermissionError`；切换到仓库内 `.runtime` 临时目录后在主环境和独立干净环境都通过。

## 当前已知问题

- 当前 Function Calling 验证覆盖已配置的 `deepseek-flash` OpenAI-compatible Chat Completions 端点；思考模式不支持 `tool_choice=required`，D1 smoke 使用 `auto` 并在提示中要求一次只读调用。其他提供商和模型尚未验证。
- D1 的 HTTP API、固定 fixture 凭证和 SQLite 均是本地演示实现；尚未连接客户系统，也不提供模型可调用的写工具。
- 只完成 D1；没有实现 D2 调查图、D3/D4 审批与事务动作、Memory、Skill 或多 Agent。

## 文档与评审历史

- [冻结基线](docs/baseline/v1.0-implementation-baseline.md) 是唯一有效的架构与验收合同。
- [R1–R5 评审记录](docs/reviews/) 用于追溯设计放行过程，不构成并行需求。
- [历史方案资料](框架规划文档/) 保留早期构思及任务记录，现已归档，不作为当前实现依据。
- [v1.0 交接原件](开发目录/) 保留本地交付包。
