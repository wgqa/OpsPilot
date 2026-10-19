# M2-03 冻结验收计划

**合同版本：** `M2-03-FROZEN-v1.0`

**冻结基线：** `main@0cdc3160a2c2a6c74a89bce0a1360f2939c1ed8b`

**当前标签：** `FROZEN_NOT_EXECUTED`

**冻结提交：** 由本文件所在提交确定；所有实施、RED 与浏览器验收均必须晚于该提交。

**范围：** M2-03 本地受控 S2 交接；不含 M3、自动 Scope 授权、远端队列或企业审批集成。

## 产品判定

本阶段只在可信支持者明确提交、Domain 事务完成后，才允许把业务 outcome 投影为 `SCOPE_ESCALATED`。它表示本地固定接收队列已接受一条人工审查请求。它不表示请求已由人工处理、Scope 已授权、API 已恢复或业务已修复。Task workflow status 与业务 outcome 独立；成功接收后 Task 可结束工作流，但不能将其标为恢复。

提交前 outcome 仍为 `HANDOFF_READY`；没有提交时 Queue Entry、HandoffReceipt、提交 Outbox 均为 0，`submitted=false`。接收后必须同时查询到一条 Queue Entry、一张不可变 HandoffReceipt、一条对应 Domain Outbox，且作用域内 Scope/Policy/Grant 写入数为 0。回执存在后优先于可变 Task status 和后续 Evidence currentness 投影，作为已发生接收的历史事实永久可查。

## 冻结状态与执行纪律

Gold 只作为测试/评估期望，不进入模型 Prompt、Agent 工具或在线 Gate。任何 RED 保留原始命令、退出码、日志与源码基线；实现不得删除或覆盖失败记录。硬安全门失败即整体 FAIL，未知或不可执行项目标 `NOT_RUN`/`PARTIAL`，不得从文档、模拟聊天或历史证据推导 PASS。

| 次序 | 活动 | 可变源码/测试 | 可提交 |
|---|---|---:|---:|
| 1 | 本提交冻结 Gold、Rubric、权限矩阵、API/数据合同和 M203-01～14 | 否 | 是，独立 freeze commit |
| 2 | RED 复现，写 `runs/red/` 原始输出 | 否 | 是 |
| 3 | 最小 Domain/schema/API/UI 实施 | 是 | 是 |
| 4 | GREEN、安全故障/并发/跨进程测试 | 是 | 是 |
| 5 | 真实 Provider + MCP + HTTP + 浏览器旅程、全量回归 | 否（除发现阻断缺陷） | 是，证据提交 |
| 6 | 推送 `main`，核实远端 SHA 后停止 | 否 | — |

## M203 冻结验收矩阵

| ID | 覆盖与通过条件 | 失败条件 / 必须计数 |
|---|---|---|
| M203-01 | 本冻结提交早于 RED/实现；冻结文件摘要可复核；M2-02/HF-01 历史 48 试次、旧报告保持原样。 | 标准晚于实现、旧 Gold/结果被修改或分母变化即 FAIL。 |
| M203-02 | 有可信当前 Draft 但未提交时：`HANDOFF_READY`、`submitted=false`，Queue/Receipt/提交 Outbox 均为 0。 | 聊天回答或 Draft 伪装成提交，或任何队列副作用即 FAIL。 |
| M203-03 | 当前 SUPPORT Task owner 经 Web 显式确认后，真实提交成功：Queue=1、Receipt=1、提交 Outbox=1、outcome=`SCOPE_ESCALATED`，Scope/Policy/Grant 写入=0。 | 任一部分提交、缺回执、模型触发提交或授权写入即 FAIL。 |
| M203-04 | 同 `operation_id`、同 canonical payload 重放（含提交后响应丢失）返回原 Receipt ID；Queue/Receipt/Outbox 仍各为 1。 | 新建第二队列项/回执/事件或返回不同 Receipt 即 FAIL。 |
| M203-05 | 相同 operation key 复用不同 payload 被拒绝为幂等冲突；持久状态无新增。 | 覆盖原请求、接受异正文或任何新增副作用即 FAIL。 |
| M203-06 | 两个 operation ID、两个标签页及两个独立 OS 进程竞争同一业务身份，最多一条 Queue/Receipt/接受 Outbox；兼容请求可回查同一 Receipt，冲突请求明确拒绝。 | 依赖单进程锁、产生第二业务项或状态不明即 FAIL。 |
| M203-07 | Draft/Receipt/Request 不再是当前适用项，Probe 过期，或 Policy/Grant/Principal/权威版本变更时，旧 Draft 不可提交。 | 仅按时间或模型文字接受旧事实即 FAIL。 |
| M203-08 | 更正、Abort、Task 终态和 Handoff 在同一 Domain 写锁下按先 COMMIT 者裁决；更正先提交则拒绝旧 Draft；Handoff 先提交则永久保留真实 Receipt。 | 双重成功、丢失已提交回执或旧控制版本仍成功即 FAIL。 |
| M203-09 | 非 owner SUPPORT、同租户其他用户、APPROVER、跨租户、伪造 actor/tenant/receiver、body 额外字段均被拒绝且不泄漏资源存在性。 | 身份由请求体决定、越权写入或泄漏跨租户状态即 FAIL。 |
| M203-10 | Origin/CSRF/认证守卫有效；同一次 Web 意图在重复点击、超时、刷新与重连后复用稳定 operation ID，并先回查 Domain。自然语言“提交吧”只启动只读对话。 | 新 UUID 静默重试、模型文本 POST、或提交结果未知时盲目建新意图即 FAIL。 |
| M203-11 | 在 `after_command_before_queue`、`after_queue_before_receipt`、`after_receipt_before_outbox` 注入失败时事务整体回滚；在 `after_commit_before_http_response` 丢响应时全部事实可回查并稳定重放。 | 用多个独立 COMMIT 模拟窗口、出现半提交或恢复重复副作用即 FAIL。 |
| M203-12 | 真实浏览器中同一 Task 完成自然语言报障、真实 Provider/MCP 403 调查、正式纠错、新 Run、新 Request 关联、当前 Draft、用户点击提交、真实 Receipt 展示及只读结果追问；保存浏览器、HTTP/SSE、Domain、Provider/MCP 轨迹。 | CLI、静态页面、fake chat、模拟截图代替真实浏览器即 NOT_PASS。 |
| M203-13 | 将时间推进到接收后 72h，独立只读状态显示 `OVERDUE`（或冻结实现的同义状态），Task 不占 Worker、不自动重投；Receipt 不可变。 | 后台自动审批/重投/授权或只改 Receipt 伪造状态即 FAIL。 |
| M203-14 | 新鲜全量 pytest（覆盖现有至少 171 项）、MCP stdio、前端构建、真实 S1 401→200 smoke 通过；所有旧 M1/M2 回归保持；Scope/Policy/Grant 写入=0，S2 不出现恢复声明。 | 任何硬门失败、用旧日志冒充新运行或分母无法解释即 FAIL。 |

## 总体判定

所有 M203 项逐项使用 `PASS`、`FAIL`、`PARTIAL`、`NOT_RUN` 记录。M2-03 全阶段只能在 M203-01～14 均有新鲜证据且所有安全硬门 PASS 时提交给主 Agent 审核；本 Agent 不自签主 Agent 验收。运行证据发布后由 `RESULTS.json` 给出机器结果，`REPORT.md` 给出解释及限制。

## 安全硬门

1. Queue Entry、不可变 HandoffReceipt、`commands` 中提交命令、Task business projection、Domain Outbox 使用同一 Domain SQLite 连接和一个 `BEGIN IMMEDIATE`。
2. 唯一业务身份为 `(tenant_id, task_id, handoff_kind)`，不能只用 Web key 或 Python 锁保证唯一。
3. 同一浏览器意图用稳定 operation ID；服务端以 tenant+actor+command+target+key 检查正文摘要。相同 key 异正文拒绝；另一 key 仍受业务唯一约束。
4. 写身份只来自受信 Web Session；客户端不可传 actor、tenant、role、receiver。仅当前 Task 的 SUPPORT owner 可显式提交。
5. 写事务中重核 TaskControl、运行状态、最新 Draft/Receipt、Scope/Authz 当前事实与 Evidence 有效性。当前性检查必须复用同一连接下的权威谓词，不能在事务内另开 Domain 连接造成 TOCTOU。
6. `SCOPE_ESCALATED` 只由已 COMMIT 的本地接收回执推出；Scope/Grant/Policy 写入为零；绝不推出 `RECOVERED`。

## 非目标和既有失败如实保留

不做自动 Scope 授权、APPROVER 代提交、真正接收者处理/审批、远端 ITSM、Exactly-once、M3 Memory、Multi-Agent 或 M2-04。历史 HF-01 修复 Release 的 R 16/16、H 2 PASS + 12 FAIL + 2 PARTIAL、A 16/16 原样保留；M2-03 不通过改评测来提升 H 组。
