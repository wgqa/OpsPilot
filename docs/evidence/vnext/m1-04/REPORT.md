# OpsPilot vNext M1-04 实施与运行报告

## 基线与结论

- 开发起点：`main@e73b691ab29dfc46bd79461623ba4e8159257e05`。
- 最终提交 SHA：以本报告提交后的 Git HEAD 为准，并在交付回报中与 origin/main 比对；Git 对象不能在报告自身内容中引用其最终 SHA。
- 分支：`main`；本卡直接提交、推送 `origin/main`。
- 本轮范围：NL-01 至 NL-09。没有进入 M1-05 Web 审批或 M2 S2 403。
- 本轮终态：所有正式验收项在本地新鲜运行中 PASS；这是实施证据，不代表主 Agent 已验收 M1-04。
- 外部运行：Microsoft Edge、真实配置的 Provider `deepseek-flash`、仓库 MCP stdio Client/Server 和同一受信 S1 Demo Domain 的业务 Probe。Demo Domain 使用本地种子业务事实；没有把离线 Gold/fixture expected label 当成在线事实。

## 改动

- 新增 `opspilot/domain/investigation_context.py`：根据受信 TaskRun/Task/Session 绑定选择初始 Message 与已应用更正，校验 digest、序号、租户/所有者及 control revision；在模型/MCP attempt 注册前事务性复核。
- `opspilot/investigator.py`：删除固定 `reported_http_status=401` 假设，给真实用户输入建立带来源的 Prompt；显式识别本阶段不支持的 Scope 扩权请求并等待用户输入；更正后的新 Run 仅复用仍当前且版本兼容的同 Task Evidence，不重置全局 D2 预算。
- `opspilot/domain/database.py`、`chat.py`：Context Provenance 记录所选消息与 Run 控制引用；保留当前 Evidence 与历史来源撤销/版本过滤规则。
- `opspilot/domain/d2.py`、`d3.py`：将当前 TaskRun 控制上下文传到外发 attempt 守卫；非 READY 结果报告按 Run 做控制版本校验，避免更正后的 Run 沿用 rev0 路径。
- `frontend/src/App.vue`、`api.ts`、`style.css`：提供初始故障描述、普通只读追问、明确关键更正三种入口；展示脱敏来源/当前 Gate/等待原因，不提供 Web 审批或动作入口。
- 测试与 Smoke：新增 `tests/test_m1_dynamic_investigation.py`、`opspilot/smokes/m1_04.py`、`frontend/e2e/m1-04-browser.mjs`；更新 M1-03 浏览器 smoke 适配新的初始输入界面。
- 学习材料：`docs/learning/HANDBOOK_MAP.md`、`docs/learning/M1-04/STUDY_NOTES.md`、`INTERVIEW_QA.md`。
- 证据：`docs/evidence/vnext/m1-04/`，包含完整 JSON、Playwright/服务日志、截图、失败记录及案例冻结文件。

## NL-01 至 NL-09 矩阵

| 验收项 | 结果 | 实际证据 |
|---|---|---|
| NL-01 初始自然语言进入 Investigator Prompt | PASS | Edge 创建 S1 Task 后，NL-A 首条 Message `message-b0b48266-4d4f-446a-aa4e-9ca8990e13bd`（seq 14）作为 `INITIAL_SYMPTOM` 被 Context Provenance 选中。Run `run-f1c001ad-4a06-46ae-aa3c-00c16f4263d4` 的 expected/current revision=0、consumed seq=14；Prompt digest `a36e876c06fd19ddf50dacdca93f35951f3286edfbd563686f0be9a2857701c1`。实际 MCP 仍验证状态。详见 `runs/20261018T084356Z/screenshots/browser-run.json` 的 `nlA` 与机器结果。 |
| NL-02 同一绑定下不同用户线索 | PASS | NL-A/NL-B 使用相同 `orders-demo / integration-a` 和配置 v7 / 主体 v2 ENABLED / 策略 v3。A 首次 digest `9ce923…455b`，B `b033d9…b354e`；实际 Provider 都完成 5 次模型请求和 4 次 MCP 调用，工具顺序分别为 config→policy→principal→probe 与 probe→principal→policy→config。最终均由当前证据得出 HTTP 401 / AUTH_REJECTED、Gate READY；不将用户怀疑主体禁用作为事实。 |
| NL-03 不确定状态和 403/Scope 输入 | PASS | NL-B 的不确定线索通过实际 Probe 与 Principal 查询核实。NL-D Task `task-c075caeb-a8b8-4bb0-be0e-84f64b2808b5` / Run `run-837fe3e2-caf1-4661-9fe6-a616658e8e31` 进入 `WAITING_INPUT / S1_SCOPE_CHANGE_UNSUPPORTED`，0 Provider、0 MCP、0 Evidence、0 动作写入。 |
| NL-04 正式关键更正 | PASS | Edge 上先形成候选 Plan，再提交 `CORRECT_TASK_INPUT`。初始消息 seq 8、更正 seq 9，新的 Run `run-4163b62f-242c-406a-ba73-ac14d6d6ae83` 同时选择二者，expected/current revision=2、consumed/applied highwater=9；旧 Plan hash `55071595…e8817` eligibility=`CANCELLED`。更正 Run 的 6 次真实模型调用、4 次 MCP 调用后仍是当前 Gate READY / `WAITING_APPROVAL`；本次浏览器流程没有真人 Approval，N1-10 事务回归验证旧资格不能复用。 |
| NL-05 关键更正与动作提交竞态 | PASS | 新鲜 N1-10（更正先提交使旧 Plan/REPAIR 不可用）及 N1-11（REPAIR 先提交后保留 Ledger 并阻断旧 checkpoint DELIVER）均通过；见 `logs/pytest-nl-final-attempt-001.log`。 |
| NL-06 只读聊天隔离 | PASS | 浏览器发送事实追问与“我批准了/立即修复”后，Task status、revision、Plan hash 与 D3 动作计数未变；没有 Web 审批控件。 |
| NL-07 真实模型 + MCP + HTTP | PASS | Provider `deepseek-flash`：NL-A 5、NL-B 5、NL-C 6 次成功模型请求；合计 16 次模型请求，16 个真实 response ID，usage 可用总计 44,296 tokens。每个业务案例有 4 次 MCP tools/call，最终 Gate READY；Probe 实测 HTTP 401 / `AUTH_REJECTED`。所有逐次 ID、digest、tool schema 与 token 记录在 `RESULTS.json`。 |
| NL-08 浏览器恢复及来源时效 | PASS | Edge 执行真实创建、只读追问、更正和刷新；SSE 中途刷新恢复流式回答。API 重启前 PID 29236，重启后 PID 33308；同 Session 在新进程 HTTP 200 恢复 `BLUE-ORBIT` 回答。历史 Evidence 版本排除由 `test_followup_run_reuses_only_live_version_compatible_task_evidence` 与 M1-03 `test_chat_evidence_versions_exclude_pre_repair_probe_and_dependent_answer` 新鲜覆盖。 |
| NL-09 权限、预算、兼容回归 | PASS | Full pytest 109/109；NL 定向 + N1-10/N1-11 9/9；typecheck/lint/build 3/3；pip check PASS；Edge 跨租户请求 404，Approver Inspector 授权读取 200，受限 D3 写入计数全为 0。 |

## 业务与安全事实

同一冻结 Domain 中，当前配置是 v7 / `cred-v1`，AuthPolicy v3 接受 `cred-v2`，Principal v2 为 `ENABLED`。真实受限 `probe_endpoint` 对固定 route `/api/orders/demo-order` 返回 HTTP 401，Evidence 标记 `AUTH_REJECTED`，Probe before/after 版本都是 config v7 / policy v3 / principal v2。Gate 通过这四类当前 Evidence 判为 `READY`，因此只产生可供独立审批的候选 Plan。

跨 NL-A/B/C 的审批、ActionPermission、ActionIntent、ActionLedger、VerificationReceipt、ReportArtifact、DeliveryRecord 和工单完成数均为 0。配置保持 v7 / `cred-v1`。候选 Plan/等待审批记录属于调查结果，不是 REPAIR/DELIVER 已执行的证据。NL-D 没有启动模型或 MCP。只读聊天的“批准”措辞没有转成业务授权。

## 运行命令与分子/分母

命令均在仓库根目录执行；测试使用全新 `.runtime` basetemp，真实浏览器运行使用独立 Domain/Checkpoint SQLite。

```powershell
.venv\Scripts\python.exe -m pytest -q --basetemp=.runtime\pytest-m1-04-full
.venv\Scripts\python.exe -m pytest -q --basetemp=.runtime\pytest-m1-04-nl-final tests/test_m1_dynamic_investigation.py tests/test_m1_task_control.py::test_n1_10_correction_invalidates_old_run_and_new_run_binds_fresh_plan tests/test_m1_task_control.py::test_n1_11_repair_commit_survives_abort_and_old_checkpoint_cannot_deliver
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run build
.venv\Scripts\python.exe -m pip check
```

- 全量 pytest：109 passed / 109，0 failed，60.63 s。原始日志 `logs/pytest-full-attempt-001.log`。
- 定向动态输入 + N1：9 passed / 9，0 failed，5.76 s。原始日志 `logs/pytest-nl-final-attempt-001.log`。
- 前端 typecheck/lint/build：3 passed / 3；日志 `logs/frontend-full-attempt-001.log`。
- pip check：1 passed / 1；`No broken requirements found`，日志 `logs/pip-check-attempt-001.log`。
- 代码与文档的 `git diff --check`：PASS；保留的原始 pytest 输出中有空行/尾随空白，若对整个提交（含原始日志）执行该命令，Git 会报告这些原样保留的日志行。
- 真实 E2E：`.venv\Scripts\python.exe -m opspilot.smokes.m1_04 --evidence-dir docs/evidence/vnext/m1-04`（本地 `.env` 提供 Provider 配置）；Smoke 编排 API、MCP、Domain/Checkpoint DB 和重启，内部调用 `npm --prefix frontend run test:e2e:m1-04` 对应的 Playwright Edge 脚本。run 结果在 `runs/20261018T084356Z/`。

## 依赖和环境

- Python 3.14.0；Node 24.16.0；npm 11.13.0。
- Python：langchain 1.4.1；langchain-core 1.6.12；langchain-openai 1.7.2；langgraph 1.2.16；langgraph-checkpoint-sqlite 3.1.2；mcp 2.3.0；pydantic 2.14.1；fastapi 0.137.1。锁定声明见 `pyproject.toml`、`requirements.lock.txt` 与 `frontend/package-lock.json`；精确运行核验见 `logs/pip-check-attempt-001.log`。
- 前端：Vue 3.5.44、Vite 8.3.4、TypeScript 5.9.3、Playwright 1.64.1、vue-tsc 3.3.13、ESLint 10.0.1。精确依赖见 `frontend/package.json`/lock 文件。
- Provider key 没有入库或写入报告；机器结果记录 `provider_api_key_recorded=false`。Model ID 为 `deepseek-flash`。

## 失败记录、局限和审计边界

首次 NL-D Edge 尝试曾因 `InvestigatorState` 未声明 `scope_clarification_required` 而被 LangGraph 丢弃 intake 标志，错误地继续做调查并到达 `WAITING_APPROVAL`。该失败真实保留于 `runs/20261018T082748Z/ABORTED_RESULT.json`；当时有候选 Plan / PlanAuthorization，但 0 Approval、Permission、Intent、Ledger、验证、报告、交付或工单写入。修正 TypedDict 状态后，最终 NL-D 0 模型/0 MCP/0 Evidence。

其他失败包括更正 Run 的 `WORKER_RETRY_EXHAUSTED`（具体 worker 错误类未持久化）、Inspector 查询变量作用域、schema 版本断言、异步 Inspector 轮询和结果聚合 SQL 参数数量，均保留在 `FAILURES.md` 和各次日志/结果中，未覆盖。一次早期 correction-context 选择器报错的最初控制台输出未单独落盘，这一点已在失败台账明确披露。

真实模型轨迹使用 `deepseek-flash`，模型输出及工具顺序存在随机性；本次只证明输入来源差异真实到达模型，并观察到不同 MCP 次序，不承诺任意线索都会产生不同工具路径。NL-Q 的额外模糊症状用例未执行，不能视作通过。真实运行是本地单实例 OpsPilot Demo Domain，不代表生产 IAM 或生产业务 API。Token usage 只报告 Provider 返回 usage 的 Investigator 调用；不能从未提供 usage 的调用推算 token。

## 学习材料与主线状态

- [源码学习地图](../../../learning/HANDBOOK_MAP.md) 已增加第 4/5/6 章与 M1-04 源码/Trace/取舍对应关系。
- [实证学习笔记](../../../learning/M1-04/STUDY_NOTES.md) 记录 Task/Run/Graph 边界、Prompt Provenance、安全 Gate 与当前 Evidence，并链接真实案例。
- [面试问答](../../../learning/M1-04/INTERVIEW_QA.md) 提供 6 题的 30 秒/2 分钟回答、追问和代码/证据入口。
- 冻结输入见 `CASES.md`；机器结果和每次模型/MCP ID 见 `RESULTS.json`；首失败与修复见 `FAILURES.md`；截图及完整 Edge/服务日志在 `runs/20261018T084356Z/`。
- 本轮无需修改冻结架构、业务完成语义或权限/事务合同。提交、推送后停止，等待主 Agent 独立验收；不进入 M1-05 或 M2。
