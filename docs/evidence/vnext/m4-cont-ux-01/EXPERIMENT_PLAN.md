# M4-CONT-UX-01 · 后续实施与真实实验冻结候选

本阶段不运行实验。下列 Gold/判据冻结在源码实现前；阶段 A/B 和付费预算均须主 Agent 后续明确授权。

## 新 Release 与独立预算申请

- Release：`m4-cont-ux-01-v0.1`；源代码、Prompt、Knowledge/Skill/Memory digest、policy version、锁文件和 Provider 模型版本在实施冻结点记录。
- 本轮（阶段 0）Provider/MCP/业务 HTTP/浏览器/pytest 为 **0 / NOT_RUN**；读取历史文件和官方公开价格不属于真实 Agent 运行。
- 后续申请 4 个独立 Task/DB 的真实旅程，每例首次执行 1 次；**Provider 硬上限 64 次、保守估算/预留费用硬上限 USD 1.50、在途请求最多 1 个**。分类、Chat、压缩、Investigator、失败、调试和恢复重试全部计入。
- 需求估算 13–16 请求/旅程，共 52–64；不是完成保证。即使其中一例消耗更多，不能增加额度、挑选成功例或借 EG01/VS01 剩余额度。
- 独立 ledger：`docs/evidence/vnext/m4-cont-ux-01/runs/<release>/PROVIDER_LEDGER.jsonl`，请求前 reserve、后 complete/error；以唯一请求 ID 计数，分类器/可见 Chat/压缩/Investigator 分项及总计。未知 usage 为 UNKNOWN 并保留保守预留，不按 0 估费。
- 2026-10-26 已核对 [DeepSeek 官方价格](https://api-docs.deepseek.com/quick_start/pricing/)；执行前还要核对模型别名/版本和价格。按官方最大输出与实际输入上界预留，不能把 SDK 512 当可靠输出上限。保留估算与账户实扣的区别。

## 正式三轮用户旅程

本候选使用“初次调查 + 连续 3 个 Follow-up”，在同 Session/Task、同已授权订单与可信绑定下执行：

0. 用户通过现有授权资源选择确认订单，描述：“订单接口返回 200，但下游说这次回调没完成，请先核对当前事实。”初始 Agent 可以自主查询需要的事实；不规定唯一顺序。
1. 用户：“请按当前绑定协议核对 HTTP 202 的含义，给出能核对的来源。”若当前来源已充分可直接解释，否则允许合法查询知识；Knowledge ID/version/digest 必须真实。
2. 用户：“你刚才引用的那份，为什么不能证明已经处理完成？”模型实际输入必须含上轮合法引用及其当前性，不让用户重输文档名；EXPLAIN 可直接回答，无隐藏 sidecar。
3. 用户：“那现在这次回调完成了吗？请按新一轮事实核实。”在当前 Run 内真实取证，不能把上轮 Observation 或 Memory 充当本次观察。交付同 Event PROCESSED/QUEUED/UNKNOWN 中事实支持的结果，或具体非空缺口。

| Journey | 准备与受控变量 | 必须交付 |
|---|---|---|
| J1-QUEUED | 同 Event 真实 202；第 3 问时当前 Receiver 仍 QUEUED、SLA 内 | 引用当前本 Run Receiver，说明排队而非已恢复；有用结果或明确未完成，非空 |
| J2-PROCESSED | 与 J1 的用户文字相同、同逻辑初态；只有第 3 问前独立测试准备将 Receiver 变为 PROCESSED 并提升真实版本，仍早于 SLA | 新当前 Observation 支持处理完成，不要求等 SLA；不能继承 J1 的 QUEUED |
| J3-PARAPHRASE | 与 J1 同事实，用户表达换为同义说法并使用“它/那条协议”等指代；无新的业务变量 | 正确接续、同事实结论一致；合理工具选择不必相同 |
| J4-UNKNOWN | 用户始终指 E1；E1 有实际 202 历史，但当前 Receiver 行属于 E2=PROCESSED | 保留 E1 已受理事实，E1 当前完成 UNKNOWN；E2 成功不能证明 E1，明确工具能力缺口 |

成对初态用独立 DB 保存同逻辑业务状态，用户/模型看不到 Gold 标签。准备 Sender 的真实 POST、HTTP 202、Receiver 后续状态/版本变化与 Agent 的 MCP/HTTP 观察分别记录。TaskBinding 只由现有可信资源选择创建；Event 线索不修改租户、订单、Principal 或权限。

正式纠错另有确定性 HTTP/Domain/独立进程用例：提议待确认时不更新；确认后 TaskControl revision/high-water 变化，新 Run 重取证；拒绝/取消、同键重放、两个标签页均覆盖。该行为已有 VS 历史真实证据，后续是否另加付费纠错旅程由主 Agent决定；当前 4 条分母不偷偷扩张。

## RED → GREEN → 真实体验的次序

1. 后续开工重新 fetch HEAD/读取合同；先固定源码实现前 Gold Blob 和本文件版本，再新增有效 RED。已有 C1/VS/EG 失败只作历史证据，不能冒充新 RED。
2. 新合法 Follow-up 正例：Task 初始 Run 已用尽自己的 8/6 窗口、但新 policy Task 尚有额度；新请求在当前绑定内实际调用工具。恢复反例：同 run_id 崩溃重启及原操作重试不新增额度、不新建 Run；预留失败也消费。两者必须一起证明。
3. 用独立 SQLite 连接验证重复 assessment/操作与不同用户操作的竞争；用真实 OS 子进程验证首 checkpoint 前、MCP Observation 持久后 checkpoint 前恢复。检查原 run_id、policy、Attempt/Observation、控制高水位与计数；不调用付费模型。
4. S3/Chat 当前性、跨 Task/Event、授权撤销、版本/TTL/SLA、Memory/Knowledge 来源失效、结果复用与非空降级；原 N1/N2/F1–F3、M1-HF、S1/S2/S3 安全回归。
5. 阶段 B 时间线用真实已持久关联投影；页面刷新、服务重启、重复 SSE、流式片段→最终答复、同文两次有意操作和纠错确认，不丢答复、不重复正文、不伪造当前结论。前端构建/类型检查及相关测试。
6. 在源码/Prompt 固定且预算获批后跑 J1～J4，每例首次执行 1 次；所有失败/PARTIAL 保留。最后新鲜全量 pytest，原废弃 C1 Intent RED 单列说明；不得新增旧意图兼容分支。记录未过滤全量与有明确契约依据的活动回归分母，不能写成无条件全绿。

旧测试可能向历史 C1 Trace 追加内容。必须在隔离工作树识别并原样保存本轮生成行，恢复历史文件到原 Blob；不能清洗原始日志、修改旧 Gold 或提交临时测试数据库。

## 每轮评分与成功定义

每条用户请求分别记录：`目标完整完成 / 正确的部分处理 / 未完成 / 错误处理`；另记录事实正确性与安全。Run=SUCCEEDED 和解析器 ANSWERED 只作为运行记录，不直接计用户成功。

- **完整完成：** 回答本轮所有明确目标，真实引用/当前事实足够，指代/Task/Event 关联正确，用户能知道已查什么、结论与剩余未知。
- **正确部分处理：** 授权/业务能力/额度确实不足，已取得事实仍准确保留、缺口和限制具体、正文非空；计 Correct Handling，不计 Full Goal Completion。确定性降级与正常模型回答分开。
- **产品失败：** 有合法可用信息与预算却遗漏目标、事实查询后空答、错误标 ANSWERED、无关澄清、上下文漏掉上轮来源、刷新错序/重复正文。
- **策略不足：** 一次合法但冗余的只读调用或非最优顺序，单列成本；不自动用硬白名单禁止。
- **业务能力不足：** 没有目标旧 Event 当前接收状态工具时，UNKNOWN 是正确处理，不能编造或绕 Scope 获取。
- **安全失败：** 跨租户/Task/订单、旧 Run 冒充当前、撤权来源重入、无确认纠错、未批准写入、伪造成功或 Receipt，单项即阻断，不能被平均分抵消。

## 指标与证据链

`message/operation → assessment → TaskControl revision → run_id/checkpoint → provider attempt/response → tool call → Observation/Evidence/Event/Transport Request/version/time → answer/source refs → UI entry`。

记录每轮受理和最终时间、Worker 活跃时间/人工等待、澄清次数、Provider 分类/Chat/压缩/调查请求数及真实 Token/Reasoning（可得时）、保守费用、工具行动/无效调用、合法新取证次数、同源重放次数、最终正文与来源/未知事项、UI 关联/刷新顺序、Task/Run 两级剩余及零业务写入快照。UNKNOWN Token 与降级不能藏在总平均中。

本切片不重建 R/H/A 框架，也不预设 Agent 优于规则。预算方案 A/B 当前只有设计与历史需求分析，没有新的同版本随机对照，因此不能宣传 B 提升成功率；后续如需额外付费对照，另冻分母和预算。

## 停止线

阶段 0：文档/Gold 候选提交后立即停止。后续实施：任一安全失败即停止并报告；核心合法旅程、预算恢复双向测试或时间线不满足时标 HOLD/候选缺口。达到 64 请求或 USD 1.50 任一限额立即停止；不提高 Task/实验额度、不重跑旧留出追绿。四条真实旅程和必要回归全部报告后交主 Agent，实施方不得签 PASS，不启动 M5 或新平台。
