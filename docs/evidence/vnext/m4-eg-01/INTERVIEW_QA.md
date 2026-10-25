# M4-EG-01 面试问答

## Q1：这轮用户能多完成什么？

用户可以把 APPROVER 确认的一个 Task 经验带入另一个 Task 的真实调查上下文，查看经验如何影响调查线索，并在当前事实冲突时验证系统不把旧案例当作新 Task 的事实。还可以在刷新后查看持久结果和当前性变化。

## Q2：模型实际作出了什么决策？

真实模型在 Task B 选择了合法的订单、回调、接收端、传输历史和 Knowledge 查询。早期调用实际选择了 Task A Memory；读到 Task B 的新 Event 证据后，后续模型 Context 将 Memory 排除。ON/OFF 一组成对实验中，二者最终诊断和工具序列相同，所以没有证据声称 Memory 提升了结果。

## Q3：为什么 HTTP 202 不代表回调完成？

202 仅证明接收端接受了请求。必须核对同一个 Event 的当前 receiver 状态；只有可信的同 Event `PROCESSED` 能证明接收处理完成。`QUEUED` 未超过 SLA 是继续观察，超过 SLA 是联系接收方排查，不是自动重试或业务失败证明。

## Q4：模型能够决定哪些事，不能决定哪些事？

模型可以选择 TaskBinding 内合法的只读 MCP 工具、调用顺序和 Knowledge 查询，并解释证据。Tenant、TaskBinding、Principal、授权、Evidence 版本/TTL、Gate、Memory 状态与业务副作用继续由可信程序控制。Memory 不会创建新审批、ActionIntent、Queue 或 Receipt。

## Q5：这次如何证明跨 Task Memory 真实进入模型？

浏览器创建 Task A Memory 候选，由 `approver-a` 确认后创建 Task B。Task B 的 `s3_model_contexts` 中实际 Provider 调用含 Memory ID 与来源 Task A ID；对应真实 DeepSeek Trace 有 Provider response ID。六条 Task B MCP Observation 独立关联 Task B Run。稍后 currentness 检查发现当前证据与历史案例冲突，Memory 被排除。

## Q6：ON/OFF 结果说明什么？

两组目标状态相同，结果均为 `RECEIVER_PROCESSING_UNCONFIRMED`，工具序列相同。ON 使用 33,249 tokens，OFF 使用 30,895，增加 2,354 tokens（约 7.6%）。这个样本说明 Memory 被真实读取，但没有证明它有净收益，因此不应该宣传准确率或推进率提升。

## Q7：如何保持历史协议和当前事实的版本边界？

Knowledge manifest 保存版本、摘要、来源和有效期；本轮追加协议 v2.1 文件而保留 v2.0 历史文件。来源失效会排除该文档作为当前依据。业务 Evidence 仍只按当前 Run 和 Gate 复核，不能从历史 Task 复用。

## Q8：本轮还剩什么没证明？

全量 pytest 仍有既有 C1 `READONLY_FOLLOWUP` RED；浏览器完整运行的自动化脚本在成功 Run 后因检查“最后一次调用仍选择 Memory”的过严断言退出。后续只读重访成功，但发生在 TTL/SLA 到期后。全量回归、浏览器即时有效结果截图和 Memory 的测得业务收益均不能标成通过。
