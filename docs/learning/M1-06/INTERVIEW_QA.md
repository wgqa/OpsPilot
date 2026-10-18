# M1-06 面试表达与追问

## 30 秒版本

我做的是一个固定 S1 认证故障场景的 OpsPilot 首切片：用户从 Vue 工作台描述问题，真实模型通过受限 Function Calling 请求只读 MCP，可信 Domain 用版本化 Evidence 决定是否生成不可变 Plan。独立审批通过后，系统从原 LangGraph checkpoint 恢复，靠持久 ActionIntent 和 SQLite 事务做 REPAIR，再用相同 service、integration、principal 和 route 实际验证 HTTP 200，最后冻结报告并用独立 DELIVER intent 写工单。M1-06 用真实 Edge/Provider/MCP、进程响应丢失、全量 116 个测试和原始证据核验这条链路；结果等待主 Agent 复核。它是本地单实例 Demo，不是生产 IAM 或分布式平台。

## 2 分钟版本

这套系统要解决的不是“让模型猜怎么修”，而是一个旧凭证引用导致订单 API 401、审批后可以安全改为当前凭证并证明恢复的业务任务。初始输入保存在 Domain；模型拿到带来源的上下文，只能选择 scoped MCP 只读工具。MCP Server 从可信 TaskBinding 得到 service、integration、principal 和固定 route，Domain 对租户及版本再做校验。Evidence Gate 是确定性逻辑，不读取模型结论作为授权。

Gate READY 后生成带内容哈希的 Plan。SUPPORT 与独立 APPROVER 通过 Web 操作；审批事务原子创建 Approval、唯一 `APPROVAL_RESUME` Run、原 checkpoint 映射和 Outbox。checkpoint 负责 Graph 进度，Domain SQLite 负责计划资格、权限和副作用事实。每个 REPAIR/DELIVER 第一次调用前都有自己的 ActionIntent；REPAIR CAS 更新配置，随后由相同身份与业务 route 的真实 HTTP 200 和订单字段验证。系统先冻结验证报告，再独立追加工单。

M1-06 的 fresh Edge Run 记录 5 个真实 Provider 响应、4 次 MCP tools/call、配置 v7→v8、业务 401→200、`demo-order/CONFIRMED`，以及一个 Repair 和一个 Deliver Ledger。审批提交后响应丢失、Repair 提交后响应丢失时都实际杀掉 API 进程，新 PID 从 Domain/Outbox/checkpoint 继续，最终业务回执各只有一份。另有独立 APR04 拒绝测试和 N1-09/10/11、来源撤销、预算、未知结果及 SSE 的新鲜回归。M1-06 的结论只是待主 Agent 审核的首切片整体验收，不意味着 M2/S2、长期 Memory 或 M4 已完成。

## 常见追问

### 模型输出为什么不能直接触发修复？

模型负责提调查方向和只读工具调用；TaskBinding、Evidence Gate、Plan 资格、审批身份、动作权限、版本 CAS 和幂等身份由可信程序及 Domain 决定。M1-04 中“我已经批准了”的聊天文本留在 CHAT_READONLY 路径；M1-06 结果显示它没有创建 Approval 或 ActionIntent。

### 为什么要创建新的 APPROVAL_RESUME Run，却恢复旧 checkpoint？

审批是新受理的 Domain 命令，要有幂等键、运行状态和 Outbox 事件；Graph 的执行位置却仍属于原 Investigation。`approval_resume_links` 将新 Run 绑定回来源 Run、原 thread、Plan、Approval 与控制版本，恢复前由 Domain 验证，避免重新调查另造 Plan。

### 这是不是 exactly-once？

不把本地 Demo 宣称为分布式 exactly-once。这里证明的是固定 S1/单实例/SQLite 边界内，先持久化 ActionIntent，事务内查同一 action identity/digest 和 Ledger；响应丢失后新进程查询权威回执并继续，实际没有重复 REPAIR 或工单写入。

### 第一次失败发生了什么？

首次 M1-04 浏览器 smoke 的 `approver-a` 登录和 pending API 都返回 200，脚本却等待已过时的 `.rail-footer`。首次 FAIL 保留并在修改脚本前先提交 amendment；随后仅改测试 helper 的角色页面 selector，用全新 DB 重跑，再在修复 commit 上跑完整 pytest。它不是产品权限或 API 失败。

### 真实验证依据是什么？

不是页面上写的“成功”字样：Domain Evidence 记录初始固定路由 HTTP 401；M1-05 的 VerificationReceipt 和实际返回体证明同一 service/integration/principal/route HTTP 200、`order_id=demo-order`、`status=CONFIRMED`。随后 ReportArtifact、独立 DELIVER Ledger、DeliveryRecord 与 TicketEntry 各有持久 ID。

### 目前最明确的边界是什么？

演示身份仅为两个本地可信租户/操作者，不是生产 IAM；业务只覆盖本地 S1 路由；没有证明分布式 exactly-once。D5 Memory 固定且通用，M1-06 未验证长期上下文压缩或 Memory 效果。D6 的 E10 仍 PARTIAL，其首次失败保留；D7 的首次 E01 和 61/64 测试失败也保留。M2、M3、M4 都未在本阶段启动。

## 证据定位

- 逐项判定及真实日志索引：`docs/evidence/vnext/m1-06/REPORT.md`、`RESULTS.json`、`EVIDENCE_INDEX.md`。
- 端到端跟读 trace：`docs/learning/M1-06/STUDY_NOTES.md`。
- 关键代码入口：`opspilot/investigator.py`、`opspilot/domain/task_control.py`、`opspilot/domain/d2.py`、`opspilot/domain/d3.py`、`opspilot/domain/events.py`、`opspilot/web/worker.py`、`opspilot/web/app.py`。
