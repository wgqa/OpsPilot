# M2-02 实施与验收报告

日期：2026-10-19
开发基线：`main@c9542ca46383ca3c903a1b245031bbb4a96c9b68`
先行冻结标准：`4efc11eb8524b4e03d4b8e17c09d08473040f1e1`
实现提交：`324c71d9ec2f48dfc3c073d242dc87ab428a720c`
冻结合同：仓库 `PROJECT_NORTH_STAR.md`、vNext v0.3 产品架构合同及冻结的 M2-02 标准。

## 结果

M2-02 交付了 S2 可信诊断与冻结申请草稿：Agent 可在同一 Task 内利用连续消息和正式纠错重新调查；S2 先通过当前绑定资源的在线 Probe，再基于同一请求关联的可信 Authz Decision 形成诊断回执与申请草稿。模型工具 schema 随 Run 当前可信证据收窄，403 后的权限事实读取仅允许最新 Probe 的 request_id；根因判断仍由 Domain Evidence Gate 完成。前端现可显示 S2 结果及草稿状态。

没有实现 HandoffReceipt、接收队列或自动 Scope 授权。`HANDOFF_READY` 只表示已形成待人工/外部流程接收的申请草稿，不代表 Scope 已授权、故障已恢复或已完成交接。S1 的 401 路径继续保持原审批和受控动作流程。

冻结的 48 条 R/H/A 评测结果：R `16/16 PASS`，H `16/16 PASS`，A `13/16 PASS、1 FAIL、2 PARTIAL`；合计 `45 PASS、1 FAIL、2 PARTIAL`。这不是 M2-02 总体 PASS。A-G6-H1 的冻结结果未被后续补充运行替换；A-G1-H1 缺少原始 Trace 与截图，A-G7-H2 的原始 fixture 实际得到 403 而非设计的 404。完整结果见 [RESULTS.json](RESULTS.json)，先行 Rubric/Gold/旅程见同目录冻结文件。

## 实际验证

| 检查 | 新鲜结果 | 证据 |
|---|---:|---|
| 完整 Python 回归 | 154 passed，115.21 秒，exit 0 | [pytest-full-final-05.txt](raw-logs/20261019-final-05/pytest-full-final-05.txt) |
| S2 Domain 定向测试 | 6 passed，3.55 秒 | [pytest-s2-10.txt](raw-logs/20261019-fix-10/pytest-s2-10.txt) |
| Python compileall | exit 0 | [compileall-final-05.txt](raw-logs/20261019-final-05/compileall-final-05.txt) |
| Vue 类型检查与生产构建 | exit 0；Vite 8.3.4 | [frontend-build-final-05.txt](raw-logs/20261019-final-05/frontend-build-final-05.txt) |
| MCP stdio tools/list 与 tools/call | exit 0；默认 4 个工具，S2 opt-in 5 个工具；真实 Probe 403 后查到同 request 的当前 DENY/SCOPE_INSUFFICIENT；跨 scope 查询被拒绝 | [脱敏 MCP Trace](traces/mcp/mcp-smoke-02.jsonl) |
| 真实 Provider/MCP 安全旅程 | 有真实模型调用和 MCP 轨迹，详见 TRACE 索引 | [TRACE.json](TRACE.json) |

完整测试命令：

```powershell
.venv\Scripts\python.exe -m pytest -q --basetemp=.runtime/m2-02/pytest-final-05
.venv\Scripts\python.exe -m compileall -q opspilot
cd frontend; npm run build
```

定向 G4 修正补充运行（不替代冻结 A-G4-H1）：

```powershell
.venv\Scripts\python.exe -m opspilot.smokes.m2_02_g4 `
  --db .runtime/m2-02/g4-guard-01/domain.sqlite3 `
  --checkpoint-db .runtime/m2-02/g4-guard-01/checkpoints.sqlite3 `
  --output docs/evidence/vnext/m2-02/runs/20261019-g4-guard-supplement/g4-guard-01.json `
  --strategy A
```

该运行得到 `HANDOFF_READY`、控制版本 1、6 次模型调用及 4 次 MCP 调用；两个 403 Probe 均跟随对应当前 Run 的 Authz Facts 查询。

补充越界负例与 401/404 运行命令及输出保存在各自 `runs/20261019-*-supplement/` 目录。修复后的 G6-H1 补充运行得到 `NO_ACTION`，0 次模型与 MCP 尝试、0 回执/草稿；原冻结 A-G6-H1 仍记 FAIL。G3-H1 401 保持 S1 `WAITING_APPROVAL`，无 S2 回执/草稿；G7-H1 404 为 `INCONCLUSIVE`。

## Provider、MCP 与浏览器轨迹

真实 Provider 模型为 `deepseek-flash`。提交包内脱敏轨迹索引累计 78 次模型调用、55 次 MCP observation；可用的 Provider token usage 合计 input 240,252、output 25,238、total 265,490。该合计包含独立补充与未完成浏览器运行，不能视为冻结 48 试次的评测成本，也不能据此做性能比较。逐运行数量、Token 记录和脱敏轨迹位置见 [TRACE.json](TRACE.json)。Task、Run、Evidence 与 Request ID 在轨迹副本中已稳定伪名化；MCP 使用真实 stdio Client/Server，S2 工具只能以可信 TaskBinding 关联的 Request ID 读取授权事实。

真实 Vue 工作台浏览器旅程已登录成功（HTTP 200），正式关键纠错请求返回 HTTP 202、`CORRECT_TASK_INPUT`、`ACCEPTED`，控制版本为 1。后续浏览器 Run 用旧 request id 并查询额外主体信息，耗尽预算后得到 `INCONCLUSIVE / S2_EVIDENCE_BUDGET_EXHAUSTED`，Task 当前结果失效。该失败原样保留在 [g4-failure-and-recovery.json](traces/browser/g4-failure-and-recovery.json)。之后加上的 per-Run 工具 schema 收窄通过了新的真实 Provider/MCP 补充 Smoke，但没有重演该浏览器路径。浏览器截图因自动化环境不能可靠确认活动 Edge URL，未生成；因此 UI 端到端证据为 PARTIAL。

## 安全边界与已知限制

- Domain 持久化实际 Probe 和 Authz Decision；HTTP 403 自身不作为充分根因证据。证据要求同 Task、同 Run/request 关联、当前版本兼容。
- S2 的运行期 Scope/Grant/Policy 写入为零；S2 不产生 ActionIntent、ActionLedger 或受限业务写入，也没有 HandoffReceipt/queue。
- 保留 D1–D7、M1、M1-HF-01 和 M2-01 回归；全量 pytest 154/154 通过。
- 固定知识包中的 legacy/current 文档只提供背景方法，不能覆盖实时 Evidence/Gate。
- 用户文字及模型输出不是权限事实；纠错通过 TaskControl 持久受理并由新 Run 消费。
- 冻结试次没有逐 Run 保存 Git SHA，因此无法证明全部 R/H/A 观察对应最终实现提交 `324c71d...`。评测是探索性对照，不是统计结论。
- Python `pyproject.toml` 精确固定直接依赖；没有 Python 全量 lockfile。环境实际 `pip freeze` 单独保留。
- 浏览器截图缺失、G1-H1 原始 A Trace 缺失、A-G6-H1 FAIL、A-G7-H2 PARTIAL 均交主 Agent裁决；没有把补充结果回写成冻结 PASS。

## 依赖与学习材料

Python 3.14.0；Node 24.16.0 / npm 11.13.0。直接 Python 依赖版本见 [python-dependencies.txt](python-dependencies.txt)，运行环境完整解析依赖见 [python-environment-freeze.txt](python-environment-freeze.txt)，前端安装版本见 [frontend-dependencies.txt](frontend-dependencies.txt)。源码学习与面试材料位于 [`docs/learning/M2-02`](../../../../learning/M2-02/)。

本轮结果提交后停止开发，等待主 Agent 独立验收；不进入 M2-03。
