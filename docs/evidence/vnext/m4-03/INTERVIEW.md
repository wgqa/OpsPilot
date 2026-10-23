# M4-03 面试问答练习

### 用户相比以前多完成了什么？

此前 S3 只能返回可信诊断标签。本轮用户能在同一个已绑定订单的 Task 中先澄清资源、持续调查、正式纠错并触发 TaskControl 新 Run，确认后把需要人工处理的案例提交到本地队列，得到可查询、可重放的 HandoffReceipt；重启页面和 API 后还能追问接收状态。

### 模型实际决定了什么？

模型理解用户的自然语言、在有限只读 MCP 工具里提出下一步、按需检索版本化知识或 Skill，并解释事实和结论。在 RHA 中 A 的下一工具会随新鲜的订单/投递/接收证据变化。模型不能绑定订单、指定任意 URL、改变 Evidence/Gate、决定交接资格、授权自己写入或声称恢复成功。

### 哪些事实和结果是可信程序证明的？

Domain 将订单绑定固定到当前租户已登记资源；工具经 MCP stdio 和业务 HTTP/接收端取得订单、事件、重试、队列事实并保留版本与关联 ID。确定 Gate 只使用当前有效 Evidence。交接由 SQLite `BEGIN IMMEDIATE` 事务复核 Task owner、Gate 和版本，并原子写入唯一队列项、Receipt、命令、Task 状态与 Outbox。`HANDOFF_ACCEPTED` 的语义严格停在“本地人工队列已接受”。

### 怎么防止把 202 误说成处理完成？

投递 HTTP 202 表示接收端接收/排队。独立 receiver Evidence 包含 event/order 关联、队列状态、accepted_at、处理 SLA。只要状态是 QUEUED，就不能说接收方已处理；超过冻结 SLA 时 Gate 指向联系接收方运营，而不是“已成功”。

### 用户更正如何让调查变化，同时不允许模型改业务身份？

先通过 Web 呈现差异并由用户确认，`CORRECT_TASK_INPUT` 写入可信 TaskControl，递增 control revision 并使旧 Run/诊断失效；新 Run 仍从 Domain 读取原始 TaskBinding，并重新请求当前 HTTP/MCP Evidence。纠错只改变调查输入，不改变订单绑定或权限。

### 如何论证 Memory 真正有用？

不能以 Context 中出现 Memory 作为收益。Task A 的审核案例实际出现在 Task B 的 DeepSeek 上下文，但 B 的正确结论和两次 MCP 查询与不使用案例一致；当前证据冲突后案例被剔除，撤销后后续 Provider context 给出 `MEMORY_REVOKED`，无关发票案例被双字组相关性排除。当前证据只证明安全的上下文控制，尚未证明经验降低成本或提高任务成功率。

### 为什么没有上向量检索或更通用的队列？

8 条冻结查询上，BM25-lite 与词法排序得到相同指标，且 v2 平均更慢约 0.047 ms；目前没有投资更重检索的证据。S3 只需要本地人工接收，所以复用 SQLite 和 Domain Outbox；生产分布式队列和 IAM 不在本阶段合同内。

### 这次实验有哪些明确局限？

Gold 只有 8 条，其中 2 条留出，能够比较稳定性但不能代表线上分布；R/H/A 都 8/8，不能据此宣称模型更准确。Memory 和知识排序语料也很小，Memory 的正确案例没有显示因果性能提升。S3 队列是单机 SQLite 演示，不等价于真实人员处理完成。Summary 实验使用隔离 fixture 注入来源 digest 变化，只证明失效路径，并未证明通用摘要压缩质量。
