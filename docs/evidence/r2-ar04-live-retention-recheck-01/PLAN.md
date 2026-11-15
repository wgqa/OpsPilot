# R2-AR04-LIVE-RETENTION-RECHECK-01

**实施状态** `ACCEPTANCE_CANDIDATE`，范围为零付费预检。

**执行状态** `AWAITING_NEW_LIVE_PROVIDER_AUTHORIZATION`。

**当前实际用量** Provider 0 次，外部 MCP 0 次，费用 USD 0。

## 任务判断

三个 Case 对应上轮因输入缺失而弃答的目标问题。复测能区分应用是否把必要事实送进最终 Prompt，以及模型是否据此答对。建议只跑一轮，然后基于结果决定 AR-04 压缩专项是否收口。

## 开工核验

| 项目 | 核验结果 |
|---|---|
| Repo | `wgqa/OpsPilot` |
| 分支 | `codex/r2-ar04-live-retention-recheck-01`，复用 `ar04a-context-journey-01` |
| 冻结 Base | `e68fd3cd924dbad6bda69b9b9d02519ff0f3a3d7`，开工 HEAD 与远端 HF-02 同为此提交 |
| 远端 main | 开工时为 `60eee87bfe3cca522011316cb4cd2c0064ad291b` |
| 北极星 | 已读取 Base 文件，Blob `43dabda468506717c6956e676dfad4304c4f38e6` |
| AGENTS | 已读取 Base 文件，Blob `807b928686a4dd2cac7b15b3c354b9943c93c910` |
| 评审 Skill | 已读取 Base 文件，Blob `d405c8d413d633824b279202cc1503dab4cf0b03` |
| 生产压缩 | `opspilot/domain/chat.py` Blob `1bbdfc878009729c625df89330f3c7e42ddae280`。Runner 核对导入的文件路径与此 Blob |
| 冻结合同 | v1.0 §5 来源不变量、Runtime Grant 与 Setup-HF01、Phase A 问题／Gold／29 条历史、旧 ABC 请求及评分、HF-02 已验证边界 |
| 遗留门禁 | 阅读 M2-01/M2-02 Deferred Gates。只读会话、来源有效性及授权边界适用。HF-02 记录的 F01 旧测试断言另行处置。独立验收待主 Agent |

## 拟议真实复测配置

| 顺序 | 策略 | 要检查的历史事实 |
|---|---|---|
| Q02-A | HYBRID | seq3 最早的 `/callback` |
| Q02-B | ROLLING_SUMMARY | 同一来源与问题 |
| Q06-B | ROLLING_SUMMARY | seq11 的 `v1.2 → v1.3` 和 `max_attempts 3 → 5`，同时核查是否错误推断部署版本 |

继续用旧 ABC 的同一问题全文、Gold、人工评分类别、合成历史和回答 Tool Schema。每个 Case 创建新的临时 Domain、Checkpoint、Session 和绑定 Grant。三个 Case 共用一个持久预算账本，共 9 个一次性请求槽位，每例最多 2 次摘要和 1 次回答。摘要无工具，回答用 `tool_choice=none`。Runner 会核对历史和实际工具 Schema，也会核对实际出站模型、参数与 Prompt 前缀。

2026-11-15 核对官方 Chat Completions。旧请求和本轮拟议请求均用 `deepseek-flash`、`thinking.type=disabled`、`temperature=0`、非流式、512 输出 Token 上限。官方模型页将别名映射为 `DeepSeek-V4.1-Flash-1017`。当前非思考模式文档注明服务端温度固定为 1.0，提交的温度值会被忽略。实验能对照请求参数，无法凭别名证明权重未变化或回答可确定地复现。[模型与价格](https://api-docs.deepseek.com/quick_start/pricing/) · [Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)

以 12,000 输入／512 输出 Token、峰值无缓存输入 USD 0.30/M、输出 USD 1.20/M 预留，每次向上取整为 USD 0.004215。9 次共 USD 0.037935，低于拟议全局硬上限 USD 0.06。每例叠加既有 Runtime Grant 预留，三个 Grant 分别最多 USD 0.012645。模型调用零自动重试。实际用量按响应 Usage 另报，费用按保守费率由本地账本估算。

本轮从主仓库 `.env` 读取配置，只输出存在布尔值。临时预检 Grant 通过绑定及数据库身份校验，模型客户端由禁止发送的 MockTransport 构造。真实配置、官方版本、价格、有效 Grant 与预算在付费执行前再核对。用户需明确授权本任务的三个 Case；上轮已用完的 21 次授权不参与本轮。

## 如何看结果

1. **L2** 依次核对首轮模型摘要、首轮持久摘要、第二轮实际 `previous_summary`、第二轮模型输出、最终 Prompt 与当前持久版本。报告引用的正文和源序列。关键数字、变化方向或来源缺失时标出部分信息，文本匹配结果单独保留给人工复核。
2. **L3** 用原问题和原评分规则逐题核对实际回答。保留 `CORRECT_SUPPORTED`、`CORRECT_UNSUPPORTED`、`SAFE_ABSTENTION`、`INCORRECT_OR_UNSAFE` 及各异常状态。词面猜中但 Prompt 缺少依据时标明无支持。证据不足时承认未知是安全弃答。实际自然语言语义判断由实施方初评与主 Agent 独立复核分别记录。
3. **失败归因** 找到必要事实首次失去正文或来源的环节，再判断是否是模型再次遗漏、回答错误或合理弃答。运行异常、来源失效、异常工具请求和预算问题停止后续发送。保存发送的完整脱敏 Trace、账本、返回 ID 与失败。未知发送保留预留。

## 六项切片判断

- **用户变化** 本轮证明复测路径可用，修复后用户能否得到有依据的历史答案由三次真实回答验证。
- **Agent 决策** 在历史回忆 Track，模型可依据现有内容回答或承认未知。
- **观察驱动** 最终输入有完整来源时可以回答。必要正文缺失时，保留合理弃答及具体丢失环节。
- **约束** 满足授权、来源、工具与预算的三例通过 Mock。在 Mock 中测试旧授权、预算不足、超时 UNKNOWN 和来源失效拒绝后续发送。
- **责任归属** 使用原 ABC Runner、正式 Assistant/Runtime Grant 和当前生产压缩函数。新增代码只冻结本轮矩阵、检查实验边界和记录证据。
- **停止线** 本轮零费用预检止于可审阅候选。获授权后的复测最多三例，三例结束或触发停止条件后，根据 Trace 给出关闭专项或定位具体未解决缺陷的建议。
