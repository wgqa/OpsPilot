# PRODUCT-01-SLICE-02 真实连续技术支持旅程

**用户结果 `PARTIAL`。** 四轮均由真实 DeepSeek 完成并持久化。模型区分了两个 Event，交付了基于目标传输记录的客户说明草稿。答复对生效配置的判断超出证据，草稿也承诺了尚未启动的后续跟进，发送前需要校稿。

## 四轮实际结果

同一 Session `session-6caaed14-76c8-4f33-ad0d-520eea33e905`。前两轮没有 Task，第三轮经可信 API 绑定 `product-01-order`，第四轮沿用该 Task。四轮 Run 均为 `ASSISTANT_V1 / SUCCEEDED`，答复均为 `CHAT_MODEL`。持久正文与该轮最终 Completion 正文逐字相同。完整输入见 [CASES.json](CASES.json)，完整答复保存在本地私有 `ANSWERS.md`。

| 用户任务 | Provider / MCP | 模型实际选择与用户得到的答复 |
| --- | --- | --- |
| 1. 了解协议升级影响 | 3 / 4 | 先发现协议并搜索 Knowledge，随后比较 v1.0.0 和 v2.0.0 并读取 v2 原文。说明失败码、重试策略和耗尽判定的区别，并指出部署版本未知。 |
| 2. 对照协议分析用户 JSON | 1 / 0 | 从会话历史读取协议和材料，直接回答。正确说明本轮没有重查，将 JSON 作为未验证材料。指出应核对上限口径和策略，部分配置建议被写成了规范要求。 |
| 3. 核实订单当前回调 | 2 / 3 | 查询 Delivery、Receiver 及订单传输历史。本轮同一个 `event-current` 的投递是 HTTP 202 / ACKNOWLEDGED，Receiver 当前是 PROCESSED。答复正确区分受理与处理完成。 |
| 4. 纠错到 `event-previous` 并起草客户说明 | 2 / 2 | 指定 `event_id=event-previous` 查传输历史，并额外重查当前投递。目标历史记录显示 HTTP 202、响应时 QUEUED，最终处理状态未知。草稿没有把另一事件的 PROCESSED 写成目标事件结论，也没有声称已修复或已发送。 |

第四轮模型原话摘录：“它是否最终被接收方处理完成，本轮无法确认”。目标传输请求是 `transport-2d39ba04-a7e3-44fc-9279-53d2a036f082`，原始受理记录时间为 2026-11-06 17:39:11.867 UTC。本轮新历史查询生成 Observation `observation-d58e31d6-ef2c-4ad4-9a4e-4c2bab4a32fb`，该 Observation 和对应 ToolMessage 都进入最终 Completion `3376a68a-f88a-41fc-a7bb-0a6cb011cd8f` 的实际请求。第三轮新取得的 Receiver 观察也进入了该轮的最终请求。逐个 Completion、请求/响应哈希、工具参数、回填关联及账本见 [RESULTS.json](RESULTS.json)。

## 从本次结果得到的改进项

1. **客户草稿的跟进状态。** 原答复写“正在进一步核实中”并承诺后续同步，执行记录只有本轮读取及已完成答复。发出前应改为最终状态尚待确认，避免把建议的下一步写成进行中的工作。
2. **模型的配置推断。** 第 3、4 轮把单次传输记录的 `max_attempts=10` 与用户 JSON 的 `5` 不同解释为配置没有生效。现有证据支持的是两个值不一致。Receiver 状态结果没有该配置字段，也没有查询生效配置的调用。第 1、2 轮亦将部分退避和配置字段建议写成 v2 硬要求。后续核对答案时以授权原文和实际字段为准。[v1 原文](../../../../knowledge/async-callback/callback-retry-contract.md) · [v2 原文](../../../../knowledge/async-callback/callback-retry-contract-v2.md)
3. **历史 Receiver 数据范围。** 当前 TaskBinding 绑定订单，Receiver 工具读取订单当前快照。历史传输工具接受 Event ID，但没有该 Event 的当前 Receiver 结果。模型建议通过页面“正式更正绑定”即可查询历史 Receiver，现有入口不提供这种能力。可明确提示需取得该 Event 的接收端日志或其它已授权证据。[订单绑定与 Receiver 读取](../../../../opspilot/domain/s3.py#L169)
4. **重复读取。** 第 4 轮又读了 `event-current` 的 Delivery，形成新 Observation，但复用第 3 轮的同一 Evidence，未补充目标 Event 的事实。可在后续评估该查询的用户价值。

F01 的历史时态问题本轮未观察到。第 2 轮正确说明零工具查询，第三、四轮的查询声明有当前 Run 证据。所有 Run 都形成了模型答复，预算终止时程序提示的 F01 路径本轮未触发。

## 执行与费用

- 本轮确认后从 `b2bc3bdf2749abf3750df96f86039600754f5010` 启动私有 `run.py`。执行时间为 2026-11-07 01:46:32 至 01:47:14（UTC+8），进程退出码 0，Claim 为 `STOPPED / FOUR_TURNS_SUBMITTED`。
- 运行使用 Python 3.14.0。核对的 FastAPI、Uvicorn、LangChain、LangGraph、MCP、HTTPX 和 OpenAI SDK 版本与 [requirements.lock.txt](../../../../requirements.lock.txt) 一致，锁文件 Blob 为 `de16e1113ac250511cee8d7b6a079b88b1ca4f99`。
- 请求 8/24，HTTP 200 为 8 次，MCP 9/12，压缩 0 次，Provider UNKNOWN 0 次。总输入 51,633 tokens，其中缓存命中 1,152。总输出 4,633 tokens，总计 56,266 tokens。最高实测单次输入 10,690 tokens，应用 Context 估算最高 10,559 / 12,000。
- 每次 Provider 请求前预留 USD 0.668468。应用账本按冻结峰值结算 **USD 0.021053**，未决预留 **USD 0**，余下 USD 1.978947。金额为应用估算，供应商账单未核对。请求携带 `parallel_tool_calls=false`，四个带工具的 Completion 仍各提出多条调用，持久时间戳显示 MCP 串行执行。[DeepSeek 官方费率](https://api-docs.deepseek.com/quick_start/pricing/)
- 持久结果的只读核对得到 1 个 Session、1 个 TaskBinding、4 个 Assistant Run 和 4 个答复。隔离库受保护表的前后摘要相同，Repair、Delivery、Handoff 记录均为 0，外部业务写入为 0。浏览器 `NOT_RUN`。

## 源码调用链

正式消息和可信订单绑定入口创建 Run，单 Worker 按 `ASSISTANT_V1` 选择执行。Assistant 在每次请求前装配当前观察与历史材料，预留后由 `ChatOpenAI` 发送。LangGraph 把模型选中的工具交给 MCP，Domain 按订单绑定读取并持久化 Observation。后续请求携带工具结果和观察 ID，最终正文经 `complete_chat_attempt` 写回原问题。历史资料可解释协议，当前业务结论取决于本轮可读的可信事实。[API](../../../../opspilot/web/app.py#L678) · [Worker](../../../../opspilot/web/worker.py#L511) · [Context](../../../../opspilot/assistant.py#L1176) · [模型调用](../../../../opspilot/assistant.py#L1266) · [MCP](../../../../opspilot/assistant.py#L1904) · [答复提交](../../../../opspilot/domain/chat.py#L2169)

基线为 `3ff5678a2f067ad2bef7945095395d26d59b5328`。总纲、AGENTS、评审 Skill Blob 分别为 `4850247350f71635d176699e304a5208d72adf0c`、`b606084799e463a6fb6ffeb6b18aa1f6b4afa64d`、`d405c8d413d633824b279202cc1503dab4cf0b03`。授权前的 `BLOCKED_BEFORE_PROVIDER_SEND` 及三项定向检查保存在执行提交的启动记录中。原始 HTTP、SQLite、授权与 Claim 留在私有运行目录，对应 SHA-256 在 [RESULTS.json](RESULTS.json)。本轮交回主 Agent 独立审查。
