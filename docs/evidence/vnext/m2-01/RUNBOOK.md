# M2-01 复现运行手册

所有命令从仓库根目录 `D:\学习\agent新项目` 的 PowerShell 执行。先确认 `main` HEAD 与工作区，再使用仓库隔离的 `.runtime/m2-01` basetemp；不要复用 M1 Demo 数据库。

## 环境

- Python `3.14.0`，Windows PowerShell。
- 虚拟环境：`.venv\Scripts\python.exe`。
- `requirements.lock.txt` SHA-256：`59658b2a1412f580237fd3a20d88163aea3579e89f6499a768796b6aaca67ae8`。
- 关键版本：FastAPI `0.137.1`、Pydantic `2.14.1`、MCP `2.3.0`、LangGraph `1.2.16`、pytest `9.1.1`。
- 本轮 M2 facts smoke 不需要模型或浏览器；报告计数 0。S1 回归 smoke 会真实调用 `deepseek-flash` Provider。

## 定向、全量与静态检查

每次运行使用尚不存在的 basetemp 目录并写入新的原始日志：

```powershell
$base = '.runtime/m2-01/pytest-directed-<new-id>'
if (Test-Path -LiteralPath $base) { throw "Use a fresh basetemp path" }
& .\.venv\Scripts\python.exe -m pytest tests/test_m2_01_facts.py -q --basetemp $base
```

```powershell
$base = '.runtime/m2-01/pytest-full-<new-id>'
if (Test-Path -LiteralPath $base) { throw "Use a fresh basetemp path" }
& .\.venv\Scripts\python.exe -m pytest -q --basetemp $base
```

本次最终源码定向命令实际结果为 8/8，通过日志 `logs/pytest-m2-01-directed-trace-fields-release.txt`；全量实际结果为 148/148，通过日志 `logs/pytest-full-trace-fields-release.txt`。默认用户 Temp 曾出现 Windows PermissionError，因此最终命令显式指定仓库内 basetemp；该环境问题的原始日志保留。

```powershell
& .\.venv\Scripts\python.exe -m compileall -q opspilot tests
& .\.venv\Scripts\python.exe -m pip check
git diff --check
```

## 真实 HTTP + MCP stdio facts smoke

```powershell
& .\.venv\Scripts\python.exe -m opspilot.smokes.m2_01_facts `
  --output docs/evidence/vnext/m2-01/TRACE.json
```

Smoke 会为 401、403、200 分别创建独立 SQLite fixtures，调用 loopback HTTP API；随后启动单独 MCP stdio 子进程，执行真实 `tools/list` 和 `tools/call`。输出包括数据库版本、Authn/Authz event、Scope/Policy 前后版本、运行期写审计和脱敏 Trace。当前记录的 `tools/list=1`、`tools/call=4`、HTTP 请求=3、运行期 Scope/Policy 写入=0。运行结果见 `logs/m2-01-real-http-mcp-trace-fields-final.txt`。

MCP 另有一个 pytest 子场景，在 tenant-B 服务端实际创建合法请求，再由 tenant-A TaskBinding 查询该 request id，确认越租户读取失败；独立 smoke 中的 cross-scope ID 是随机非本任务 request id。二者在报告中分别描述。

## S1 真实闭环回归

冻结 S2 Outcome 不影响既有 S1 受控修复回归。实际记录入口命令：

```powershell
& .\.venv\Scripts\python.exe -m opspilot.cli d3-smoke `
  --db .runtime/d3-domain.sqlite3 `
  --checkpoint-db .runtime/d3-checkpoints.sqlite3
```

最终新鲜运行的两进程原始输入/输出和 Trace 位于 `s1-d3-smoke-release/`。实际使用的独立 `d3-start` 和 `d3-approve` 命令、参数、进程 ID 记录在 `s1-d3-smoke-release/REPORT.md` 与 `process_logs.json`。验证结果包括：首个 HTTP 401、独立 Approver、审批前零写入、REPAIR 一次、同身份 HTTP 200、报告先冻结、DELIVER 一次和唯一工单回执。

## 证据

- HTTP/MCP Trace：`TRACE.json`。
- 冻结标准：`ACCEPTANCE_PLAN.md`、`S2_GOLD.json`、`S2_RUBRIC.json`、`TRACE_SCHEMA.json`、`DEFERRED_GATES.md`。
- 评估矩阵：`RESULTS.json`。
- 失败尝试：`FAILURES.md` 与 `logs/` 原始日志。
- SHA-256 索引：`SHA256SUMS.txt`。
- 独立 S1 闭环：`s1-d3-smoke-release/`。

先行标准提交 `832dd632dd0ed27201015a4e66f50e1a4771fec1` 必须早于实现/功能 RED；最终实现提交为 `ff4a925e358101abee5769da324d73d978088881`。冻结标准先行、实现代码再提交的顺序保持不变。
