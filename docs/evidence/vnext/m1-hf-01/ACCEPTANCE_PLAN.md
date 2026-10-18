# M1-HF-01 冻结验收计划

**状态：FROZEN BEFORE HF TEST EXECUTION**  
**冻结基线：** `main@8e7c48ad9a8fa0fff51c0cf69d3717eeaac62842`  
**冻结时间：** 2026-10-18（Asia/Shanghai）  
**任务卡：** `开发目录/OpsPilot_vNext_Luna_M1-HF-01_ACE48996E5A1AEE6A2A4E7BA99E59A90E4AEA4E4BB8AE5A1.md`  
**范围：** 只修复第三方审计确认的 M1 P1 恢复缺陷和同根因 Worker health 假阳性。M2-01、S2、Knowledge、Skill、Memory、外部业务系统、多 Worker 与新架构均不在本轮范围。

## 基线与执行边界

- 本地 HEAD 与 `origin/main` 均核实为 `8e7c48ad9a8fa0fff51c0cf69d3717eeaac62842`，当前分支为 `main`。
- 起始 tracked 工作树干净。`开发目录/` 中既有的未跟踪交接资料（含本任务卡）是用户资料，保留原样，不纳入提交。
- 冻结标准提交前未运行本轮测试、故障注入、真实 Provider 或浏览器 smoke。
- `task_controls`、TaskBinding/Run、审批与动作回执仍由现有 Domain SQLite 授权；LangGraph checkpoint 只作执行位置。任何恢复先通过 Domain 与 TaskControl 校验，唯一 action identity 和已提交回执必须可核对。
- 回归优先采用新鲜 SQLite、确定性故障注入和真实独立 OS 子进程；不调用付费模型。若真实模型/浏览器 smoke 实际执行，再单独记录本轮新鲜证据。
- 原版 RED 只记录实际执行的失败；不能复现时标记 `NOT_REPRODUCED` 并给出限制，不从任务卡描述伪造失败日志。第三方指出的三个 P1 作为已报告缺陷背景，不能冒充本地 RED。

## HF-01～HF-10 冻结矩阵

| ID | 冻结输入与故障点 | 必须满足的 PASS 判据 | 预期定向测试 / 证据 |
|---|---|---|---|
| HF-01 | 旧 Run 为 `INTERRUPTED_RECOVERABLE`，预算耗尽且所属 Task 已 ABORTED；队列中另有正常 Task。 | 旧 Run 在当前 Worker fence 下安全终止或权威拒绝；不改写 Task `ABORTED`；Worker 不退出；第二 Task 实际处理完成可观测。 | `test_hf01_aborted_expired_recoverable_run_does_not_starve_next_task`；Run/Task/health/outbox 状态与子进程日志。 |
| HF-02 | 与 HF-01 类似的旧 Run 因正式关键纠错和控制版本变化而失效；纠错 Run 与旧 Run 调度交错。 | 旧 Run 不续执、不创建新 Plan/Intent/Ledger；纠错 Run 可推进；其他 Task 可调度；控制 revision 与 pending/applied high-water 保持一致。 | `test_hf02_stale_run_after_correction_is_blocked_and_new_run_progresses`；Run、TaskControl、Plan、Ledger、事件快照。 |
| HF-03 | Run 保持 `QUEUED` 时发生缺模型配置、非法执行身份或等价 pre-claim 错误；另一个健康 Run 等待执行。 | 失败被 owner/epoch fence 保护的持久机制分类记录并有限退避/终止；不高速反复选中同一 Run；第二 Run 实际推进；不虚增 Provider/MCP 成功。 | `test_hf03_preclaim_failure_is_bounded_and_worker_continues`；retry_state、事件、选择次数、第二 Run 状态、脱敏 Worker health/log。 |
| HF-04 | Web `APPROVAL_RESUME` 在 REPAIR Domain COMMIT 后、调用方收到回执前抛 Python 异常或真实子进程退出。 | 相同 Plan 与 Source Checkpoint 恢复；REPAIR Ledger=1、Config v7→v8 一次；恢复到同身份在线 VERIFY、冻结 Report、DELIVER；最终工单/TicketEntry=1，无二次 REPAIR。 | `test_hf04_approval_resume_recovers_after_repair_commit`（Python 故障）及独立进程复现；比较 Plan/Run/Checkpoint/Ledger/Receipt/Report/Delivery IDs。 |
| HF-05 | 同一续跑链路在 VerificationReceipt 成功后、冻结 Report 后各中断。 | 回执和报告按同 Plan 幂等复用；无重复写配置/工单；报告存在时继续 `DELIVERY_PENDING`，无验证回执时不得冻结/交付或跳过验证。 | 参数化 `test_hf05_approval_resume_recovers_after_verification_or_report_commit`；阶段前后 Domain 快照、Run 状态、原始失败日志。 |
| HF-06 | DELIVER Domain COMMIT 后、响应前中断；Task `COMPLETED` 而 `APPROVAL_RESUME` 尚未 `SUCCEEDED`。 | 仅在同 Plan 的 COMMITTED REPAIR、成功 VerificationReceipt、冻结 Report、COMMITTED DELIVER、DeliveryRecord 与 TicketEntry 全部核对通过后完成 Run 收尾；Action/Ticket 身份及数量不变。不完整时 fail closed，不报告成功。 | `test_hf06_approval_resume_reconciles_committed_delivery`（完整/缺回执负例）与真实子进程 crash；所有稳定 ID 与 count。 |
| HF-07 | 初始 Run 已 claim 为 `RUNNING`，首个 Graph checkpoint 创建前真实子进程退出。 | 新 Worker 核验 owner/tenant/TaskControl/Run/revision/输入/预算/Domain 进度后，以同一 `run_id` 和 `thread_id::run_id` 合法 cold-init；不新建 Task/Run/Plan、不重置预算。 | `test_hf07_claim_without_first_checkpoint_recovers_same_run_in_new_process`；两个 PID、checkpoint thread、Run 与预算快照。 |
| HF-08 | `apply_pending_critical_inputs` 已提交，消息为 `APPLIED_TO_RUN`，首 checkpoint 尚未创建即退出。 | 从原受理 Message/Command 与 `task_run_inputs` 的真实 source ID、sequence、digest、tenant/owner/revision/high-water 装配输入；不再次 apply、不额外增加 revision；新 Prompt 能看到纠错且 provenance 仍为 `USER_INPUT_UNTRUSTED`。 | `test_hf08_applied_correction_survives_precheckpoint_crash_without_reapply`；独立进程、DB 前后快照、实际模型入参或确定性 Prompt 捕获。 |
| HF-09 | 恢复前注入 abort、revision/pending 变化、Plan CANCELLED、跨租户身份、不同 Plan/Approval，及潜在已产生动作结果但回执缺失/不一致。 | 所有授权/作用域/版本不一致 fail closed；缺失或冲突回执保持 `ACTION_OUTCOME_UNKNOWN`；禁止 APPROVAL_RESUME 无 checkpoint cold-start，禁止重复副作用。 | `test_hf09_resume_negative_matrix_fails_closed`（必要时拆分多个用例）；断言 checkpoint 访问、Run/Intent/Ledger/配置/Ticket 变化均符合门禁。 |
| HF-10 | Worker 正在运行、Worker Task 已退出、`start_worker=False` 时分别请求 `/api/health`。 | API liveness 与 Worker 活性/就绪分开表示；配置开关不得被当作运行证明；退出可见为 degraded/not-ready；仅限本地单实例语义，不宣传生产监控。 | `test_hf10_health_reports_api_and_worker_liveness_separately`；HTTP 响应 JSON、事件循环 Task done/cancelled 状态及锁 owner。 |

## 固定执行与停止规则

1. 本文件先提交到 `main`。随后新增定向 RED 测试并在原版代码上运行；原始 stdout/stderr 原样保存在 `docs/evidence/vnext/m1-hf-01/logs/`。只对真实复现的失败标 RED。
2. 先处理 HF-01/02/03/10 Worker；再处理 HF-04/05/06/09 审批恢复；最后处理 HF-07/08 首 checkpoint 恢复。每次源代码修复前先保留该项 RED。
3. 若实现需要触碰审批权限、TaskControl 原子裁决、Plan 或 REPAIR/DELIVER 完成语义，停止并提交设计变更说明。不得删除现有校验，不得重新创建含潜在动作的 Graph。
4. 每个子进程窗口保存 PID、exit code、注入点、源/恢复 Run、Plan/checkpoint 与 Domain 回执 ID；对失败和重试分别留档，不覆盖。
5. 最终复跑 HF 定向、既有 M1 全量 pytest、D1–D7/N1-09/10/11/APR-01…10/F1–F3/D4 相关回归。再跑 `compileall`、`pip check`、`git diff --check`；若改前端则另跑 typecheck/lint/build。
6. 每项只有在有本轮新鲜日志且判据满足后才标 PASS；缺环境/未执行/未复现用 `PARTIAL`、`NOT_RUN` 或 `NOT_REPRODUCED`。M1-HF-01 交付不代表 M2 放行；完成后停止等待主 Agent。

