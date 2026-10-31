# AR-02-LIVE-01 P0 Provider 预检

**状态：** `P0_FREE_CHECKED / P1_NOT_AUTHORIZED`

**核验日期：** 2026-11-01
**目标：** 只完成无网络协议捕获和实验级额度预检；本轮没有真实 Provider 请求。

## 冻结的请求协议

- Provider：DeepSeek 官方 OpenAI 兼容 Chat Completions，模型标识 `deepseek-flash`。
- 非思考模式：SDK `extra_body` 设置 `thinking: {type: disabled}`，本地 MockTransport 捕获到相同 JSON 字段。
- 生成上限：`max_tokens: 2048`。不能把这个参数当作 Provider 违约时的绝对账单上限。
- 工具调用：有工具时由 Agent 自主选择，出站 `tool_choice=auto`；`parallel_tool_calls=false`。
- 超时：30 秒；自动重试：0；模型、模式和参数不兼容时不移除字段、不切换模型、不重发。
- Provider 构造默认关闭。启用还要求明确 `AR-02-LIVE-01` 作用域、冻结模型、API Key 和官方 HTTPS 主机；工厂构造本身不发请求。

DeepSeek 文档说明 `thinking.type=disabled` 选择非思考模式，Chat Completions 中经 OpenAI SDK 应通过额外请求体传递该字段；`max_tokens` 是输出上限字段。文档同时说明输入与输出合计受上下文长度限制。参考[Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/) 和 [Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)；本地测试使用 `httpx.MockTransport`，不是 Provider 协议实测。

## 费用与总额度

官方价目表截至核验时列出 `deepseek-flash` 峰时 cache-miss 输入价 `$0.30/M`、输出价 `$1.20/M`、上下文 `1M`、最大输出 `384K`。本预留不计 cache-hit 折扣：

```text
输入余量 = 1,000,000 - 384,000 = 616,000 tokens
每次保守预留 = 616,000 × $0.30/M + 384,000 × $1.20/M
             = $0.1848 + $0.4608 = $0.645600
16 次全未知总预留 = $10.329600
P0 总预留上限 = $10.50，16 次全部未知时余量 = $0.170400
```

来源：[DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)。价格和供应商行为会变化；这只是按当前公开边界建立的应用侧预留，不是供应商账户级硬性费用保证。若 Usage 缺失、畸形或调用结果未知，完整 `$0.645600` 预留保留且不得重发；合法 Usage 到账后按峰时 cache-miss 费率结算，不使用缓存优惠，并释放未使用预留。输出 Usage 超过请求 `2048`、上下文边界或本次预留时，将账本置为 `BUDGET_BREACH`，拒绝后续出站。

| 维度 | P0 固定值 | 执行方式 |
|---|---:|---|
| Provider dispatch | 16 次 | 持久账本、`BEGIN IMMEDIATE`、跨 Session/Run 共用 |
| MCP `tools/call` | 12 次 | 外发前预留；`tools/list` 元数据读取不计入此项 |
| 应用侧费用预留 | USD 10.50 | 每次模型出站前预留最坏公开边界 |
| 原 Task/Run 限额 | 不变 | 与实验总限额同时生效，按较小剩余额度拒绝 |

账本通过唯一作用域 `AR-02-LIVE-01` 延迟创建；普通应用启动不创建该账本，也不更改 `PRAGMA user_version`。未知/已预留记录跨连接重开继续占用额度。事务竞争和超限前拒绝由本地 SQLite 测试验证。

## P1 单独授权申请（当前未获批）

仅申请执行本任务卡冻结的首次 S01 和同 Session 五轮 S02；不扩样、不重跑。请单独明确批准以下整组边界后才可发出真实请求：

- `deepseek-flash`，官方 Chat Completions，非思考模式，`max_tokens=2048`。
- Provider 最多 16 次、MCP `tools/call` 最多 12 次；逐次发送前持久预留。
- 应用侧费用预留总上限 USD 10.50；每次按 USD 0.645600 最坏公开边界预留，合法 Usage 到账后结算；未知、超时、取消或丢失响应不释放预留、不重试。
- `tool_choice=auto`、`parallel_tool_calls=false`、30 秒超时、`max_retries=0`。不因错误更换模型/模式或静默移除参数。
- 仅冻结 S01 与 S02 输入及当前只读授权工具；无业务修复、审批、交接、外部写入或浏览器自动化。
- 费用金额是应用侧约束，不保证供应商违反公开上下文、价格或 Usage 口径时绝对不超支；如账号层有可用硬额度，应同时设置。

在用户明确批准上述参数前，P1 保持 `NOT_RUN`。
