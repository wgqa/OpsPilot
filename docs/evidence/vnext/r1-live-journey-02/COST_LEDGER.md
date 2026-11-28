# R1-LIVE-JOURNEY-02 费用与次数

## 本 Campaign

| 项目 | 结果 |
|---|---:|
| 真实 Provider 发送授权/请求 | 0 |
| 真实 Usage | 无 |
| 应用侧真实结算估算 | USD 0.00 |
| UNKNOWN 未决预留 | USD 0.00 |
| 真实 MCP 调用 | 0 |
| 持久 Campaign Grant / DB / Claim | 未创建 |

没有本次 Campaign 专属的明确付费授权，因此未创建正式 Grant 或数据库、未启动 Worker 真实发送路径，也未借用历史额度。单元测试中的 Grant、发送许可、Usage 和预留均只存在隔离临时 SQLite 与 MockTransport 中，不代表实际 Provider 费用。

## 冻结策略

- Campaign：`R1-LIVE-JOURNEY-02`
- Provider 上限：12 次；数据库内 `SEND_GRANTED`/已发送状态累计，Worker 重启后不重置。
- 应用池上限：USD 8.00。
- 每次发送前预留：USD 0.645600。
- 12 次最大保守预留：USD 7.747200；与总池差额 USD 0.252800。
- Model：`deepseek-flash`，`max_tokens=2048`，输入上限 12,000，超时不超过 30 秒，并发 1，零重试。

按 DeepSeek 官方 2026-11-08 页面：`deepseek-flash` 高峰 cache-miss 输入为 USD 0.30/M，输出 USD 1.20/M，context 1M，max output 384K。极端上界计算为 616,000 输入 × 0.30/M + 384,000 输出 × 1.20/M = USD 0.645600。官方价格可变，未来真实发送前必须重新核对；配置版本或容量不符时现有 Campaign 绑定校验 fail closed。

这是一项应用侧保守预留，不是供应商账单，也不保证 Provider 违反已接受输出限制时绝对不超额。新 Campaign 只使用独立数据库/Grant；旧 Campaign ledger 与 USD 0.645600 历史 UNKNOWN 预留均不变。
