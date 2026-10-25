# 源码学习地图与面试追问

## 用户目标如何贯通

`frontend/src/App.vue` 的同一任务消息、关键更正确认、补查卡片 → 原 FastAPI/TaskControl 受理 → 原 `run_investigation()` → S3 的 `investigate → execute → gate → next_step` → 有来源的用户答复。没有合并 Chat 与 Investigator，也没有第二套 Task 状态机。

## 一、事实不是执行计划

`domain/s3_history.py` 保存同一个 Event 的多次真实 HTTP Transport Attempt：Event 标识业务消息，Request 标识一次发送。每次请求/响应、序号、实际执行时间和 digest 不可变；`event_created_at` 与本次实际 POST 时间分别记录。`history_snapshot()` 在已授权绑定订单内有界读取，明确只覆盖已记录观察；没有记录不能证明没有发送。测试 Sender 不在 MCP/Web 工具列表。

`domain/s3_mcp.py` 只暴露历史读取；`domain/s3.py::current_s3_evidence()` 继续验证当前 Scope/Grant/Principal、版本、事实 digest、Run/Attempt/Observation 与 TTL。历史传输事实可以今天重新观察，但昨天的诊断不会因今天的 Run 复活。

## 二、一次观察驱动一次正常决策

`S3Nodes.model_call()` 保存整批候选，却只让第一个进入执行。`_reconsider_candidates()` 把其余候选及原 Call/Tool ID 保留到 Graph state；新 Observation、反馈与候选一起进入下次正常 Prompt。Agent 可改参数、放弃候选、继续读其他合法来源、澄清或回答；不增加每个候选的 Reviewer/Reflection 请求。候选是建议，不是自动执行队列。

`next_step()` 替换 S3 原 `after_gate()` 的混合终止职责：Domain 的 DIAGNOSED 表示诊断事实充分，不表示用户最新问题已回答。新问题不需跨多个模块添加特殊 Case 分支。S1/S2 路由与 Gate 未改。

## 三、Context 与结果的权威分离

Prompt 每次重读原 `investigation_context`，沿用 C1 的历史来源校验；先前回答有界进入当前上下文，但旧 Run Evidence 只作为历史线索。`domain/context_engineering.py::investigator_context_budget()` 是原 Investigator 的同一实现，移动后公开复用；原私有名称用 import alias 保持兼容。`model_io.py` 收纳原纯文本/脱敏小函数，S3 不再反向依赖 Investigator 的私有函数。

业务 Diagnosis 的正文仍要求真实模型来源及对应 Gate。新增窄表 `s3_run_answers` 只保存用户交付内容及来源，不授予 Handoff/Approval 资格；为必要的确定性降级保留可见答复。历史答复只在当前授权与同租户/Session/Task 的来源机制下读取。只读补查继续使用原 C1 结果表，绝不写正式 Diagnosis。

## 四、停止不是空白失败

有有效 final answer 时直接复用，并重新校验来源。模型未按格式完成、预算不足或 Provider 失败时，`s3_delivery.factual_partial()` 只汇总本轮可信事实和明确未知，标记 DETERMINISTIC_FALLBACK；不把它计为模型正常回答。S3 typed processing_claim 只能匹配同 Event 当前 Receiver，其他 Event 的 PROCESSED 不支持目标 Event 恢复。该校验不验证任意自然语言全部语义，不能宣称通用幻觉检测。

Task 的 MODEL/MCP 累计额度存于已有 execution budget 行；默认 8/6，隔离实验 12/8、16/10 只可在首次尝试前设置，重启和新 Run 不清零。重复查询可给模型反馈，但仍消耗正常 MODEL 额度，不通过递归上限制造无限调查。

## 五、实验与失败的学习点

先冻结、再 RED/GREEN；四个 P2/P3 留出未参与 Prompt 调优。真实实验发现：合法 fenced JSON 的解析缺口会造成额外模型调用；测试 Receiver 遗漏协议字段会使 Gate 正确拒绝正式诊断；SDK max_tokens 不能当作 Provider 实际账单上界。原始尝试与修复后的对照分开，不能只展示最后成功的一次。

补充两个真实接线教训：已应用纠错的高水位属于可信 TaskControl，新补查 Run 必须在原创建事务中继承，不能默认置零；否则安全校验会正确拒绝合法连续任务。原脱敏函数的 2000 字符是预览边界，不能先裁断合法结构化响应再解析。最终 S3 使用既有 20000 字符结果边界，S1/S2 默认不变；相关 RED 和真实 Web 失败均保留。

最终协议追问虽正确接续来源，但出现错误的“过 SLA 才能证明完成”限定。这是有真实来源仍可能发生的模型解释质量问题，Domain 未采信它为授权或业务事实；不能把来源可追溯等同于自然语言结论全部正确。

## 面试问答

1. **为什么不直接执行模型一次返回的所有工具？** 后面的候选基于旧观察，可能已无意义；串行观察回送给模型，同时保留候选来源，兼顾动态决策与审计。
2. **DIAGNOSED 为什么还要继续？** Gate 只判断正式业务证据是否充分，用户可能问的是旧 Event 时间线或协议依据；这属于用户目标履约。
3. **同订单已处理能证明旧 Event 吗？** 不能。必须关联 Event、Transport Request、订单/协议版本及本轮 Receiver 证据；E2 不替 E1 背书。
4. **怎么避免预算耗尽后白屏？** 用当时有效的可信事实形成明确部分答复，保存与展示，但不伪装模型完成或业务恢复。
5. **为什么还需要不可变历史和新 Observation？** 同一事实可重复观察，但历史时间线不应被更新覆盖；当前性由本轮成功工具观察和权限/版本共同决定。
6. **Memory/Knowledge 能授权吗？** 不能，它们只提供方法、协议线索；当前事实、预算和业务权限仍由 Domain/执行层控制。
7. **A 一定胜过规则吗？** 不预设。R 在固定已知问题上可能更便宜，H 也可能误判调查焦点；分别报告履约、来源、失败、Token、延迟和降级。
8. **这次简化了什么，没做什么？** S3 的结束逻辑与 Gate 解耦，共享纯函数不再私有反向调用；没有 Planner、Goal Manager、多 Agent、通用 Runtime 或新写能力。
