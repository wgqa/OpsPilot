# 阶段 A 实际四请求旅程

证据级别：确定性模型替身 + FastAPI TestClient 原 API + LangGraph/Worker + 真实 MCP stdio/本地 HTTP + SQLite。不是真实 Provider 或浏览器体验。

## 合法次序变体：knowledge

Task：`task-a99fd66d-5743-4a8c-8397-49fa06ae358c`；完整记录 `TRACE.jsonl:19`。

1. 用户：订单返回 200，但下游回调还未完成，请核实。

   实际持久答复：本轮同一事件 event-e0da9653-4b97-4831-bbc0-84ce53407b1a 接收状态为 QUEUED，来源 evidence-e83c89e6-e3d5-4a81-9240-94449b779570。

   source_message_id=`message-f406768d-9b0e-41e7-bd06-307960824c81`；Run=`run-d387a4a0-23e4-4985-9977-cd922d5e0c01`；累计活跃时间 `1774ms`。

2. 用户：请按当前绑定协议核对 HTTP 202 的含义，给出能核对的来源。

   实际持久答复：根据 receiver-ack-contract-v2@2.1.0，HTTP 202 表示受理，不代表处理完成；本轮投递证据仅证明受理。

   source_message_id=`message-25dbc84c-c92b-44a7-93f2-864983b8eba7`；Run=`run-c1-followup-bb495899-c4e2-4e7f-9aed-4e87bf4b6b8d`；累计活跃时间 `3236ms`。

3. 用户：你刚才引用的那份，为什么不能证明已经处理完成？

   实际持久答复：刚才引用的是 receiver-ack-contract-v2@2.1.0。它只约定 202 受理，不能证明接收方处理完成；当前状态须另取本轮事实。

   source_message_id=`message-c229a174-e7f2-406d-8ce1-d0bc358da1cf`；Run=`run-9177c5be-992c-439c-afae-35ae19b0ebca`；累计活跃时间 `3236ms`。

4. 用户：那现在这次回调完成了吗？请按新一轮事实核实。

   实际持久答复：本轮同一事件 event-e0da9653-4b97-4831-bbc0-84ce53407b1a 接收状态为 PROCESSED，来源 evidence-c34fda96-261c-48ce-8b6e-a70af04d7e7b。

   source_message_id=`message-86745cab-9587-4639-944f-c550607c4800`；Run=`run-c1-followup-f47771c5-27c8-43f0-b104-6d70f3b68c1a`；累计活跃时间 `4562ms`。

独立测试准备在第 4 次请求前将同 Event Receiver 从 QUEUED 改为 PROCESSED 并递增真实版本；该动作不是 Agent 工具或业务修复。Agent 本轮新 Observation 才支持 PROCESSED 回答。

总计 9 Investigator MODEL + 6 MCP，辅助 3 分类 + 1 Chat；旧 Diagnosis/Task/Control/审批与业务写表快照不变。新策略 24/18、Run 8/6 或 4/3、辅助 8 全部有剩余，未触发 300000ms 时间限制。

## 合法次序变体：delivery

Task：`task-90b0aceb-ed41-43ce-96f9-ca1363f9af13`；完整记录 `TRACE.jsonl:20`。

1. 用户：订单返回 200，但下游回调还未完成，请核实。

   实际持久答复：本轮同一事件 event-a0d36929-d43d-4a5d-ae86-253767f4256a 接收状态为 QUEUED，来源 evidence-a84adb5f-6d12-4258-aa17-ff49504a9f5a。

   source_message_id=`message-1c77b930-b89c-4647-a06e-fe61598613fe`；Run=`run-4fcff4d2-e7a8-42e6-a877-b04b999de330`；累计活跃时间 `1712ms`。

2. 用户：请按当前绑定协议核对 HTTP 202 的含义，给出能核对的来源。

   实际持久答复：根据 receiver-ack-contract-v2@2.1.0，HTTP 202 表示受理，不代表处理完成；本轮投递证据仅证明受理。

   source_message_id=`message-f347e7ba-b154-489c-842a-a8106b2a3a9c`；Run=`run-c1-followup-f61f5ac8-a155-49d2-b397-61d371942911`；累计活跃时间 `3226ms`。

3. 用户：你刚才引用的那份，为什么不能证明已经处理完成？

   实际持久答复：刚才引用的是 receiver-ack-contract-v2@2.1.0。它只约定 202 受理，不能证明接收方处理完成；当前状态须另取本轮事实。

   source_message_id=`message-99794c3b-93b0-4a24-aa62-f0562586e8c7`；Run=`run-fb2bf7a2-7be3-4e72-b76f-36a1eb2c80df`；累计活跃时间 `3226ms`。

4. 用户：那现在这次回调完成了吗？请按新一轮事实核实。

   实际持久答复：本轮同一事件 event-a0d36929-d43d-4a5d-ae86-253767f4256a 接收状态为 PROCESSED，来源 evidence-d2613d95-98ad-4605-9ddf-9f7105bb3659。

   source_message_id=`message-399e4d56-eb93-4df8-b6d7-8e1a663a0265`；Run=`run-c1-followup-3c90883b-6a52-41b1-9aaa-f7c6f6428b15`；累计活跃时间 `4549ms`。

独立测试准备在第 4 次请求前将同 Event Receiver 从 QUEUED 改为 PROCESSED 并递增真实版本；该动作不是 Agent 工具或业务修复。Agent 本轮新 Observation 才支持 PROCESSED 回答。

总计 9 Investigator MODEL + 6 MCP，辅助 3 分类 + 1 Chat；旧 Diagnosis/Task/Control/审批与业务写表快照不变。新策略 24/18、Run 8/6 或 4/3、辅助 8 全部有剩余，未触发 300000ms 时间限制。
