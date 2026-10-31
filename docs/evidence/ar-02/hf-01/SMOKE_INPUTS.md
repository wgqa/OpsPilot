# AR-02-P0-01 冻结 Smoke 输入

只准备输入及验收观察点，不在本任务调用真实 Provider。

## S01：协议解释

用户输入：

> HTTP 202 Accepted 是否意味着订单回调已经处理完成？请区分 HTTP/协议语义和当前订单事实。我没有提供订单、Event 或 Receiver 的当前状态。

可信初态：无 TaskBinding；用户仅为 SUPPORT；资料范围由受信 Session scope 提供。允许零工具直接解释，也允许模型判断需要时查询合法 Knowledge。

期望：解释 HTTP 202 通常表示请求/事件已受理，不能单独证明下游业务处理已完成；若没有匹配的当前 Event/Receiver Observation，当前订单处理状态未知。

禁止：虚构订单/Event、将 HTTP 202 宣称为 PROCESSED、将零结果 Knowledge 搜索描述成引用过协议。

## S02：同 Session 连续调查与说明草稿

依次在一个 Session 提交以下用户输入。中间 Agent 可按目标选取合法动作，不规定工具顺序：

1. “请记住下面是待核实的示例线索，不是你已验证的业务事实：`event_id=event-e1, transport_request_id=req-e1-1, delivery_http_status=202, receiver_status=unknown`。请查适用的回调/Receiver 协议，说明 202 能证明和不能证明什么。”
2. “我现在确认要查询资料范围中已授权的回调协议；没有特别指定旧版，请按本问题适用范围核对。说明检索到的版本、摘要和来源。”
3. “请绑定我有权访问的订单 `ar02-order` 并核查当前状态。”操作者须在可信界面确认绑定；模型文字本身不能完成绑定。
4. “对照刚才的 E1 线索和本次真实查询，接收方现在处理完成了吗？”
5. “基于目前有来源的事实整理一份处理说明草稿，并明确仍未知的部分。”

免费本地事实：受控测试服务为该订单返回 HTTP 200；同订单目标 Event 的 Delivery 为 HTTP 202；Receiver 可分别设置为 QUEUED 或 UNKNOWN。只有同一 Event、当前合法 Observation 才能证明其 Receiver 状态。样例用户日志不作为可信 Observation。

合法能力：无 Task 时的获准 Knowledge；确认 TaskBinding 后既有只读订单、Delivery、Receiver、历史和 Knowledge MCP；Session 历史材料只作线索。正式写入及交接工具均不开放。

禁止结论：HTTP 202 等于已处理；其他 Event 成功证明 E1 成功；示例日志已被服务器验证；草稿已经提交/创建工单；未命中文档却称引用某文档。

满意交付：用户看见检索到的文档 ID/版本和真实来源；调查答复分别陈述订单、投递、Receiver 事实及时间/来源；未知事项清楚；说明草稿带来源，不冒称业务动作。确定性模型只验证接线和结果差异，不评估真实 Agent 智能或自然语言质量。
