# M2-03 面试问答

## 为什么不能只靠 Idempotency-Key？

它只标识某个客户端操作。另一标签页、客户端重启或另一进程可能产生不同 key，因此还需要数据库业务唯一约束 `(tenant_id, task_id, handoff_kind)`。本地演示用两标签页和两个 OS 进程分别验证了这两层保护。

## 响应丢失后如何避免重复提交？

客户端先用稳定 operation ID 提交。即使 SQLite 已提交而 HTTP 响应丢失，页面也先 GET 回查；找到不可变 Receipt 后停止。若暂时无法回查，浏览器保留同一 ID。服务器对相同正文返回原 Receipt，对同 key 异正文拒绝。

## 为什么使用一个事务写 Queue、Receipt 和 Outbox？

它们共同代表“本地受控接收已发生”。若拆成多次提交，崩溃可能留下没有回执的队列项，或已显示接收却没有事件。事务内包含 Command、业务唯一记录、Task 投影和 Outbox，因此中间故障整体回滚；提交后丢响应则可幂等回查。

## 任务为什么可以结束，但系统又说业务没有恢复？

Task workflow 状态描述调查工作是否继续执行，`SCOPE_ESCALATED` 描述接收队列已收件，`RECOVERED` 描述业务调用成功。三者是不同的业务事实。M2-03 只实现第一类工作流结束和本地接收，不授予 Scope，也不做真实权限升级或业务恢复。

## 403 是否足以证明缺少授权 Scope？

不够。HTTP 403 只是一次响应。系统还要根据同一个 Request/Event 关联读取可信 Authz Decision，并核对资源绑定、主体、Policy、Grant 和当前版本；MCP 工具也只接受可信 TaskBinding 范围内的请求 ID。

## 更正与交接同时发生时由谁裁决？

Domain SQLite 的写锁和 TaskControl 版本负责串行化。更正先提交会使旧 Draft/控制版本失效，交接被拒绝；交接先提交后，已 COMMIT Receipt 是不可变历史事实，不会被之后终止或聊天操作擦除。

## 故障注入覆盖了哪些窗口？

测试在 Command 后、Queue 后、Receipt 后 Outbox 前注入异常，验证事务零残留；另在提交成功后模拟 HTTP 响应丢失，验证重放回查同一 Receipt。真实浏览器还让两个标签页对同一意图并发提交，并丢弃一个已提交响应。

## 这是不是 exactly-once 或企业审批？

不是。这里实现的是本地 SQLite 范围的原子持久化与幂等接收，不能宣传成跨网络 exactly-once。`local-scope-review` 是本地受控演示队列；M2-03 不包含远端 ITSM、真实接收人工作台、人工审批或 Scope 自动授权。
