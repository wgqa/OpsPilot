# AR-04B-MEMORY-JOURNEY-01 — 交付报告

状态：ACCEPTANCE_CANDIDATE。实施方未签 PASS。

## 用户现在得到什么

正式离线 Assistant 路径可以把经候选/可信确认的项目 Semantic Memory 或从已核验同任务诊断建立的 Episodic method Memory 放进模型处理器实际消息。新 Task 仍通过可信 TaskBinding 和当前合法 MCP Observation 调查。J6 补充用例证明同一 Session/Task 的后续问题保留上一轮实际答复作历史线索，同时重新查询当前同 Event Receiver，交付 QUEUED、不能宣称处理完成、草稿未提交的回答。

以上是 Fixture Model 下的正式链路行为。真实 DeepSeek 调用为 0，不能据此宣称真实用户模型质量提高。

## 实施与测试

- 修复 Memory 仅在 Manifest 可见、未进入模型消息的问题。
- 发送前、checkpoint 续跑前和最终答案事务提交前复核来源；相同 Memory ID/Digest 不能掩盖指导正文被篡改。
- 当前 Delivery HTTP 202/ACKNOWLEDGED 与 Receiver QUEUED/PROCESSED 来自本 Run 的本地授权 MCP/Domain 结果；Memory 不成为业务 Evidence。
- AR-04B 定向测试 9/9 通过；M3/D5 回归 28/28、Assistant/TaskControl 回归 14/14 通过。
- AR-04A Context/取消回归为 7/8，唯一失败记录在 FAILURES.md。没有运行全量 pytest。
- 真实 Provider、浏览器、费用和外部业务写入均为 0。
- 见 RESULTS.json、TRACE.jsonl 和 runs/ 原始日志/脱敏 JSON Trace。代码实现提交为 bdf696fb6189199123c2c87b32614d745a2f604f；最终候选完整 SHA 在分支 HEAD 与交付消息中核验。

## 六问与双向限制验收

1. **用户多完成什么？** 新 Task 和同 Task 连续追问可引用已确认的方法/项目约定，而不要求用户重说；当前事实仍由新 Run 查询。
2. **哪些决定由 Agent 作出？** 正式接口仍让模型选择合法工具与停止时机；本轮是确定性 Fixture Model，不证明真实模型自主决策。
3. **什么观察改变行动？** 同 Event 当前 Receiver 为 QUEUED 或 PROCESSED 时结论不同；Memory 撤销导致不外发或不提交答案；有效未撤销的 Memory 和正常调查仍可继续。
4. **新限制保护什么，合法路径是否保留？** 提交时要求 Manifest、模型输入和当前 Memory 来源一致，防止伪造“使用过 Memory”或失效后提交答案。正例证明有效 Memory 可发送、Tenant B 仍查自己的订单，撤销后 ON/OFF 可继续但不带旧记忆。
5. **有什么简化？** 复用 _prepare_context、现有 Memory 校验、assistant_calls 与答案事务；抽出可在同一事务调用的校验函数，不新增存储或状态平台。
6. **证据到哪、何处停止？** RED→GREEN、E1–E6、J6 与适用回归完成到离线层；真实 Provider、浏览器和全量 pytest 未运行。停止在候选提交，交主 Agent 独立验收。

## Gold 与能力等级

- **Level 1 — 接线：** 离线证明 Memory 已进入模型处理器输入，并可与 Manifest 对照；不是实际 Provider HTTP 证据。
- **Level 2 — 合理决策：** Fixture 展示当前事实区分 QUEUED/PROCESSED 和 Memory 非权威边界；真实 LLM 未验证。
- **Level 3 — 可重复实际收益：** 未证明。各 ON/OFF Fixture 输出和工具路径一致，没有测出质量改善。

G1/G3/G4/G6/G7/G8/G10 有离线正反证据。G2 仅通过 Fixture Model handler 输入验证。G5 只证明接口没有规定工具顺序；自主性未证实。G9 验证 Memory 估算并计入既有 12,000 Token 预算，正常上下文与相关回归通过；没有专门的超限 Memory 样本。

## Context Engineering 与面试说明

- **Context 与长期 Memory 不同。** Context 是本 Run 实际送入模型的临时输入；Memory 是有来源、版本、Digest 和生命周期的长期参考。入口是 chat._prepare_context 与 assistant.Loop.context；测试核对模型处理器输入和 Context budget。
- **Episodic 与 Semantic 不同。** Episodic Memory 从核验过的历史业务结果提炼调查方法；Semantic Memory 保存经授权确认的项目约定。来源分别沿 episodic_memory 生命周期和 semantic_memory 候选/确认流，两者都不能替代当前事实。
- **为什么需要来源、版本、有效期、撤销。** 引用可能来自旧版本、撤销源或错误租户；相关证明包括跨 Tenant 正反例、M3/D5 版本/来源回归及发送前、续跑、答案提交竞态。
- **为什么是方法而非 Evidence。** 当前状态由本 Run 的 TaskBinding-scoped MCP Observation 取得。E2/E3 在同一历史经验下仍分别读取当前 QUEUED/PROCESSED。实现和证据在 tests/test_ar04b_memory_journey_01.py 与 runs/ 中。
- **Memory 如何影响模型调用。** Loop.context 从有预算的 _prepare_context 结果提取 guidance；awrap_model_call 将它放进本次 SystemMessage；assistant_calls.request_json 保存序列化 messages、Manifest refs 和预算。G3 RED 证明只写 Manifest 不够。
- **ON/OFF 如何区分接线与收益。** ON 有 Memory、OFF 没有，证明接线；只有结果、工具选择或成本出现可复核改善才证明收益。本轮 Fixture 两边结果相同，Level 3 不成立。
- **为什么复用 LangChain/LangGraph 与 Domain。** 项目已有统一 Assistant 模型/MCP/Checkpoint 和 Domain 来源事务；本任务修复的是 Context 到现有模型调用的断点。替换为 Pi/Ragent 会引入额外架构变量，无法隔离 Memory 接线效果。本轮没有给这些框架做性能排名。

## 停止线

离线候选和必要回归已完成；不运行真实 DeepSeek，不合并 main，不进入 AR-05/R2。由主 Agent 独立检查 Diff、Gold、Trace 和日志后裁决。
