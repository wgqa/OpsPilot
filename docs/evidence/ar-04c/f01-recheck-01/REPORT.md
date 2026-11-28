# F01 真实模型定向复验

**执行结果：`PARTIAL_STOPPED_PROVIDER_LIMIT`；实施状态：`ACCEPTANCE_CANDIDATE`。** 四轮问题均已提交。前三轮有真实模型答复；第四轮工具读到了当前 `PROCESSED`，但达到 8 次 Provider 上限，模型没有机会读取该结果并形成最终答复。用户收到的是程序生成的限额说明。

## 用户实际得到什么

| 轮次 | 实际用户问题与结果 | 模型/工具行为 |
|---|---|---|
| 初次调查 | 询问回调协议、订单及处理情况。答复说明 HTTP 202 是接收、Receiver 为 QUEUED、当时未完成，并提供未提交说明草稿。 | 3 次真实 Provider；实际执行订单、Delivery、Receiver 和 Knowledge 四次只读 MCP。 |
| 历史解释 | 询问上一轮依据及本轮查询。答复正确表示**本轮没有新查询、当前状态未知**；但开头又错误地说“上一轮没有做任何新的查询”。上一轮实际执行了四次 MCP。 | 1 次真实 Provider，0 次 MCP。合法零工具解释没有被阻断，但时间指代仍有事实表述错误。 |
| 当前 QUEUED | 明确要求重新核实同一事件。答复基于本轮新观察说明仍是 QUEUED，区分 202 与业务完成。 | 2 次真实 Provider；实际查询 Receiver 和 Delivery，关联相同 Event / delivery_version。 |
| 当前 PROCESSED | 本地可信夹具将相同 Event 的 Receiver 从 QUEUED v1 改为 PROCESSED v2 后，以完全相同问题再次核实。用户收到程序的额度提示，没有模型最终答复。 | 2 次真实 Provider 后，实际 MCP 已取得 PROCESSED Observation；尝试第 9 次模型调用时被拒绝，所以这条 Observation **没有送达模型形成最终结论**。 |

第四轮的程序提示为 `PROGRAM_LIMIT`，包含 `AR02_LIVE_PROVIDER_LIMIT`，明确说未提交模型最终答复。它还写“本说明未重新取得业务事实”；同一 Run 实际已取得新 Observation，因此这句程序说明可能让用户误解，应与实际工具证据一起理解。

第二轮原答复及其他完整答复在 [JOURNEY.json](JOURNEY.json)。第二轮的新问题明确要求区分历史与本轮，措辞不同于原 LIVE 的 J4；本次对照不能单独证明原话下的 F01 已完全修好。原 LIVE `G7 ON FAIL` 不改写。

## 同 Event 证据

- Event `event-c1603aa0-e8b4-41c3-a701-3fc0b03e5467`；绑定订单 `ar04c-order`。初次 Receiver Observation `observation-405d4aa8-ff4c-43b5-9c76-539b4dd92418` 为 QUEUED。
- 第三轮 Receiver Observation `observation-d24a35c8-0890-4f81-bf4d-8b0de687f9e4` 为 QUEUED；对应 Delivery Observation `observation-fc1e016a-4ab9-429c-9701-19deb975f1e8` 为 ACKNOWLEDGED / HTTP 202。
- 第四轮 Receiver Observation `observation-b4690566-ca99-4a6e-9f7a-5390fb521a25` 为 PROCESSED v2，关联同一 Event。它是本 Run 的本地 MCP 结果，不是模型最终答复。
- 真实 Knowledge 调用返回 `receiver-ack-contract-v2` v2.1.0，Digest `5fb3732339600ad1332960df08a00299358b8c4ea47c20f6fedc39b568c9850e`。Memory ON 在 8 次实际模型请求中均选中一条经确认的历史经验；不据此宣称 Memory 带来收益。
- Observation 与 `d2_attempts.run_id` 的关联、时间、参数及来源见 [SOURCE_OBSERVATIONS.json](SOURCE_OBSERVATIONS.json)。测试夹具变化见 [FIXTURE_TRANSITION.json](FIXTURE_TRANSITION.json)。

## 执行、成本与边界

- Base：`08b007dda384b03a3b7d1ac6351d8c4ee1dcfb45`；实际模型执行源码：`85ae33818d3052301fcf6468f10de0956e68fb71`；分支 `codex/ar04c-f01-context-currentness-01`。
- 真实 DeepSeek HTTP 200：8 次；MCP `tools/call`：10 次。输入 44,850 tokens，输出 3,893 tokens；缓存命中输入 1,408 tokens。
- 账本按峰值、不依赖缓存折扣结算 USD **0.018130**，是应用侧估算而非供应商账单；单次预留 USD 0.668468，最后未决预留为 0。停止原因是**请求次数**而非 USD 5.25 总额。
- 8 次请求均选中已确认 Memory，Context 估算最高 9,371 / 12,000；请求携带 `parallel_tool_calls=false`。三次模型响应仍分别返回 3、2、3 条 Tool Call，实际 MCP 时间戳显示逐条执行；保留原始报文，不在本轮修补或重试。
- Claim 状态 STOPPED，旧 Claim 及状态文件哈希未变。隔离夹具只更新目标 Receiver 的状态和版本；其他受保护表内容与计数未变。没有外部业务写入、审批、Repair、交接或工单提交。
- [PROVIDER_HTTP.jsonl](PROVIDER_HTTP.jsonl)、[TRACE.jsonl](TRACE.jsonl)、[BUDGET_LEDGER.json](BUDGET_LEDGER.json) 和 [RESULTS.json](RESULTS.json) 保留真实响应、Completion ID、Usage 与失败；原始数据库、Checkpoint、Claim 和完整原始日志留在私有运行目录，哈希见 [PRIVATE_EVIDENCE_INDEX.json](PRIVATE_EVIDENCE_INDEX.json)。
- 预检为真实 API/Worker、本地 MCP、MockTransport：11/11；旧授权路径兼容 1/1。完整 pytest、浏览器与额外付费实验未运行。

## 六维摘要

**用户变化：** 本次真实模型能提供初次调查和当前 QUEUED 结论；PROCESSED 的最终用户答复未完成。

**Agent 决策：** 真实模型自主选择了 Knowledge、订单、Delivery、Receiver 与历史传输查询；没有预设工具顺序。

**观察驱动：** 模型主动查询了新状态；PROCESSED Observation 已取得但未送入下一次模型调用，不能声称模型依据它改变了最终结论。

**新增约束：** 新身份维持 8 次 / USD 5.25、一次性 Claim、授权和来源检查；离线测试覆盖合法及拒绝路径。

**简化结果：** 复用现有 Assistant、Worker、MCP 与账本，仅增加本实验身份和修正后的单次费用预留。

**证据与停止线：** 一次真实旅程，8 次 Provider 上限触发后停止；保留全部失败，不重跑、不改 Gold，不自行合并 main。

**最终提交：`ACCEPTANCE_CANDIDATE`，业务复验部分完成；交主 Agent 独立裁决。**
