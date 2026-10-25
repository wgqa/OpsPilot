# 前端最小时间线投影 · 待审设计

范围只覆盖当前 Session/Task 的连续调查，不增加 Domain 业务状态或新的消息存储。

## 已核实的现状

`App.vue` 先遍历 `displayMessages`，再遍历 `readonly_followups`，最后遍历 `investigation_answers`。因此不同存储类型无法自然交错。VS Web-03 保存的真实刷新可访问性文本中，初始问题→协议追问→协议 Chat 回答先显示，更早的初始调查答复在后面；对应截图也保存。这是历史真实 UI 原件，不是本阶段新浏览器运行。

当前 `displayMessages` 用“同 Task 最近的前一个 USER Message”推测 Assistant 属于哪次请求。现行 API 的 MessageItem 没有 Assistant 的 Run/source_message_id；仅凭时间、正文或邻近 sequence 无法可靠处理两个消息交错、迟到回答和正式纠错复制消息。当前 Run API、C1/初始调查结果已经有精确 source_message_id，可以直接复用。

## 唯一派生集合

建议在前端用一个 computed 生成 UI Entry，而不写一个新 Domain Timeline：

| 现有来源 | 稳定 UI key | 真实时间 / 关联 | 显示 |
|---|---|---|---|
| USER Message | `message:<message_id>` | Message sequence、created_at、task_id | 用户原文；初始/未验证补充标记 |
| Chat Assistant Message | `chat-answer:<answer_run_id>` | Message created_at + 已持久 Chat Run 的源 Message | 一份最终解释正文、形成时间、来源详情 |
| `s3_run_answers` | `investigation-answer:<run_id>` | source_message_id、created_at、report_ref | 初次/正式纠错调查答复，MODEL 或确定性事实降级清楚标记 |
| `c1_readonly_followup_runs` | `followup:<run_id>` | source_message_id、created_at/completed_at | 补查答复或非空具体缺口；result_state 与原因 |
| 更新提议/确认 | `update:<assessment_id>` | source_message_id、confirmed_at/cancelled_at、correction_message_id | 该问题的确认卡与处理状态；只一次原文 |
| 活跃 Run | `pending:<run_id>` | Run created_at、source_message_id、status | 在对应问题后显示“等待分类/待确认/补查中/解释中/可恢复”；最终产物持久后移除暂存项 |
| Chat chunks | `stream:<run_id>` | attempt_id+chunk_seq 去重 | 暂存片段；最终 Message 提交后被同 Run 的唯一最终正文替代 |

全局按**持久发生时间**排序；相同时按关联源 Message sequence、UI 类型固定顺序与稳定 ID 作 tie-break。每个答复显示“回复第 N 问”并可定位源 Message。不能按最后拉取时间、Date.now、数组到达顺序或字符串 locale 时间排序。运行中占位转最终记录是正常状态更新；同一已持久快照的刷新不能变序。

## 必要的最小读取补充

纯前端有足够的初次调查/C1 Run 关联，缺 Chat 最终 Assistant 的精确关联。推荐在现有 `GET /api/sessions/{sid}/messages` 中通过 `chat_run_answers → task_runs` 做只读 JOIN，为 Assistant 增加可空的 `answer_run_id`、`answer_source_message_id`。沿用原 Session owner、S3 当前 Scope 校验和撤权后正文隐藏；不返回 Prompt、Secret 或额外资源事实。

这是读取投影，不迁移消息、不新增表/状态、不修改 Chat 提交流程。旧客户端忽略新增字段；Taskless Chat 使用相同关联。若主 Agent 要求绝对纯前端，本阶段须标记晚答/并发关联能力未证明，不能继续用“最近消息”猜测并称验收完成。

## 防重复、纠错与历史当前性

- 一个 Run 只显示一个用户消费的回答。不要把正式 Diagnosis explanation、`s3_run_answers` 和 Assistant Message 的同一正文重复展开；正式 Gate/Receipt 摘要放现有 Inspector 或答案元信息，保留可查 ID。
- INVESTIGATE 的原 Chat Run 为路由 BLOCKED 时，只显示补查结果；不会把这个预期 BLOCKED 呈现成用户的第二个失败回答。其他非路由失败仍显示真实原因。
- 正式纠错原文与确认后 `CORRECT_TASK_INPUT` Message 是两个持久记录。仅在同一 assessment 的 source_message_id/correction_message_id 链接可核对时，投影为“原问题 + 已确认/应用到新 Run”一次正文；详情保留两个 ID/revision/time。两个独立相同文本的用户操作不得按正文折叠。
- 每个答复标“形成于某时，本 Run 当时的观察”。历史回执/答案不因刷新被标当前；新的当前性由 Domain 返回的有效状态控制。撤销/过期来源不能因 UI 缓存重新作为当前事实。
- S3 撤权后遵守服务端隐藏/拒绝结果，清除该受限结果的显示缓存；不能从旧 SSE 或本地消息副本重建被隐藏正文。APPROVER 的历史审计摘要权限不扩展成整个 Task 对话权限。
- SSE 至少一次事件只触发拉取；按 event_seq 去重。结果合并依稳定 ID，不按文本。刷新、重连和 Worker 重启不得调用模型或复制答案。

## 验证边界

后续阶段 B 用相同固定响应集打乱到达顺序、重复 SSE、延迟 Chat、纠错确认、失败/恢复和页面刷新，核对 UI key 集合、关联源消息、正文次数与稳定顺序。再用冻结真实三轮旅程核对截图/DOM、Provider 请求数和服务器记录；不能只测字符串模板。

当前 API 默认 Message 分页 100、Inspector Run 50/C1 结果 20 的边界足以承载本次 4 条用户请求；本切片不承诺无限会话历史合并或建设分页平台。Context 的历史压缩/截断与 UI 可阅读历史也不是同一件事；UI 完整记录不意味着模型上下文载入全部历史。
