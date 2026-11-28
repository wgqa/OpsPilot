# R1-LIVE-JOURNEY-01 费用勘误

原始 `../REPORT.md` 与 `../COST_LEDGER.md` 保留原样。本文件更正其中把 DeepSeek Flash 输出价格读作 USD 1.32/M 的错误，不追溯改写原始 `BLOCKED_BEFORE_PROVIDER_SEND` 事实。

按 2026-11-08 核对的 DeepSeek 官方价格页，`deepseek-flash`（官方版本 `DeepSeek-V4.1-Flash-1017`）峰值价格为输入 cache miss USD 0.30/M、输出 USD 1.20/M；上下文容量 1M、最大输出 384K。费用预留不依赖 cache hit 折扣。

```text
可计费输入极端容量 = 1,000,000 - 384,000 = 616,000 tokens
单请求预留 = 616,000 × 0.30 / 1,000,000
           + 384,000 × 1.20 / 1,000,000
           = USD 0.6456
16 次最大预留 = 16 × 0.6456 = USD 10.3296
批准总预算 = USD 11.00；余额空间 = USD 0.6704
```

因此，按本轮冻结的公开容量极端口径，16 次请求的计算上界低于 USD 11.00；上轮“USD 11.06688 超预算”的判断不成立。此勘误不代表供应商账单保证，也不允许超过本轮 16 次或 USD 11.00 的授权。

来源：[DeepSeek 官方价格表](https://api-docs.deepseek.com/quick_start/pricing/)（本轮核对日期 2026-11-08）。
