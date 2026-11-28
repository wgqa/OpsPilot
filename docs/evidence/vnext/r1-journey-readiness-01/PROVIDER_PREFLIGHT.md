# 真实 Provider 预检（不含发送授权）

核验日期：2026-11-08。价格和模型细节来自 DeepSeek 官方文档，随时可能变化；正式运行前必须重新核对并由独立授权固定 Grant 价格版本。本轮未创建可发送 Grant，也未访问 DeepSeek API。

## 当前接线与协议

- 正常 Assistant 使用显式启用的 Runtime Grant 和 Worker 注入的 `runtime_grant_binding`；单独存在 API Key 不授权出站。
- 实际当前实现：`deepseek-flash`，OpenAI-compatible base URL `https://api.deepseek.com`，Chat Completions 路径 `/chat/completions`；异步正式 Worker 显式走 `httpx.AsyncClient`。自动重试为 0，超时 30 秒。配置采用非思考模式 `thinking={"type":"disabled"}`，`max_tokens=2048`，`stream=false`，工具场景 `tool_choice=auto`、`parallel_tool_calls=false`。
- 离线新旅程通过正式 SDK 与 HTTPX `MockTransport` 捕获并断言序列化报文、预算预留先于传输、有效 Usage 结算。它不是 Provider 兼容性实测。

## 官方协议和计费依据

- [DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)：当前 `deepseek-flash` 映射为 `DeepSeek-V4.1-Flash-1017`，表列 context 1M、maximum output 384K；价格按 1M token 计费。Peak cache-miss input 为 USD 0.30/M、output 为 USD 1.20/M；off-peak 与 cache-hit 更便宜。本方案不依赖 cache hit 或 off-peak 折扣。官方说明价格可能调整。
- [DeepSeek Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)：`max_tokens` 为最大生成 token 参数，接受 1 至 384K；响应 schema 含 model、choices/finish reason 与 usage；`finish_reason=length` 表示输出被长度或上下文限制截断。
- [DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)：OpenAI 格式通过 `thinking.type=disabled` 关闭 Thinking；该参数通过 `extra_body` 发送。

本地 12,000-token Context 上限使用应用侧估算，不能等同于 Provider 账单的数学保证。模型文档容量是供应商公开的上界，不代表正常请求预期长度。

## 费用场景计算

统一采用 peak、无 cache 优惠：

```text
目标请求配置下（输入 12,000 + 输出 max_tokens 2,048）：
12,000 × $0.30/M + 2,048 × $1.20/M = $0.0060576 / request

输入 12,000、假设 max_tokens 未按预期限制但仍受模型 output 上限约束：
12,000 × $0.30/M + 384,000 × $1.20/M = $0.4644 / request

按官方 1M 总 context 与 384K 最大 output 的可行组合求单请求上界：
输入 616,000 + 输出 384,000 = 1,000,000 tokens
616,000 × $0.30/M + 384,000 × $1.20/M = $0.6456 / request
```

`1M context` 包含输入和生成内容，不能再加 384K 输出。按 1M 输入 + 384K 输出得到的 USD 0.7608 是虽保守但不可同时发生的松上界；下面采用可行总 context 上界 USD 0.6456。

### 建议供下一次授权审议的保守配置

- 只运行一次 J1/J2 连续旅程，并在既有合法结果所属 Session 内分别做 J3/J4 只读回读；不让真实模型重跑 S1/S2 Investigator，也不触发 D3/S2 写入。
- Provider 最多 16 次（包含模型回答和可能的压缩请求）、并发 1、每次超时 30 秒、自动/手动重试 0 次；Campaign 费用上限建议 USD 10.50。
- 按 USD 0.6456 的公开容量峰值预留每次，16 次合计 USD 10.3296，低于上限并留 USD 0.1704。实际 Campaign Grant 必须绑定当前价格版本、数据库身份和新的一次性授权。实际发送虽只配置 `max_tokens=2048`，持久预留仍应覆盖官方最大可计费上下界，不依赖本地 tokenizer 估算或缓存优惠。
- 费用未知、Usage 缺失/超界、Grant/价格不匹配、来源撤权、任一请求超时或结果 UNKNOWN 时停止全 Campaign，保留预留，不重试；使用用户输入原文和原冻结 Gold；全程无外部业务写入。

以上仅是待批准建议，不授权创建 Grant、调用 Provider 或消费任何 Claim。若官方价格/容量变化，须按执行当天数据重新计算；若现有 Runtime Grant 无法持久预留上述金额或无法确保单飞/未知结果停止，则应在发送前阻断，不得改用旧实验身份。
