# OpsPilot 多轮任务连续性审计

2026-11-23 · 快手电商 Agent 面试反馈 · 第一轮分析，供主 Agent 与用户评审

**建议先修一个用户旅程。** 支持工程师昨天排查订单 A 的回调，今天又讨论协议 B。重新打开工作台，说“继续”，系统应找回正确目标；选定 A 后，应带回仍有效的条件，并重新核实 Receiver 的当前状态。现有 Session、TaskControl、压缩和 MCP 足以承载这个旅程。最薄弱的两处是**选哪个任务**和**哪些旧条件今天还有效**。

两个离线反例使这个优先级可检验。在同一 Session 建 A、B 两个合法 Task，显式追问 B，待发 Context 中同时出现 A 的专属条件。在四条都有效、每条都有消息出处的约束上，主线压缩函数只保留后三条。前者验证到 Context Builder，后者验证到纯函数；均未观察到模型最终选错或线上用户受影响。[复现、测试与证据等级](EVIDENCE.md)

## 一、审查前置核验

| 核验项 | 本轮实际范围 |
|---|---|
| 仓库与目标 | `wgqa/OpsPilot`。GitHub 读取远端 main 并与本地对象核对，分析 Base = 源码 HEAD = `60eee87bfe3cca522011316cb4cd2c0064ad291b`。当前用户目录是另一个分支 `antigravity/ar03-protocol-compare@9abad4de9903ee26a62930a89f7e0392c6f888b2`，远端同名分支已核对。两树有 740 个文件差异。 |
| 工作范围 | 分析在从 Base 单独检出的本地 `codex/interview-task-continuity-audit-20261123` 交付。相对 Base 的交付 Diff 仅含本目录文档与离线证据。根工作区有既存未跟踪文件和不可遍历的旧 pytest 目录，本轮基于 Git 对象与已核对提交的工作树。 |
| 本次实读 | main 的 [总纲](../../../PROJECT_NORTH_STAR.md) Blob `e36f2f75509738551ac6d4a2de5b4f9cf44a7991`、[AGENTS](../../../AGENTS.md) `f174a6ab7f23f9e6d8b3ef98d455b99a75193143`、[Skill](../../../.agents/skills/opspilot-slice-review/SKILL.md) `d405c8d413d633824b279202cc1503dab4cf0b03`。比对当前目录，main 另有 11 月 4 日开源参考与轻核心约定，已读取[设计参考](../../learning/OPEN_SOURCE_AGENT_REFERENCES.md)。 |
| 合同优先级 | 本轮任务卡仅授权分析。总纲 §0/2/3/4/6/8 和不变量优先；[v1.0](../../baseline/v1.0-implementation-baseline.md)、[vNext 架构](../../handoff/vnext/OpsPilot-vNext-v0.3-product-architecture-contract.md)、[API](../../baseline/API_CONTRACT.md)、[状态](../../baseline/STATE_TRANSITIONS.md)、[权限](../../baseline/ACCESS_MATRIX.md)、[恢复](../../baseline/EVENT_RECOVERY.md)、[来源链](../../baseline/MEMORY_LINEAGE.md) 均按上述 main SHA 引用。较早合同的阶段状态按当时范围理解。 |
| 冻结与遗留 | AR‑04A [Gold](../../evidence/ar-04a/context-journey-01/GOLD.md) Blob `6c8ba3867e2dad983abe6f1b85bd559fc28e36ac`，AR‑04B [Gold](../../evidence/ar-04b/memory-journey-01/GOLD.md) `f5056cbb3344208e2e34671ea08a50963d3aea3d`。[M2‑01](../../evidence/vnext/m2-01/DEFERRED_GATES.md) 与 [M2‑02](../../evidence/vnext/m2-02/DEFERRED_GATES.md) 分别为 `2e65870a`、`2536030b`，包括审批后证据再验证、Web 幂等、交接回执和项目权限边界。此次不重签这些门禁。 |
| 裁决与缺口 | 仓内记录 AR‑04A 为 ACCEPT_WITH_LIMITS，J6 正式纠错端到端留缺。AR‑04B 报告是 ACCEPTANCE_CANDIDATE；本轮未取得其单独主 Agent 签字原件。冻结 E01–E10、G1–G8、AR‑04A/B 及历史 RED 单独保留。此处没有实现候选可供阶段验收。 |

## 二、现状与面试反馈映射

标记以 **main、指定入口、指定能力** 为单位。ALREADY_SUPPORTED 有实现和对应测试，PARTIALLY_SUPPORTED 有可用子链且仍有明确缺口，MISSING 在所查入口、存储和测试中未找到所需语义，NOT_APPLICABLE 表示不属本地产品承诺。测试的静态审阅、本人复跑和历史结果在证据页分别列示。

| 面试问题 / 入口 | 判定 | 现有机制、缺口与用户风险 | 源码 / 测试 |
|---|---|---|---|
| 多轮消息归属、条件补充、目标调整 | PARTIALLY_SUPPORTED | Session、Message、Task link、run input 和可信 owner 持久化。已知 Task 的旧入口可辨 FOLLOW_UP、HYPOTHESIS、CRITICAL_CORRECTION、OUT_OF_SCOPE，FOLLOW_UP 又可解释或调查。专业 Assistant 入口按传入的 task_id 走 ASSISTANT_V1；带 Task 时检查 S3 binding。两条链不能互相代领覆盖。缺少同 Session 多目标的语义归属。 | [Web 两入口](../../../opspilot/web/app.py)、[分类与提案](../../../opspilot/domain/investigation_updates.py)、[M4 对话测试](../../../tests/test_m4_01_dialogue_updates.py)、[专业入口测试](../../../tests/test_ar02_assistant.py) |
| 正式纠错、撤销早期条件 | PARTIALLY_SUPPORTED | 同任务纠错可确认，TaskControl 推进 revision、高水位，阻断旧 Run/Plan；取消待确认提案有竞态测试。调查输入按序加载已应用纠错。撤回一个已生效条件、同时保留其他条件，目前缺少逐项替代关系；取消提案也无法表达这件事。 | [TaskControl](../../../opspilot/domain/task_control.py)、[输入校验](../../../opspilot/domain/investigation_context.py)、[确认/取消竞态](../../../tests/test_m4_01_dialogue_update_safety.py) |
| 隔天“继续”、切换、多目标消歧 | MISSING（自然语言入口） | 可重新打开 Session，Worker 也可按指定 Run 恢复。但 App.vue 第 524、542、756 行在重开时取最近关联的 Task，再把它作为下一条消息的 task_id。该值无法说明用户主动选过 B。两个目标均在授权域内时，权限检查也无法发现选错。 | [工作台](../../../frontend/src/App.vue)、[消息客户端](../../../frontend/src/api.ts)、[已知 Run 恢复测试](../../../tests/test_m1_worker_recovery.py)、[双任务复现](EVIDENCE.md) |
| “重新生成”指重新表达、重查或重做 | MISSING（显式区分） | 有历史答复、来源校验、操作幂等键，以及 EXPLAIN/INVESTIGATE 分类。当前专业发送请求是正文加 task_id，缺少“基于哪次答复改写”的意图标识；新命令、新模型请求、重放旧命令的语义不同。普通聊天重发也不具备 D3 执行权限。 | [客户端](../../../frontend/src/api.ts)、[分类](../../../opspilot/domain/investigation_updates.py)、[幂等与审批测试](../../../tests/test_m1_task_control.py) |
| 压缩、材料保留、过滤无关轮次 | PARTIALLY_SUPPORTED | 有 RECENT_WINDOW、ROLLING_SUMMARY、HYBRID，记录预算、序号引用、摘要依赖、排除原因。原始任务和最近正式纠错逐字锚定。普通用户文本候选按 Session 取最近至多 500 条；同一会话的另一个 Task 可混入。摘要含初始目标、否定、约束、纠错、未决事项、时间线，但分类内条数/字数限额会丢仍生效的内容。 | [chat.py 的 _prepare_context、_compact_summary_document](../../../opspilot/domain/chat.py)、[块预算](../../../opspilot/domain/context_engineering.py)、[策略对照测试](../../../tests/test_m302_context.py)、[长旅程测试](../../../tests/test_ar04a_context_journey_01.py) |
| Session Context / Task State / User Memory 分层 | PARTIALLY_SUPPORTED | Session 提供对话来源与摘要；TaskControl、Run、Binding、Plan 持有执行事实。Episodic / Semantic Memory 有候选、可信确认、撤销、适用范围和来源检查，Semantic 可修订和过期。main 未找到按个人 owner 管理的稳定偏好或以当前问题召回未完目标的机制。项目方法记忆适合帮助调查，不能据此判断用户要继续哪个 Task。 | [数据表](../../../opspilot/domain/database.py)、[Episodic](../../../opspilot/domain/episodic_memory.py)、[Semantic](../../../opspilot/domain/semantic_memory.py)、[修订与过期测试](../../../tests/test_m303_semantic_memory.py) |
| Memory 召回与预算、撤销穿透 | ALREADY_SUPPORTED（已覆盖的项目记忆路径） | 可信 Binding 派生租户/项目，按来源、状态、问题类型和适用性筛选；Episodic 限选至多三条，部分 S3 场景结合当前问题与事实排序。进入 Context 块预算，出站、checkpoint 续跑和回答提交均有复核。AR‑04B 覆盖撤销前后竞态、合法相邻路径；专门的大 Memory 挤占预算 G9 尚缺。 | [召回](../../../opspilot/domain/episodic_memory.py)、[装配](../../../opspilot/assistant.py)、[AR‑04B 测试](../../../tests/test_ar04b_memory_journey_01.py)、[G9 缺口](../../evidence/ar-04b/memory-journey-01/FAILURES.md) |
| Task 材料失效或权限撤销 | PARTIALLY_SUPPORTED | `sources_current` 对 Evidence、Knowledge、协议版本/摘录、Skill 分类型校验；摘要按依赖、版本和作用域重查。普通粘贴文本属于未验证消息。其原文可以作为历史出现；重新选择材料时需区分原话、受权限约束的正文、过期结论。主线未证明任意材料撤销后所有衍生答案和改写路径都安全。 | [来源复核](../../../opspilot/domain/assistant.py)、[摘要复核](../../../opspilot/domain/chat.py)、[失效摘要与合法回答](../../../tests/test_ar04a_context_journey_01.py) |
| Agent Loop 的继续、澄清、停止、目标完成 | PARTIALLY_SUPPORTED | Assistant 通过 create_agent、中间件、stdio MCP、AsyncSqliteSaver 循环；最后的非空模型回答可完成聊天 attempt。Investigator 有 NEED_MORE、证据不足/预算停止、可信 Gate。S1 恢复须真实业务验证，S2 草稿/诊断/交接由不同事实证明。开放式多轮目标缺少可追溯的交付要求和未完成项；自然语言结论也可能超出回执。 | [Assistant 尾部提交](../../../opspilot/assistant.py)、[Investigator](../../../opspilot/investigator.py)、[S2 草稿](../../../opspilot/domain/s2_diagnosis.py)、[S2 回执](../../../opspilot/domain/s2_handoff.py)、[S2 诊断测试](../../../tests/test_m2_02_s2_diagnosis.py) |
| 异步 Run、取消、故障恢复、未知结果与幂等 | ALREADY_SUPPORTED（本机持久 Worker 和既有 D3 动作）；用户主动暂停为 PARTIALLY_SUPPORTED | 202 后排队、OS 锁、epoch fencing、活跃预算、abort 和审批 interrupt 已有实现。Assistant reserve 在 I/O 前记账，已 OK 且 digest 相符可回放；未知结果停。D3 先持久化 Intent，REPAIR/DELIVER 分开消费，历史 Ledger 可对账。Run 已知与用户隔天仅说“继续”是两个不同入口；abort 不可当可逆暂停。 | [Worker](../../../opspilot/web/worker.py)、[Run 控制](../../../opspilot/domain/task_control.py)、[调用账本](../../../opspilot/domain/assistant.py)、[D3](../../../opspilot/domain/d3.py)、[进程崩溃/响应丢失测试](../../../tests/test_d4_recovery.py) |
| 长时异步工具的返回与查询 | PARTIALLY_SUPPORTED | Assistant 对 MCP 调用先 reserve，再 await 结果；同一逻辑调用成功可回查，未知则停止。现有本地 Worker 可以跨进程恢复 Run。所查入口未见可适配任意外部后台作业的 job_id/status/cancel 协议。若将来有具体慢工具，才为该工具保存外部受理 ID、以只读查询对账、显式区分本地停止与远端取消。 | [await 与 reserve](../../../opspilot/assistant.py)、[调用身份](../../../opspilot/domain/assistant.py)、[进程恢复测试](../../../tests/test_m1_worker_recovery.py) |
| 验证、收益与复杂度 | PARTIALLY_SUPPORTED | 有历史 R/H/A、Trace、AR‑04A 的目标/材料 marker、AR‑04B 的 ON/OFF 与实际消息检查。但 marker 出现无法证明四条条件均生效，固定策略也无法证明真实模型判断正确。尚缺同资源相邻任务、次日恢复、撤销后合法补查与重新生成的成对留出评价。 | [R/H/A 入口](../../../opspilot/smokes/m2_02_rha_matrix.py)、[AR‑04A 结果](../../evidence/ar-04a/context-journey-01/RESULTS.json)、[AR‑04B Trace](../../evidence/ar-04b/memory-journey-01/TRACE.jsonl)、[新评测设计](EVALUATION.md) |
| 跨主机 exactly-once、任意第三方不可查询工具 | NOT_APPLICABLE | 当前合同是本地单库、单 Worker 和受控动作；无法据此承诺分布式外部系统的恰好一次。外部非幂等提交若结果未知，应保持未知并对账。 | [恢复合同](../../baseline/EVENT_RECOVERY.md)、[本地恢复测试](../../../tests/test_d4_recovery.py) |

### 已有候选工作与历史失败

- **C01 / AR‑06**。在本地候选 `e3dd3e6e83359bde364925a087f0d4430f04583a` 核对到 40 轮 Fixture、500 条以上未摘要历史、个人记忆显式写入、跨 Session 修订、关闭召回和自动整合。若以后纳入个人偏好，先取这些实现与测试逐项比对。它们没有改变本报告对 main 多目标恢复的判定。[会话测试](https://github.com/wgqa/OpsPilot/blob/e3dd3e6e83359bde364925a087f0d4430f04583a/tests/test_c01_a_session_context.py) · [个人记忆测试](https://github.com/wgqa/OpsPilot/blob/e3dd3e6e83359bde364925a087f0d4430f04583a/tests/test_c01_b2_a_personal_memory.py)
- **E09-D 的失败值得保留**。历史执行报告记录了前 8 轮成功，第 9 轮压缩收到 HTTP 200，但 JSON 无效，用户没有得到答复；已有摘要也丢了 max_attempts 等字段。恰好用尽 512 个输出 Token，缺少 finish_reason，不能断定截断就是根因。E10-H 则在合法记忆辅助下读到 Receiver=QUEUED，但最终答复没准确解释被撤销的另一条记忆；冻结评分上限 PARTIAL。均为候选的历史记录。[E09-D](https://github.com/wgqa/OpsPilot/blob/e3dd3e6e83359bde364925a087f0d4430f04583a/docs/evidence/r2-ar06-eval-01/e09-d-live-20261115-01/E09_LIVE_REPORT.md) · [E10-H](https://github.com/wgqa/OpsPilot/blob/e3dd3e6e83359bde364925a087f0d4430f04583a/docs/evidence/r2-ar06-eval-01/e10-h-live-01/E10_LIVE_REPORT.md)
- **AR‑04 后续修复可复用**。候选 `b7c444586c0ee782109e3d5931034abb27a3d597` 有 29 条冻结消息、压缩引用/预算与持久化的 MockTransport 检查，Q06-B 局部仍 PARTIAL，回退读取新式引用尚未验证。本人以同一四约束输入复测候选，仍只保留三条，丢失项由“仅 E7”变为“使用 v2”。可复用候选的引用保留策略，有效任务条件仍需单独投影。[候选报告](https://github.com/wgqa/OpsPilot/blob/b7c444586c0ee782109e3d5931034abb27a3d597/docs/evidence/r2-ar04-live-retest-version-admission-01/REPORT.md)
- **PROGRAM_LIMIT 已有候选**。PRODUCT‑01 已针对“查到了事实却在获得最终回答前用完预算”做了中性提示、用户请求时重新校验来源的只读展示。复用该证据来设计中断反馈；仍须检查默认历史回流和跨任务隔离。[连续性评审](https://github.com/wgqa/OpsPilot/blob/e3dd3e6e83359bde364925a087f0d4430f04583a/docs/evidence/vnext/product-01-continuity-review-01/REPORT.md)

## 三、最小增量方案

以下为候选设计。先冻结反例及正例，再确认实施基线。第一批仅选已有订单回调调查或协议解释旅程，不扩展业务写动作。

### 1. 先解析所指，再装配 Context

用户进入原 Session 或新开会话。服务端从可信身份、当前会话链接、用户主动选择及本人可读的未完 Task 生成候选，只提供最小识别信息；跨 Session 延续优先导航回原 Session。在没有绑定的协议问答中，“再说简单点”可直接关联刚刚展示的答复，不能为了统一流程强建 Task。

有明确选定对象且无矛盾，使用该目标；只有一个与指代相符、可继续的目标，展示“继续调查订单 A 的回调”并沿用它；多个均合理时显示可区分的目标与未决问题，等待选择；零个匹配时说明缺什么或询问要新查什么。**最近展示**和**用户显式指定**须在客户端请求中可区分。同一任务内有两个合理目标时，也允许只澄清目标，不要求另建 Task。候选枚举时先鉴权，提交选择时复验归属、revision、当前状态和 operation_id。候选过时就刷新；选错目标不会被服务器的同租户检查自动识别。

第一步可在 App.vue、消息受理和既有 Session/Task 查询上完成。将普通用户历史分成当前 Task 消息、可追溯的相关无 Task 材料、其他 Task 三类；保留从无绑定协议咨询到合法订单绑定的 AR‑04A 正例。明确切换到另一个已有 Task 时走其原绑定；用户要换受信订单、服务、主体时仍走正式绑定入口。允许独立的新问题直接回答。上述过程不要求每条消息新增一次模型调用。

### 2. 逐项保存有效条件，按引用组装工作上下文

| 层 | 建议数据与权威 | 使用与失效 |
|---|---|---|
| Session Context | 复用 sessions、messages、session_task_links、context_summaries、dependencies 和 manifests。消息保留原文与归属；摘要是可重建的历史视图。 | 预算先留本轮问题、合法目标、正式锚点、必要条件与当前证据，再分配方法提示和历史。每个选入/排除项有引用、理由和估算 Token。 |
| 任务工作状态 | 首选在现有调查更新提案/确认事务旁，增一张有界追加表（建议名 `task_intent_changes`）。字段含 tenant_id、task_id、goal_id、item_id、类型（目标/条件/材料引用/未决项）、操作（新增/替换/撤回/挂起/恢复）、前项引用、source_message_id、source_digest、适用修订、operation_id。文本保留可核对短引用。按 Task+来源命令+项设唯一约束。 | 同项最新有效操作构成投影；撤回留下历史且从有效项排除，替换只影响所指项。已有消息足以无歧义投影时先不建表。未确认的语言解析保留提议；影响正式调查依据的变更复用 CORRECT_TASK_INPUT、CAS 与旧 Plan 失效。个人偏好、用户原话都无权修改 Policy。 |
| Task 执行态 | 复用 TaskControl、run inputs、runs、ActionIntent/Ledger/Receipt。工作项的“已答复/待查”与业务 Outcome 分别投影。 | 可暂停的是用户目标的后续推进；首片优先支持已到等待点或两次 Run 之间的挂起。活动调用中的“暂停”需明确展示进行中并在安全边界停止后续派发；未完成这项前不能显示“已暂停”。恢复前检查未知调用和最新状态，等待审批保持原入口。 |
| User / Project Memory | 项目方法继续走现有 Episodic/Semantic 选择器。个人偏好如确需接入，复用 C01 候选，按 trusted owner、租户、开关、来源版本、有效状态、数量与 Token 上限读取。 | 临时条件只属该目标。用户说“仅这次用中文”不能成为长久偏好。修订/撤销后，重查依赖其版本的摘要、答案、缓存和 checkpoint，排除旧正文。长期经验只指导接下来查什么。 |

目标、未决问题和材料都要追溯到消息或受信资源。例：“限 E7、只看昨夜、分别列 Delivery/Receiver”；后来说“时段放宽到全天，另外两个条件不变”。投影只替换时间项，保留 E7 和输出要求。引用冲突且用户意图不清时，可解释已知部分并询问有歧义的一项。保留用户否定、排除的假设、缺少的材料；相同条件合并其来源。版本、时效、Grant、正式修订和工具结果在 Domain 重查。来源失效后不得通过引述旧答案取得其受限正文。合法新来源仍可继续，普通用户自述按其原有权威显示。

**老数据与并发。** 对没有逐项记录的旧 Task，从已核实的 CREATE_TASK 和已应用纠错按序重建只读视图，标注来源与歧义；不批量从摘要反推确认项，不为旧 Task 制造审批或 Run。提案确认、正式纠错和工作项变更在同一个 Domain 事务提交，失败整体回滚；并发撤回/替换用预期版本拒绝旧提交，同键异摘要拒绝。无需另存整份 Prompt。有效项超预算时，优先按当前子问题取回原文；仍无法满足时展示缺项或请用户缩小范围，保留未选条件的引用。

### 3. 在现有 Loop 上区分输出与完成

`消息 → 确定对象/澄清 → 读取有效工作项与当前授权来源 → 原 Assistant 或 Investigator → 模型按观察选择解释、补查、询问、收口 → Domain 核对 Outcome 与回执 → 面向用户说明已完成/待解决内容`。

| 观察 | 合法下一步和可交付结果 |
|---|---|
| 用户只要求改写某条回答，依赖仍有效 | 指向 answer/message ID，复用现有答复及许可来源，出一份新表述，可有已记账模型调用，工具派发为零。问“再查现在怎样”则创建新的合法只读查询；“重新生成”孤立且有歧义则澄清。重新执行已提交动作只能从既有受控入口对账。 |
| 所需证据可在当前绑定、预算内补查 | 模型选合法查询；Delivery=202、Receiver=QUEUED 时报告已受理且处理未完成，必要时查同事件。Receiver=PROCESSED 且来源匹配时可回答处理结果。简单解释可直接结束。 |
| 缺少只有用户能提供的对象/材料 | 提问并持久保留未决项；若用户仅想要现有事实，可先交付已知部分。审批只能转交可信角色。 |
| 预算耗尽、工具失败、权限不足 | 展示停止原因、已核实部分、缺失项与合法下一步。只读临时错误按既有预算/错误合同处理；权限撤销停止相关读取，未知费用或副作用先查账。禁止把一个最终消息或 SUCCEEDED 计为业务恢复。 |
| 完成判断 | 说明型目标按已交付要求和有效依据评测；调查型要求绑定目标、必要材料、当前事实、未决项逐一可核对；S1、S2 需分别对齐在线验证与交付、诊断/草稿/受控交接，S3 区分订单、投递和接收端。自由文本是否完整由冻结 rubric 独立判读，不增设“模型自己给 PASS”的执行门。 |

## 四、优先级、成本与停止线

估算按熟悉仓库的一名开发者、单机 SQLite、复用现有前后端、Fixture 和评审人可用计算，是规划量级；没有 measured latency 或真实模型收益。

| 优先级 / 切片 | 最小变更与用户收益 | 工程及运行成本 | 验收后停止 |
|---|---|---|---|
| P0a 对象选择与上下文隔离 | 先修双 Task 原话串入、区分自动恢复的页面焦点与用户选择；实现已到等待点的次日继续/歧义澄清。 | 约 2–4 人日；索引范围的候选查询、零额外必需模型往返。风险是错误排除绑定前材料。 | 案例 2、3、6 以及合法绑定前材料正例。 |
| P0b 有效条件与目标完成 | 仅为 P0a 旅程增加逐项来源、替换和撤回投影；挂到两个上下文消费入口；明确停止文案与 Outcome 判据。 | 约 3–5 人日；至多一张新表、小范围迁移、候选读取与 Token 增量需测。核心代价是同时维护旧会话语义和 CAS。 | 案例 1、4、7，外加冻结回归。两片各自先过离线；只读验收不升级任何动作权限。 |
| P1 改写/重查与恢复组合 | 引用回答的改写、材料失效时重组、运行中暂停的安全边界；复用已存在的恢复/回执对账，无新写工具。 | 约 2–4 人日；可能多一个明确选择。原生技术恢复作为 P0 回归门；发现重复写则立即阻断发布。 | 案例 5、6、8，加取消与合法只读补查。 |
| P1 条件保真对照 | 选 AR‑04 后续候选复跑真实反例，加入 20–40 轮、同义表达与不同事实的配对比较。 | 约 1–2 人日准备与评分；真实 Provider 另列预算与授权。 | 能解释收益、失败与成本后停止，允许结果无增益。 |
| P2 个人记忆/跨会话偏好 | 仅在留出集显示重复询问稳定偏好时评估 C01 的最小接入。 | 约 2–4 人日用于基线差异、迁移/撤销回归；不计入 P0。 | 收益不足则保留实验。向量库、分布式队列、通用任务平台、多 Agent 和通用 Coding Agent 无本轮业务依据。 |

### 五、评测与正式规划六问

[八个验收案例、对照指标、取证与上线门槛](EVALUATION.md)是本轮第五项交付。源码、测试和两项负例详见[证据记录](EVIDENCE.md)。

1. **用户变化**：目标是隔天回到正确调查，保住仍有效的条件，让用户只补缺失项。本次交付仅分析。
2. **Agent 决策**：让模型在许可数据内判断指代、解释、澄清或补查；身份、挂起状态、正式纠错、许可和回执由程序裁决。减少串题本身属于可靠性收益。
3. **观察驱动**：同一句“下一步”，一个尚未查 Receiver 的目标可补查；同事件已有当前 PROCESSED 时可直接解释；两个合理目标时先澄清。允许其他同样合法的调查顺序。
4. **约束双向检查**：拒绝把 A 的专属条件带进 B，同时保留无 Task 阶段用户明确给 B 的材料；拒绝已撤销来源，同时允许有效替代来源；阻断盲重试，同时允许回查既有回执。
5. **责任与简化**：先修查询范围、焦点来源和上下文投影，复用命令、账本、预算与 LangGraph；仅在消息无法可靠表达替代关系时增量持久化。无生产组件增删。
6. **证据与停止线**：按有效目标和最终事实给分，留存错题、实际输入和成本。先完成离线双向回归、再独立评审；本轮不进入实施。八案真实模型端到端效果为 **HOLD / UNVERIFIED**。
