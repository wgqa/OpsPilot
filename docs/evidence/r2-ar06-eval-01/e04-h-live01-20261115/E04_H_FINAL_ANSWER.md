# 能确定的内容

**1. 文档目录里确实只有 v1 和 v2 两个版本（本次检索确认）**

项目 `orders-protocol-review` 的授权文档范围内，`callback-retry` 家族只有两个版本：

| 文档 ID | 标题 | 版本 | 来源 |
|---|---|---|---|
| `callback-retry-contract` | Callback failure and retry policy v1 | 1.0.0 | local:orders-async-demo/contract-v1 |
| `callback-retry-contract-v2` | Callback failure classification and retry policy v2 | 2.0.0 | local:orders-async-demo/contract-v2 |

- 目录中**没有 v1.4**，也没有 1.4.x 的任何条目。
- 项目配置的契约版本是 2，最新可用契约版本也是 2（`latest_available_contract_version: 2`）。但这只是文档项目配置，**不能证明线上部署版本**。

**2. 两份文档对 retry 的解释确实不一致（已逐字比对）**

v1.0.0（第 1 行）：
> A 503 response with TEMPORARY_UNAVAILABLE is retriable. Retry state SCHEDULED and a trusted retry_at mean the sender will make another attempt… Contact the callback operator only when the attempt limit is reached and the trusted retry state is EXHAUSTED.

v2.0.0（第 1 行）：
> A 503 response is retriable only when the server records a retryable failure code and a current retry policy. Retry state SCHEDULED with retry_at is still pending. EXHAUSTED is actionable only when attempt_count reaches max_attempts and the failure response digest/event/request all match the current delivery row.

差异要点（比对结果 DIFF-001 / EVID-001，1 处 Root 段修改）：

- **可重试判定**：v1 是“503 + 特定码 `TEMPORARY_UNAVAILABLE` 即可重试”；v2 改为“503 只有在服务端记录了可重试失败码**且**存在当前重试策略时才可重试”，即从“按状态码/固定码判定”变成“按服务端记录 + 策略判定”。
- **SCHEDULED 的含义**：v1 说 SCHEDULED + 可信 `retry_at` 表示发送方会再试，应等待、不要并行重发；v2 说 SCHEDULED + `retry_at` 只是“仍待处理（pending）”，措辞更弱。
- **EXHAUSTED 的可操作性**：v1 只要求“达到尝试上限 + 可信状态为 EXHAUSTED”；v2 增加了 `attempt_count` 达到 `max_attempts`，并且失败响应摘要、event、request 都要与当前 delivery 行匹配。
- **字段层面**：v2 明确引入 `attempt_count` / `max_attempts` 作为判定参数（比对工具标注为“词法线索”，仅提示，不证明运行时已采用）；v1 只笼统说“attempt limit / attempt count”，没有这两个字段名。

**3. 可以确定的方法论结论**

- 两份文档都是**静态规范文本**，`deployment_version_verified: false`。它们只能说明“规范怎么写”，不能说明线上跑的是哪一版。
- 因此“发布记录写 v1.4”与“文档只有 v1/v2”之间，**不能**用文档目录去否定或确认发布记录；两者属于不同证据层。

# 缺口（目前无法确定）

1. **v1.4 是什么**：目录里没有该版本，无法判断它是笔误、内部构建号、未纳入本项目的分支版本，还是文档缺失。需要你确认发布记录里 v1.4 的出处（哪个系统、哪条记录、时间）。
2. **线上实际运行版本**：本轮没有任何运行时/部署观察，无法确认生产实际加载的是 v1、v2 还是 v1.4。
3. **retry 字段的运行时真实语义**：v1 与 v2 文本冲突，但哪一套在生效、`attempt_count`/`max_attempts` 是否真的被消费方使用，均未验证。
4. **v1.4 与 v1/v2 的关系**：是否存在 v1.4 的迁移说明、是否介于两者之间、是否已被 v2 取代，均无资料。
5. **调用方/消费方就绪度**：无法判断线上调用方、队列、消费者是否已采用 v2 契约。

# 建议的下一步（尚未执行）

- 若你想继续查具体订单/回调事件的实际重试状态，需要在页面上确认一个合法订单范围，我可以据此做只读查询；本轮我没有做任何业务状态查询，也没有创建工单或联系接收方。
- 若你想把“v1.4 与 v1/v2 的版本关系”作为正式问题追下去，我可以提交一个受控调查建议（仅记录建议，不创建任务、不授予权限），需要你在页面上核对原始问题与受信资源后明确确认。

另外提醒：在版本关系澄清前，不要按 v1 的“503 + TEMPORARY_UNAVAILABLE 即重试”或 v2 的“EXHAUSTED 即可操作”任一方单独下结论；两者对 EXHAUSTED 的可操作条件不同，误判可能导致重复重发或过早联系回调方。
