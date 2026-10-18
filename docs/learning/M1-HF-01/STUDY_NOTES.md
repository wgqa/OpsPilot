# M1-HF-01 源码学习笔记

## 恢复证据有两类

LangGraph Checkpoint 表示图执行到哪里；它不证明 REPAIR 或 DELIVER 是否提交。Domain SQLite 保存 Plan、Permission、ActionIntent、ActionLedger、在线 VerificationReceipt、冻结报告与 DeliveryRecord。进程在 Domain COMMIT 后丢失响应时，要对账同一 Plan 的持久回执，不能因 Graph 仍在旧节点就重复动作。

反过来，Domain 没有 Ledger 也不能单独证明可随意重建 Graph：Checkpoint 可能损坏/丢失，或只读 Probe 已发出而结果未知。冷恢复仅允许符合条件的初始 `INVESTIGATE` Run，并核对 owner/tenant、TaskControl、原始输入、纠错 high-water、预算和 Domain 阶段。发现 Plan 或动作痕迹便阻断；动作结果不明时保留 `ACTION_OUTCOME_UNKNOWN`。

## 三个修复边界

1. Worker 以单 Run 为异常边界。可恢复错误写入持久有限重试与退避；配置/权限错误使用受控码；旧 owner/epoch 不覆盖新状态。`CancelledError` 交由服务生命周期处理。
2. `task_control.py` 对审批恢复检查同 Plan 的资格和回执，再按 `VERIFYING`、`DELIVERY_PENDING`、`COMPLETED` 继续或对账；缺回执、取消、租户不符时 fail closed。
3. `investigation_context.py` 只读装配原始输入；`investigator.py` 确认 Checkpoint 不存在后才初始化同一 `thread_id::run_id`。已 apply 的纠错不重新消费、不增加 revision，且在 Prompt 保持 `USER_INPUT_UNTRUSTED`。预算和 Attempt 延续 Domain 数值，未知 Attempt 不被当作免费额度。

## 建议阅读顺序

1. `opspilot/web/worker.py`：owner/epoch、异常边界、失败分类。
2. `opspilot/domain/task_control.py`：事务门禁、retry、审批恢复阶段回执。
3. `opspilot/domain/investigation_context.py`：初始输入和 Domain 活动检查。
4. `opspilot/investigator.py`：Checkpoint 选择、Run 恢复、预算与 Prompt。
5. `opspilot/web/app.py`：API liveness 和 Worker health。
6. `tests/test_m1_hf_worker.py`、`tests/test_m1_web_approval.py` 与两个 `m1_hf_*_worker.py`：故障注入。

本地 SQLite 单实例测试不证明生产分布式锁、IAM 或外部服务 exactly-once。
