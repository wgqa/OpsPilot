# M4-01 面试问答

## 用户相比以前多完成了什么？

以前用户能在聊天里追问或补充线索，但补充文字不会成为同一个业务 Task 的正式调查输入。现在用户发出明确事实纠错后，工作台先生成一个可审阅的版本化提议；Task owner 确认后，同一条原始消息才通过 `CORRECT_TASK_INPUT` 改变 TaskControl，并触发一个新的 Investigator Run。刷新页面或重启 API 后仍能看到提议、确认结果、Run 和调查状态。

## 模型实际决定了什么？

模型只对最新聊天输入做狭窄分类：普通追问、正式纠错、假设讨论或越界请求，并为纠错生成简短变更摘要。它不决定用户是否有权改 Task，不决定提议版本是否仍有效，不设置 TaskBinding、资源、Scope、Gate、审批或 Run，也不声称用户描述的状态已经被证实。

## 哪些行为仍由可信程序控制？

认证会话提供 Actor 和 Tenant；Domain 关联 Task owner 与 Session；TaskControl 在事务中复核当前状态、revision、原始消息摘要、确认 operation ID 和幂等重放，再提交既有关键纠错命令。Worker 只执行新受理的 Run。MCP Server 从受信 TaskBinding 取得范围，Evidence Gate 根据可信事实作判断。用户消息和模型摘要一直标记为不可信输入。

## 哪些结果由真实证据证明？

401 组由真实 Probe 返回 HTTP 401、同一集成与主体上的认证失败事件和当前配置版本证明；确认用户声称“403”后，系统仍按新 Probe 维持 401 判断。403 组由真实 Probe、成功认证事件、同一 Request ID 的 Scope Authz Decision（DENY / `SCOPE_INSUFFICIENT`）、MCP Evidence 与 DiagnosisReceipt 关联证明。两组对照使用分别准备的隔离数据库；Agent 运行前后 Scope/Grant 不变。

## 为什么模型 Intent 不能直接执行 CORRECT_TASK_INPUT？

模型只是从聊天内容推断用户意图，可能把假设误判为纠错，也可能被提示注入影响。先展示提议、再由用户明确确认，随后由 Domain 复核身份、Task 状态、控制版本和幂等身份，避免分类输出越过可信边界。模型提供的是交互价值，TaskControl 提供的是状态裁决。

## 如何避免重复确认创建多个 Run？

提议与 operation ID 持久化。确认写入 Domain 时，TaskControl 用 `BEGIN IMMEDIATE` 竞争更新同一提议，并在一个事务里应用关键输入和创建唯一 INVESTIGATE Run。重放同一 operation ID 返回原 correction message 与 run ID；若版本已变化或提议已取消，则拒绝提交。

## 为什么纠错不修改 TaskBinding？

用户的自然语言只提供待验证线索。服务、集成、主体和路由由初始可信 TaskBinding 固定；如果聊天文本能直接改绑定，同一条消息就可把调查范围从授权资源移到任意资源。新 Run 会使用原绑定重新查询真实 MCP 事实。

## 401 和 403 两组实验区别在哪里？

401 表示认证未通过，S1 事实仍成立；403 组由测试准备程序在独立库中先把凭证配置到可认证状态，同时保留缺失的 `orders.read` Scope。Agent 本身只读调查。403 结论必须以真实授权事件与 Probe 的同一 Request ID 关联，不能从用户说了“403”或 HTTP 状态码单独推断根因。

## 如何验证任务状态不是前端临时状态？

状态写入 SQLite Domain。浏览器脚本先完成真实页面操作，随后终止并重启 API 进程，仍使用同一个数据库、Task 与 Session 重新登录并读取确认记录、控制版本及调查结果。截图记录页面，Domain Trace 记录持久来源。
