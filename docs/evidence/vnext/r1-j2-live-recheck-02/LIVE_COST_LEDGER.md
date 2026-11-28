# R1-J2-LIVE-RECHECK-02 — 费用账本

- Campaign 应用池：USD 8.00；Provider 上限 12；单次发送前持久预留 USD 0.645600。
- 本轮真实发送：9 次；每次都先预留，均收到 HTTP 200 和合法 Usage 后结算；没有未决/UNKNOWN 预留。
- 9 次临时总预留：USD 5.810400；账本按 Usage 结算：USD 0.024332；应用池剩余 USD 7.975668。
- 总 Usage：60006 输入 + 5273 输出 = 65279 tokens；本轮最大单次输入 11464 / 12,000，最大输出 1303 / 2,048。
- 供应商最终账单没有独立查询；下方“结算”是 OpsPilot 应用账本估算，不冒充 DeepSeek 发票。
- 公开价格基准：DeepSeek V4.1 Flash 峰值 cache-miss 输入 USD 0.30/M、输出 USD 1.20/M；预留按公开最大上下文/输出保守计算，12 次合计 USD 7.7472。
- 单次预留公式：`(616,000 input × $0.30 + 384,000 output × $1.20) / 1,000,000 = $0.645600`。
- [DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)；[Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)

| 案例 | Completion ID | HTTP / dispatch | Input / output / total tokens | 单次预留 | Usage 结算估算 |
|---|---|---|---:|---:|---:|
| J1-01 | `1b41536a-30b1-4567-b557-5605bfbd84ea` | 200 / DELIVERED | 1898 / 57 / 1955 | $0.645600 | $0.000638 |
| J1-01 | `a64f95df-c4e2-4f48-9d90-3812581b4ea8` | 200 / DELIVERED | 3493 / 116 / 3609 | $0.645600 | $0.001188 |
| J1-01 | `5741e2ac-3b6f-4b47-aba4-20cdaf794094` | 200 / DELIVERED | 4779 / 1141 / 5920 | $0.645600 | $0.002803 |
| J1-02 | `fd9bb639-0079-4503-91d1-769a6ee0c4ca` | 200 / DELIVERED | 5326 / 816 / 6142 | $0.645600 | $0.002577 |
| J2-01 | `a294d3b0-81f8-4ae2-8e2b-e9dfc338c195` | 200 / DELIVERED | 5050 / 199 / 5249 | $0.645600 | $0.001754 |
| J2-01 | `d155e7c6-e6a2-4b1e-8999-1914461b099c` | 200 / DELIVERED | 8344 / 292 / 8636 | $0.645600 | $0.002854 |
| J2-01 | `c359bc09-5f72-43b6-a8dd-2c9ba421dccc` | 200 / DELIVERED | 10508 / 1303 / 11811 | $0.645600 | $0.004716 |
| J2-02 | `ad0e220e-c7ac-44d6-bf57-949a8864d854` | 200 / DELIVERED | 9144 / 210 / 9354 | $0.645600 | $0.002996 |
| J2-02 | `83831aee-6414-461e-b558-76259e4875bf` | 200 / DELIVERED | 11464 / 1139 / 12603 | $0.645600 | $0.004806 |

价格和实际请求合同在发送前由授权 Runner 核验；私有账本保存 request/body digest、Completion ID、Usage、状态和结算。
