# Provider 发送前核验

**结论：** `BLOCKED_BEFORE_PROVIDER_SEND`。本轮真实 Provider 请求为 0。

## 官方模型与价格（2026-11-08 核对）

DeepSeek 官方 Models & Pricing 将 `deepseek-flash` 指向 `DeepSeek-V4.1-Flash-1017`，OpenAI-compatible Base URL 为 `https://api.deepseek.com`，公开总 Context 为 1M tokens、最大输出为 384K。当前峰值、未命中缓存单价为输入 USD 0.30/M、输出 USD 1.32/M；价格可能变化。此处保守使用峰值价格，不使用周末/非峰时或缓存优惠。

- [官方 Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)
- [官方 Chat Completions 参数定义](https://api-docs.deepseek.com/api/create-chat-completion/)
- [官方 Thinking Mode 参数说明](https://api-docs.deepseek.com/guides/thinking_mode/)

官方 API 将 `max_tokens` 定义为最大生成 Token 数；在工具存在时 `tool_choice` 默认 `auto`，thinking 可通过 `extra_body` 发送 `{"thinking":{"type":"disabled"}}`。本任务仍要求核对最终序列化请求，而不是只检查模型构造参数；上轮 J1/J2 MockTransport 已捕获过正式 SDK 报文，但这不验证 Provider 对参数的实际运行行为。

## 最坏容量界与授权额

沿用该项目既有预检的保守处理：不把 `max_tokens=2048` 或本地 Token 估算包装成供应商绝对账单上界，按官方可行最大容量 `616,000 input + 384,000 output = 1,000,000 total tokens` 计算：

```text
616,000 × USD 0.30 / 1,000,000
+ 384,000 × USD 1.32 / 1,000,000
= USD 0.69168 / 请求

USD 0.69168 × 16 次 = USD 11.06688
超过本次 USD 11.00 授权额 USD 0.06688
```

虽然仅按 `max_tokens=2048` 推算会得到更低数字，但那不是本轮已接受的公开容量保守预留合同；本轮不擅自缩小上界来制造 READY。价格页面也提示价格可调整。

## Runtime Grant 与运行配置核验

1. `assistant_runtime_grant.py::reserve_dispatch()` 目前按持久 Grant 中的 `max_input_tokens`/`max_output_tokens` 计算发送前预留；`provision_default_grant()` 限制其最大值为 12,000 / 2,048。按当前官方费率，该组合仅预留 USD 0.00630336/请求，而非上述 USD 0.69168/请求。
2. `validate_http_request()` 用应用侧估算限制输入；`store_response()` 在响应到达后才根据实际 Usage 检查是否超过预留，超限会将池暂停并记 `VIOLATION`。这能阻止后续请求，但不能把发送前预留说成已覆盖公开最大计费容量。
3. 当前 Runtime Grant 数据库没有跨 Session 的 Campaign 16 次 Provider 发送硬上限。`assistant_runtime_spends` 会持久记录 dispatch，但 `reserve_dispatch()` 没有 Campaign 级累计次数拒绝；旧实验 `provider_limit` 不属于本次普通 Runtime Grant 授权，不能借用。
4. 新隔离工作树中没有 `.env`，本进程的 Provider/Runtime 开关和模型环境均未设置。开发目录已有本地 `.env` 的密钥值未输出、未复制、未验证；该配置的模型名与 Base URL 为 `deepseek-flash` / `https://api.deepseek.com/v1`，但 `OPSPILOT_MODEL_CONFIG_VERSION` 与 `OPSPILOT_MODEL_PRICE_VERSION` 未设置。未建立 Grant。
5. 上轮正式 API/Worker 的 MockTransport 证据验证了 DeepSeek SDK 会发到 `/chat/completions`，`model=deepseek-flash`、`max_tokens=2048`、disabled thinking、`tool_choice=auto`、`parallel_tool_calls=false`、非流式且没有 `max_completion_tokens` 别名；该证据复用自本分支 Base，未重新发模拟 Campaign。

由此，费用总上界、持久发送前费用预留和跨 Session Campaign 发送数三个条件都未同时成立。为遵守停止线，本轮没有启动 Worker 或提交任何真实用户轮次。
