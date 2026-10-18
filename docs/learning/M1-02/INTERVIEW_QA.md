# M1-02 源码追问卡

## 1. 为什么登录请求中的 actor_id 不直接成为可信身份？

`actor_id` 只是查 registry 的键；只有角色密码通过后服务端才签发随机 cookie。后续身份来自 `authenticate_session()` 的数据库记录，并且 TaskControl 再验证 tenant/role/owner。Header 伪造测试证明它不能覆盖可信身份。源码：`opspilot/web/auth.py`、`web.app.current_user`。

## 2. 为什么所有写请求要校验 Origin 和 CSRF？

浏览器 Cookie 会自动随同源请求发送。Origin 将写入来源限制到本地配置源；随机 CSRF token 只保存 digest，并通过 `X-CSRF-Token` 与当前会话 digest 比较。logout、Session/Task/Message/abort 均走相同写依赖。源码：`auth.check_origin`、`auth.verify_csrf`、`web.app.write_user`。

## 3. 首次 Task 创建如何处理响应丢失和并发重试？

`create_task_with_initial_run()` 在 `BEGIN IMMEDIATE` 中先核对 Session owner，再用可信资源配置建 TaskBinding，随后写 Message、Command、Run、budget 与 Outbox。事务唯一 idempotency key 加 canonical digest：相同请求返回原 IDs；异摘要返回冲突；任一步触发器失败时整个事务回滚。源码：`opspilot/domain/task_control.py`。

## 4. 为什么 Worker 不直接把 Task 状态改成“完成”？

它只调 TaskControl claim/finish 和现有 Investigator。Task/Plan/Approval/Action 最终状态仍由 Domain SQLite 更新；Graph checkpoint 只有运行续点价值。CHAT_READONLY 当前没有回答执行器，所以保持 QUEUED/NOT_IMPLEMENTED，不写业务 Task 终态。源码：`opspilot/web/worker.py`、`task_control.finish_task_run()`。

## 5. 单实例 Worker 是如何限制第二进程的？

同一 DB 路径映射到一个本机 lock 文件，进程先获得 OS 排他锁，再递增持久 `web_worker_state.epoch`。另一个进程拿不到锁就不能注册或恢复。Windows 强杀后文件锁释放有短暂延迟，启动路径做了有界重试；仍持锁时 fail closed。源码：`SingleInstanceWorker.acquire/register/release()`。

## 6. 重启时为什么不能一见 RUNNING 就盲目重放？

只有确认获得新 worker 排他锁后才能把旧进程 Run 改为 `INTERRUPTED_RECOVERABLE`。随后同一 `run_id` 使用原 checkpointer，并执行 TaskControl/D3 resume 授权。D3 的外部动作结果由 Intent/Ledger/Verification/Delivery 持久事实判定，Unknown 不从 Graph 推测成功。源码：`recover_running_task_runs()`、`run_investigation()`、`authorize_workflow_resume()`。

## 7. Outbox 与 SSE 各自负责什么？

Outbox 是 Domain 事务提交事实的一部分；projector 把它投影成持久 `session_events.event_seq`。SSE 只是传输。重连用 Last-Event-ID 读历史，不触发任何动作。旧已提交 Ledger 的 reconciler 只补事件。源码：`opspilot/domain/events.py`、`web.app.event_stream()`。

## 8. 如何证明这条链路真的调用模型和 MCP？

真实端口 smoke 读取 D2 持久尝试、模型 trace 的 model ID/provider response ID/Token usage、MCP observation 的工具名/状态/证据 ID；本轮得到 5 条带 Provider response ID 的成功模型 trace、另有 1 个进程退出时的 RESERVED attempt，4 次 MCP tool call。随后 Task 与 Run 都是 WAITING_APPROVAL，审批、Intent、Ledger、验证和交付计数均为 0。原始脱敏数据见 `docs/evidence/vnext/m1-02/logs/real-model-taskrun.jsonl`。
