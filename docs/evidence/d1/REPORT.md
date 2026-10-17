# OpsPilot D1 执行报告

**执行日期：** 2026-10-17（北京时间）
**分支：** `d1/implementation-2026-10-17`
**状态：** WP-01 至 WP-06 的 D1 验收项均已执行并通过，等待主 Agent 复核；D2 未开始。
**架构合同：** [v1.0 实施基线](../../baseline/v1.0-implementation-baseline.md)，未修改冻结语义。

## 环境与依赖

在独立干净虚拟环境 `.runtime/clean-venv` 中从 `requirements.lock.txt` 安装并运行。运行环境为 Windows、CPython 3.14.0。直接依赖版本如下；完整传递依赖由 lockfile 固定。

| 包 | 锁定版本 |
|---|---:|
| langchain | 1.4.1 |
| langchain-openai | 1.7.2 |
| langgraph | 1.2.16 |
| langgraph-checkpoint-sqlite | 3.1.2 |
| mcp | 2.3.0 |
| pydantic | 2.14.1 |
| pytest | 9.1.1 |

执行命令：

```powershell
python -m venv .runtime\clean-venv
.\.runtime\clean-venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.runtime\clean-venv\Scripts\python.exe -m pip check
.\.runtime\clean-venv\Scripts\python.exe -m pytest -q -s --basetemp=.runtime\clean-pytest-final
.\.runtime\clean-venv\Scripts\python.exe -m opspilot.cli smoke tool-call
.\.runtime\clean-venv\Scripts\python.exe -m opspilot.cli smoke mcp
.\.runtime\clean-venv\Scripts\python.exe -m opspilot.cli smoke checkpoint
.\.runtime\clean-venv\Scripts\python.exe -m opspilot.cli smoke s1
```

`pip check` 输出 `No broken requirements found.`；pytest 输出 `8 passed in 4.91s`。Windows 默认 pytest 临时目录曾遇到 `PermissionError`，改用仓库内 `.runtime` 后在干净环境通过。失败记录保存在 [pytest-default-temp-permission-failure.txt](pytest-default-temp-permission-failure.txt) 和 [pytest-uncreated-basetemp-failure.txt](pytest-uncreated-basetemp-failure.txt)。版本与 lockfile SHA-256 见 [clean-environment.txt](clean-environment.txt)。

## WP-01 / WP-02：真实模型 Function Calling

真实端点类别为 OpenAI-compatible Chat Completions，模型 ID 为 `deepseek-flash`。模型真实返回 `get_demo_service_info` 工具调用，脚本使用该调用的参数执行类型化只读工具，并记录 `tool_call_id`、Schema 和 Domain Observation。完整脱敏日志在 [tool-call-smoke.txt](tool-call-smoke.txt)，无效参数的拒绝记录在 [tool-argument-negative.txt](tool-argument-negative.txt)。

成功记录的关键值：

```text
tool_call_id = call_00_ET_caWigzLCR57hwBGEchWF7532
tool_name = get_demo_service_info
arguments = {"service_id":"orders-demo"}
observation = tenant-a / integration-a / principal-a / cred-v1 / config_version 7
             accepted_credential_ref=cred-v2 / principal_status=ENABLED
```

Schema 拒绝 `service_id=7`（`string_type`）和额外的 `tenant_id`（`extra_forbidden`）。首次请求使用 `tool_choice=required`，端点在思考模式下返回 HTTP 400；端点文档说明思考模式不支持 `required` 或具名选择，D1 实现改为 `auto`，并在提示中明确要求模型只调用一次工具，随后调用通过。[DeepSeek Chat Completions API 文档](https://api-docs.deepseek.com/api/create-chat-completion/)记录了该兼容约束。第一次实际工具执行时本地 demo 数据库尚未初始化，出现 `OperationalError`；smoke 现会在调用前建立 S1 fixture，之后通过。每次失败尝试见 [tool-call-smoke-attempt-1.txt](tool-call-smoke-attempt-1.txt)、[tool-call-smoke-attempt-2.txt](tool-call-smoke-attempt-2.txt)、[tool-call-smoke-attempt-3.txt](tool-call-smoke-attempt-3.txt)。

本机模型设置保存在根目录 `.env`；`.env` 已由 `.gitignore` 忽略，`.env.example` 仅保留空变量名。密钥没有进入输出或 Git 变更。

## WP-03：真实 MCP stdio

官方 MCP Python SDK `2.3.0` 客户端启动独立 stdio Server 子进程，真实完成 `tools/list` 与 Domain-backed `tools/call`。列表含两个只读工具：`get_demo_service_info(service_id: str)`、`get_integration_config(integration_id: str)`；Schema 不接收 tenant、Authorization 或 URL。成功调用的 structured content 来自 SQLite Domain 查询。把 `integration-b` 交给服务端绑定的 `tenant-a` scope 后，SDK 返回 `is_error=true`。原始脱敏记录见 [mcp-smoke.txt](mcp-smoke.txt)。

## WP-04：跨进程 LangGraph checkpoint 恢复

LangGraph `1.2.16` 使用 SQLite `SqliteSaver` 持久化 interrupt。进程 A（PID `26596`）保存 `d1-cross-process-resume` 的中断状态并退出 0；错误 actor 在 checkpoint 读取前被拒绝（退出 3）；进程 B（PID `4364`）以同一 thread ID 恢复并退出 0。`task_id=d1-task`、`draft_marker=draft-401` 和 `evidence_count=2` 均保留，状态到达 `complete`。完整记录见 [checkpoint-smoke.txt](checkpoint-smoke.txt)。

## WP-05：S1 无模型真实业务因果链

smoke 通过 loopback HTTP 请求调用真实 Python Domain API，未调用模型。POS：同一 `tenant-a / integration-a / principal-a / GET /api/orders/demo-order` 首次使用 `cred-v1`、版本 7 得 HTTP 401；测试 fixture 将引用切至 `cred-v2`、版本 8 后，同调用方和路由得到 HTTP 200，业务响应为 `order_id=demo-order`、`status=CONFIRMED`。授权事件顺序为 `AUTH_REJECTED`、`AUTH_ACCEPTED`。

DISABLED：同一 `principal-a` 即使切到 `cred-v2`、版本 8 仍得 HTTP 401；事件为两次 `AUTH_REJECTED`，主体没有自动启用。完整请求/响应见 [s1-smoke.txt](s1-smoke.txt)。另运行独立 CLI API Server 与 Probe，首个真实业务请求返回 401，证据见 [cli-reset.txt](cli-reset.txt)、[cli-api-server.txt](cli-api-server.txt)、[cli-api-probe.txt](cli-api-probe.txt)。

## WP-06：交付、边界与已知问题

- D1 代码、测试、依赖锁、基线/评审/交接文档和本报告均已放在当前分支，准备提交主 Agent 复核。
- MCP 工具保持只读，server 启动时固定租户；fixture-only 配置切换只在测试 fixture 模块中，未暴露为 Agent/MCP 工具。
- API、SQLite 和凭证 fixture 是本地 demo，不是客户系统或生产 IAM。Function Calling 仅验证配置的 `deepseek-flash` 兼容端点；其他模型/提供商尚未验证。
- 未实现 D2 调查图、D3/D4 审批事务、Memory、Skill、多 Agent、Redis 或其他 P1 项；D1 结束后停止扩展，等待主 Agent 验收。
- 基线无变更，无 ADR 需求。

## 证据文件

- [S1 POS/DISABLED smoke](s1-smoke.txt)
- [MCP stdio smoke](mcp-smoke.txt)
- [Checkpoint 跨进程 smoke](checkpoint-smoke.txt)
- [真实模型 Function Calling](tool-call-smoke.txt)
- [模型参数错误路径](tool-argument-negative.txt)
- [独立干净环境 pytest](pytest-clean.txt)
- [依赖一致性检查](pip-check.txt)
