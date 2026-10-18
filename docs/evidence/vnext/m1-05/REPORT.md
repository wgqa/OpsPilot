# OpsPilot vNext M1-05 最终交付报告

- **任务范围：** Web 双角色审批、持久审批恢复 Run、原 LangGraph Checkpoint 恢复及真实 S1 受控业务闭环。仅实现 M1-05。
- **开发起点：** `main@688aad851d7677b3a03b420408d524a05d3103a9`。
- **实现提交：** `3a0a0f4d9448538def1d977f01403f4061cff548`（实现及完整证据）；本轮最新 main 提交 SHA 也在最终交付消息中给出。
**结果：** APR-01 至 APR-10 均有通过证据；完整 pytest、定向测试、真实 Edge/Provider/MCP/HTTP smoke 与前端/依赖检查通过。失败尝试和修复保留在 [`ATTEMPTS.md`](ATTEMPTS.md)。

## 实现与事务合同

`POST /api/tasks/{task_id}/plans/{plan_hash}/approval` 只接受 APPROVER 服务端会话，并由现有 Origin、CSRF、Idempotency-Key 和可信 Cookie 校验入口保护。Domain 的 `submit_web_plan_approval()` 在一个 SQLite `BEGIN IMMEDIATE` 事务内复核 tenant、submitter/approver 分离、来源 INVESTIGATE Run、WAITING_APPROVAL、TaskControl revision、无待处理关键更正、ACTIVE Plan、principal 状态和配置/主体/Policy 版本。审批、幂等 Command、唯一 `APPROVAL_RESUME` Run、`approval_resume_links` 持久映射以及 `PLAN_APPROVED/REJECTED`、Run 入队 Outbox 同事务提交。SQLite Trigger 故障注入已证明链接插入失败会回滚整笔审批和入队。

`approval_resume_links` 绑定 `approval_id / plan_hash / source_investigation_run_id / source_checkpoint_thread_id / resume_run_id / control_revision`，唯一键限制每个 Task/Plan 一份审批恢复映射，新 Run 只有一个可被 Worker 认领。恢复前 Domain 核验新 Run、原 Run、角色/所有者、审批、计划资格、控制 revision、Task 状态与 checkpoint thread 的派生关系；随后 Investigator 校验持久 checkpoint 的 Plan hash、stage 和 interrupt。新的 Run 是调度身份，原 checkpoint 是继续同一图的状态地址。审批后不重跑调查、不生成第二份 Plan。原调查 Run 保留 `WAITING_APPROVAL` 历史状态。

审批拒绝也写入同一持久映射并通过原 interrupt 恢复，生成拒绝报告但不创建 ActionIntent 或工单。Plan 取消、Task abort、关键纠错、资源版本变化和重复审批都在 Domain/TaskControl 门禁中拒绝过期续接。动作仍使用原 D3 ActionIntent/CAS/REPAIR/VERIFY/冻结 Report/独立 DELIVER 协议；没有 UI 旁路执行器。

## APR-01 至 APR-10 验收矩阵

| ID | 结果 | 证据 |
|---|---|---|
| APR-01 双角色与最小审核视图 | PASS | Edge 中 `support-a` 创建当前 S1 Plan、独立 `approver-a` 查看同租户冻结 Plan/Evidence；没有 Support Session 内容或凭据。测试覆盖未登录、跨租户、Support approve、缺 CSRF。截图见 [`approver-plan-review.png`](runs/20261018T100615Z/screenshots/approver-plan-review.png)。 |
| APR-02 原子批准与新 Run | PASS | `test_apr02_approval_resume_run_outbox_and_command_commit_atomically` 注入 link insert 失败并核实所有表/Outbox 回滚；同 key 重试与新 key 同决策返回同 approval/Run，异正文 409，第二审批者 409。机器映射见 [`RESULTS.json`](RESULTS.json)。 |
| APR-03 真实 Web S1 闭环 | PASS | Microsoft Edge 双角色真实交互；真实 Provider 5 次响应、MCP 4 次只读调用；同一业务 route 从 401 经获批 CAS 恢复到真实 200；配置恰好 v7→v8、REPAIR=1、DELIVER=1、Frozen Report=1、DeliveryRecord=1、TicketEntry=1。 |
| APR-04 拒绝且零业务写 | PASS | `test_apr04_rejection_resumes_original_graph_without_action_intents` 通过原 Graph 恢复拒绝决定；ActionIntent、Ledger、DeliveryRecord、TicketEntry 为 0，配置保持 v7。 |
| APR-05 竞态与旧资格 | PASS | `test_apr05_stale_resource_plan_and_abort_before_approval_fail_closed` 覆盖 stale version、abort 和 pending correction；`test_apr05_plan_cancel_blocks_queued_resume_before_checkpoint_access` 覆盖批准后 Plan cancel；`test_apr05_abort_after_approval_blocks_resume_before_checkpoint_access` 覆盖批准后、REPAIR 前 abort。既有 N1-11/D4 回归验证 REPAIR 提交后 abort 仍保留历史 REPAIR Ledger并阻断未提交 DELIVER。 |
| APR-06 重试、冲突与双审批者 | PASS | 同幂等 key 同请求稳定返回同 ID；同 key 异决定 409；另一 key 同一决定只回查原审批与 Run；第二同租户审批者不能新增审批、许可或 Run。 |
| APR-07 进程退出和恢复 | PASS | Edge 真实 API 子进程在审批事务 COMMIT 后退出码 86；另一个 API/Worker 子进程在 REPAIR COMMIT 后退出码 87；第三个 PID 恢复原 checkpoint 并完成 VERIFY/REPORT/DELIVER。最终仍恰好一个 REPAIR 与一个 DELIVER Ledger。 |
| APR-08 等待与活跃总时限 | PASS | 人工等待阶段原调查 Run 已释放；Support 只读追问不改 Task/Plan/控制版本或业务计数。C1 `active_elapsed_ms` 在只读追问前后均为 9,130，`active_started_at=null`，deadline=600,000 ms。 |
| APR-09 权限、泄露与未知结果 | PASS | 新增审批 API role/tenant/CSRF/自批隔离测试、readonly 聊天冒充批准 smoke、Action/TaskControl F1–F3 与 ACTION_OUTCOME_UNKNOWN 原回归均通过。结果界面从 Domain 收据推导；仅有审批或 `COMPLETED` 不显示为 DELIVERED。 |
| APR-10 全量、浏览器与学习材料 | PASS | 新鲜 `116 passed`；M1-05 审批定向 `7 passed`；Edge smoke 与真实 Provider/MCP/HTTP 轨迹通过；typecheck/lint/build、pip check、compileall、Node 语法检查均通过；学习地图、源码笔记与面试问答已交付。 |

机器可读矩阵、运行 ID、回执、token 数据和可验证事件摘要见 [`RESULTS.json`](RESULTS.json)。原始 Edge/API 日志和逐次运行快照位于 `runs/`；日志已脱敏。`.env`、Cookie、真实凭据、Node/venv、运行用 SQLite 数据库没有进入提交。

## 真实模型、MCP、HTTP 与业务回执

真实浏览器输入为“订单 API 在凭证轮换后返回 401，请调查当前事实。”模型 `deepseek-flash` 返回 5 个实际 Provider response ID，其中 4 次 Function Calling 依次选择 `get_integration_config`、`get_auth_policy`、`get_principal_status`、`probe_endpoint`；真实只读 MCP 返回四条匹配 TaskBinding 的 Evidence，最后一条为 `/api/orders/demo-order` 的 HTTP 401。Provider token 用量为 input=12,484、output=894、total=13,378（包含供应商可用的 cache/reasoning 细项），完整 response ID、tool digest 和逐调用 usage 均见机器结果。

计划 hash 为 `6704359197f2e5ec22dc78e5d535c9a1a6e997dc63c48424482f17405107364d`。独立审批人为 `approver-a`，初始 Task owner/support 为 `support-a`；执行器由服务端 Worker 配置绑定。source INVESTIGATE Run `run-6de351d4-2753-40a9-9854-0f994d4c142e` 在审批后仍为 `WAITING_APPROVAL`。新 `APPROVAL_RESUME` Run `run-972f609c-c06b-4210-a781-07c462066c15` 通过 revision 0 的持久 link 指向 checkpoint `opspilot-910c0cd0-a97e-4e42-b39f-72107a3599ed::run-6de351d4-2753-40a9-9854-0f994d4c142e`，最终 `SUCCEEDED`。

真实 ActionLedger 记录 REPAIR `COMMITTED`、配置 v7→v8，DELIVER `COMMITTED`。在线 VerificationReceipt 证明同一绑定身份及业务路由返回 HTTP 200，业务字段为 `order_id=demo-order`、`status=CONFIRMED`。此后冻结报告 `report-18796c34-01c0-46bf-a019-81b37a0318cc`，向 `INC-A-001` 恰好追加一个 TicketEntry；最终 Domain `business_outcome=DELIVERED`、Task `COMPLETED`。完整 outcome 截图见 [`support-delivered-outcome.png`](runs/20261018T100615Z/screenshots/support-delivered-outcome.png)。

浏览器路径截图：[`support-waiting-approval.png`](runs/20261018T100615Z/screenshots/support-waiting-approval.png)、[`approver-plan-review.png`](runs/20261018T100615Z/screenshots/approver-plan-review.png)、[`approval-response-lost.png`](runs/20261018T100615Z/screenshots/approval-response-lost.png)、[`support-readonly-while-waiting.png`](runs/20261018T100615Z/screenshots/support-readonly-while-waiting.png)、[`support-delivered-outcome.png`](runs/20261018T100615Z/screenshots/support-delivered-outcome.png)。审批响应丢失时 Edge 收到 HTTP 502 并提示稍后重查；Domain 已提交的 Approval/Run/Outbox 保留，新进程恢复后界面呈现最终 Domain 回执。浏览器路由切换期间一个 EventSource GET 被取消，之后 history 与 stream 均为 HTTP 200，投影事件序号 776 个且唯一、递增，没有触发副作用重放。

## 验证命令与依赖

```powershell
.\.venv\Scripts\python.exe -m opspilot.smokes.m1_05 --evidence-dir docs/evidence/vnext/m1-05
```

```powershell
$env:TEMP = (Resolve-Path .runtime).Path + '\m1-05-temp-apr2-20261018'
$env:TMP = $env:TEMP
.\.venv\Scripts\python.exe -m pytest -q --color=no --tb=short --basetemp .runtime/m1-05-pytest-apr2-20261018 tests/test_m1_web_approval.py
```

最终全量命令：

```powershell
$temp = (Resolve-Path '.runtime').Path + '\m1-05-temp-final2-20261018'
$base = (Resolve-Path '.runtime').Path + '\m1-05-pytest-final2-20261018'
$env:TEMP = $temp
$env:TMP = $temp
& .\.venv\Scripts\python.exe -m pytest -q --color=no --tb=short --basetemp $base
```

日志显示 `116 passed in 64.37s`。定向命令及实跑日志见 `pytest-approval-directed.txt`。前端新鲜执行 `npm run typecheck`、`npm run lint`、`npm run build`；Vite 生产构建 13 modules。另执行 `python -m pip check`、`python -m compileall -q opspilot tests` 和 `node --check frontend/e2e/m1-05-browser.mjs`，均通过。依赖锁文件仍为 `requirements.lock.txt` 与 `frontend/package-lock.json`，未引入新依赖。

运行环境：Windows 11 `10.0.26200`、Python 3.14.0、Node 24.16.0、npm 11.13.0、Microsoft Edge 155.0.4283.45；FastAPI 0.137.1、Uvicorn 0.49.0、Pydantic 2.14.1、LangGraph 1.2.16、SQLite Checkpointer 3.1.2、MCP 2.3.0、LangChain Core 1.6.12、pytest 9.1.1；Vue 3.5.44、Vite 8.3.4、TypeScript 5.9.3、vue-tsc 3.3.13、ESLint 10.0.1。锁文件哈希与逐调用模型数据一并列在 `RESULTS.json`。

## 失败尝试、已知限制与阶段边界

首轮全量 pytest 受 Windows 用户 Temp ACL 阻挡；改用仓库 `.runtime` 后新鲜全量通过。真实 Edge 开发过程中保留了 selector 错误、恢复重试耗尽、C1 断言错误和测试会话切换错误及修复；细节见 [`ATTEMPTS.md`](ATTEMPTS.md)。SSE 页面切换时记录的一次 `net::ERR_ABORTED` 属于 EventSource 关闭过程，重新连接 history/stream 均成功。

可信演示账号是本地 SQLite Demo 用户，不构成生产级 IAM。业务 HTTP 只请求项目的 loopback Demo API，不能代表外部生产服务、多实例队列或跨主机 Checkpointer 能力。M1-06、M2 和其他扩展未启动，等待主 Agent 审核本轮结果后再决定。

## Git 交付

本轮沿用用户已批准的单人 `main` 工作流：起点本地和 `origin/main` 均为 `688aad851d7677b3a03b420408d524a05d3103a9`。`开发目录/` 中预先存在的用户附件保持原样且未暂存。提交并推送后，分支、远端 SHA 和剩余未跟踪附件状态由最终交付消息复核。
