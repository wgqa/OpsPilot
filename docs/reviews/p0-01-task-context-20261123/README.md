# P0-01 任务归属与上下文隔离

2026-11-23 · 第一轮复核与实施设计

**已复现根因。** 请求、持久 Run、来源消息都指向 B，A 的专属文本仍在 Context Builder 被选中，并进入发给 MockTransport 的 Chat Completions JSON。两项隔离断言均失败。B 的任务原文、当前追问、合法的无 Task 协议说明均出现在同一份请求中，为修复提供了保留项。[原始 pytest 输出](red-pytest.txt) · [Builder 快照](builder-context.json) · [SDK 请求与账本](mock-sdk-wire.json)

## 前置核验

| 项目 | 本轮范围 |
|---|---|
| Repo / Base / HEAD | `wgqa/OpsPilot`。GitHub commit 接口核实远端 `main=60eee87bfe3cca522011316cb4cd2c0064ad291b`；主目录当前为 `antigravity/ar03-protocol-compare@9abad4de9903ee26a62930a89f7e0392c6f888b2`，与同名远端一致。 |
| 工作树与 Diff | 本地 `codex/p0-01-task-context-plan` 从上一轮仅含审计资料的 `e8f897bf1b293c2249fe8f2617bbac7acf3aa052` 建立。复现时源码、前端、既有测试、合同、治理均与 `60eee87` 一致。交付新增本目录的设计、离线探针和 RED 证据。 |
| 总纲 / AGENTS / Skill | 实读基线的 [PROJECT_NORTH_STAR](../../../PROJECT_NORTH_STAR.md) Blob `e36f2f75509738551ac6d4a2de5b4f9cf44a7991`、[AGENTS](../../../AGENTS.md) `f174a6ab7f23f9e6d8b3ef98d455b99a75193143`、[Skill](../../../.agents/skills/opspilot-slice-review/SKILL.md) `d405c8d413d633824b279202cc1503dab4cf0b03`。设计参考采用仓内“在已有 Context 模块修改装配”的职责分工。[开源参考](../../learning/OPEN_SOURCE_AGENT_REFERENCES.md) |
| 冻结合同 | 使用同一个 Base 下的 [v1.0 不变量](../../baseline/v1.0-implementation-baseline.md)、[API](../../baseline/API_CONTRACT.md)、[权限](../../baseline/ACCESS_MATRIX.md)、[状态转换](../../baseline/STATE_TRANSITIONS.md)、[恢复](../../baseline/EVENT_RECOVERY.md)、[来源链](../../baseline/MEMORY_LINEAGE.md)。[AR‑04A Gold](../../evidence/ar-04a/context-journey-01/GOLD.md) Blob `6c8ba3867e2dad983abe6f1b85bd559fc28e36ac`、[AR‑04B Gold](../../evidence/ar-04b/memory-journey-01/GOLD.md) `f5056cbb3344208e2e34671ea08a50963d3aea3d`。特别保留 AR‑04A G3 的绑定前材料、Task-less 摘要隔离和 G4 的原始任务/正式纠错锚点。 |
| 遗留门禁和裁决 | [M2‑01](../../evidence/vnext/m2-01/DEFERRED_GATES.md) `2e65870a`、[M2‑02](../../evidence/vnext/m2-02/DEFERRED_GATES.md) `2536030b` 的 TTL/再验证、幂等、交接和授权合同继续适用。AR‑04A 仓内记录为 ACCEPT_WITH_LIMITS，J6 长旅程未覆盖。AR‑04B 历史实施报告所载 9/9 与上一轮独立执行停滞分开记录，独立验收结论仍为 UNVERIFIED。 |
| 运行范围 | 临时 SQLite、FastAPI TestClient、正式 Worker 单次派发、真实 stdio MCP 握手、真实 ChatOpenAI/SDK 序列化与本地 MockTransport。没有真实 Provider 网络或付费调用，没有浏览器 E2E。S3 夹具只向本机回环写入初态。 |

## 一、调用链与可信来源

| 环节 | 源码所见及本轮证据 |
|---|---|
| **选择与重开 Session** | `selectSession` 清理旧页面状态并加载当前会话。 `refreshSession` 从 `GET /messages` 的最近 Task 消息恢复焦点，缺失则从 `GET /sessions/{sid}` 的最后关联 Task 恢复。 `sendMessage` 将当前 `taskId` 传给 `assistantSend` 或 `send`。焦点是请求目标的输入。浏览器自动焦点与用户选择的区别留给后续切片；本 RED 直接在 HTTP 请求中给出正确 B。 [App.vue 第 386、513、739 行](../../../frontend/src/App.vue) · [api.ts 第 344 行](../../../frontend/src/api.ts) |
| **API 受理** | `MessageRequest.task_id` 是可选目标。认证/Origin/CSRF 独立校验。专业 `/assistant/messages` 带 Task 时先查当前可读资源和 S3 binding，随后调用 `admit_task_message(..., assistant_core=True)`。经典 `/messages` 也走同一受理，带 Task 的普通聊天可先分类。 `/assistant/order` 经正式入口创建已认证订单绑定。 [schemas.py 第 27 行](../../../opspilot/web/schemas.py) · [app.py 第 639 行](../../../opspilot/web/app.py) |
| **Domain 持久关联** | `admit_task_message` 对可信 identity、Session owner、Task owner、租户、`session_task_links` 和幂等键作校验。事务中将同一获准 Task 写入 Message、Command 和 Run；`task_runs.source_message_id` 与 `consumed_message_seq` 固定该 Run 的输入。 `task_bindings` 保存受信 actor/资源，S3 绑定另持久化订单。本轮 HTTP 反例核对 `requested.task_id == run.task_id == source_message.task_id == B`。 [task_control.py 第 1092、1150、1265 行](../../../opspilot/domain/task_control.py) |
| **Worker 选择执行器** | `_dispatch_run` 按持久 `assistant_runs` 标记走 `run_assistant` 并先以可信 owner claim。经典 Chat 用 `_process_chat_run`，由 `prepare_chat_attempt` 与发送前重建理应共享同一个 `_prepare_context`。业务 Investigator 的 `investigation_context` 与关键纠错分类的历史查询已有 Task 限定，属于定向回归面。 [worker.py 第 304、510 行](../../../opspilot/web/worker.py) · [分类历史](../../../opspilot/domain/investigation_updates.py) · [调查输入](../../../opspilot/domain/investigation_context.py) |
| **Context Builder** | `_prepare_context` 读取持久 Run，确认 Session 和绑定关系。当前 source_message 查询按 ID、Session、tenant、角色、类型筛选，缺少 Task 一致性。普通 USER 历史按 `session_id + tenant_id + role + CHAT_READONLY + sequence` 取最近 500，完全没有 Task 条件；A 的 CREATE_TASK 首条消息也是 `CHAT_READONLY`，会被读入。B 的任务锚点和助手回复查询另有 Task 条件，因此拼入 B 的原文时，A 文本已在历史里。该混合历史同时作为压缩素材的上游。 [chat.py 第 1050、1131、1142、1162、1364 行](../../../opspilot/domain/chat.py) |
| **出站与续跑** | `_run_assistant` 从选中历史创建 LangChain 消息，使用 `assistant-v1:<run_id>` checkpoint。 `Loop.context` 重建 `WORK_CONTEXT` 并附加有限的历史来源/答复。 `awrap_model_call` 采用 `request.messages` 作为实际历史，附加新 System 消息，先写 `assistant_calls.request_json`，再交给 SDK。复跑从真实 SDK 捕获一份带 A 文本的 JSON；重建元数据无法移除已在 Graph 消息里的文本。MCP 子进程以 `--run-id` 查持久 binding，仅看到 B 绑定的合法工具范围。 [assistant.py 第 557、631、706、1227、1285 行](../../../opspilot/assistant.py) · [assistant_mcp.py 第 15 行](../../../opspilot/assistant_mcp.py) |

**根因是读取上下文时用 Session 范围覆盖了 Task 范围。** 当前租户和 owner 一致仍允许合法 A/B 并存。消息正文和模型输出只提供用户意图或线索，可信归属取自受理后持久化的 `task_runs.task_id`、`source_message_id`、`messages.task_id`，以及已校验的 Session/Task 绑定。B 的调查权限来自 Domain。测试覆盖到了请求外发边界，未观察模型是否会采纳 A。 [SDK 请求](mock-sdk-wire.json)

另有两条可能把旧污染带回的路径。 `_message_source_valid` 校验普通 MESSAGE 的 Session/tenant/digest，只对 `CORRECT_TASK_INPUT` 比较 Task。旧 B 答复因此可以通过直接的普通来源检查，即使其来源是 A。专业 Assistant 的 `WORK_CONTEXT.prior_answers` 可带无 Task 答复摘录，当前分支只查该 Run 的业务/工具来源，不检查全部普通消息依赖。若旧的无 Task 答复曾读到 A，摘录也需要校验。另需覆盖尚在恢复的 checkpoint，因为 `graph.ainvoke(None)` 读取旧 seed。上述派生路径为源码发现，将通过后续定向测试验收。 [旧答复来源检查](../../../opspilot/domain/chat.py#L463) · [专业答复摘录与 checkpoint](../../../opspilot/assistant.py#L557)

## 二、建议的最小修复

### 原始消息与公共内容

在 `opspilot/domain/chat.py` 的历史选取层，按已验证的 Run 归属在 SQL **先按 Task 过滤再排序、限额和压缩**。用同一个语义校验派生来源。原始用户消息在同一 tenant、Session 并满足序号/角色/类型边界时，按下表使用。

| 消息来源 | B Run | 无 Task Run |
|---|---|---|
| B 的普通消息 | 可选；保持时序与预算 | 排除 |
| A 或其他非空 Task | 排除；即使同订单、同 owner | 排除 |
| `task_id IS NULL` 的普通 Session 用户消息 | 可作为公共、未验证背景参与现有预算 | 可用 |
| 被选中 Run 的当前 source message | Task 必须精确一致；NULL 与 NULL 相合 | 同左 |
| 任务原始输入与正式纠错 | 继续走现有锚点与 Task 限定 | 无 Task 纠错 |

查询可用 `task_id IS NULL OR task_id = :run_task_id`，当前消息用 NULL-safe 精确相等。普通历史和派生校验都应由结构化归属判定，沿用来源 digest 检查。既有 NULL 表达“当时按 Session 聊天受理”，因此本轮保留其公共资格。若用户自己把 A 的文字粘贴到无 Task 消息或 B 当前消息中，这份文字仍属于用户本次提交的未验证内容；语义识别和重新归类不在本切片。

### 已保存的派生上下文

- **答复与摘要。** 将普通 MESSAGE 的 Task 归属检查扩展到旧答复来源。历史答复只在其所在域通过校验后复用。旧的 B 摘要如果依赖 A，沿现有依赖检查排除重建；保留 `context_summaries.task_id` 精确匹配。B 的压缩允许同 Session 的 NULL 普通 USER 消息作为原始背景依赖，摘要正文仍归 B；`SUMMARY` 与 `ASSISTANT_MESSAGE` 依赖继续精确匹配。这样允许同会话的原始协议材料随 B 压缩，同时保住 AR‑04A 对 Task-less 摘要的隔离。
- **Assistant 的历史摘录。** 在 `Loop.context` 的无绑定历史答复摘录路径，按答复原属的 NULL 范围检查依赖，再允许其进入 `WORK_CONTEXT`。沿用已有 `source_refs.prior_answers`／Manifest 引用识别旧的间接依赖；引用可用就验证原答复先前的依赖，避免悄悄丢掉干净的绑定前问答。测试需确认历史 MCP 投影继续按已授权的来源规则核验。
- **运行中保存的上下文。** 让已有 Manifest 或账本提供 Run 的上下文来源，复用来源检查在采用旧 checkpoint seed 前验证所带文本。当前重建结果与旧 seed 的来源需要对应，单靠重建后新的 `selected_message_ids` 不能证明旧消息干净。旧 snapshot 若含异 Task、或无法证明符合新边界，停止这次只读续跑并给可重开的提示，保留原账本与未知调用语义。对干净 seed 保留原回放。优先使用已有 Manifest/账本的引用和摘要信息；缺少区分新旧选取策略的标识时，可以增已有 JSON 中的版本字段，避免迁表。是否需要这一处生产改动，以专项 RED 为准。

### 文件和风险

| 文件 | 变更预期与验收 |
|---|---|
| [opspilot/domain/chat.py](../../../opspilot/domain/chat.py) | 必改。当前 source_message 归属、历史 SQL、普通 MESSAGE 及摘要依赖范围的共同规则。若提交时仍能将越界旧来源写成可复用引用，复用同一校验做拒绝，避免只在读时遮掩。 |
| [opspilot/assistant.py](../../../opspilot/assistant.py) | 检查 `WORK_CONTEXT` 摘录与 checkpoint 恢复旁路，专项失败证实需要时接入同一来源检查。保留模型出站顺序、预算和既有序列化适配。 |
| `tests/test_p0_01_task_context.py`（拟） | 从本目录的两项 RED 提升为可重复的回归，加入 NULL 方向和旧派生来源用例。既有冻结测试与历史证据单独保留。 |
| [frontend/src/App.vue](../../../frontend/src/App.vue)、[app.py](../../../opspilot/web/app.py)、[task_control.py](../../../opspilot/domain/task_control.py) | 调用链核查和既有行为回归。修复从后端读取层落地，用户可以用原接口携带正确 B ID。 |

主要风险是只用精确 B 过滤会抹掉合法的绑定前原始材料；如果无条件放宽摘要及答复依赖，又会让旧污染回流。其次，前置校验不能把所有旧 checkpoint 一概报废。需要新增成对用例证明干净旧来源与同 Task 历史仍能使用。历史记录保持可查，运行时排除问题上下文即可。

## 三、RED → GREEN → 回归计划

| 阶段 | 场景与判据 |
|---|---|
| **RED 已保存** | 原审计条件在经典 Builder 复现，并用专业 API + 单次 Worker 派发复现到 SDK JSON。A/B 绑定同一个演示订单，Task 是唯一关键差异。两项隔离断言失败，HTTP 受理与 B Run 成功交付仍成立，证明只看 Run 状态会漏检。 |
| **既有正例基线** | 本轮独立复跑 AR‑04A、M1 幂等受理、AR‑02 无任务受理共 6/6 通过，作为候选比较基线。 [原始日志](baseline-regression.txt) |
| **GREEN 核心** | 在实施授权后的隔离候选重跑两项同样输入，保存新的 Builder 快照、`assistant_calls.request_json` 和 MockTransport 请求。逐类比对全部 `messages[].content` 和选入 ID，A 文本与 A 选中来源均为零；公共协议说明、B 原始锚点、B 本轮追问仍在。记录 SDK 派发次数、Run 状态、受控表计数和预算估算，比较前后语义，忽略随机 Run ID。 |
| **双向回归** | B→A 反向，NULL Run 过滤所有 Task 文本，B 保留同 Task 历史及最新正式纠错，跨 Session/tenant 的 Task 或来源拒绝。构造较新的 A 消息超过窗口，确保合法旧 B/NULL 消息不会在过滤前被挤掉。用 `RECENT_WINDOW` 与实际触发压缩的旅程验证，压缩请求、重用摘要、回答请求均不进 A；合法 NULL 原文或其在 B 摘要里的明确来源仍可用。 |
| **派生与恢复** | 预置历史 B 答复引用 A，以及干净的 B 答复和一组合法 NULL 摘录。断言污染文字及引用不上 wire，干净数据继续用。覆盖错归属的 source_message、旧 B 摘要依赖 A、以及已保存 A 文本的 B checkpoint；后者出站计数为 0，干净续跑按原回放策略。比较真实发给 MockTransport 的 JSON，避免只检查 manifest。 |
| **适用旧门禁** | 复跑 [AR‑04A 长会话](../../../tests/test_ar04a_context_journey_01.py)、[AR‑02 Context 连续性](../../../tests/test_ar02_context_continuity_01.py)、[M3 压缩与纠错锚点](../../../tests/test_m302_context.py)、[M1 Chat](../../../tests/test_m1_chat.py)、[M1 TaskControl](../../../tests/test_m1_task_control.py) 的相关用例。单列 AR‑04B，定向复跑卡在 TestClient shutdown 时记录 `HOLD / UNVERIFIED` 与线程栈。涉及历史未知请求的分支应保持零重复派发。 |

### 正式规划六问

1. **用户变化**。同会话明确跟进 B 时，仍能沿用 B 自己的条件和合法共用说明，避免误用 A。
2. **Agent 决策**。本轮修正输入范围。模型保留解释、澄清与选择 B 绑定内合法查询的空间。
3. **观察驱动**。用户请求与正文完全相同，改变已校验的 Task 目标就应改变哪些任务专属条件进入上下文。改变当前 Receiver 观察仍允许模型选择不同合法下一步。
4. **约束双向检查**。排除其他 Task 的原文及污染衍生内容，并以同 Task、NULL 背景、合法压缩和干净续跑证明有用信息仍可达。
5. **归属与简化**。复用 Domain 的现成归属与来源引用。在查询层收窄候选，可让普通回答与压缩共用过滤，避免分别在前端、Prompt 和模型输出加规则。
6. **证据和停止线**。本轮结束在 RED 与实施设计。实施授权后需提供同一样本 GREEN、实际输入差异与上述定向回归；真实 Provider 效果与阶段放行为 **HOLD / UNVERIFIED**。
