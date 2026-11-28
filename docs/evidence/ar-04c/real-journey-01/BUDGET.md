# AR-04C-REAL-JOURNEY-01 — 预算合同

**状态：** 免费预检合同；付费未授权。  
**时点：** 2026-11-05 官方 DeepSeek 文档核对。

## 总上限与独立分配

| 边界 | 每条件 | OFF+ON 合计 |
|---|---:|---:|
| Provider dispatch | 8 | 16 |
| 应用侧 USD 硬上限 | $5.25 | $10.50 |
| MCP 调用次数 | 不设置固定低次数 Gate，持久计数 | 不设置固定低次数 Gate |
| 并发 Provider | 1 | 1 |
| 超时 | Provider 30s；MCP 12s；Assistant Run 60s | Task 活跃时间 300s；Campaign 3600s |
| 重试 | 0 | 0 |
| Context 输入 | 12,000 tokens | 12,000 tokens |
| Provider 输出请求 | `max_tokens=2048` | `max_tokens=2048` |
| Graph recursion limit | 36 | 36 |

每个条件使用独立 Domain DB 和 Checkpoint，但在各自数据库中只拥有固定一半预算。两边总额因此被数学地限制在 $10.50。每个条件的 Provider 计数上限为 8。每次 MCP 仍由既有 Campaign dispatch、D2 Attempt Ledger、Session/TaskBinding、Context 来源重验及执行时间管控；同名工具可为补充当前证据再次调用。

## 价格与单次预留

2026-11-05 重新核对 DeepSeek 官方 [Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/) 后确认，`deepseek-flash` 对应 `DeepSeek-V4.1-Flash-1017`，峰值缓存未命中输入价格为 `$0.30/M`、峰值输出为 `$1.20/M`，上下文为 1M、最大输出为 384K。此前把 `$1.32/M` 误读为 Flash 输出价；该价格属于同表的 V4 Pro 峰值缓存未命中输入。AR-04C 使用保守的峰值价格，不依赖缓存或非高峰折扣，单次最坏预留为：

`(616,000 × $0.30 + 384,000 × $1.20) / 1,000,000 = $0.645600`

旧实验仍保留旧价格版本和账本。本实验使用 `DEEPSEEK_FLASH_PEAK_2026-11-05` 和 AR-04C 专属预留常量，不回写任何旧费用。

每次发出前，现有账本先原子预留 `$0.645600`；只有返回有效 Usage 后才按峰值费率结算并释放未用预留。UNKNOWN、Usage 缺失或不一致均保留预留并持久关闭 Campaign。对于符合请求参数的常规 12K 输入/2048 输出，按官方峰值费率及向上取整，预估约 `$0.006058`；但费用守卫不依赖 Provider 一定遵守输出限制。

16 次全部按单次完整最坏额度预留为 `$10.329600`，低于 `$10.50`；每个条件 8 次的最坏预留为 `$5.164800`，低于各自 `$5.25`。因此即使每次都按整个模型最大输入/输出包络预留，两条件的请求上限与各自预算仍能同时满足。有效 Usage 返回后释放未用预留；若费用或调用额度触限则拒绝后续发送。

## 价格更正记录

冻结初稿曾把 Flash 输出价格误记为 `$1.32/M`，导致 `$0.691680` 单次预留与 8 次/每条件、`$5.25` 条件预算不相容。该误读在付费授权及任何 Provider 出站之前通过重新打开官方价格表发现；以本更正替换准备阶段初稿的费率和预留。历史旧实验仍使用原价格版本、代码逻辑和账本，本更正只作用于新 AR-04C 实验。

## 可追踪和恢复

- 每次 Provider/MCP dispatch 均在外发前通过已有 `ar02_live_dispatches` 原子记录。
- 每个正式 Task 采用实验专属版本化 policy `AR04C_MEMORY_ON_OFF_V1`。Task/Run 保留最多 8 MODEL 预算和现有 300,000 ms 活跃时间；MCP 存储列的 `0` 仅作为现有 NOT NULL Schema 哨兵，由此版本解释为“不设低 MCP 次数上限”。此策略仅允许绑定到 `orders-async-demo` 的 Task，不改变普通 Task 或历史策略。
- provider dispatch 的稳定 logical key 及 UNKNOWN 状态不能通过恢复、新 Run 或新消息重放。
- 用户授权、实验 allowlist、一次性 Claim、token、预算行和合同 Digest 必须全部精确匹配；API Key 存在不构成授权。
- Phase C 不创建真实授权文件、Claim、token 或调用者可执行入口。后续只有获得明确授权后才可以建立一次性 Claim；Claim 仅可创建一次，必须在任何外发前持久消费，失败/未知也消耗，不可复用。

