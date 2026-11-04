# AR-04A-CONTEXT-JOURNEY-01 — 冻结旅程与 Gold

**状态：** `FROZEN`（实施前冻结；实施方不得自行修改本文件，需主 Agent 批准）
**冻结日期：** 2026-11-04
**实施方：** 主代码开发 Agent（隔离工作树）
**裁决权：** 主 Agent；本文只是验收候选的冻结标准，不是 PASS。

## 0. 开工核验（实际读取，非引用）

| 项目 | 值 |
|---|---|
| Repo | `wgqa/OpsPilot` |
| 工作树 / 分支 | `D:\学习\agent新项目\.worktrees\ar04a-context-journey-01` / `codex/ar04a-context-journey-01` |
| Base SHA | `48234e5dabb6ed28ea816b8ebc438288409353b8`（= R1 合并后 `origin/main`） |
| `PROJECT_NORTH_STAR.md` | 已实际读取全文；Blob `1f737712c7a36ceb34433ac09c3fbba3c3305542` |
| `AGENTS.md` | 已实际读取全文；Blob `32c45506cceeaa8c76a5c56bf8360ff476b58856` |
| `.agents/skills/opspilot-slice-review/SKILL.md` | 已实际读取；Blob `d405c8d413d633824b279202cc1503dab4cf0b03` |
| R1 裁决（继承） | `ACCEPT_WITH_LIMITS / MERGE_APPROVED`；merged main = `48234e5`；pytest 674 passed / 1 failed（保留的历史 C1 RED）；R1-INTERACTIVE `HOLD / NOT_RUN` |
| 本轮 Provider 调用 | 0（本文件仅规划；后续确定性测试亦为 0） |
| 本轮业务写入 | 0 |

## 1. 目的与服务对象

北极星第 1 优先是「用户确实获得智能的任务推进」，第 2 是 Context Engineering 等 Agent 工程能力。本切片针对一个**真实用户任务**：

> 用户先就回调协议提问、粘贴一段配置材料，再说「我现在要查这个订单」，
> 绑定可信订单后问「这个回调到底处理到哪了、202 算不算成功」，
> 随后正式纠正一个关键输入，最后追问「现在处理情况和下一步建议」。

现状（源码审计，见 `AUDIT.md`）：正式调查入口 `ASSISTANT_V1`（Web 默认路径）复用 `_prepare_context` 的来源选择，但

1. **不执行上下文压缩**：`_prepare_context` 判定 `needs_compression` 时，`prepare_chat_attempt` 返回 `CHAT_CONTEXT_COMPRESSION_REQUIRED`，`run_assistant` 直接返回错误，不落答复；
2. **丢弃摘要**：`assistant.py` 只把 `prepared["messages"]` 里的 user/assistant 转成初始消息，`HISTORICAL SESSION SUMMARY`（system 角色）被静默丢弃；
3. 压缩/摘要机制本身已在经典聊天路径完整实现（`context_summaries`、`context_summary_dependencies`、`context_compression_attempts`、失效传播）。

因此本切片不新建 Context 框架，而是**把既有压缩与摘要机制接进真实调查链路**，并证明用户目标在长会话中仍然保持。

## 2. 能力边界（不得被本切片改变）

- TaskBinding / TaskControl / Domain 授权与业务写入边界不变。
- 摘要与用户材料始终是**未信任历史**，不得成为 Evidence、授权或当前业务事实。
- 当前业务事实只来自本 Run 的 TaskBinding 作用域内 MCP 观察。
- 超预算仍超预算时必须 **fail-closed**，不得静默截断后给出成功答复。
- 既有 One-shot Provider 费用控制、合法自主工具选择与补查能力不变。

## 3. 冻结旅程（同一 Session）

| 步骤 | 用户输入（要点） | 期望系统行为 | 禁止 |
|---|---|---|---|
| J1 | 协议咨询：「HTTP 202 能否证明对方处理完成？」（无 Task） | 只读解释；引用已授权资料或明确资料缺口；不绑定、不写入 | 声称已诊断/已修复；把 202 当完成 |
| J2 | 粘贴一段配置/排查材料（用户材料，约 4–5k tokens） | 作为**未验证材料**使用；说明能/不能支持什么 | 把材料当业务事实或授权；把嵌入指令当策略 |
| J3 | 3–5 轮追问 + 无关历史 | 继续围绕目标回答；历史不无限膨胀 | 因历史变长而静默失败、丢目标或答非所问 |
| J4 | `POST /api/sessions/{sid}/assistant/order` 绑定订单 | 建 Task + TaskBinding + 正式 Run；绑定只来自可信 API | 由聊天文字创建绑定 |
| J5 | 「这个事件现在处理到哪了？」 | 调 `get_callback_delivery` / `get_receiver_processing`；区分 202 受理与 Receiver 状态 | 用历史 Event/订单快照推断当前；跨 Event 借用 |
| J6 | 正式纠正（`CORRECT_TASK_INPUT` + 提案确认） | 新 Run 携带已应用纠错；旧证据不得支撑新结论；逐字保留纠错原文 | 把聊天文字当正式纠错；静默替换 TaskBinding |
| J7 | 「现在处理情况和下一步建议？」 | 基于本 Run 当前观察回答；说明未知与下一步 | 声称完成/已交接/已修复；越权写入 |

## 4. Gold 判据（可执行断言）

- **G1 长会话不断裂**：J4/J5/J6/J7 的 Run 必须到达终态且 `SUCCEEDED`，用户能看到持久答复；不得出现停留在 `RUNNING`、无答复、或 `CHAT_CONTEXT_COMPRESSION_REQUIRED` 直接中止。
- **G2 压缩真实发生且可核验**：会话中出现至少一条 `context_summaries.state='CURRENT'` 记录，其 `context_compression_attempts` 为 `SUCCEEDED`，依赖行完整。
- **G3 摘要进入真实模型输入**（2026-11-04 实施前修订，见 §9）：至少一个正式 Run 的外发 wire 中出现 `HISTORICAL SESSION SUMMARY`，且其 `summary_id` 可在 `context_summaries` 中找到、currentness 校验通过；同时绑定轮与后续调查轮仍必须包含 J1 目标与 J2 材料（逐字或摘要）。原措辞要求“摘要出现在调查轮 wire”，与既有 Task 作用域隔离（Task-less 摘要不得进入 Task Run）冲突；修订后同时新增作用域隔离断言，安全性不降低。
- **G4 原始输入与正式纠错逐字保留**：`CREATE_TASK` 原文与最近一次 `CORRECT_TASK_INPUT` 必须以原文出现在模型输入中（锚点），不被摘要改写。
- **G5 当前事实只来自本 Run**：J5 之后的答复必须基于本 Run 的 `get_callback_delivery`/`get_receiver_processing` 观察；不得把历史 Event 或旧 202 当当前证据。
- **G6 失效不回流**：把摘要依赖的来源改成不再 current 后，下一次模型输入中不得再出现该摘要文本；排除原因可查。
- **G7 fail-closed 保留**：若压缩后仍超预算，必须以明确失败码结束且零 Provider 外发，不得静默截断成"成功"。
- **G8 越权与副作用为零**：整个旅程零业务写入；Approval/ActionIntent/Ledger/Handoff 计数不变；摘要不得提升任何证据权威。

## 5. 对照设计（同一旅程）

- **v1 / 现状**：`ASSISTANT_V1` 不压缩、丢摘要 → 期望 G1/G3 失败（RED）。
- **v2 / 本切片**：调查链路复用既有压缩与摘要 → 期望 G1–G4 通过。
- 两版本使用同一 Session 脚本、同一 FixtureModel 决策、同一 Domain 初态；仅压缩/摘要接线不同。
- 预算以 `OPSPILOT_CONTEXT_INPUT_BUDGET_TOKENS` 控制并在报告中如实标注（默认 12000）；对照双方使用同一预算。

## 6. 证据面

- `assistant_calls.request_json`（逐字外发 wire，assistant.py 记录）
- `context_summaries` / `context_summary_dependencies` / `context_compression_attempts`
- `chat_context_manifests` 与 `GET /api/runs/{run_id}/context`
- `assistant_calls` MCP 结果（本 Run 真实 MCP 调用）
- pytest 原始日志与 `RESULTS.json`（本目录 `runs/`）

## 7. 证据等级与限制（预先声明）

- 本轮为 **离线确定性 FixtureModel**，不是真实模型自主性证据。
- 真实收费 Provider 对照未获授权 → `NOT_RUN`；不得宣称真实模型增益。
- 浏览器体验 `NOT_RUN`（R1 STOP 继续有效）。
- 单次旅程、无统计显著性；只声明"该切片在该旅程上可用且安全"。

## 8. 停止线

一条长会话调查旅程实现并通过 G1–G8 后停止；不进入 AR-04B Memory、不进入 AR-05、不合并 main。

## 9. 变更控制

冻结后如需修改判据，必须记录：修改点、原因、对已跑结果的影响，并交主 Agent 裁决；不得为了让实现通过而回改 Gold。

| 日期 | 修改 | 原因 | 影响 |
|---|---|---|---|
| 2026-11-04 | G3 由“调查轮 wire 必含摘要”改为“任一正式 Run wire 含当前摘要 + 绑定轮/调查轮仍含目标与材料 + 作用域隔离断言” | 审计确认 Task 作用域隔离是既有安全设计：`_latest_current_summary` 只接受 `task_id` 精确匹配，Task-less 摘要不得进入 Task Run；强行改写会引入跨 Task 摘要复用风险 | 未降低安全要求；新增“摘要不得跨 Task 复用”的固定断言。已跑结果为此修订后重新测得 |

**J6 正式纠错的状态：** 本切片未完成端到端覆盖（确认纠错会创建 legacy Investigator Run，需要额外的 provider seam），在 `REPORT.md` 标记 `NOT_COVERED` 并列为下一小切片；G4 的“最近正式纠错逐字保留”因此在本轮只有代码与既有 M1/M4 测试证据支撑，未在本旅程内复验。
