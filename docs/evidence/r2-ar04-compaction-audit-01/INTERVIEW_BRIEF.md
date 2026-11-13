# 面试简报：如何审计 Agent 的上下文压缩

## 90 秒回答

我先把“压缩”拆成两个问题：什么时候触发，以及触发后究竟把什么交给模型。OpsPilot 当前 `HYBRID` 用 `F > E && H`：`F` 是分配优先级前的完整候选上下文估算，`E` 是输入预算扣除工具 Schema、系统提示、WORK_CONTEXT 和工具结果预留后的余额，`H` 表示最新 12 条历史之外仍有合格旧消息。超预算且有旧历史时才生成摘要。`ROLLING_SUMMARY` 只要有旧历史就主动生成结构化摘要；`RECENT_WINDOW` 不生成摘要，而是只选择最近 12 条历史。因此“裁掉旧消息”和“生成摘要”不是同一种机制。

我用隔离 Domain 和 Checkpoint、固定合成消息与确定性 Fixture Model 跑边界实验，不访问付费 Provider，也没有实时 MCP 调用。结果复现了 `HYBRID` 的单 Token 边界、`ROLLING_SUMMARY` 的主动压缩、`RECENT_WINDOW` 的零摘要调用、多批摘要的父摘要链接，以及工具 Schema 变大后可用预算下降。每个案例都保留了来源序号、Context Manifest、实际 Fixture Model 输入和预算估算；这些结果证明的是程序选择与持久化路径，不是自然语言记忆能力。

信息保持评测里，摘要带来源 ID，正式更正和被排除假设可以追溯；但早期 API 配置未进入摘要，协议 `max_attempts` 与部署版本被截断，摘要没有保留 `Receiver=QUEUED` 和 unresolved 项。最终请求仍包含一条完整长结果和最新用户状态，但这不能证明模型会基于摘要回忆早期材料；自然语言保真和回忆均标为 `NEEDS_LIVE_SEMANTIC_EVAL`。C06 的 `ROLLING_SUMMARY` 触发为 true，但在初始 `Loop.context()` 预检构造首批摘要材料时因 `6176 > 6000` 抛出内部预算错误；没有摘要尝试或模型调用，公开结果只有 `WORKER_RUN_FAILED`。这是 fail-closed 的错误可见性缺陷，最小修复候选是 `assistant.py` 预检边界仅映射该类型异常；本切片不修生产代码。

## 可复述的实验结论

- 默认预算：上下文窗 16,384；配置输入上限 12,000；输出预留 512；安全边距 1,024；压缩输入上限 6,000；摘要输出上限 512；近期历史窗口 12 条。
- 边界：`C03` 把有效预算设置为比 `F` 少 1 Token，`HYBRID` 触发一次摘要调用；`C04` 在有效预算明显高于 `F` 时仍由 `ROLLING_SUMMARY` 主动压缩；`C05` 的 `RECENT_WINDOW` 不生成摘要。
- 工具 Schema：配对用例加入一个未调用的只读假工具 Schema，预留量约增加 1.5K Token，有效预算随之下降并触发 `HYBRID`。
- 批次：`C07` 和 WP3 的最多两次摘要加一次回答遵守每 Run 三次模型尝试上限；第二次摘要携带父 Summary 引用。
- 边界失败：单条超长用户消息已触发 `ROLLING_SUMMARY`，但 source envelope + prompt 为 6,176 Token，超过 6,000 上限，首批构造失败且没有模型调用；超长助手历史可在摘要请求中做头尾截取并写明省略标记，原始助手消息仍保存在隔离 Domain。

## 证据边界

| 结论 | 证据等级 |
|---|---|
| 调用链、默认值、触发公式、摘要字段、失效检查 | 固定 Base 源码读取 |
| 触发边界、序号范围、预算和 Manifest | 离线 Fixture；实际 Domain SQLite、Context Manifest 与持久化 Request JSON |
| Fixture 实际收到的输入 | 离线 Fixture Model 捕获的消息数组；不等于真实 Provider 的线上请求或用量 |
| 摘要是否真实保留语义、早期事实回忆是否可靠 | `NEEDS_LIVE_SEMANTIC_EVAL`；本任务未使用真实模型作判断 |
| 原始行和撤销来源的回归 | AR-04A pytest Fixture/MockTransport 测试；不是生产数据或线上验收 |
| 行业实现 | 指定版本的固定源码静态阅读；未在 OpsPilot 中移植或基准运行 |

完整调用图、公式、场景表和失败记录见 `ALGORITHM.md`、`RESULTS.json`、`CONTEXT_BREAKDOWN.md` 与 `COMPARISON.md`。

## 验收候选自查

> **用户变化：** 无生产能力变化；本任务交付可复跑的压缩算法和信息丢失证据。
> **Agent 决策：** 未更改或声称提升模型自主决策。
> **观察驱动：** 单 Token 超预算、存在旧历史但未超预算、滚动策略以及 Schema 增大分别产生不同合法压缩/选择结果。
> **新增约束：** 没有生产硬约束变更；源失效和 fail-closed 由 Fixture/Mock 回归验证。
> **简化结果：** 不修改生产压缩策略；以三种既有策略对照，不增建 Memory/Context 服务。
> **证据与停止线：** 本地保存的 Fixture/Mock Trace、实际 Fixture 输入、14 项 AR-04A 回归；语义质量未用真实模型评测。提交 `ACCEPTANCE_CANDIDATE`，等待主 Agent 独立裁决。
