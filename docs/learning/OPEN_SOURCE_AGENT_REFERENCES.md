# 开源 Agent 参考：源码入口、机制与采纳边界

> **定位：** 这是开发指导，不是阶段任务卡、不是验收合同，也不是“外部项目已经证明”的证据。它的用途只有一个：在设计 Agent Core、Context/Memory/Knowledge/Skill/MCP 装配、模型调用保障、取消/恢复或模块拆分之前，先看清两个可复查的外部实现到底怎么分层，再决定 OpsPilot 采纳、裁剪还是拒绝。
>
> **研究基线：** OpsPilot 代码以 `48234e5dabb6ed28ea816b8ebc438288409353b8`（`origin/main`）为准；外部仓库在 2026-11-04 通过浅克隆实际读取，commit 见下文。本文**没有运行** Ragent 或 Pi，也没有用它们做过性能、成本或效果对照。所有“机制”描述都来自源码静态阅读，不能写成“已被外部验证”或“本项目已实现”。
>
> **与其他文档的关系：** 方向与权力边界以 [PROJECT_NORTH_STAR.md](../../PROJECT_NORTH_STAR.md) 第 0、3、6、8 节为准；本文不新增治理合同，也不得覆盖冻结的安全、审批、事务和 Gold。

## 0. 一页结论

1. **两个项目都没有手写“会思考的循环”。** Ragent 把循环交给 AgentScope 的 `ReActAgent`，自己写中间件；Pi 的 `agent` 包核心是循环、事件和队列，压缩、会话树、技能都在 `coding-agent` 应用层。真正值钱的是**分层与调用边界**，不是某个 ReAct 实现。
2. **Context 策略可以放在应用层，但事实与授权不能。** Pi 的压缩在 `agent-session.ts` 里挂 `prepareNextTurn`；Ragent 的压缩是 `onReasoning` 中间件。两者都让核心循环不知道“摘要”这件事。OpsPilot 应保持同样方向：循环用框架，Context 装配和摘要账本在现有 Domain，不把摘要塞进 Agent Core。
3. **外部项目的“记忆”比 OpsPilot 宽松。** Ragent 会从用户发言自动学习长期记忆，Pi 不做跨任务长期记忆。OpsPilot 的 Memory 必须经过来源、候选、独立确认、撤销和派生失效检查，不能照搬“自动记住”。
4. **外部项目的“取消”只到进程内。** Ragent 有会话闸门、SSE 断开取消和收尾补存；Pi 有 `abort()`，文档说明中止会把排队消息交回编辑器。它们都没有 OpsPilot 这种“模型调用已外发但结果未知”的持久账本问题。取消后的 `UNKNOWN` 收口、禁止盲目重发必须留在 OpsPilot Domain。
5. **不要因为参考项目有某个部件就扩建。** Pi 明确不做 sub-agent 和 plan mode；Ragent 的 middleware 链也不是通用插件平台。OpsPilot 只在出现**真实重复调用和职责冲突**时抽取，不能把“别人有”当成阶段授权。

## 1. 事实卡：Ragent

### 1.1 仓库与版本

| 项目 | 值 |
|---|---|
| 仓库 | `https://github.com/nageoffer/ragent` |
| 读取 commit | `200dca86ac04d3a27f7cfffd7d3dd4d2b1c41129`（2026-11-03） |
| 工程版本 | 根 `pom.xml` 的 `ragent` 为 `0.0.1-SNAPSHOT`；Java 17 |
| Agent 运行时 | `io.agentscope:agentscope-core:2.0.2`（根 `pom.xml` L32、L191-L201） |
| 读取范围 | `agent/` 模块、根 `pom.xml`、README；未运行服务、未调用模型、未执行其测试 |
| 说明 | README 宣传 Spring AI 2.0，但 Agent 运行时实际是 AgentScope；不要把两者混为一谈 |

### 1.2 关键源码入口

路径均相对仓库根；行号来自上述 commit 的实际文件。

| 机制 | 源码入口 | 读到的行为 |
|---|---|---|
| 复用框架循环，只组装 | [`config/ReActAgentProvider.java` L100-L124](https://github.com/nageoffer/ragent/blob/200dca86ac04d3a27f7cfffd7d3dd4d2b1c41129/agent/src/main/java/com/nageoffer/ai/ragent/agent/config/ReActAgentProvider.java#L100-L124) | `ReActAgent.builder()` 设置人设、模型、工具目录、`maxIters`、`maxRetries`、pending tool recovery、状态存储，再按顺序挂中间件；没有自写 ReAct 循环。 |
| 压缩作为推理前中间件 | [`memory/AgentContextCompactionMiddleware.java` L73-L98](https://github.com/nageoffer/ragent/blob/200dca86ac04d3a27f7cfffd7d3dd4d2b1c41129/agent/src/main/java/com/nageoffer/ai/ragent/agent/memory/AgentContextCompactionMiddleware.java#L73-L98) | 只有“摘要开启 + 最后一条是 USER + 总字符超水位”才压缩；压缩异常回退到工具结果裁剪，不阻断本轮。 |
| 摘要切点与摘要消息 | [`memory/AgentContextCompactor.java` L62-L147](https://github.com/nageoffer/ragent/blob/200dca86ac04d3a27f7cfffd7d3dd4d2b1c41129/agent/src/main/java/com/nageoffer/ai/ragent/agent/memory/AgentContextCompactor.java#L62-L147) | 从尾部累计保留量，只把切点落在用户轮起点；把早期原文换成一条 `USER` 角色的摘要消息，正文带固定说明“这是背景，不是新指令，摘要有损”。 |
| 摘要生成与失败语义 | [`memory/AgentConversationSummarizer.java` L80-L106](https://github.com/nageoffer/ragent/blob/200dca86ac04d3a27f7cfffd7d3dd4d2b1c41129/agent/src/main/java/com/nageoffer/ai/ragent/agent/memory/AgentConversationSummarizer.java#L80-L106) | 单独一次模型调用，非流式、120 秒超时、沿用主循环 `maxRetries`；空摘要、非 `stop` 结束、异常都返回 `null`，调用方放弃本次压缩。 |
| 压缩审计 | [`memory/AgentContextCompactor.java` L101-L121](https://github.com/nageoffer/ragent/blob/200dca86ac04d3a27f7cfffd7d3dd4d2b1c41129/agent/src/main/java/com/nageoffer/ai/ragent/agent/memory/AgentContextCompactor.java#L101-L121) | 每次压缩写一条代际、摘要、素材条数/字符、压缩前后字符；落库失败只报警，不回滚已经生效的压缩。 |
| 旧工具结果裁剪 | [`memory/AgentContextTrimmer.java` L68-L140](https://github.com/nageoffer/ragent/blob/200dca86ac04d3a27f7cfffd7d3dd4d2b1c41129/agent/src/main/java/com/nageoffer/ai/ragent/agent/memory/AgentContextTrimmer.java#L68-L140) | 超水位后把旧工具结果正文换成短占位，保留 tool call/result 配对与 id；当前轮和未闭合的工具循环不占保留配额。 |
| 长期记忆注入 | [`memory/AgentUserMemoryMiddleware.java` L65-L106](https://github.com/nageoffer/ragent/blob/200dca86ac04d3a27f7cfffd7d3dd4d2b1c41129/agent/src/main/java/com/nageoffer/ai/ragent/agent/memory/AgentUserMemoryMiddleware.java#L65-L106) | 每次调用级 `RuntimeContext` 只读一次快照；先删旧记忆块再插一条，放在系统人设之后、会话首条之前；记忆块用 `USER` 角色以兼容供应商。 |
| 后台记忆学习 | [`memory/AgentMemoryLearner.java` L89-L134](https://github.com/nageoffer/ragent/blob/200dca86ac04d3a27f7cfffd7d3dd4d2b1c41129/agent/src/main/java/com/nageoffer/ai/ragent/agent/memory/AgentMemoryLearner.java#L89-L134) | 用户级锁 + 游标批量读；模型判断在事务外；提交时用游标 CAS 把“变更 + 游标”放一个事务；提交异常返回 `UNKNOWN`，不推游标。 |
| Skill 渐进披露 | [`skill/SkillLoadTool.java` L39-L124](https://github.com/nageoffer/ragent/blob/200dca86ac04d3a27f7cfffd7d3dd4d2b1c41129/agent/src/main/java/com/nageoffer/ai/ragent/agent/skill/SkillLoadTool.java#L39-L124) | 工具 description 里只放技能清单（名称 + 描述），模型判断命中后调用 `load_skill` 才返回手册正文；正文每次从注册表读，改手册无需重建 Agent。 |
| Skill 工具遮蔽 | [`skill/AgentSkillMaskingMiddleware.java` L74-L113](https://github.com/nageoffer/ragent/blob/200dca86ac04d3a27f7cfffd7d3dd4d2b1c41129/agent/src/main/java/com/nageoffer/ai/ragent/agent/skill/AgentSkillMaskingMiddleware.java#L74-L113) | 未加载手册时隐藏“必须先看手册才会用”的工具；解锁只认上下文里成功 `load_skill` 的 metadata；手册被压缩带走后工具重新隐藏。它只管可见性，不替代操作确认。 |
| 运行闸门、取消、收尾 | [`service/impl/AgentChatServiceImpl.java` L82-L100](https://github.com/nageoffer/ragent/blob/200dca86ac04d3a27f7cfffd7d3dd4d2b1c41129/agent/src/main/java/com/nageoffer/ai/ragent/agent/service/impl/AgentChatServiceImpl.java#L82-L100)、[L221-L283](https://github.com/nageoffer/ragent/blob/200dca86ac04d3a27f7cfffd7d3dd4d2b1c41129/agent/src/main/java/com/nageoffer/ai/ragent/agent/service/impl/AgentChatServiceImpl.java#L221-L283)、[L343-L372](https://github.com/nageoffer/ragent/blob/200dca86ac04d3a27f7cfffd7d3dd4d2b1c41129/agent/src/main/java/com/nageoffer/ai/ragent/agent/service/impl/AgentChatServiceImpl.java#L343-L372) | 同一会话先拿闸门再启动；流结束时按注册顺序补存状态、释放闸门、再调度后台记忆；SSE 超时/错误/完成都触发本地取消。 |
| 工具批事实 | [`tool/AgentToolBatchMiddleware.java` L56-L97](https://github.com/nageoffer/ragent/blob/200dca86ac04d3a27f7cfffd7d3dd4d2b1c41129/agent/src/main/java/com/nageoffer/ai/ragent/agent/tool/AgentToolBatchMiddleware.java#L56-L97) | 一次 acting 开一批、`doFinally` 收口；成功/异常/取消都收口；有结果事件却没有工具体记录时，标成“执行前短路”，且该判定不随追踪开关变形。 |
| 用户取消后的口径修正 | [`confirm/AgentConfirmDenialMiddleware.java` L58-L76](https://github.com/nageoffer/ragent/blob/200dca86ac04d3a27f7cfffd7d3dd4d2b1c41129/agent/src/main/java/com/nageoffer/ai/ragent/agent/confirm/AgentConfirmDenialMiddleware.java#L58-L76) | 只把“用户在确认卡片点取消”的框架拒绝文案改写成“操作未执行，不是权限不足或系统故障”；规则拒绝不动。 |

### 1.3 这份实现明确没有做的事

- 没有把“摘要”当业务事实：摘要消息自我声明是背景、不可当新指令，且角色选择是为了供应商兼容，不是为了提升权威。
- 没有在压缩失败时强行继续：失败就退回裁剪或放弃本轮压缩，不会把半成品摘要写进上下文。
- 没有让 Skill 解锁变成授权：遮蔽只影响模型可见工具，操作确认和业务校验仍在别处。
- 没有把后台记忆学习放进对话事务：模型调用在事务外，提交只包“变更 + 游标”。

## 2. 事实卡：Pi

### 2.1 仓库、重定向与版本

| 项目 | 值 |
|---|---|
| 用户给出的入口 | `https://github.com/badlogic/pi-mono` |
| 实际解析 | GitHub API 将其解析到 repository id `1035029907` 并重定向到 `https://github.com/earendil-works/pi`；作者仍是 Mario Zechner（badlogic） |
| 读取 commit | `d8981c7ba00a722c897d7270b7f421418512a784`（2026-11-04） |
| 版本 | 根 `package.json` 为 `pi-monorepo`；`packages/coding-agent/package.json` 为 `@earendil-works/pi-coding-agent` `1.5.0` |
| 读取范围 | `packages/agent/src`、`packages/coding-agent/src/core`、`docs/how-pi-works.md`、`docs/compaction.md`、`docs/skills.md`、`docs/sessions.md`；未运行 CLI、未调用 Provider |
| 说明 | 记录重定向是事实要求：如果只写旧地址，新 Agent 无法复核到同一棵树 |

### 2.2 关键源码入口

| 机制 | 源码入口 | 读到的行为 |
|---|---|---|
| 薄 Agent Core | [`packages/agent/src/agent-loop.ts` L172-L330](https://github.com/earendil-works/pi/blob/d8981c7ba00a722c897d7270b7f421418512a784/packages/agent/src/agent-loop.ts#L172-L330) | `runLoop` 只做：取 steering/follow-up、每轮准备请求、流式取 assistant、执行工具、写回 tool result、`finishTurn` 决定继续或结束。核心不实现摘要算法，只留 `transformContext`/`prepareRequest`/`prepareNextTurn` 等 hook；压缩就是挂在 hook 上的应用层逻辑。 |
| 扩展点而非硬编码 | [`agent-loop.ts` L228-L248](https://github.com/earendil-works/pi/blob/d8981c7ba00a722c897d7270b7f421418512a784/packages/agent/src/agent-loop.ts#L228-L248)、[L295-L307](https://github.com/earendil-works/pi/blob/d8981c7ba00a722c897d7270b7f421418512a784/packages/agent/src/agent-loop.ts#L295-L307) | `prepareRequest` 在每次 Provider 请求前重建上下文；`finishTurn` 可返回 `end` / `continue`；`prepareNextTurn` 可在下一轮前替换上下文。压缩就是从这些口子挂进去的。 |
| Agent 类只管状态与队列 | [`packages/agent/src/agent.ts` L194](https://github.com/earendil-works/pi/blob/d8981c7ba00a722c897d7270b7f421418512a784/packages/agent/src/agent.ts#L194) | `Agent` 持有 model、messages、tools、streaming 状态、steering/follow-up 队列；没有 session、compaction、memory、knowledge。 |
| 核心包确实不含压缩/会话 | `packages/agent/src` 全文搜索 `compaction` 只命中 `agent-loop.ts` L210 的一句注释 | 这是分层证据：压缩属于应用层策略，不属于循环。 |
| 压缩挂在下一轮准备 | [`packages/coding-agent/src/core/agent-session.ts` L918-L933](https://github.com/earendil-works/pi/blob/d8981c7ba00a722c897d7270b7f421418512a784/packages/coding-agent/src/core/agent-session.ts#L918-L933) | 包装 `prepareNextTurnWithContext`，先按阈值压缩，再调用原有准备逻辑；压缩是应用层对框架 hook 的使用。 |
| 触发条件 | [`compaction.ts` L267-L270](https://github.com/earendil-works/pi/blob/d8981c7ba00a722c897d7270b7f421418512a784/packages/coding-agent/src/core/compaction/compaction.ts#L267-L270)、[L120-L130](https://github.com/earendil-works/pi/blob/d8981c7ba00a722c897d7270b7f421418512a784/packages/coding-agent/src/core/compaction/compaction.ts#L120-L130) | `contextTokens > contextWindow - reserveTokens` 才压缩；默认 `reserveTokens=16384`、`keepRecentTokens=20000`。 |
| 压缩结果是一个条目 | [`packages/coding-agent/src/core/session-manager.ts` L91-L104](https://github.com/earendil-works/pi/blob/d8981c7ba00a722c897d7270b7f421418512a784/packages/coding-agent/src/core/session-manager.ts#L91-L104)、[L1272](https://github.com/earendil-works/pi/blob/d8981c7ba00a722c897d7270b7f421418512a784/packages/coding-agent/src/core/session-manager.ts#L1272) | `CompactionEntry` 保存 `summary`、`firstKeptEntryId`、`tokensBefore`、可选 `usage` 和 `details`；原始条目仍在会话树里，只是不再进入模型请求。 |
| 摘要失败不落检查点 | [`compaction.ts` L585-L593](https://github.com/earendil-works/pi/blob/d8981c7ba00a722c897d7270b7f421418512a784/packages/coding-agent/src/core/compaction/compaction.ts#L585-L593) | `stopReason=error` 或 `length` 都视为失败：后者是半成品摘要，不能持久化为检查点。 |
| 摘要调用统一收口 | [`compaction.ts` L618-L638](https://github.com/earendil-works/pi/blob/d8981c7ba00a722c897d7270b7f421418512a784/packages/coding-agent/src/core/compaction/compaction.ts#L618-L638) | 所有压缩/分支摘要共用 `completeSummarization`，统一处理重试、`cacheRetention: none`、取消信号；摘要 Usage 会随条目保存。 |
| 会话树 | [`docs/how-pi-works.md` L25-L31](https://github.com/earendil-works/pi/blob/d8981c7ba00a722c897d7270b7f421418512a784/packages/coding-agent/docs/how-pi-works.md#L25-L31)、[`docs/sessions.md` L32-L42](https://github.com/earendil-works/pi/blob/d8981c7ba00a722c897d7270b7f421418512a784/packages/coding-agent/docs/sessions.md#L32-L42) | JSONL 每条形如“带 id、指向 parent 的树节点”；活动分支决定模型上下文；分支切换可以生成 `branch_summary`，原分支不删除。 |
| Skill 渐进披露 | [`packages/coding-agent/src/core/system-prompt.ts` L173-L181](https://github.com/earendil-works/pi/blob/d8981c7ba00a722c897d7270b7f421418512a784/packages/coding-agent/src/core/system-prompt.ts#L173-L181)、[`docs/skills.md` L43-L45](https://github.com/earendil-works/pi/blob/d8981c7ba00a722c897d7270b7f421418512a784/packages/coding-agent/docs/skills.md#L43-L45) | 启动时系统提示只放技能名称、描述、路径；完整 `SKILL.md` 由模型按需读取；`description` 负责路由。 |
| 扩展机制 | [`docs/how-pi-works.md` L41-L49](https://github.com/earendil-works/pi/blob/d8981c7ba00a722c897d7270b7f421418512a784/packages/coding-agent/docs/how-pi-works.md#L41-L49) | 扩展是进程内 TypeScript 模块，可注册工具、命令、快捷键、Provider、事件处理器；扩展运行在 Pi 进程和相同 OS 权限下，因此“扩展能力”不等于“安全隔离”。 |

### 2.3 这份实现明确没有做的事

- 没有在 Agent Core 里做记忆、知识检索或业务授权；Pi 是编码 Agent，不是企业任务 Agent。
- 没有把压缩条目当业务事实：它只是“以后请求从哪个条目开始”的上下文边界。
- 没有靠删历史来压缩：原条目仍在树里，可导出、可回看。
- 没有任何 Domain 级别的审批、幂等、回执或“未知结果”账本；这些不能从 Pi 借鉴。

## 3. 对照矩阵：外部机制 → OpsPilot 当前实现 → 决策

> OpsPilot 列以 `48234e5` 为准。AR-04A 的压缩记账/取消收口候选尚未合入 `main`，因此**不算当前实现**；下文只在“统一调用保障”一节把它标为待合并候选。

| 外部源码入口 | 技术机制 | OpsPilot 当前实现（`48234e5`） | 采纳 / 裁剪 / 拒绝 | 对应验证 |
|---|---|---|---|---|
| Ragent `ReActAgentProvider` L100-L124 | 复用 AgentScope 循环，自己只组装工具、预算和中间件 | [`opspilot/assistant.py` L840](../../opspilot/assistant.py#L840) 用 LangGraph `create_agent` 建循环；自定义逻辑在 `Loop` 中间件（L471、L585、L662） | **采纳**：循环继续用框架，不手写 ReAct；**拒绝**：再包一层“通用 Agent 平台” | `tests/test_ar02_assistant.py`、`tests/test_m1_chat.py` |
| Pi `agent-loop.ts` L172-L330 | 核心只有模型-工具循环、事件、队列；策略通过 hook 注入 | 同上：`create_agent` + `AgentMiddleware`；`prepare`/工具钩子承担策略 | **采纳**：核心保持薄；**裁剪**：不复制 Pi 的事件类型体系 | `tests/test_ar02_assistant.py` |
| Pi `agent-session.ts` L918-L933 | 压缩在应用层挂 `prepareNextTurn`，核心不知道摘要 | 经典 Chat Worker 在 [`opspilot/web/worker.py` L349-L391](../../opspilot/web/worker.py#L349-L391) 调压缩；摘要在 [`opspilot/domain/chat.py` L1703](../../opspilot/domain/chat.py#L1703) 准备、L1822 完成 | **采纳**：策略在应用/Domain 层；**保留差异**：OpsPilot 需要摘要依赖与失效，不只是上下文替换 | `tests/test_m302_context.py` |
| Pi `session-manager.ts` L91-L104 | 压缩=一条 `CompactionEntry` + `firstKeptEntryId`，原历史不删 | [`opspilot/domain/database.py` L910-L965](../../opspilot/domain/database.py#L910-L965) 的 `context_compression_attempts` / `context_summaries` / `context_summary_dependencies`；`_summary_is_current` 在 [`chat.py` L635](../../opspilot/domain/chat.py#L635) | **裁剪**：不引入会话树/分支 UI；**拒绝**：把摘要简化成单条不可追溯文本 | `tests/test_m302_context.py`、`tests/test_ar02_context_continuity_01.py` |
| Ragent `AgentContextCompactor` L62-L147 | 摘要替换早期原文，切点只在用户轮；摘要以 `USER` 角色回填并声明“有损背景” | `context_summaries` 保存结构化摘要、版本、覆盖范围、来源依赖；`context_summary_dependencies` 记录 MESSAGE/MODEL_ATTEMPT/MEMORY/EVIDENCE/SKILL/SUMMARY | **采纳**：摘要必须声明派生与非权威；**拒绝**：单一审计表代替依赖失效 | `tests/test_m302_context.py` |
| Ragent `AgentContextTrimmer` L68-L140 | 超水位后把旧工具结果换成短占位，保护最近循环 | 当前以 `RECENT_WINDOW`/`ROLLING_SUMMARY`/`HYBRID` 控制窗口与摘要；压缩输入会对助手历史做有界截断（[`chat.py` L995](../../opspilot/domain/chat.py#L995)），但没有独立的工具结果逐条驱逐器 | **暂缓**：先不新增第二套裁剪器；若真实长工具结果造成预算问题，再评估并入现有 Context 装配 | 现有 `tests/test_m302_context.py`；新能力尚无证据 |
| Ragent `AgentUserMemoryMiddleware` L65-L106 + `AgentMemoryLearner` L89-L134 | 长期记忆按用户自动学习；模型调用在事务外，游标 CAS 提交，异常返回 `UNKNOWN` | Episodic/Semantic Memory 在 [`opspilot/domain/episodic_memory.py`](../../opspilot/domain/episodic_memory.py#L29)、[`semantic_memory.py`](../../opspilot/domain/semantic_memory.py#L199)；候选需独立确认，可撤销 | **采纳**：事务只包提交、未知不重试；**拒绝**：从用户发言自动生效的长期记忆 | `tests/test_m301_memory.py`、`tests/test_m303_semantic_memory.py`、`tests/test_d5_context.py` |
| Ragent `SkillLoadTool` L39-L124 + `AgentSkillMaskingMiddleware` L74-L113 | 先给技能清单，模型按需加载正文；未加载时隐藏相关工具，压缩后重新隐藏 | Skill 由 [`opspilot/skill_assets.py` L26](../../opspilot/skill_assets.py#L26) 按问题类型装载，内容作为方法提示进入上下文（[`investigator.py` L687-L739](../../opspilot/investigator.py#L687-L739)） | **采纳**：Skill 只给方法、不定义权限；**裁剪**：暂不引入 `load_skill` 工具和工具遮蔽；**拒绝**：用工具可见性当授权 | `tests/test_d5_context.py`、`tests/test_m1_chat.py` |
| Ragent `AgentChatServiceImpl` L221-L283、L343-L372 | 会话闸门、SSE 断开取消、收尾补存、再调度后台任务 | 任务/Run 的 worker fence 在 [`chat.py` L66](../../opspilot/domain/chat.py#L66)；Assistant 调用账本在 [`domain/assistant.py` L299-L330](../../opspilot/domain/assistant.py#L299-L330)；实验账本在 [`assistant_experiment.py` L216-L260](../../opspilot/domain/assistant_experiment.py#L216-L260) | **采纳**：取消必须收口、收尾顺序明确；**保留差异**：OpsPilot 还要持久化 `UNKNOWN` 并禁止盲目重发 | `tests/test_ar02_assistant.py`；取消 `UNKNOWN` 的完整收口仍是 AR-04A 候选，未入 `main` |
| Ragent `AgentToolBatchMiddleware` L56-L97 | 工具批边界与“执行前短路”事实，不依赖追踪开关 | `assistant.py` 的 `awrap_tool_call`（L662）在 MCP 调用前后持久登记 `assistant_calls`；实验账本在 `reserve_dispatch`/`complete_dispatch`/`mark_unknown` | **采纳**：执行事实与可观测性解耦；**裁剪**：不新建 batch 表，复用现有调用记录 | `tests/test_ar02_assistant.py` |
| Pi `system-prompt.ts` L173-L181 | 技能清单进系统提示，正文按需读取 | 当前 Skill 内容整体进入方法提示，没有按需加载 | **裁剪**：暂不引入，因为会改变工具与权限边界；保留为后续有界实验候选 | `tests/test_d5_context.py` |
| Pi `docs/how-pi-works.md` L41-L49 | 扩展是进程内模块，能力大但信任边界弱 | OpsPilot 用 Domain 显式接口和冻结合同，不开放进程内扩展 | **拒绝**：不引入第三方进程内扩展平台 | 方向性判断，无运行证据 |

## 4. 五条架构原则

### 4.1 轻量核心

**Agent Core 只负责：** 模型决策循环、合法工具调用的发起与参数校验、Observation 回填、执行进度与停止条件。

**不负责：** 上下文压缩与摘要账本、Memory 检索/写入、Knowledge 搜索、Skill 选择策略、MCP 传输、授权/审批/预算/幂等/Usage 收口、业务事务。

判断方法：如果把某个能力从 Core 拿掉，模型仍然能“决定下一步做什么”，只是少了一种信息来源或保障，它就不属于 Core。Pi 的 `packages/agent` 和 Ragent 对 AgentScope 的复用都符合这一点；OpsPilot 也应保持 `create_agent` 只承载循环，把 `Loop` 中间件限制在“调用前后的必要保障”，不要让它长成第二个 Runtime。

### 4.2 职责分离

| 关注点 | OpsPilot 现有落点 | 不应放进去的东西 |
|---|---|---|
| Context 预算与装配 | [`opspilot/domain/context_engineering.py` L200](../../opspilot/domain/context_engineering.py#L200)、[`opspilot/domain/chat.py` L1050](../../opspilot/domain/chat.py#L1050) | 模型自由决定的权限、业务状态 |
| 会话摘要与依赖 | `context_summaries` / `context_summary_dependencies` / `context_compression_attempts`（[`database.py` L910-L965](../../opspilot/domain/database.py#L910-L965)） | 把摘要当当前 Evidence 或审批依据 |
| 分层 Memory | [`episodic_memory.py`](../../opspilot/domain/episodic_memory.py#L29)、[`semantic_memory.py`](../../opspilot/domain/semantic_memory.py#L199) | 自动学习后直接生效、跨任务授权继承 |
| Knowledge | [`assistant_knowledge.py`](../../opspilot/domain/assistant_knowledge.py#L164)、[`knowledge_assets.py`](../../opspilot/domain/knowledge_assets.py) | 用文档覆盖当前 Authz/HTTP 事实 |
| Skill | [`skill_assets.py` L26](../../opspilot/skill_assets.py#L26) | 用 Skill 文本定义工具、权限、审批 |
| MCP / 工具 | [`assistant_mcp.py`](../../opspilot/assistant_mcp.py#L1)、[`mcp_server.py` L19](../../opspilot/mcp_server.py#L19)、`assistant.py` 的 `awrap_tool_call` | TaskBinding 之外的任意 scope、任意 URL/凭据 |
| 模型调用保障 | [`assistant_experiment.py` L216-L260](../../opspilot/domain/assistant_experiment.py#L216-L260)、[`domain/assistant.py` L299-L330](../../opspilot/domain/assistant.py#L299-L330) | 在 `assistant.py` 复制第二套预算/幂等状态机 |
| 可信业务事务 | `opspilot/domain/` 的 TaskControl / Plan / Approval / Intent / Ledger / Receipt 模块 | 模型文字、摘要、Memory、Skill、框架 checkpoint |

**硬规则：** 任何“模型能读到的东西”都不可信为授权；任何“业务副作用”都只能由 Domain 事务和可信角色触发。外部项目越轻，越要把这条写清楚，而不是跟着变轻。

### 4.3 统一调用保障

OpsPilot 现在至少有三种外部调用：回答模型调用、上下文压缩模型调用、MCP 工具调用；未来还会有记忆蒸馏等。它们必须共用同一类保障语义：

- 出站前授权/预算检查与预留；
- 稳定幂等键（同键异摘要拒绝）；
- 实际 Usage 结算；
- 取消/超时/异常的 `UNKNOWN` 收口；
- 恢复时先回查，禁止把 `UNKNOWN` 当“未发生”直接重发。

**当前实现状态（必须如实区分）：**

- `ASSISTANT_V1` 的模型/工具调用已接入 `assistant_calls`；启用实验账本时，同时接入 `reserve_dispatch`/`complete_dispatch`/`mark_unknown`，见 [`assistant.py` L585-L660](../../opspilot/assistant.py#L585-L660) 和 [`domain/assistant.py` L299-L330](../../opspilot/domain/assistant.py#L299-L330)。
- 经典 Chat Worker 的压缩调用仍是 [`worker.py` L376](../../opspilot/web/worker.py#L376) 的直接 `model.ainvoke`，由 `chat_attempts` / `context_compression_attempts` 计数，但没有接入实验账本。这是历史路径的已知差异，不应被描述成“所有调用已统一”。
- 截至 2026-11-04，存在一个未合入 `main` 的 AR-04A 候选分支，尝试把 Assistant 压缩调用接入 `reserve_dispatch`/`complete_dispatch`/`mark_unknown` 并补取消收口；它不能作为当前实现或验收结论引用。

**给新 Agent 的规则：** 新增一种模型调用时，先找现有入口复用；如果现有入口类型不匹配，扩展该入口的 `kind` 或适配层，**不要**在 `assistant.py` 里新建一张表、一个新的计数器或一套新的“先 RESERVED 后 OK”的状态机。判断重复的搜索起点：`reserve_dispatch`、`complete_dispatch`、`mark_unknown`、`mark_not_dispatched`、`assistant_calls`、`context_compression_attempts`。

### 4.4 Agent 自主性

**由模型决定：** 先查哪个合法工具、是否补充查询、是否澄清、是否停止、是否使用某个 Skill/Knowledge/Memory 线索、如何根据 Observation 修正判断。

**由程序守住：** TaskBinding 与资源 scope、工具白名单与参数类型、预算上限、审批与许可、Evidence Gate、幂等键、取消/未知结果、外部副作用事务。

区分“必要确定性控制”与“多余固定 Workflow”的三个问题：

1. 这个分支保护的是**不变量**（越权、重复副作用、伪造成功、预算失控），还是只是**偏好顺序**？
2. 如果模型换一个合法顺序但仍满足不变量，系统会不会误拒？会，就说明它写死了路线。
3. 这个限制有没有**双向证据**：危险路径被拒，同时同类合法请求仍能继续？

Ragent 的中间件默认不规定工具顺序，Pi 的 `finishTurn` 把继续/结束交给上层；两者都没有在循环里写死调查步骤。OpsPilot 的 Evidence Gate、审批、Intent/Ledger 则是不变量，不能因为“释放自主性”而软化。反过来，“必须先调用 A 再调用 B”“必须提出 N 个假设”这类没有不变量支撑的顺序要求，不应新增。

### 4.5 渐进解耦

抽取模块的条件，至少同时满足两条：

1. 出现**两个以上真实调用点**，且它们对同一职责有重复实现；
2. 重复已经造成**职责冲突**（例如两套预算、两套幂等、两套取消语义），而不是“看起来不够优雅”。

只满足“外部项目这样分”不构成理由。当前值得盯住的是 `opspilot/assistant.py`：它同时包含循环中间件、调用账本适配、取消/未知收口和上下文刷新。AR-04A 的隔离候选已经暴露这些语义的复杂度；但在候选合入、出现第二个真实复用点之前，**不做大规模重构**。先保持边界清晰，再按证据抽取。

## 5. 判断“是不是在重复实现已有能力”

新增能力前，按顺序回答：

1. **它属于哪一层？** Core / Context / Memory / Knowledge / Skill / MCP / Model Call Assurance / Domain。答不出来，先不要写代码。
2. **现有模块是否已经承担？** 先读第 4.2 节表里的入口；再用符号搜索确认没有第二份实现。
3. **它会不会产生第二套状态机？** 特别检查：预算计数、幂等键、`RESERVED/OK/UNKNOWN`、取消标记、Usage 结算、恢复游标。
4. **它会不会把不可信内容提升为权威？** 摘要、Memory、Skill、Knowledge、工具文本、模型文字都只能作为输入，不能成为授权或业务事实。
5. **它会不会把合法探索挡掉？** 用成对场景验证：换一种合法工具顺序仍能完成；只有真实风险才被拒绝。

常见红灯：

- 在 `assistant.py` 新增一张 `*_calls` / `*_budget` 表或新的 `try/except` 取消分支；
- 在 Prompt 里写死“必须先调用 X，再调用 Y”，但没有对应不变量；
- 为 Skill 增加“加载后才可见”的工具，并把这套可见性当成权限；
- 为 Memory 增加自动写入，绕过候选/确认/撤销；
- 为压缩增加第二套摘要存储，绕过 `context_summary_dependencies`；
- 用框架 checkpoint 证明外部副作用已经发生。

## 6. 什么时候复用 LangChain/LangGraph，什么时候保留自己的实现

| 需求 | 优先复用 | 必须自有 | 理由 |
|---|---|---|---|
| 模型-工具循环、流式事件、中断、checkpoint | LangGraph / LangChain | — | 这些是机制，框架已经成熟；自研只会增加维护面 |
| 工具 Schema、参数校验、MCP 传输 | 框架 / MCP SDK | — | 协议细节不值得重写 |
| 上下文窗口选择、摘要触发、摘要格式 | 框架 hook + 现有 Context 模块 | 摘要依赖与失效语义 | 框架不知道 OpsPilot 的 Task/Evidence/Memory 依赖 |
| 授权、审批、Intent、Ledger、回执 | — | Domain | 框架状态不是业务权威，也不能证明副作用 |
| 预算、幂等、Usage、取消后的 `UNKNOWN` | — | 现有调用保障模块 | 这是跨调用、跨恢复的持久语义，框架不提供 |
| Memory 候选/确认/撤销 | — | Domain | 需要可信角色和来源链 |
| Skill/Knowledge 资产 | 文件与注册表 | 适用范围与版本校验 | 内容不可信，不能定义权限 |

一句话：**框架拥有“怎么跑”，OpsPilot 拥有“什么算事实、谁有权、失败了算什么”。** 当框架能力覆盖机制时，不要再写一套；当语义涉及业务事实与授权时，不要交给框架。

## 7. 未验证项与维护

复核方式（2026-11-04）：

```powershell
git clone --depth 1 https://github.com/nageoffer/ragent.git
git -C ragent rev-parse HEAD   # 200dca86ac04d3a27f7cfffd7d3dd4d2b1c41129
git clone --depth 1 https://github.com/earendil-works/pi.git
git -C pi rev-parse HEAD       # d8981c7ba00a722c897d7270b7f421418512a784
```

随后按表内路径、行号打开文件；行号只对上述 commit 有效，仓库更新后必须重新核对。

- Ragent 与 Pi 都只做了静态源码阅读；没有启动服务、没有调用真实 Provider、没有运行其测试。本文不能支持“它们在生产中如何表现”的结论。
- OpsPilot 的映射以 `48234e5` 为准；AR-04A 的记账/取消候选是隔离分支，未合入 `main`，不能写成已实现。
- 外部仓库会继续移动；引用具体机制时必须同时给 commit 和路径。重命名（如 `badlogic/pi-mono` → `earendil-works/pi`）要记录实际解析结果，不能只写旧地址。
- 本文不建立第二套治理。与 `PROJECT_NORTH_STAR.md`、冻结任务卡或安全合同冲突时，以这些文件为准，并停止相关变更请求裁决。
- 更新记录：2026-11-04 初版，核对 Ragent `200dca86` 与 Pi `d8981c7`；补入五条原则、对照矩阵和“重复实现”检查清单。
