# R2-AR06-LIVE-EXEC-01 · 首批真实模型结果

**状态：`ACCEPTANCE_CANDIDATE`**

**执行代码：** `codex/r2-ar06-auto-live-eval-01@3cd1536ed8c69d6924be2b63121d95dd52a57080`

**执行时间：** 2026-11-14 UTC

**评分：** 候选评分，等待主 Agent 独立复核；不构成正式 PASS。

## 范围与冻结材料

本批共 3 个开发集案例：E01-D 是已有历史首次运行，本轮未重跑；E05-D 与 E07-D 各新建独立 Runtime 并执行一个真实 Run。E05 和 E07 使用各自独立的 USD 0.05 Runtime Grant。未运行任何 H 留出案例、E03、E08、E09 或安全负例。

- `CASES.json` SHA256：`c1acd3fa789befa733aa96bf3a49b08357ff071f3b627b4c40319882e2805cf8`
- `RUBRIC.json` SHA256：`859985480169b04824a96a97db3031c312a68abbb550be3a96ffa6cbe5040944`
- 三例均与冻结输入逐字匹配。每例输入 SHA、Session/Run、Response ID 及 Trace SHA 见 [`LIVE_RESULTS.json`](LIVE_RESULTS.json) 和 [`CASE_TRACE_INDEX.md`](CASE_TRACE_INDEX.md)。

| Case | 类型 | Run | Provider 请求 | Input / Output Token | 应用费用估算 | MCP / Observation / Evidence | 候选评分 |
|---|---|---|---:|---:|---:|---:|---|
| E01-D | 历史真实首次尝试 | SUCCEEDED | 1 | 2,487 / 491 | USD 0.001336 | 0 / 0 / 0 | PASS_CANDIDATE |
| E05-D | 本轮真实执行 | SUCCEEDED | 1 | 2,537 / 426 | USD 0.001273 | 0 / 0 / 0 | PASS_CANDIDATE |
| E07-D | 本轮真实执行 | SUCCEEDED | 2 | 7,629 / 675 | USD 0.003099 | 3 / 3 / 3 | PARTIAL_CANDIDATE |

合计为 **3 个案例 Run、4 次 Provider 请求、14,245 Token、3 次 MCP 调用、3 条 Observation、3 条 Evidence**。费用账本累计 USD 0.005708，其中本轮 E05/E07 共 USD 0.004372。E01 的历史运行不计入本轮新授权支出。样本只覆盖 3 个 D 开发案例，不能解释为全量 Benchmark 成功率或泛化结果。

## E01-D：HTTP 202 解释

保留原始首次结果，没有重新提交。Session `session-57d5d0a8-bb16-4be9-ab6a-c58f18049976`，Run `run-7ff06937-6268-4fa3-a51e-4ce63100436e`。Provider Response ID：`814c3218-c068-4aff-a0c4-2b55ac6a1ade`。

模型说明 202 表示已接受处理请求，不证明回调已处理完成；它明确表示本轮没有查询业务系统，也没有声称具体订单状态。输入与冻结 E01-D 原题完全一致。历史候选评分为 PASS_CANDIDATE，正式评价仍由主 Agent 决定。原始导出 SHA、Domain DB SHA 与 Checkpoint SHA 已复核未变化，值见 Trace Index。

## E05-D：JSON 与 503 材料分析

独立 Runtime：`user-demo-r2-e05-live01`；Session `session-36f1742a-826c-4d25-9712-43fbe0037ff2`；Run `run-4b15215e-3f49-445d-be88-98999d85e63d`。Provider Response ID：`527572e1-b29a-4c47-a809-8df1ee9347c7`。运行耗时 5,930 ms，1 次请求，2,537 输入 / 426 输出 Token，结算 1,273 micro-USD，UNKNOWN 为 0；没有 TaskBinding、MCP、Observation 或 Evidence。

回答按“已知 / 推断 / 未知”组织：复述 `api_version=v1`、`max_attempts=5`、`backoff=fixed` 与日志字段；把 503 的含义和“若该配置生效则重试排程一致”标成推断；没有把材料称为线上当前配置，也没有编造当前订单状态或确定根因。回答保存在完整 Trace 中。候选评分 PASS_CANDIDATE；这只是单次案例判断。

## E07-D：同 Event Delivery / Receiver 调查

独立 Runtime：`user-demo-r2-e07-live01`；使用 `r2-e07-queued` 业务数据 Fixture（模型仍为真实 DeepSeek）；Session `session-300f9d82-85f7-4bff-a3d6-6da8d99324b3`；TaskBinding `task-73c28480-0392-47c4-866d-8a5e505ae619`；Run `run-c6be60b9-e6b0-4310-8c8f-853c00934d4f`。绑定范围为 `tenant-a / support-a / orders-async-demo / async-integration-a / async-principal-a / async-order`。这是本地可信绑定和只读 MCP 调查，没有外部业务写入。

Agent 自主进行了 3 次 MCP 读取：`get_order_status`、`get_callback_delivery`、`get_receiver_processing`，随后生成最终回答；模型没有被预设工具顺序。两次 Provider Response ID 为 `377d6ab2-2aca-49d3-bd79-cd9e77008be5` 和 `c88b0aa9-67af-41a5-9f3d-ceab2b8035d1`。耗时 8,023 ms，累计 7,629 输入 / 675 输出 Token，应用账本结算 3,099 micro-USD，UNKNOWN 为 0。

Delivery 当前观察为 `ACKNOWLEDGED / HTTP 202`；Receiver 当前观察为 `QUEUED`；两者 Evidence 都关联 Event `event-00000000-0000-4000-8000-000000000001`。Receiver `accepted_at=2026-11-14T08:29:25.517444Z`，本轮观察约在 `08:31:49Z`，300 秒 SLA 截止约 `08:34:25Z`。模型正确区分订单 `COMPLETED` 与回调尚在队列中，并说明 202 不是处理完成。

候选评分为 **PARTIAL_CANDIDATE**：回答称“订单、Delivery、Receiver 三个来源的 event_id 一致”，但当前 Run 的 `get_order_status` Observation 不含 `event_id` 字段。Delivery 与 Receiver 的同 Event 关联确有证据，然而将第三个来源也纳入一致性结论缺少来源支持。这个来源准确性缺陷不能由正确的主结论抵消；原始回答和 Trace 保留，未重跑。

## 费用、Grant 与停止状态

Provider 为 `deepseek-flash`，Endpoint 主机 `api.deepseek.com`，配置版本 `deepseek-v4.1-flash-1017`。本地费率为输入 USD 0.30 / 百万 Token、输出 USD 1.20 / 百万 Token，与[DeepSeek 官方价目页](https://api-docs.deepseek.com/quick_start/pricing/)当前公布的峰值费率一致。费用是应用账本按真实 Usage 结算的估算值，不是供应商发票。

- E05 Grant：上限 USD 0.050000；已结算 USD 0.001273；余额 USD 0.048727。
- E07 Grant：上限 USD 0.050000；已结算 USD 0.003099；余额 USD 0.046901。
- 两个 Grant 独立，均到 `2026-11-15T08:30:00Z` 过期；不会自动延长。服务已分别由 `Stop-UserDemo.ps1` 优雅停止，Domain、Checkpoint、日志与账本保留。
- E05/E07 的 Provider 发送总数为 3；Run 均成功，没有 UNKNOWN、失败后重试或重复提交。另无浏览器自动化、Fixture Model 派发或外部业务写入。
- 三份 Trace 与两个 Runner 结果文件经本地 `.env` 中配置的密钥/密码值扫描，未发现未脱敏值；提交副本与 Runtime 原件 SHA256 完全一致。

## 运行备注与限制

E05 Grant 创建后再执行离线账本预检时，预期得到 `OFFLINE_PREFLIGHT_REQUIRES_NO_RUNTIME_GRANT`；创建 Grant 前离线预检已通过，之后正式 Live Preflight 也通过。此为离线模式拒绝带 Grant Runtime 的设计行为，不是 Live 失败。

一次人工读取 E07 Trace 的 PowerShell 命令误把已解析对象再次交给 `ConvertFrom-Json`，产生只影响该读取命令的转换警告；随后按实际对象结构只读核对成功，应用 Run、导出文件及费用记录均未受影响。

这是一次小样本真实模型案例研究。没有独立 H 留出、重复采样或统计检验；不能推导模型总体成功率、成本分位数或 R/H/A 优势。正式结论交主 Agent 独立评分。
