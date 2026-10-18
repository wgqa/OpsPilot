# M1-02 实施学习笔记

## 1. HTTP 身份是凭证，不是客户端声明

`POST /api/auth/login` 的 actor_id 只用于查本地 Demo registry；密码验证后签发随机 cookie，`web_auth_sessions` 保存 token digest、CSRF digest、可信 role/tenant 与期限。后续路由从 cookie 重建身份，再把 owner/tenant scope 交给既有 Domain 查询。`X-Actor-ID` 等 Header 不能改变身份。因为这是本机演示密码表，它展示认证与资源隔离流程，不代表生产 IAM。

实验：真实 Uvicorn 进程中的 `support-a`、`approver-a`、`support-b` 用独立 Cookie jar 登录；匿名读取是 401，跨租户读取为 404，Approver abort 为 403。伪造身份 Header 下 `support-b` 仍收到 404。

## 2. “创建 Task”是一个命令事务

客户端可能收不到 HTTP 响应，但服务端已经提交。单独调用 create binding、再写首条问题、再插 Run 会让重试创建多个 Task。`create_task_with_initial_run()` 把 Session scope 校验、TaskBinding、首 Message、Command、INVESTIGATE Run、C1 预算和两个 Outbox 事件放进同一个 `BEGIN IMMEDIATE`。canonical digest 让相同 key 重放原 IDs，让同 key 异请求冲突。Trigger 故障测试证明中途失败没有孤儿行。

首条自由文本确实持久化，但当前 investigator 的提示仍按固定 401 S1 逻辑构造，因此不宣称用户首条文本已经改变模型上下文；这留给合同里的后续阶段。

## 3. Worker 只占有执行，不拥有业务真相

后台 worker 从持久 QUEUED Run 读取工作，单机 OS 文件锁阻止第二个进程启动，数据库 owner epoch 为 owner 记录提供递增 fencing 标识。worker 调用既有 `run_investigation(..., run_id=...)`，由 TaskControl 校验 claim/revision；LangGraph checkpoint 只恢复进度，D3 仍从 Domain 的 Plan、Intent、Ledger 和 Receipt 判定副作用。等待审批结束当前 Run，释放推进占用；不自动批准。

OPS-01 实际在模型调用 attempt 与 checkpoint 已落盘时强制结束 Uvicorn 进程，新 owner 记录 `INTERRUPTED_RECOVERABLE` 后恢复同一 Run，最终到达 `WAITING_APPROVAL`。第一次恢复尝试暴露 D3 `revision=0` 的 `or -1` 边界；最小修复后完成了真实重启验证。

## 4. Outbox 是事实投影，不是执行队列

命令和 D3 事务先提交 Domain 事实，再同事务写 Outbox，并幂等投影到 `session_events`。event_seq 是数据库游标，不使用时间戳排序。浏览器只收到脱敏后的引用 payload；消息正文、Prompt、Authorization 和凭据不会进入 SSE。断线重连通过 `Last-Event-ID` 回放，至少一次投递由客户端按 event ID 去重。

N2-01 在子进程真实提交 REPAIR 后立即退出，新的 FastAPI 进程回放 `REPAIR_COMMITTED`；配置版本、Intent、Ledger、事件仍分别只有一次。N2-03 的历史 Ledger 数据是测试 fixture，只验证 reconciler 补事件、不写配置。

## 5. 总截止时间与单次超时是两种预算

C1 活跃时长保存在 `task_execution_budgets`，只累计 worker 正在调查的时段；审批/输入等待期间停表，恢复时沿用剩余值。MODEL≤8、MCP≤6 次调用预算仍由 D2 的 `d2_attempts` 持久累计。单次模型/MCP 超时不能代替任务整体 deadline。虚拟时钟测试跨过暂停和恢复，真实进程 smoke 另验证 attempt 计数跨 crash 不清零。

## 运行验证

真实端口脚本：`python -m opspilot.smokes.m1_web --evidence-dir docs/evidence/vnext/m1-02`。主要 HTTP/SSE、崩溃注入和模型轨迹见 [M1-02 证据报告](../../evidence/vnext/m1-02/REPORT.md)。
