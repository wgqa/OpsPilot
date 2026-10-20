# 执行命令与第三方阅读顺序

工作目录：`D:\学习\agent新项目`。所有补证在当前冻结生产源码上新鲜执行；仅隔离测试入口和只读证据脚本新增。详细版本在 `runs/environment.json`。本文件中的本地 Runtime 数据库、口令文件不提交。

## 实际测试命令

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -q --basetemp=.runtime/m3-closeout-01/pytest-full-01
.\.venv\Scripts\python.exe -X utf8 -m pytest -q tests/test_m301_memory.py tests/test_m303_semantic_memory.py tests/test_m302_context.py --basetemp=.runtime/m3-closeout-01/pytest-focused-01
```

在 `frontend` 下按顺序执行：

```powershell
npm run typecheck
npm run build
npm run lint
```

标准输出和错误输出通过 `2>&1 | Tee-Object -FilePath <对应日志>` 保存，各自 `$LASTEXITCODE` 存对应 exit-code 文件。没有通过改测试或预算阈值取得通过。

## 实际服务与浏览器操作

本轮临时控制器启动命令：

```powershell
.\.venv\Scripts\python.exe -X utf8 -u .runtime/m3-closeout-01/journey-01/service_control.py
```

控制器复用 `opspilot.smokes.m1_03` 的既有 `_server_environment`、`_start`、`_wait_http`、`_start_vite`、`_kill`。使用随机合成本地口令，真实 API8001 和前端5174；不会从原8000服务获取身份。源脚本留在 `runs/helpers/` 供审查，包含最初未能捕获请求体的观测器，**没有把它改写成一次成功观测**。Worker deadline 使用既有 helper 的240000ms；原模型8次／MCP6次计数上限未改。

操作顺序：

1. support-a Web 创建 Session／Task A、故障输入，等待真实调查。
2. 正常退出、以 approver-a 登录，在 Web 批准当前不可变 Plan，用户确认原生弹窗。
3. 受控执行完成后，support-a Web 从当前任务创建 Episodic Candidate。
4. approver-a Web 选择该候选，用户确认激活。
5. 按已先提交的 `CASE-B-SETUP.md` 执行已有 fixture，输出 `fixture-second-incident.json`。此动作与正常业务写入分开。
6. support-a Web 新建 Session／Task B，真实调查后只读追问，保存依赖历史方法的助手消息。
7. approver-a Web 撤销同一 Memory，用户确认。
8. support-a 同 Session 新只读 Chat，查 Manifest 排除理由。
9. 对同 Task B 通过 Web 提交正式关键更正；用户确认。只读监视脚本在新 Run 已有当前 MCP 和 Checkpoint 后向控制器写 restart 命令，由既有 `_kill` 终止本轮自有 API 树并重启同库。没有直接SQL更改业务状态。
10. 浏览器刷新，查同 Run ID、撤销排除、等待审批及事件；保存最终 DOM／截图16。

另一个全新运行目录才能重跑初始化控制器；不要在已有证据目录直接重新执行，否则会追加原日志。任何复跑应分配新目录并保留本次 PARTIAL 和 GAP-01；不能修改原观测器后将历史记录改称成功。

## 只读导出与索引重算

```powershell
.\.venv\Scripts\python.exe -X utf8 docs/evidence/vnext/m3-closeout-01/export_trace.py .runtime/m3-closeout-01/journey-01/domain.sqlite3 .runtime/m3-closeout-01/journey-01/checkpoints.sqlite3 docs/evidence/vnext/m3-closeout-01/runs/journey-01/TRACE-final-domain.json
.\.venv\Scripts\python.exe -X utf8 docs/evidence/vnext/m3-closeout-01/summarize_evidence.py
```

第二条可只依赖已提交 JSON／日志重算 `RESULTS.json`、`TRACE.json`；其环境清单反映执行机器，应在另目录比较重算输出，不能覆盖本次原件。索引脚本是本轮只读数据对账，不是新评测框架。16项 Domain 对账都通过，但不会把它们转换成原始 Provider 请求体证明。

## 五分钟阅读地图

1. `REPORT.md` 首段、GAP-01 和十条件结论：本次 PARTIAL 的确切边界。
2. `RESULTS.json`：实际数量、逐项状态和未知费用；不是整体 M3 自签 PASS。
3. `TRACE.json` 与 `TRACE-final-domain.json`：A 的审批／Intent／Ledger／Verification／Report／Delivery → Episodic 生命周期 → 不同 B 的 Provenance → 撤销与旧助手排除 → 同 Run恢复。
4. `fixture-second-incident.json`、`CASE-B-SETUP.md`：v8→v9 合成第二事故及不变性；不能将准备动作称 Agent 修复。
5. `screenshots/05-task-a-completed.png`、`08-episodic-active.png`、`13-episodic-revoked.png`、`16-same-run-recovered.png`，以及对应完整 DOM。
6. `process-events.jsonl`、`crash-trigger.json`、原始 api.log：旧／新 PID 与同 Run，额外未知模型尝试。`provider-wire.jsonl` 只有启动记录，没有请求体。

核心源码复用未改：`opspilot/domain/episodic_memory.py` 负责来源、确认、撤销与当前资产守卫；`investigator.py::_prompt_messages` 构造历史提示及当前事实；`domain/chat.py` 维护只读 Context 与消息依赖；`web/worker.py` 和既有 TaskControl／Domain／Checkpoint 负责恢复及唯一业务权威。冻结生产源码可由基线 SHA 离线读取。

复盘追问：

- 历史200为什么不能证明 B 已恢复？A 的来源回执与 B 当前请求／版本不同；B 当前 Probe401且没有审批／动作。
- 怎么知道恢复的是同 Run？崩溃前 Run／thread、持久 Checkpoint 与新进程之后保持一致，预算6→8／5→6；没有新建替代 Run。
- 为什么仍 PARTIAL？实际模型响应、Token 和 Provenance 可查，但观测器挂错 httpx，SDK 用 httpx2，真实传输请求体没有独立保存。
- 为什么不宣称 Memory 有收益？本轮只有一次应用旅程，未重新进行冻结 ON/OFF 对照；“合法检索使用”不等于性能增益。
