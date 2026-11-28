# R1-LIVE-JOURNEY-01 成本与发送账本

## 本 Campaign 账目

| 项目 | 数值 | 说明 |
|---|---:|---|
| Provider 请求上限 | 16 | 用户授权的整个 Campaign 累计上限 |
| 应用预算上限 | USD 11.00 | 本次授权硬上限 |
| 本次真实 Provider HTTP | 0 | 发送前被保守费用门禁阻断 |
| 本次 MCP `tools/call` | 0 | Worker 未启动 |
| 本次持久 Provider 预留 | USD 0.00 | 未创建 Runtime Grant 或发送 Claim |
| 本次实际 Usage / 供应商账单 | 无 / USD 0.00 | 没有请求出站；不是估算账单 |
| 本次 UNKNOWN 请求 | 0 | 未发送请求 |

## 公开容量成本界

```text
1,000,000 input+output context
max output = 384,000
max input at this combination = 616,000

616,000 × 0.30 / 1,000,000 = USD 0.18480
384,000 × 1.32 / 1,000,000 = USD 0.50688
per-request conservative public-cap reserve = USD 0.69168
16 × 0.69168 = USD 11.06688
over USD 11.00 authorization = USD 0.06688
```

这使用峰值、无缓存优惠价格。即使本次实际请求参数更小，也不把本地估算或模型遵守 `max_tokens` 的历史行为伪装成项目当前已接受的最大可计费容量保证。

Runtime Grant 当前源码会依据配置的 12,000 / 2,048 Token 计算预留：按本次官方费率为 USD 0.00630336/次，16 次仅 USD 0.10085376。此数不能作为上述公开容量预留的替代。响应后才发现 Usage 超界并暂停池，不满足本任务要求的发送前保守预留。

## 旧账本

本轮未读取、修改、清理、重建或复用任何旧实验 Claim、Runtime Spend、UNKNOWN 预留或历史预算数据库。历史数据继续由各自证据目录负责。
