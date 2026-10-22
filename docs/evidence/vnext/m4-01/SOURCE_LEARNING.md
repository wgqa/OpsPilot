# M4-01 源码学习地图

## 用户动作到业务状态的路径

1. `frontend/src/App.vue` 显示聊天消息、分类结果、待确认纠错卡和历史状态。卡片展示原消息、目标 Task、Task 控制版本、变更摘要及建议输入；用户只能确认或取消已生成的提议。
2. `frontend/src/api.ts` 调用 `POST .../investigation-updates/proposals`、`GET .../investigation-updates`、`POST .../{proposal_id}/confirm` 和 `POST .../{proposal_id}/cancel`。API 绑定原始 `source_message_id` 与提议返回的 `operation_id`。
3. `opspilot/web/app.py` 从已认证会话解析身份，检查 CSRF、请求体和 Task 作用域，再进入 Domain。客户端不能指定可信 Actor、Tenant、TaskBinding 资源或版本。
4. `opspilot/domain/investigation_updates.py` 在可信身份和 Task owner 范围内读取原始持久消息与近期对话，调用真实 Provider 分类。返回值仅有 intent 和用户描述的 change summary；摘要、分类及正文都属于不可信输入。模型调用、响应 ID、Token 与请求/响应摘要被持久记录，重复评估复用原评估结果。
5. `opspilot/domain/task_control.py::admit_task_message` 是确认后的业务裁决入口。它在同一 Domain 事务中核验 owner、提议状态、原始消息摘要、Task 控制版本、任务状态和稳定幂等键，再以原始正文提交既有 `CORRECT_TASK_INPUT` 命令，阻断旧控制版本的 Run/Plan，并受理唯一的新 `INVESTIGATE` Run。模型不能写入用户确认之外的消息，也不能选择调查资源。
6. Investigator 新 Run 通过原有 MCP / Evidence / Gate 流程重查资源。`opspilot/domain/chat.py::get_task_inspector` 只投影可信 Domain 中的 Task、当前 Evidence 和 Gate。M4-01 对 `NOT_APPLICABLE` S2 记录作显示隔离：它不能覆盖当前 S1 Gate；已有 S2 Gate 决策仍按原有路径显示。
7. `opspilot/smokes/m4_01.py` 使用独立随机口令、独立 SQLite 与真实 Edge 浏览器进程启动 API/UI，随后直接关联 TaskBinding、TaskControl、消息、Run、Provider Trace、MCP Observation、Evidence、认证事件和授权决策。Browser 操作完成后会重启 API，再用同一个 Task/Session 查询持久结果。

## 需要掌握的设计取舍

- **对话和 Investigator 仍是两个 Runtime。** 普通追问和假设走 `CHAT_READONLY`，解释信息但不改变业务 Task。显式纠错先保留为聊天消息，再由模型给出狭窄的意图标签；只有用户在 UI 确认后，TaskControl 才把原始消息作为关键输入应用到新 Investigator Run。
- **模型分类是交互提示，不是权限。** 结构化 JSON 便于校验和展示，但模型可能误判或输出无效 JSON。因此服务端验证固定标签、键集合、长度、来源消息及当前版本；越界意图不形成可确认提议。所有业务绑定和授权仍由 Domain 决定。
- **明确修订前提和已知新值是不同情况。** 首轮真实 Gold 的两条漏判说明：用户可以明确撤回旧描述，同时要求工具查出新值。提示 v2 因此允许这类输入生成待确认候选；普通“再解释一下”仍是 FOLLOW_UP。原 8/10 和修正后 10/10 同时保留，不把十条固定样本称作泛化收益。
- **两阶段确认解决“检测意图”和“改变调查”之间的边界。** 候选提议先持久化但不改控制版本，用户确认后才调用 TaskControl。稳定 operation ID 支持重复点击/响应丢失回查；来源消息 ID 令同一句聊天只评估一次。并发竞争由 Domain 写事务决定唯一结果。
- **用户线索和真实事实分开。** TaskControl 记录纠错的接受版本与应用版本，MCP 重新读取真实资源。401 仍由 HTTP Probe 的真实请求证明；403 由 Probe、同一 Request ID 的 Domain Authz Decision、Scope Evidence 与 S2 DiagnosisReceipt 共同证明。用户所写的 403 本身不能构成 Evidence。
- **阶段命名不是合同扩张。** 本次用户授权沿用原 M4 总合同，将“对话驱动调查”作为 M4-01。M4-01 不增加新 MCP 工具，不提交配置、Grant、权限、审批、REPAIR、DELIVER 或 Handoff 写入，也不表示 M4 总体验收完成。

## 可复现实验位置

冻结标准在实现之前独立提交，见 `TASK_CARD.md`、`ACCEPTANCE_PLAN.md`、`GOLD.json` 和 `RUBRIC.md`。浏览器与 Domain 的新鲜运行按 `runs/web-*/` 保存，Targeted pytest 与最终全量 pytest 各有独立日志。原始失败仍保留在 `FAILURES.md` 所列的目录。

`python -m opspilot.smokes.m4_01_intents` 复跑冻结的十条 Provider 意图样本，经真实 FastAPI 鉴权和 Domain 持久化，关闭 Worker 以隔离分类本身；它不冒充浏览器或 MCP 实验。`python -m opspilot.smokes.m4_01` 才执行真实 Edge、Provider、MCP、HTTP、TaskControl 与重启旅程。
