# M4-01 冻结验收计划

状态：**FROZEN BEFORE IMPLEMENTATION**  
基线：`90c80fd57a85af5abc745c7602acd871646e4735`（本地 `main` 与 `origin/main` 一致）  
范围：仅 M4-01 对话驱动调查；不得开始 M4-02。

## 产品结果与权威边界

用户可以在同一 Task 的连续对话中提出普通追问、明确纠错或假设。普通追问与假设保留 `CHAT_READONLY` 语义；纠错先生成可审阅的提议，任务、控制版本、原消息和变更摘要均可见。只有 Task owner 明确确认后，可信 Domain 才以原始用户消息调用现有 `CORRECT_TASK_INPUT` / TaskControl，提升控制版本、阻断过期业务 Run/Plan，并创建唯一的新 Investigator Run。调查重新读取当前受信 MCP 事实；用户文字、模型分类和摘要都不是 Evidence、Gate、TaskBinding 或授权。

为把单次 Web 意图绑定到原始聊天输入，冻结以下 API 行为：

- `POST /api/tasks/{task_id}/investigation-updates/proposals`，以已持久化的 `source_message_id` 评估一次输入。`Idempotency-Key` 固定为该 source message ID。响应为结构化 intent；只有 `CRITICAL_CORRECTION` 才有可确认 proposal。
- `GET /api/tasks/{task_id}/investigation-updates` 返回该 Task 的持久评估和待确认提议，供刷新或重启后恢复界面。
- `POST /api/tasks/{task_id}/investigation-updates/{proposal_id}/confirm` 要求 `expected_control_revision` 和稳定 `operation_id`。`Idempotency-Key` 必须等于该 operation ID。确认只提交 proposal 绑定的原始用户消息，不接受客户端改写消息、Task ID、Actor、资源绑定或版本。
- `POST /api/tasks/{task_id}/investigation-updates/{proposal_id}/cancel` 持久取消提议，不创建 TaskControl 命令或业务 Run。

Proposal 响应需包含 `proposal_id`、稳定 `operation_id`、`source_message_id`、`target_task_id`、冻结时的 `expected_control_revision`、当前有效 Task 输入快照、原始消息及模型 `change_summary`。Model 不得提供或覆盖 server-bound 的消息 ID、Task、身份或版本。

具体错误状态以现有 Web 错误映射为准；无效身份/作用域、版本陈旧、终态 Task 和幂等键异载荷必须拒绝，且无新增 Investigator Run、ActionIntent、Ledger 或受限业务写入。

## 冻结场景与门槛

| ID | 场景 | 冻结结果 |
|---|---|---|
| M401-01 | 普通追问 | intent=`FOLLOW_UP`；回答完成；TaskControl revision、业务 Run 数、Plan/审批/动作状态不变 |
| M401-02 | 明确事实纠错，用户确认 | intent=`CRITICAL_CORRECTION`；确认前只有提议；确认后原消息以 `USER_INPUT_UNTRUSTED` 进入一个新 INVESTIGATE Run，TaskControl revision 增加一次，旧业务 Run/Plan 失效 |
| M401-03 | 假设、反事实、试探 | intent=`HYPOTHESIS`；不生成可确认的正式纠错，不改变 TaskControl 或业务 Run |
| M401-04 | 否定更正、同义表达、混合追问与纠错 | 否定/假设不生成提议；明确纠错加追问生成提议且两部分都保留原文；只允许确认清晰的 Task 输入纠正 |
| M401-05 | 同一确认重复点击/响应丢失后重放 | 同一 `operation_id` 回查相同 correction message 与 run_id；没有第二个 CORRECT_TASK_INPUT 或 Investigator Run；同键不同请求拒绝 |
| M401-06 | TaskControl 版本在提议后变化 | 旧 proposal 确认失败并标为 stale；不创建 correction message/Run |
| M401-07 | 取消提议 | 状态持久为 CANCELLED；刷新/重启后仍可见；TaskControl revision、业务 Run 数不变 |
| M401-08 | 权限、Task 状态与资源边界 | 仅被绑定的 SUPPORT owner 可确认；APPOVER、跨租户、错误 Session/Task、ABORTED/COMPLETED Task 均不能推进；客户端字段不能改 TaskBinding |
| M401-09 | 事实不变的 401 实验 | 用户确认更正后新 Run 重新真实 Probe；HTTP 401 仍为当前结果；Evidence/request_id 关联可信事实；模型不得迎合文字制造 403 或 READY |
| M401-10 | 受控准备后真实 403 实验 | 独立 fixture 准备被标记；新 Run 的 403 与 Authz Decision/Request ID 关联；Grant/Policy 来自 Domain；Agent 运行期不写 Scope |
| M401-11 | 浏览器刷新与 API 服务重启 | Task、proposal 状态、关联消息/Run 和最终 Gate/Evidence 可从同一持久库重新读取；恢复不重复创建 Run/动作 |

## 冻结判分

1. **Correct Handling**：M401-01..08 按表逐项通过；普通问题、假设和否定更正不正式改变 Task；模型结构化输出无效、越界或模糊时必须 fail closed。
2. **Actual Recovery / investigation progress**：M401-09 和 M401-10 都必须取得真实 Provider、真实 MCP、真实 HTTP 与可信 Domain 关联 Trace。对“不变”场景，成功结果是继续证明 401，Gate 必须由当前可信 Evidence 决定；对“事实变化”场景，成功结果是匹配当前 Authz Decision 的 403 诊断，不是业务恢复。
3. **Control Safety**：M401-02 的新 Investigator Run 必须只由 owner 确认后的 TaskControl 命令创建；所有负例不得产生越界输入、额外 Run 或副作用；运行期 Config/Grant/Policy/Scope 写入数为 0。M4-01 不产生审批、REPAIR、DELIVER 或 Handoff。
4. **Fresh evidence**：本阶段所有 pytest、前端检查、浏览器与服务重启记录需为本轮新鲜运行；旧 D/M3 报告只作为基线，不得拼接成 M4 PASS。
5. **阶段状态**：提交实现者只报告证据和已知失败；M4-01 是否 PASS 由主 Agent 独立裁决。

## 运行限制和继承问题

- 全程只在当前授权 M4-01 范围；不增加 MCP 工具、业务场景、Memory、Skill、多 Agent 或新写能力。
- TaskBinding 固定由可信 Domain 创建；确认的用户输入只能作为未验证调查线索。
- S1/S2 Gate、审批、ActionIntent/Ledger、E01-E10 与 M1-HF-01 不改语义，并执行既有安全回归。
- 上阶段报告把 M3 摘要 DAG 目标标为 PARTIAL；M3-HF-02 的两条历史 Worker retry 耗尽根因仍 `ROOT_CAUSE_NOT_PROVEN`。已记录的新鲜有限 Worker 检查不是历史根因证明；本轮不触碰这两项。
- M2-02 冻结的 Evidence TTL、Web operation id 与 Scope 授权门禁继续生效。本阶段不触及 S1 配置/工单提交，纠错命令使用其独立稳定幂等键。

## 预期证据

`REPORT.md`、机器可读 `RESULTS.json`、`GOLD.json`、真实脱敏 `TRACE.json`、未过滤的 `FAILURES.md`、每次原始 stdout/stderr、Provider 调用/Token、MCP list/call、HTTP request_id/Evidence/Authz Decision、TaskControl 与 proposal 行、截图、源码学习地图及面试问答。Trace 必须可从浏览器操作关联到 source message → model assessment → proposal/version → confirmation operation_id → correction command/message → INVESTIGATE Run → MCP observation → Evidence → Gate。
