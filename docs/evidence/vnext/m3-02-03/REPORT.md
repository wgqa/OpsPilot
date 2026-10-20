# M3-02 + M3-03 实施与证据报告

**状态：PARTIAL，提交主 Agent 独立复核；不自签阶段 PASS。** Context Builder、压缩、来源 DAG、Inspector、Episodic 检索深化和 Semantic 生命周期已实现。补证已完成真实 Semantic 跨 Task 使用、撤销后的新调用、同 Run 进程崩溃恢复，以及原 26 轮长会话的重启续聊。严格按冻结 E2E-03 的“可信业务案例 → Episodic Candidate → Web 审核 → Task B → 撤销 → 恢复”解释，本阶段没有重新录制这一整条新鲜 Web 旅程；不能用 Semantic 用户约定的链路冒充业务案例抽取。其自动化回归与 M3-01 历史真实案例证据分别列明。

## Git 与阶段顺序

| 阶段 | SHA |
|---|---|
| 任务卡基线 | `5ade2b5deedbb3704b09e9d6fbbfbffa3ab8deb8` |
| 独立冻结标准 | `3cb826d0d41984c898aefa5081d347d94a7c9c21` |
| 原始 RED | `48be70422f03b567b09a6bd45efc42d7a98ad598` |
| M3-02 实现 | `f9f9d8a7c724a477578ff9eed2a48f4972078ee0` |
| M3-03 实现 | `a0ac67836c5dc641d316628689621c986e91b57a` |
| 本次继续起点 | `c57cd28827335dddb8ab21afa093131b1a6faaec` |
| 补充 RED | `9d264d1780d585d4b763f8e54af919ac0d29f1a0` |
| 最小修复 | `e2c48e78e5d41f2cc0c74632665fa3600502005e` |
| 最终证据提交 | 交付消息给出；本提交的父提交即上述修复 |

直接使用 main，不创建分支或 PR。用户未提交的 `AGENTS.md`、`PROJECT_NORTH_STAR.md`、`开发目录/` 和历史临时目录均未暂存。依赖基线没有变更。原冻结 Gold、原始失败日志和 M3-01 的 12/16 结果未改写。

历史阶段顺序存在证据缺口：M3-03 实现提交时，M3-02 的可持久复核跨进程证据尚未补齐；本报告不追认当时核心门禁已全部通过。此次补证不能伪装成先前已存在的验收材料。

## 本次最小修复

1. **摘要被可选历史挤出。** 真实低预算长会话生成了摘要，但 1400 输入预算内的较长近期回答优先级更高，导致摘要最终被排除。保留现场 `long-recovery-01/before.json`，定向 RED 见 `continuation-01/summary-priority-red-02.log`；仅将有效历史摘要排在可选近期历史之前，可信控制、当前事实及当前输入继续优先。
2. **正式纠错未进入 Chat 历史。** 旧查询只选 `CHAT_READONLY`。长对话可能丢失最初描述，正式 `CORRECT_TASK_INPUT` 更没有被直接选入。现在从相同 Tenant/Session/Task 的持久命令选择原始任务输入和最近正式纠错，作为预算必保留的 `TASK_INPUT_ANCHOR / UNTRUSTED_USER_INPUT`；原文不能代替 MCP 事实或授权。它们超过预算时仍显式停止，不截掉可信控制。来源写入及递归校验支持同 Task 纠错消息，出站前继续重验。定向 RED 见 `input-anchor-red.log`。
3. **登录错误文案。** `INVALID_CREDENTIALS` 的 401 现在准确提示所选身份口令不匹配或未配置；过期会话仍提示重新登录。没有改变认证检查、口令或用户原服务。真实错误口令 RED/GREEN 的 DOM 与截图已保存。

未修改 TaskControl、Gate、Approval、Plan、REPAIR/DELIVER 事务或业务完成语义，没有新增业务场景。

## 新鲜自动化验证

| 运行 | 结果 | 原始日志（`runs/` 下） |
|---|---|---|
| 首轮补证完整 pytest | 223/223，退出 0，173.61s | `continuation-01/pytest-full.log` |
| 摘要优先级修复后完整 pytest | 224/224，退出 0，169.99s | `continuation-01/pytest-full-after-summary-fix.log` |
| 两项补充修复专项 | 11/11，退出 0，9.76s | `continuation-01/input-anchor-green.log` |
| **最终完整 pytest** | **225/225，退出 0，173.64s** | **`continuation-01/pytest-full-final.log`** |
| 前端 typecheck/build | 退出 0 | `continuation-01/frontend-build.log` |
| 前端 lint | 退出 0 | `continuation-01/frontend-lint.log` |

命令：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -q --basetemp=.runtime/pytest-m302-final-continuation-03
.\.venv\Scripts\python.exe -X utf8 -m pytest -q tests/test_m302_context.py --basetemp=.runtime/pytest-m302-input-anchor-green
# frontend/ 目录
npm run build
npm run lint
```

pytest 覆盖原 M1、M1-HF-01、M2 与 M3-01 安全回归。前端构建之后只有 Python/测试/证据变更。具体依赖版本见 `runs/m303-final/environment.txt`：Python 3.14.0、FastAPI 0.137.1、LangGraph 1.2.16、langchain-core 1.6.12、tiktoken 0.14.0、pytest 9.1.1、Pydantic 2.14.1、Uvicorn 0.49.0。

## 真实 Semantic Web、Provider 与 MCP 链路

来源 Task A 为 `task-9444df29-9e21-4b7f-9b26-df6ff17cf123`；用户在独立 approver-a Web 会话确认 `semantic-8669bb64-f2b1-41a9-ae9c-10c3ef5a7626 v1`。Task B 为 `task-7379b52e-d364-4836-84e5-579e5d3aad31`，Run `run-733ea4a7-56c8-4679-a899-02dbb914427a`。真实 DeepSeek `deepseek-flash` 5 次 Provider 响应、18,731 Token，真实 TaskBinding MCP stdio 4 次成功查询。5 份 Provenance 均选入 Task A 的项目约定。用户说 403，实际 HTTP Probe 是 401，Gate 仍为 `AUTHENTICATION_FAILURE_REMAINS_S1`，业务只到 `WAITING_APPROVAL`。来源记录分别见 `TRACE-task-a.json`、`TRACE-task-b.json`，位于 `runs/m303-final/`。

原 API 的 Web 撤销事件为 `semantic-event-185260f4-01dd-4a13-ae62-7b0eb500dae5`，UTC 12:53:38，状态 REVOKED v2。为解决后续演示登录阻塞，本次从撤销前 Task B 的真实 Domain/Checkpoint 做 SQLite backup，建立 loopback 隔离副本 8001/5174，只为副本配置合成演示口令。没有改动原 API8000、前端5173、用户口令、真实模型配置或原数据库。

该副本的独立人工 Web 撤销时间是 UTC `2026-10-20T15:34:29.477`，与原 API 的撤销事件分开记录，不混算。

| 副本本次调用 | 可信观察 |
|---|---|
| 撤销前 Chat `run-64d6cebe-7dd1-41ce-9bc0-acdb348a0423` | SUCCEEDED；2015 Provider Token；选入 ACTIVE v1；产生依赖该记忆的助手回答 |
| 撤销后 Chat `run-d8d3a865-a29a-424f-90b5-74fdef397090` | SUCCEEDED；2956 Provider Token；选用 Memory 为空；排除 `SEMANTIC_MEMORY_REVOKED` 及旧回答 `MEMORY_REVOKED_EXPIRED_OR_CHANGED` |
| 新调查 `run-5aa57324-4cd2-4888-b207-b993ae799e44` | 5 Provider 响应、4 MCP；到 WAITING_APPROVAL；监控器没触发崩溃，不算恢复成功 |
| 崩溃调查 `run-5b0d9abe-20ca-438c-8f3d-2a5f92d6da37` | 同 Run 在新进程恢复；5 个完成 Provider 响应、1 个未知中断预留、4 MCP；全部新上下文排除撤销 Memory；WAITING_APPROVAL |

崩溃发生在 1 个 MCP 观察和 5 个 Checkpoint 已持久化之后；API 进程树由 `_kill` 的 Windows `taskkill /T /F` 终止，启动父 PID 从 34200 变为 27804。实际监听的 Uvicorn 子 PID 在 `api.log` 中。恢复的同 Run 没有重置预留调用数：6 次 MODEL attempt、4 次 MCP attempt；5 个完成响应已知 17,066 Token，另一个预留请求的 Provider 结果与费用未知。不得把未知请求算成未发生或零成本。完整 Trace、`crash-trigger.json`、进程日志和截图见 `runs/continuation-01/`。

两份副本的 Approval、ActionIntent、ActionLedger、Delivery、Scope Handoff 新增数均为 0；没有受控业务写入。Scope/Policy/Grant 的当前数据保存在脱敏 Trace，可核对没有授权写入。

## 真实 20+ 轮会话、低预算压缩与恢复

原 `session-110cf55c-6d52-4f6e-b301-60bc2282c019` 保留 26 个 Chat Run（21 成功、5 失败）、最初任务原文和正式纠错。没有重建消息或手工设置压缩状态。本次对实际 SQLite/Checkpoint 做一致备份，在 8002/5175 新进程继续同一 Session/Task，继续使用 **1400 输入预算**。

- 第 27 轮 `run-c616d2f0-83d5-4be6-9916-9bbd369187a5`：第一份真实模型摘要持久后，杀死原 API 进程树；Worker 恢复同 Run。最终计数为 `SUCCEEDED / INTERRUPTED / SUCCEEDED` 三个摘要 attempt，没有最终回答，按 `CHAT_ATTEMPTS_EXHAUSTED` 安全停止。已知 Provider Token 为 5200，中断请求 usage 未知；完整失败与进程事件保留，没有为通过而加预算或重置 Run。
- 最小修复后再次重启 API，第 28 轮 `run-b7ad6557-588e-4c4f-9eef-fc388b02c6ed`：**真实压缩一次 + 回答一次，SUCCEEDED**；摘要 Provider 1360 Token、回答 1298 输入 + 851 输出 = 2149 Token。Manifest 本地估算 **1374/1400**，选入 Summary v24（范围 seq1–39）及最初任务 Message 和正式纠错 Message 的原文锚点。
- 真实回答正确复述读取 demo-order、禁止改配置/凭证/权限/代签、401 只是待核实历史观察、没有当前 request/Probe 证据，不称恢复。没有当前有效 MCP Evidence，过期证据及依赖它的旧回答被排除。

这一真实会话累计 **28 个 Chat Run：22 成功、6 失败**。第 27 轮失败来自本次刻意注入崩溃后的原有预算裁决，仍计入分母。专项 `LONG_CHAT_CASES.json` 中另计划的 20 轮补充会话只实际提交了第 1 轮并成功，工具等待失败后未继续；不把未执行的 19 轮记为完成。20+ 轮证明来自上述真实原会话的延续。

证据在 `runs/long-recovery-01/`：原始前态 `before.json`、完整 `TRACE.json`、进程事件、两次模型新 Run、浏览器 DOM 和可离线查看截图。

## 能力清单与对照局限

- 共享预算计算器与块分配、三种策略、主 Hybrid、持久来源摘要、摘要递归依赖与失效重建、出站再次复核、Provider usage 与本地估算分存、Web Inspector：均有源码与自动化/上述真实证据。
- v9→v11 幂等迁移，旧 Episodic 来源、人审和撤销协议保留；检索默认 1、最大 3、扫描上限 100，记录适用与排除理由。Semantic 支持项目来源、候选、项目授权 APPROVER 确认、版本化修订、撤销、到期与审计。
- 原真实策略对照 `runs/strategy-comparison-03/TRACE.json` 不改写：Recent Window SUCCEEDED，2799 Token，21088ms；Rolling Summary FAILED/CHAT_ATTEMPTS_EXHAUSTED，6020 Token；Hybrid 同样 FAILED，4640 Token。后两者都包含 RuntimeError 与有界重试。此次 Hybrid 补证成功不能改写原对照，也不足以证明策略总体收益。**效用 NOT_PROVEN。**
- M3-01 历史 Memory 8 对/16 arms，12/16，P03/P04 badcase，仍 `UTILITY_NOT_PROVEN`。本阶段没有重新取得一套独立的完整 Episodic ON/OFF 真实 Web 评测，历史数据不作为本次新鲜结果。
- 原主工作台两个 Task B 以 `WORKER_RETRY_EXHAUSTED`、0 Provider/MCP 结束；失败仍在原库，根因未证实。隔离副本成功不意味着原失败已被修好。
- 撤销前只读模型曾错误暗示“取得审批后才能收集只读事实”；这是模型解释 badcase，不是权限契约。实际只读 MCP 调查不依赖审批，没有因此产生业务写入。
- 出站来源复核与实际网络 I/O 之间仍有非原子窗口；SQLite loopback Demo、合成本地身份不能宣传为生产 IAM。没有实测金额账单，不把 Token 折算成真实费用。

## 运行、审计与停止

原有真实 S1 v7/401→v8/200、同 integration/principal/route 以及主体禁用负例在 `runs/verification-01/real-s1-http-smoke.jsonl`；真实 S2 MCP stdio 403、SCOPE_INSUFFICIENT、请求关联与越域拒绝在相邻 JSONL。这些是本阶段先前的新鲜运行，和本次补证的 HTTP401只读观察分开计数。

`export_continuation_trace.py` 通过只读 SQLite 连接导出白名单事实、来源和账本；不导出 credentials、Cookie 或 Web 认证会话。原始库及临时测试服务脚本留在项目 `.runtime/`，不提交数据库或本地密钥。运行命令和副本来源见 `RUNBOOK.md`。所有本次子服务已停止，原8000/5173服务仍运行。

机器矩阵见 `RESULTS.json`，原始索引见 `TRACE.json`，错误与尝试见 `FAILURES.md`，源码学习材料见 `docs/learning/M3-02/`、`M3-03/`。本轮停止于修复与证据交付，不进入 M4、S3、新业务工具、通用 Memory 平台或多 Agent。是否验收通过由主 Agent 独立决定。
