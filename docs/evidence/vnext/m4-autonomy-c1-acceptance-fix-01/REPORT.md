# OpsPilot M4-Autonomy C1-REV1 Acceptance Fix 01

- **状态：** `ACCEPTANCE_CANDIDATE`，等待主 Agent 独立验收；实施方不签署 PASS。
- **Repo / Branch：** `wgqa/OpsPilot` / `codex/m4-autonomy-c1`
- **本轮 Base：** `dddcacfea08c657c70888749dc96a1115b595d0d`
- **主线基线：** `origin/main@77ea80e87e538f0f1fae8118ef231ec622601755`
- **验收冻结提交：** `1edabde`
- **RED 测试与失败证据提交：** `a31ae47`
- **实现提交：** `8f0036f1023f25104004905ab534a7d44e5a60a4`
- **证据提交：** 与本报告同一交付提交，SHA 在交付消息中给出以避免自引用。
- **范围：** 只修复 `opspilot/s3_investigation.py::S3Nodes.report()` 的只读补查结果路径。

## 开工核验与冻结合同

正式开工前从 Base 提交重新读取了总纲和 Agent 规则：

- `PROJECT_NORTH_STAR.md` Blob：`1f737712c7a36ceb34433ac09c3fbba3c3305542`；实际复核第 8 节，包含限制的双向验收、失败分类、证据等级与固定裁决要求。
- `AGENTS.md` Blob：`30319000ed0054007e9b7b6b46bf98b1493c8179`；确认当前阶段由本轮任务卡和主 Agent 验收决定，旧实现合同不能改变 C1 范围。
- 冻结的 C1 合同：`docs/evidence/vnext/m4-autonomy-c1/FROZEN_PLAN.md`、`REV1-ACCEPTANCE-ADDENDUM.md`。原 C1-01～08 Gold、REV1 报告、E2E-02/E2E-03 失败及 Provider/Web/MCP 轨迹均未覆盖或改写。
- 本轮用户任务卡作为本次修复的优先范围，测试标准先单独提交，再提交 RED 测试与日志，随后才提交源码修复。
- 目标 Base 中没有 `.agents/skills/opspilot-slice-review/SKILL.md`；本轮按已实际读取的 AGENTS 和 North Star 第 8 节执行，没有声称读取该缺失文件。

当前分支基于指定主线基线。自本轮 Base 起没有新增合并提交；候选只包含冻结、RED、修复和证据提交。本地 `knowledge/api-scope/current-v1.0.md`、`knowledge/api-scope/legacy-v0.8.md`、`skills/auth-scope-triage/SKILL.md` 的既有未提交修改保持原样且未暂存。

## 问题与最小修复

旧逻辑用同一个条件判断 `readonly_followup` 和剩余 Task MODEL 预算。预算到上限时，整个只读分支被跳过，后续普通路径会调用 `persist_s3_diagnosis()`。冻结的 FIX-01 在旧代码上复现了这个行为：模型额度 8/8 时没有只读结果行，却新增一条 `INCONCLUSIVE` S3 Diagnosis，将 Task 从 `WAITING_HANDOFF` 改为 `INCONCLUSIVE`，并新增 Domain Outbox 事件；旧 Diagnosis 本身未改写。

修复将两项职责分开：`readonly_followup` 无条件决定结果持久化走只读路径；MODEL 预算只决定是否调用可选解释模型。预算耗尽时，不请求 Provider，仍持久化 `PARTIAL`，原因码为 `FOLLOWUP_BUDGET_OR_PROVIDER_EXHAUSTED`。业务 Diagnosis、Task 状态、TaskControl revision、审批/Plan/动作记录、Handoff Queue/Receipt 和 Domain Outbox 不变。改动没有提高预算、清空 Attempt、改变 Gate 或新增 Runtime/Guard。

相对本轮 Base 的业务源码 Diff 只有 `opspilot/s3_investigation.py`。新增独立回归文件 `tests/test_m4_autonomy_c1_acceptance_fix_01.py` 和本目录证据。

## RED、GREEN 与回归

新测试在实现提交之前运行。`red-04.log` 的有效 RED 为 1 failed / 1 passed：预算耗尽负例失败，直接用当前 Knowledge 解释的正例通过。RED Trace 显示：Diagnosis 数量 `1→2`；Task `WAITING_HANDOFF→INCONCLUSIVE`；TaskControl revision `0→0`；Outbox `6→7`；只读结果仍未完成。Approval、Plan、ActionIntent、Ledger、Queue、Receipt 计数均未增加。原 Diagnosis 的正文和 digest 保持不变。

有一个初次环境准备失败：系统 Python 缺 `langchain_core`，见 `red-01.log`；它发生在 pytest 收集阶段，不作为产品 RED。`red-02` 和 `red-03` 的有效复现也原样保留；`red-03` 首次 Trace 提取误把 traceback 中的测试源码行识别为 Trace，正式 `TRACE.jsonl` 使用 `red-04` 的有效结构化输出。

GREEN 验证：

- 新 FIX-01/02：2 passed。预算耗尽时输出 `PARTIAL` 和预算原因码，未调用 Provider，业务快照逐项不变；当前 Knowledge 足够时使用 1 次模型替身调用直接解释，来源带 `receiver-ack-contract-v2` 的版本和 digest，不新增 MCP 工具调用。
- 已有 Investigator MCP 补查集成：1 passed。Task 预算充足时，确定性模型替身选择 `search_callback_knowledge`；真实本地 MCP client/server 产生同 Run Observation、版本化 Knowledge 来源和 `ANSWERED` 只读结果，Diagnosis 未写入。关联 Task/Run/Message、Observation、ModelTrace 与 Context Provenance 见 `TRACE.jsonl`。这是 MCP/Domain 集成轨迹，不是外部 Provider 或真实 Agent 自主性证明。
- S3、M4-03 HF-01/HF-02、M1 TaskControl、TTL 和 C1 follow-up 定向回归：92 passed。
- 全量 pytest（排除历史预实现 RED 文件）：325 passed，284.68 秒。历史 `tests/test_m4_autonomy_c1_red.py` 断言的是未实现基线必须拒绝 FOLLOW_UP；文件、断言和历史运行记录保持不变。
- 第一次全量尝试为 324 passed / 1 failed，原因是 M2-02-HF-01 子进程没有继承模型环境配置，未进入故障注入。该失败日志保留；父进程从主工作区 `.env` 仅在进程内加载配置后，该用例单独 1 passed，之后完整套件 325 passed。没有打印或复制密钥。

依赖环境：Python 3.12.14、pytest 9.1.1、FastAPI 0.137.1、LangGraph 1.2.16、langgraph-checkpoint 4.3.0、langchain-core 1.7.0、langchain-openai 1.7.2、MCP 2.3.0、uvicorn 0.49.0。`requirements.lock.txt` SHA-256：`59658b2a1412f580237fd3a20d88163aea3579e89f6499a768796b6aaca67ae8`。

本轮没有运行真实外部 Provider 或浏览器 E2E；历史真实 Web/Provider/MCP 证据仍在 REV1 目录，未冒充为本轮新证据。前次 C1 Web E2E-04 报告的隐藏 Chat sidecar 消耗为 3,709 tokens，作为历史独立成本继续记录，本补丁未重构 Chat 或再次调用 sidecar。E2E-02/E2E-03 仍保留；E2E-03 的 `ANSWERED` 误标记继续作为产品质量样例。现有 FOLLOWUP_PROMPT 已要求来源缺失、不回答目标或有实质缺口时使用 `PARTIAL`，解析器对缺失标签 fail-closed；本轮未新增封闭语义关键词白名单，也未改写 E2E-03 的历史结果。

## North Star 第 8 节六个自问

1. **用户因此能多完成什么？** 预算耗尽时，用户仍能看到这次只读追问的持久 `PARTIAL` 结果和明确缺口；此前可能被写入正式 Diagnosis 并把 Task 状态改成 `INCONCLUSIVE`。
2. **哪些决定真正由 Agent 作出？** 本轮不增加 Agent 自主性。已有合法调查仍可由模型选择 Knowledge/MCP；程序保证只读结果始终落在只读存储路径。
3. **什么不同观察会导致不同合理行动？** 预算尚有额度且当前来源可回答时允许生成解释；Task MODEL 额度耗尽时跳过可选模型调用并交付 `PARTIAL`。已有来源足够时无需额外 MCP 查询。
4. **新增硬限制保护什么，是否误伤合法任务？** 只读 Run 不得创建业务 Diagnosis 或改变 Task 状态。负向耗尽测试与正向直接解释、真实本地 MCP 合法查询均通过；预算上限仍保留。
5. **有没有更轻的做法，旧限制能否删除？** 仅拆开既有职责分支，预算检查仍限制 Provider 调用；没有新增预算、Guard 或 Runtime，也没有改变工具策略。
6. **拿什么验收，做到哪里就停？** 以冻结 FIX-01/02、已有 MCP 跟进、92 项定向回归和 325 项全量 pytest 验收。真实 Provider/Web 不属于本次新运行，历史证据保持可查；本轮止于修复并交主 Agent，不进入 C2/C3/C4。

## 六维实施方交付摘要

- **用户变化：** 只读追问在模型预算耗尽时也有可持久查看的未完成结果，且不污染业务 Diagnosis 或 Task 状态。
- **Agent 决策：** 调查工具选择能力保持；仅解释调用受剩余预算影响。
- **观察驱动：** 当前可用来源和预算状态决定是否再生成解释，但不能决定结果写入模式。
- **新增约束：** 保护只读/业务状态隔离；直接解释与合法 MCP 路径未被阻断。
- **简化结果：** 复用现有 `readonly_followup` 职责分支和持久化函数，无新增抽象。
- **证据与停止线：** 原始 RED/GREEN、完整日志、确定性模型与 MCP Trace 均可核对；真实 Provider/Web 本轮未运行；本地其他工作保留。实施方状态为 `ACCEPTANCE_CANDIDATE`，主 Agent 尚未独立复核，禁止据此合并或启动 C2。
