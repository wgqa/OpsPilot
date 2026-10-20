# Agent Engineering 面试追问：用源码和证据作答

这些答案对应当前本地 Demo。真实运行结果见本轮 REPORT；没有把 Memory 提升收益、未知 Worker 根因或企业 IAM 当成已证明。

### 1. 为什么普通聊天不直接推进业务 Graph？

用户追问可能只需解释。`web/worker._dispatch_run()` 把 CHAT_READONLY 与调查/审批恢复分流；Chat 读 Domain，不能写 Plan/Approval/Intent。否则一句“好的”可能错误获得修复资格。正式纠错通过 `admit_task_message()` 提升控制版本，才会开新的调查 Run。

### 2. 什么才证明 S1 修复，而不是模型说修好了？

同绑定 service/integration/principal/route 的真实 HTTP 200、订单字段、版本，以及 COMMITTED REPAIR Ledger、VerificationReceipt、冻结报告和独立 DELIVER。源案例 Memory 的 HTTP200 属历史，不属于新 Task。查 TRACE 的这些回执比读模型回答更可靠。

### 3. 为什么 Memory 候选还要 APPROVER？

提取输入可能有不可信外部文字，成功案例也可能不适用。Domain 从可信回执建立候选，由独立角色确认，检索仍核对租户/项目、状态、版本、过期和来源。确认只批准作为历史方法提示，不赋予目标 Task 执行动作许可。

### 4. 为什么不直接用向量库？

当前有限案例和项目范围可由 SQLite 确定检索，关键问题是来源、当前性和撤销传播。向量相似度不能证明有效权限或业务事实，反而增加同步/失效面。本轮没有可证明的召回瓶颈，因此不引入向量平台。

### 5. Hybrid 是否已经证明比最近窗口更好？

没有这种普遍结论。Hybrid 用可信必选块、摘要、近期历史与可选资产控制成本和遗忘，工程行为有测试；本轮专门测来源失效。固定预算真实实验仍有 TTL/依赖未形成的失败。提升任务成功率需要另外冻结公平对照，不能凭更多 Token 下结论。

### 6. 3600 Token 是 Provider 的硬限制吗？

是应用用 cl100k_base 算的输入预算。Provider 的分词和额外消息开销不同，Usage 必须单独保存。`context_budget_for_model()` 也明确默认窗口不是厂商规格；不能把本地估算当账单精确值。

### 7. 可选 Memory 被裁掉后还有风险吗？

有。当前历史回答可能是在 Memory 有效时产生的，即使没有直接 Memory 块，后续模型仍会读到改写的方法。本轮 P1 就是 B 回答只引用 A 的 MODEL_ATTEMPT。修复后 `_message_source_valid()` 沿祖先 AssistantMessage 递归校验来源。

### 8. 为什么不能只搜索 Memory ID 判断撤销？

ID 不出现不代表方法没进入文本，ID 出现在排除审计也不代表有效注入。需要结构化 selected/excluded 集合、内容 digest、版本、来源 DAG 和真实请求消息角色/正文摘要共同核对。本轮 hook 还直接比较资产经验字段与 Domain 的选定版本。

### 9. Summary 表里 ACTIVE 就能直接加载吗？

不能。`_summary_is_current()` 检查消息、模型、Evidence、Memory、TaskState、父摘要等依赖；源失效要递归排除。父摘要 superseded 可作为特定 digest 的历史祖先，但不是无条件当前资产。环保护避免坏依赖反复递归。

### 10. 如何保证 Summary 没把历史修复写成当前成功？

压缩 prompt 和结构约束区分历史/当前，持久依赖可追溯，后续模型还有可信任务状态。仍需实际摘要内容和后续请求检查；程序 Schema 不能证明所有语义都正确。没有当前 Ledger/验证回执，模型文字始终不能产生成功状态。

### 11. 模型压缩成功但来源刚过期怎么办？

`complete_chat_compression_attempt()` 再计算来源后才提交，可能拒绝这次结果并重新构建有效 Context。本轮有真实 HTTP200 但 Domain 提交失败的实例。不能把这次当持久 Summary，也不能在没有保存 Usage 时按零成本统计。

### 12. PromptManifest 与实际 HTTP 请求差在哪？

Manifest 描述应用准备了什么；SDK 可能再序列化或走另一个传输客户端。本轮在原 httpx2 request hook、序列化后和 send 前捕获 body，在内存核对后只导出安全投影。旧挂错 httpx 的记录仍保留 PARTIAL。

### 13. hook 会改变模型行为吗？

验收 hook 不改 body、参数、Tool Schema、timeout 或 retry；保存原 body hash 验证。它增加少量观察耗时，隔离于生产入口，不能证明完全零扰动，也不能证明 Provider 内部一定使用每一条文本。

### 14. 崩溃后为什么有 UNKNOWN Attempt？

本地登记并发送请求后、持久返回前崩溃，外部 Provider 可能已经处理。恢复不能凭空补响应或 Usage，也不能清预算。保留原 Attempt，使用新受限尝试继续，统计已知 Token 为下界且另列未知请求数。

### 15. 业务动作如何避免重复，和模型请求有什么不同？

业务动作先持久 Intent，Domain 同一事务检查 Plan/审批/控制版本，再 CAS/追加 Ledger，重复回查同身份回执。模型调用在外部网络，不具有同一事务，不能声称 exactly-once。Checkpoint 只管进度，两类保证不混算。

### 16. 重启会不会重新注入撤销经验？

每次构建 Prompt 都重新查 SQLite 当前资产与依赖，Checkpoint 不保存可直接复用的旧经验正文。A 的同 Run、两进程实际请求均排除旧资产；摘要跨进程还需对应真实 Summary DAG 的额外证据，不能只用直接 Memory 测试推断。

### 17. 零模型/MCP 调用为何仍可能与 Context 有关？

`_prompt_messages()` 和部分初始化发生在 Attempt 登记前，MCP tools/list 也不同于 tools/call。历史只有汇总零值和重试耗尽时，无法定位原异常。当前注入只能证明错误分类，结论 ROOT_CAUSE_NOT_PROVEN 比猜一个修复诚实。

### 18. 发现问题为什么不顺手重构？

本轮约束只允许直接阻塞的 P0/P1 最小修复。派生来源问题有两类确定性 RED 才改 35 行；Scope 否定误拒、异常元数据丢失和性能机会都进审计清单。扩大改动会让旧可靠性工程失去可定位回归边界。

### 19. 什么测试算真实端到端？

新鲜 Browser/Web 操作、真实 Provider/MCP、可信 Domain 和实际 HTTP 业务回执按身份联接。确定性 Provider 单测、API 验收、浏览器点击必须明确区分。API 驱动后浏览器展示真实持久内容，不应称为人工点击全部流程。

### 20. 如何公平表达 Memory 的价值？

把方法迁移正确、当前事实不被历史污染、成本与失败分开统计。ON/OFF 同样的合法环境、预算和 Gold，保留所有尝试。本轮没有重跑公平消融，不声称提升，也不要求动态 Agent 胜过合理规则；交付的是可核对的跨 Task 使用与来源治理边界。
