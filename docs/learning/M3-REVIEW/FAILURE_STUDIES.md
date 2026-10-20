# 从失败读懂 Context 与恢复边界

下列历史案例与本轮新鲜实验分开。完整尝试、原始日志和身份见 `docs/evidence/vnext/m3-hf-02/FAILURES.md` 与 TRACE。

## 1. 历史：摘要被挤出、正式纠错丢失

M3-02/03 与 CLOSEOUT 的历史材料记录过摘要优先级和正式纠错锚点的问题。风险不是“回答变短”，而是后续模型失去用户约束，重复旧调查或误用旧事实。现有实现保留初始/最新正式输入、提高有效 Summary 优先级，并对必须块 fit-or-fail-closed。

这是历史修复的源码解释，**不是本轮重跑了旧浏览器实验**。本轮完整 227 项回归包含这些既有约束；新鲜真实 HTTP 测量另列，不拼接历史 PASS。

## 2. 历史：Provider 观察挂错客户端

应用构造 Prompt、保存 Manifest，甚至配置了某个 httpx hook，都不证明原 SDK 用它发送。CLOSEOUT 原失败保留 PARTIAL。本轮确认 SDK 使用 httpx2，先用非敏感固定标记证明真实请求与返回，再跑业务。证据保存 body digest、角色/长度、资产投影和一致性比较，不保存完整 Prompt。

教训：先独立验证观测工具，再跑昂贵业务。日志数量不是覆盖率；必须给出明确的观察层与不能证明的部分。

## 3. 新鲜：崩溃时模型响应与费用未知

A 阶段在真实 MCP + Checkpoint 后杀死隔离 API 进程，实际模型请求已经被 hook 看见，但没有取得完整 SDK 返回。恢复保留同一 Run、原预算与 Checkpoint，新的请求不加载撤销资产。

旧 Attempt 仍 RESERVED，不能按零 Token 算，也不能从 HTTP 请求已发出推断 Provider 已完成。这个 UNKNOWN 不等于业务重复：业务提交有独立 Intent/Ledger。测试目标是可恢复且不重置安全边界，不是消除所有外部 I/O 不确定性。

## 4. 新鲜：第一轮 B 压缩碰到 Evidence TTL

冻结八个 ACTIVE 轮次、3600 输入预算，真实 Memory 已影响第一条回答。第一份真实 Summary 只压缩两个用户消息，不含目标助手依赖，因此不能算目标链完成。后续压缩实际源材料包含依赖 Memory 的助手，却在模型返回前后跨越当前 Probe 的 300 秒 TTL。

提交函数重新计算有效来源并抛出 TaskControlError，没有提交目标 Summary。日志只持久异常类，精确错误码未记录；“来源过期后原压缩不再需要”是由时间与重新计算路径支持的解释，不能把推断写成当时捕获的异常文本。该次模型 HTTP200 可确认，响应 ID/Usage 未提交，成本未知。

系统随后用有效来源回答并达到有界停止。不能因为八个 Chat Run 都 SUCCEEDED 就把 Memory→Summary 实验判 PASS，也不能把仍有效的用户来源 Summary 在撤销后保留说成撤销失败。

## 5. 新鲜 P1：派生回答洗掉了来源依赖

最小路径：Memory ACTIVE → A 回答有直接 Memory 来源 → 预算裁掉 Memory 块但保留 A → B 回答只保存 A 的 MODEL_ATTEMPT → 撤销 Memory → C Context 仍选 B。

RED01 保留一个测试准备失败及 Semantic 真实失败；修正测试准备后 RED02 两种资产都在“B 应被排除”断言失败。这里使用明确标注的确定性测试 Provider，不冒充真实业务。

根因：MODEL_ATTEMPT 只检查完成状态和 response digest，没有验证对应助手的传递来源。最小修复沿租户/Session/Task 范围查 chat_run_answers，递归调用原验证、加环保护和单次局部 cache。RED02→GREEN 26/26，完整 227/227。一次预先冻结的真实修复后对照另存 P1 前缀，实际能证明到哪一层见 SUMMARY_LINEAGE，不用单测替代真实 DAG。

## 6. 新鲜：否定措辞被安全守卫保守误拒

来源准备输入“不自行修复或授予Scope”触发 S1_SCOPE_CHANGE_UNSUPPORTED。原 Task 的正式澄清又被旧输入中的词影响。源码 `_requires_scope_clarification()` 扫描多条输入，授予 Scope 属变更词，但否定词白名单没覆盖该表达。

没有越权，属于 P2 产品体验问题；本轮不扩范围修自然语言守卫。改用已经调查完成、另经真实独立审批的案例作为来源，并把这个更换写入预先提交的实验身份协议。两个失败 Run、0 Provider/MCP 与审批前置失败都保留。

## 7. 历史 Worker 两次重试耗尽：根因未证明

现有记录只有 WORKER_RETRY_EXHAUSTED、retry_count=3、0 Attempt/Observation，缺原异常类/堆栈。当前有限注入 RuntimeError 可走三次 recoverable retry 后阻断，STALE TaskControl 则立即阻断，2/2 通过。注入直接驱动真实 wrapper/Domain，不声称测了实际退避墙钟或整个 Scheduler。

不能把“注入也得到相同终态”当历史根因。`_prompt_messages()` 发生在某些 Attempt 登记之前，MCP 初始化也早于 tools/call，所以零计数不能排除 M3 关联。结论保留 ROOT_CAUSE_NOT_PROVEN，未改生产 Worker。

## 8. 怎样向评审解释失败

先指出可直接证实的事实，再列最小原因假设、缺失证据、改动边界和新鲜复验。把未知成本、准备错误、工具超时、真实业务失败分别计数。不要把全部异常称为模型问题，也不要为了全绿修改语义或追加无限轮次。
