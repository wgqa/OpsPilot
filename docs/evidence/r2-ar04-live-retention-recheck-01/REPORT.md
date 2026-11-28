# R2-AR04-LIVE-RETENTION-RECHECK-01

**实施状态** `ACCEPTANCE_CANDIDATE`，待主 Agent 独立验收。

**真实执行** `STOPPED_AFTER_FIRST_SUMMARY_BEFORE_PERSISTENCE`。真实请求 1 次，回答请求 0 次。L3 为 `NOT_RUN`。

## 执行基线

| 核验 | 结果 |
|---|---|
| Repo 与分支 | `wgqa/OpsPilot` · `codex/r2-ar04-live-retention-recheck-01` |
| 任务 Base／实跑 HEAD | `e68fd3cd924dbad6bda69b9b9d02519ff0f3a3d7`／`0878683773e8bfef9c33f809be538b39df63fb66` |
| 北极星／AGENTS／Review Skill | 实跑前重读，Blob 分别为 `43dabda468506717c6956e676dfad4304c4f38e6`、`807b928686a4dd2cac7b15b3c354b9943c93c910`、`d405c8d413d633824b279202cc1503dab4cf0b03` |
| 生产压缩 | `opspilot/domain/chat.py` Blob `1bbdfc878009729c625df89330f3c7e42ddae280` |
| 授权与冻结合同 | 本轮用户回复“授权”，对应 Q02-A → Q02-B → Q06-B、6 摘要／3 回答、USD 0.06、零自动重试。合成历史、Gold、Runtime Grant、来源与停发条件沿用本任务卡和 PLAN |
| 证据范围 | 本次实际发包与持久 Trace，离线重放，实施方复核。主 Agent 独立复核待执行 |

[授权记录](EXECUTION_AUTHORIZATION.json)保存在首笔发送前。实际运行前再次核对官方模型和峰值无缓存费率，`deepseek-flash` 对应 `DeepSeek-V4.1-Flash-1017`，输入 USD 0.30/M、输出 USD 1.20/M。9 个槽位保守预留上界 USD 0.037935。Runtime Grant 在新临时数据库绑定，`live_run_01/PREFLIGHT.json` 记录了首笔发送前的复验。[官方定价](https://api-docs.deepseek.com/quick_start/pricing/) · [Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)

## 逐题对照

| Case | 上轮真实结果 | 本轮 L2 | 本轮 L3 |
|---|---|---|---|
| Q02-A · HYBRID | 最终输入缺 `/callback`，`SAFE_ABSTENTION` | 首轮真实摘要完整写出 `endpoint=/callback` 并引用 seq3。应用尝试状态为 FAILED，无持久摘要，未构造最终 Prompt | `NOT_RUN`，无回答 |
| Q02-B · ROLLING_SUMMARY | 最终输入缺 `/callback`，`SAFE_ABSTENTION` | `NOT_STARTED`，前一例触发停发 | `NOT_RUN` |
| Q06-B · ROLLING_SUMMARY | 最终输入缺协议及参数变更，`SAFE_ABSTENTION` | `NOT_STARTED`，前一例触发停发 | `NOT_RUN` |

上轮评分是原实施方初评。新一轮不存在可评分的最终回答。[逐例对照 JSON](live_run_01/COMPARISON.json)

## 本轮失败归因

**实跑证据**　唯一请求 Q02-A:SUMMARY:1 返回 HTTP 200、`finish_reason=stop` 和完整 Usage。模型首轮摘要有需要的端点和合法输入序列引用。Domain 记录 `FAILED / TaskControlError` 且 `summary_id=null`。缺少回答 Manifest 时，旧 Runner 的后处理最后记录 `KeyError`。Domain 记录只保留异常类名，实跑的具体 `TaskControlError.code` 和完整 Sequence→Message ID 映射未捕获。[实际 Trace](live_run_01/LIVE_REQUESTS.jsonl.gz) · [原 Runner 结果](live_run_01/LIVE_RESULTS.json)

**离线复现**　取这次真实首轮摘要原文，用三组确定性测试 Message ID 在当前生产函数中重放。文档结构和原始序列引用通过校验。转换为 Message ID 后，第一轮完整文档估算为 1040–1084 Token。两组紧凑后为 511、505 Token。另一组添加 `unresolved_items[2]` 之前已用 462 Token，最短候选仍把总量推到 515，触发 `CONTEXT_SUMMARY_FACT_RETENTION_BUDGET_EXCEEDED`。同样三组 ID 下，上轮 Q02-A 的首轮响应均可紧凑入预算。该路径可复现，且与实跑失败阶段一致。原始 ID 缺失使实跑的具体错误码仍为 `UNVERIFIED`。[重放证据](LIVE_AUDIT.json) · [复核脚本](verify_stopped_run.py)

**对照差异**　两次首轮请求的模型参数、系统指令及 seq1–16 选择范围一致。seq16 的长材料节选随运行而变，节选估算从 666 到 672 Token，另外该节选的 Message ID 不同。因此两次请求正文并非逐字节一致。当前官方文档还说明 `deepseek-flash` 非思考模式忽略提交的温度值。[逐项核对](LIVE_AUDIT.json) · [Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)

## 预算、停止与收口

- 实际 Provider Usage 为 **4,106 输入、481 输出、4,587 总 Token**，其中 Provider 报告 3,584 输入缓存命中。以峰值无缓存率按实际 Usage 保守估算 **USD 0.001809**，账户账单 `UNVERIFIED`。
- 其余 8 槽为 `NOT_SENT_FINAL`，请求结果未知为 0，未决预留为 0。实际跟踪到 MCP 尝试 0 次。Runner 退出码 1。只有这一轮真实执行。[费用账本](live_run_01/COST_LEDGER.json) · [命令与退出码](TEST_RUN_LIVE.txt)
- **关闭本次复测执行。** 真实回答改善还未得到验证，不能据此把 AR-04 的 L3 保真标为通过。建议将已定位的缺口单列为一个问题，用这份冻结响应和已复现的 512 Token 边界做最小回归，先补齐明确错误码与来源预算证据，再由主 Agent 决定是否值得局部修复。当前结果支持停止继续扩大本轮压缩实验。

## 六项验收说明

- **用户变化**　当前已证实首轮模型提取了目标事实，应用未能将其带到最终回答。
- **Agent 决策**　本轮只观测到真实模型的摘要输出。历史回忆答案未运行。
- **观察驱动**　同一真实响应离线重放时，来源 ID 的估算开销使持久化在边界附近出现不同结果。
- **新增约束**　复用 Runtime Grant、全局账本与异常停发，实际只发送一个槽位。
- **简化结果**　本次候选只增加授权、真实 Trace 与离线复核证据。
- **证据与停止线**　首笔真实请求已对账，三组离线复现已记录。保留原失败等待独立验收。
