# M4-CONT-UX-01 Stage B 集中收口报告

**状态：`INTERMEDIATE_IMPLEMENTATION`**  
**验收候选：未提交。** 真实浏览器验收仍为 `NOT_RUN / BLOCKED_BY_TOOL_ENVIRONMENT`，按既有 Computer Use 停止限制执行。  
**开发基线：** `main@e0ecb9463dcce8e1390a30f812d5f8b42cea9f4a`  
**冻结计划提交：** `020de9e4ab8763027614257559053b7963b3bc4e`  
**RED/测试提交：** `1f56d83e8abf0f218b70a8d389d8704e382d92cf`  
**源码实现提交：** `2bbb4e86286302597fc3d5085715ac407859d379`

## 用户现在可以完成什么

已持久化的初始 S3 调查答复、同 Task 的只读补查、正常 Chat 答复，以及已确认纠错后新 Run 的 `ANSWERED` / `PARTIAL` 答复，可以按可信来源挂在各自原用户问题下。未关联或不完整的来源不会被猜测为相邻问题的答案。撤权后的 S3 答复、诊断回执与来源继续被隐藏。

普通正文只显示调查结果、未完成状态和必要未知事项。Run、Message、Receipt、TaskControl 与未信任输入标识移入可展开的执行详情。刷新授权恢复时会明确重新读取会话消息。

本轮未执行浏览器旅程，因此以上是 API/投影和构建可证明的实现能力，不代表本次真实浏览器验收。

## 实施内容

1. `get_task_inspector()` 的 Runs 查询返回数据库受信的 `r.task_id`。S3 诊断摘要只在同一 tenant、TaskBinding、当前 Scope 的 SQLite 读取快照内，按不可变 `receipt_id` 查得其 `run_id`；Scope 失效分支仍不返回 Receipt 或诊断 Run 关联。
2. `InspectorRun` 用真实 API 字段精确建模，移除了该投影路径上 `as unknown as ConversationRun[]` 的假定。投影要求 Answer、Run、Task 与 `source_message_id` 一致。
3. 单一纠错来源解析器仅接受已确认、同 Task、同源问题、已应用至相同 Run 的正式纠错；Run 状态、持久调查答复、Follow-up、Chat Assistant Message、流式结果与诊断挂接复用该映射。原始 ID 与持久化来源不改写。冲突 Run ID 不参与关联。
4. 普通授权 Inspector 响应不再使并行消息请求失效。仅从已拒绝状态恢复授权时使旧消息读取失效；现有 `App.vue` 路径会紧接着发起一次新鲜会话消息读取。
5. 正文和工程来源详情分层；程序限制说明仍标为程序生成，`PARTIAL`、失败及待确认状态仍可见。

没有新增 Schema、Timeline 表、Domain Gate、权限服务、Runtime 或业务写能力。TaskBinding、S3 Gate、预算、Approval、TaskControl、ActionIntent、Ledger、Handoff 和历史回执均未修改。

## RED / GREEN 与回归

- 冻结的 4 项前端 RED：`0 passed / 4 failed`。覆盖 Answer/Diagnosis、纠错映射、Follow-up/流式映射、有效授权下并行消息刷新被误丢。原始日志：`runs/red-frontend-01/node-test.log`。
- 真实 API JSON RED：`0 passed / 3 failed`。FastAPI TestClient 返回的真实 Inspector Runs 没有 `task_id`，初始调查、C1 Follow-up 与纠错后最终 Answer 被投影为未关联。原始 JSON 和日志：`runs/red-api-01/`。
- GREEN 前端投影：`15 passed`（既有 11 项 + 4 项新增）。
- GREEN 真实 API JSON 集成：`4 passed`。包括初始调查/C1 Follow-up/撤权，实际 `/messages` Chat 答复一次性关联，正式纠错的 `ANSWERED` 与 `PARTIAL` 及诊断关联。
- 后端定向回归：`47 passed`，覆盖 Stage B API/S3 Scope、C1 Follow-up、M4 S3、TaskControl、Web Events 和 Event 进程恢复。最后补充的 Chat API 投影用例另在最终 closeout API 运行中通过（与该回归集的 closeout 模块有 3 项重叠）。
- TypeScript 检查、Vite 生产构建、改动文件 ESLint：最终运行全部退出码 0。
- 未运行全仓 pytest；未运行真实浏览器/DOM/SSE 刷新；未调用真实 Provider 或 MCP，也没有付费调用。确定性 Chat 完成和分类不应描述成模型智能效果。

所有新鲜命令、执行环境和退出码见 `RESULTS.json`；原始输出、实际响应 JSON 与失败运行保留在 `runs/`。`TRACE.jsonl` 从最终 TestClient 响应快照提取，不是手工合成调用日志。

## 限制与风险

- 本次只在确定性前端投影、真实本地 FastAPI API 响应、Domain 持久数据及本地 HTTP 取证辅助路径上验证。没有覆盖真实浏览器的可访问性树、截图、页面刷新或实际 SSE 连接，阶段 B 整体验收不能签署。
- 最终对话体验尚需在已批准且可用的浏览器环境完成；本轮没有任何 Computer Use 或替代浏览器自动化。
- 后端 47 项定向回归和新增 4 项 API 用例通过，但没有宣称全量 pytest 通过。
- 全部 RED、实现中失败与修正记录保存在 `FAILURES.md` 和对应原始运行日志；没有改写既有 Gold 或历史证据。

## 六问摘要（实施方）

1. **用户变化：** 持久的调查/聊天结果能回到确切问题下；未关联时不臆测来源。
2. **Agent 决策：** 本切片不增加 Agent 自主决策，也不调用真实模型；修复展示和来源关联。
3. **观察驱动：** Task 来自 Inspector Run 行；纠错仅依据已确认并应用的 Assessment/Message/Run 关系；诊断通过 Receipt→Run 的受信关联。
4. **新增约束与合法任务影响：** 只有精确来源链成立才显示为某问题的正式结果；合法授权刷新、新 Chat、Follow-up 与已应用纠错仍可显示。未知来源留在未关联区域。
5. **简化结果：** 统一一份纠错来源映射，不另建 Timeline/权限服务；将授权恢复后的读取接到现有刷新函数。
6. **证据与停止线：** 15 项前端测试、4 项 API 投影集成、47 项定向后端回归、类型/构建/ESLint通过；浏览器和全仓 pytest 未运行。停在 `INTERMEDIATE_IMPLEMENTATION`，交主 Agent审查。

