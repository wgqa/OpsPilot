# 真实 Campaign 费用账本摘要

应用账本按每次 Provider dispatch 先预留 USD 0.645600。有效 Usage 返回后按冻结峰值费率、把全部 `prompt_tokens` 当作 cache miss（不使用缓存折扣）结算。金额逐请求向上取整到 USD micro。

| 轮次 | Completion ID | Input | Cache hit | Cache miss | Output | 发送前预留 | 应用账本结算 |
|---|---|---:|---:|---:|---:|---:|---:|
| J1-01 | `ab262ab0-b2f6-4071-b6e6-f65b19b73677` | 1,653 | 0 | 1,653 | 55 | $0.645600 | $0.000562 |
| J1-02 | `946d179b-cff5-4817-90ed-7365b8057889` | 1,759 | 256 | 1,503 | 67 | $0.645600 | $0.000609 |
| J2-01 | `4df2dbd1-6798-477e-99ea-b26fb793db9e` | 2,175 | 256 | 1,919 | 142 | $0.645600 | $0.000823 |
| J2-02 | `23d7fa13-90cb-4ed8-8266-f6f6f6e2987e` | 2,277 | 256 | 2,021 | 197 | $0.645600 | $0.000920 |
| **合计** |  | **7,864** | **768** | **7,096** | **461** | **$2.582400** | **$0.002914** |

所有四笔 Usage 有效，Runtime Grant 行状态为 `RESPONSE_STORED`；费用池的 `committed_or_reserved_usd_micro=2914`，剩余 USD 10.997086。Campaign 随后被显式标为 `STOPPED / CAMPAIGN_FINISHED`。剩余 12 次额度没有复用，本 Campaign 不能重启。

这里的 USD 0.002914 是应用账本按冻结费率计算的估算，不是 DeepSeek 供应商账单。Runtime HTTP 响应已持久保存，但 LangChain/Assistant 没有完成结果交付：`assistant_calls.status=UNKNOWN`，四个 Run 均 `FAILED`。因此 HTTP 200、Usage 与结算不代表用户旅程成功。

费率和公开容量见 [勘误](ERRATA.md) 及 [DeepSeek 官方价格表](https://api-docs.deepseek.com/quick_start/pricing/)。
