# Observation Contrast Live — Processed Runtime

**分类：** 探索性反事实对照；不是 E08-H 首次正式运行，不计入冻结 12 例分母。
**代码基线：** `codex/r2-ar06-observation-contrast-01@e92949fa66abddff8b496cb127756c30a49d9654`
**执行：** 2026-11-14 UTC；唯一新案例 Runtime：`user-demo-r2-obscontrast-live02`。
**评定：** `UNVERIFIED`；仅提交结构化真实证据，等待主 Agent 独立评分。

## 执行身份与初态

- 原题：冻结 E07-D 用户输入；实际输入 SHA256 `58a3fa04a1ff5197fb8ff6f604bfd8c5e4975a7fac202f5850f58ee37e6a9354`，与已保存 E07-D 相同。
- Run：`run-0905ca66-c1cb-41c6-8173-70b24fb7d361`，状态 `SUCCEEDED`；Session：`session-7ac6b1d6-7ef0-47b4-811d-b62379623176`；TaskBinding：`task-371f99f1-b888-43e9-9192-f0d2ffd93a4a`。Run 的 `source_message_id` 与用户消息 `message-376ab9d5-03a4-48ff-a96b-5869fe6ebb45` 一致，最终 Assistant 消息 `message-dd9a121c-1021-4d9b-93f9-bfbbed9ea042` 已导出。
- 可信绑定：tenant `tenant-a` / actor `support-a` / service `orders-async-demo` / integration `async-integration-a` / principal `async-principal-a` / 订单 `async-order`。
- 目标 Event：`event-00000000-0000-4000-8000-000000000101`；本次当前 Run 的 Receiver Observation `observation-880fd0ba-3603-4484-87c1-13ab52f79e5d` / Evidence `evidence-742a4cc2-1594-405c-a4b6-97116f2124b5`，`PROCESSED`，version 3，observed at `2026-11-14T16:21:41.544+00:00`，来源 `s3://event-00000000-0000-4000-8000-000000000101/v3`。
- Decoy：`async-order-decoy` / Event `event-00000000-0000-4000-8000-000000000102`，Fixture 状态 `QUEUED`。模型未查询 decoy；本 Run 没有把它用作目标事实。
- 本 Run MCP Observation 共 3 条，均为只读工具。无业务写入、审批或交接。

## 模型决策与结论

模型自主进行了两次 Provider 派发：首次选择 `get_order_status`、`get_callback_delivery`、`get_receiver_processing`，随后根据工具结果生成最终回答；本次没有在用户提示中规定工具顺序或提供预期答案。最终回答指出：订单为 `COMPLETED`；HTTP 202 对应 Delivery `ACKNOWLEDGED`，并不单独证明处理完成；当前同一目标 Event 的 Receiver Observation 为 `PROCESSED`，所以回调处理现已完成。回答也说明 Delivery 响应体曾记录 `receiver_state=QUEUED`，随后 Receiver 当前状态为 `PROCESSED`。

完整原始脱敏回答见 [FINAL_ANSWER.md](FINAL_ANSWER.md)，全量模型输入/输出、工具调用、Observation、Evidence、TaskBinding、Run 和账本见本目录 Trace。

## Provider 与费用

- Provider：DeepSeek `deepseek-flash`；真实 Provider 请求数 2，响应数 2；UNKNOWN 0；自动重试/重提 0。
- 价格版本：`DEEPSEEK_FLASH_PEAK_2026-11-14`；本地保守峰值费率为输入 USD 0.30 / 1M tokens、输出 USD 1.20 / 1M tokens，与 [DeepSeek 官方 Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/) 的 cache-miss 输入及输出峰值价格一致。
- Response IDs：`ab68fc4f-4d44-44d7-bb79-541c85536426` (`tool_calls`, 2,868 input / 134 output)；`a66ec297-a4ad-466e-a499-e8e54800c81a` (`stop`, 4,740 input / 547 output)。
- Token：输入 7,608 / 输出 681 / 总计 8,289；Usage 完整。
- 应用账本两笔 `DELIVERED`：USD 0.001022 + USD 0.002079 = USD 0.003101；耗时 8,944 ms；3 MCP calls / 3 Observations / 3 Evidence。
- 本 Runtime Grant 上限 USD 0.050000；运行后已结算 USD 0.003101，可用 USD 0.046899，开放/UNKNOWN 预留 USD 0。此余额不构成额外 Run 授权。

## 与原 E07-D 首次结果对照

原 E07-D Trace/Result 未改写、未重跑：Runtime `user-demo-r2-e07-live01`，Run `run-c6be60b9-e6b0-4310-8c8f-853c00934d4f`；原目标 Event `event-00000000-0000-4000-8000-000000000001` 的 Receiver 为 `QUEUED`。两例使用同一冻结输入，但为不同 Runtime、Session、Task 和 Event。

| 指标 | E07-D 首次 | 本次 Processed 对照 | 差值（对照 - E07） |
|---|---:|---:|---:|
| Provider sends / responses | 2 / 2 | 2 / 2 | 0 / 0 |
| Input tokens | 7,629 | 7,608 | -21 |
| Output tokens | 675 | 681 | +6 |
| Total tokens | 8,304 | 8,289 | -15 |
| App fee | USD 0.003099 | USD 0.003101 | USD +0.000002 |
| Elapsed | 8023 ms | 8944 ms | +921 ms |
| MCP calls / observations | 3 / 3 | 3 / 3 | 0 / 0 |
| Target Receiver | `QUEUED` | `PROCESSED` | changed with isolated fixture state |

两次模型回答的结论分别跟随各自 Run 中同一 Event 的 Receiver Observation：E07-D 为 `QUEUED`；本次为 `PROCESSED`。这是一个真实模型对照观察，样本量为 1 次新 Run；它不构成统计性或总体能力结论。

## 证据完整性与运行收尾

- Trace SHA256 `fc900d753ea8dd807f558f057cb8b106f609acd6910f3d1604da091858f8085d`；Runner Result SHA256 `1978332da6bae1e0c24989f6fbf79d634387c353ad661be9165c78d0eaee82c9`；独立最终回答 SHA256 `d030598a183649010ea95580e2f5a6e40fa0976894f17ac77be3f2a953095534`。
- Trace 导出标记 `api_key_cookie_authorization_and_configured_passwords_removed=true`、`secret_values_included_in_export=false`。
- E07-D 既有仓库 Trace SHA256 `aacf15bdb81a24461b612551a23800a12c86f54a275f95185a3d24cdb34ebb59`，本次未改动。
- 初次 Stop 脚本调用因 Windows CIM 返回空 `ExecutablePath` 而报错。随后检查发现登记的 API/前端 PID 均已不存在且没有对应监听；再次执行 Stop 脚本成功清理残留进程清单。未使用强制结束；Domain、Checkpoint、Trace、Spend 和日志保留。首次 Stop 异常作为环境收尾瑕疵记录。
- 本次未改生产源码、冻结 Gold/Rubric 或原 E07 结果；未新增 Worktree；未合并 main。

## 证据文件

- [脱敏 Trace](OBSERVATION_CONTRAST_PROCESSED_TRACE.json)
- [Runner Result](OBSERVATION_CONTRAST_PROCESSED_RESULT.json)
- [最终回答](FINAL_ANSWER.md)
