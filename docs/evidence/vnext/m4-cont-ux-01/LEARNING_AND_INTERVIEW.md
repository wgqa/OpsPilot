# 连续调查 · 源码学习与面试材料

本阶段基于源码与历史原件复盘，没有新业务实现或效果实验。沿用仓库 Handbook 联学方向，但本轮没有重新通读外部 Handbook 全文；下表是可核对的原理与项目映射，不把章节名当实现证据。

| 主题 | 原理 / 源码入口 | 已理解/复现 | 已接入实际业务 | 已证明效果 / 限制 |
|---|---|---|---|---|
| Context Engineering | `investigation_context.py::load_prior_readonly_followups`；`chat.py::_current_evidence/_prepare_context`；`S3Nodes.prompt/model_call` | 历史最多 3 条、每答 1,600 字符，有来源状态；摘要是有损派生，不能提升权威 | 分类器/Chat/Investigator 共用历史装配；EG-HF 重验同 Run 当前部分观察 | C1 真代词追问已可续接；最新部分事实修复只有确定性出站验证，未证明本轮真实三问自然语言效果；长摘要来源链不在本切片补建 |
| LangGraph / Domain | `investigator.py::run_investigation`；`task_control.py::claim_task_run/resume_task_run`；M1-HF HF07/08 | 新用户 Run 是新执行生命周期；崩溃恢复是同 Run 同 checkpoint/控制快照 | Run-specific `thread_id::run_id`、Domain revision/high-water 和首次 checkpoint 前恢复已有实现 | 旧跨进程原件可查；新 budget policy 与这些窗口兼容尚待实施/验证。Checkpoint 不授予业务写权限 |
| Agent Budget | `d2.py::reserve_attempt/attempt_counts`；`execution_budget.py`；分类/Chat reservation | 全部预留含失败占额度；请求预算、Token 窗口和活跃时限不同 | Task 8/6 跨 Run 累计已在真实旅程发生；辅助模型另表记账 | 真实饥饿/空 PARTIAL 已复盘；两级 24/18、Run 4/3、辅助 8 仅是候选，收益未证明 |
| Evaluation | `S3Nodes.report`；`s3_delivery.py::supported_response/factual_partial`；C1 result storage | Run SUCCEEDED 只表示执行结束，ANSWERED 可能只是模型/解析标签 | 已存 Run、用户答复、正式 Diagnosis 与 Handoff 分开 | HF 最后一问 Run SUCCEEDED 但正文 0；VS16配置耗尽仍 PARTIAL。新完整目标指标尚未执行 |
| UI projection | `App.vue::displayMessages` 及三个渲染循环；`web/app.py::get_messages` | 存储/事件权威与用户时间线是两层 | 当前答案均可持久回读 | 真实刷新原件存在错位；新统一派生投影尚未接入，不能声称改善已验证 |

## 五组面试问答

### 1. 跨轮对话为什么不能直接拼全部历史？

**30 秒：** 历史回答能解决“刚才那份”的指代，但里面的业务事实可能过期。OpsPilot 用同 Task/Session 的持久答案和来源 ID 续接，Knowledge 重新验版本/digest，旧 Run Evidence 永远标历史；当前问题要用当前 Run Observation。

**2 分钟展开：** 从 `load_prior_readonly_followups()` 看来源装配，再到 S3 实际出站与 Chat Manifest。用 C1 代词解释成功作正例，EG-HF Gate 子集误当上下文全集导致 202 丢失作反例。选择相关信息、控制窗口、重验权威是不同职责；不能靠整个数据库入 Prompt 或额外 Memory 层补洞。

**追问：** 摘要中含被撤销来源怎么办？答：重验其依赖并排除派生历史；不因摘要是系统生成就信任。当前切片不宣称重做长对话压缩效果。

### 2. 新 Run 和恢复 Run 的区别如何落到代码？

**30 秒：** 新 Run 由可信新 Command/Message 受理；恢复复用同 run_id、控制版本、高水位、Attempt 与 checkpoint。不能让 Worker 重启伪装成新用户请求来获得额度。

**2 分钟展开：** 看 TaskControl 事务的 operation 幂等与 C1 source_message_id 唯一关联；再看 `thread_id::run_id`。M1-HF 首 checkpoint 前恢复必须先证实 Domain 没有冲突业务进展；正式纠错已应用也不能重复 apply。已有 Intent/Ledger 永远按业务身份对账，不由 checkpoint 推断重做。

**追问：** Checkpoint 落后于 MCP 观察怎么办？答：复用已持久的同 Run 成功 Observation；不重复取证或清空累计预算。

### 3. 为什么提高 Task 额度还不足以解决连续体验？

**30 秒：** 只提高总额仍可能被第一轮吃光。历史 16 次模型例仍以 PARTIAL 结束。候选设计保留 Task 总限额，同时给每个可信新 Follow-up 小窗口；恢复沿用原窗口，辅助模型另计。

**2 分钟展开：** 用 HF 初始4、协议3、当前查询1=8 的真实账本说明饥饿；用 VS 初始4+纠错4后新问0调用说明新消息不等于新额度。再解释两级计数如何沿用同一 SQLite Attempt 事务，以及过小 Run cap 会误伤合法复合调查，必须有正例和未知事项交付。

**追问：** 失败为什么还扣次数？答：可能已发送并产生费用；RESERVED/未知状态不退款，真正重试预留新 Attempt，审计能说明每一次。

### 4. Run=SUCCEEDED 为什么不是成功率？

**30 秒：** 它只代表运行结束。用户是否得到了所问的答案、证据是否同 Event 当前、是否有真实业务回执，要分别判断。空 PARTIAL 不能算用户成功；正确 UNKNOWN 可以是安全且正确的处理，但不是完整目标达成。

**2 分钟展开：** 对照 HF 最后一问 SUCCEEDED/正文0，VS旧错误 SLA 解释，以及 S1 必须真实HTTP200+订单字段、S2/S3 交接必须 Receipt 的差别。评测分别报目标完成、正确处理、事实正确、安全、费用，按每轮目标评分而非 parser 标签。

**追问：** 所有 UNKNOWN 都算对吗？答：当前合法工具能查且还有额度却没查是产品失败；工具能力确实不足且明确来源/缺口才是正确部分处理。

### 5. 时间线为什么应做读取投影？

**30 秒：** Message、Run 和答案已经持久，UI 应用真实 ID/时间组合显示，避免再建一套业务状态。当前按类型分段导致早答晚放，按最近用户猜来源也有并发风险。

**2 分钟展开：** 看 VS Web-03 刷新文本与 `App.vue` 三个循环。新投影按持久时间排序，答案显式关联 source_message_id，SSE按event_seq去重，流式暂存用run_id交接到最终正文。Chat 关联缺字段时用既有 `chat_run_answers` 只读 JOIN 增补，不修改 Domain 事实。

**追问：** 同样文字的两次问题要折叠吗？答：不要按正文去重；两个 operation 是两个意图。只合并同一持久答案或同一纠错提议链的重复呈现。
