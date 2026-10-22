# 冻结验收逐项证据映射

本表的 `AP-M401-*` 对应 `ACCEPTANCE_PLAN.md` 的验收行；`GOLD.json` 中的 M401 编号是意图输入样本编号，两者命名空间分开，避免把某条意图样本当成同编号业务验收。冻结文件未改写。本表记录实现者的实际执行证据，独立验收仍待主 Agent。

| 验收 | 本轮结果 | 核查入口 |
|---|---|---|
| AP-M401-01 普通追问 | 符合预期；只读回答、无提议、控制版本和业务 Run 数不变 | `test_m401_01_followup_is_explanation_only`；最终 S1 `JOURNEY.json.ordinary_followup` |
| AP-M401-02 确认纠错 | 符合预期；原文进新 Run，受理/应用版本为 1/2，旧排队 Run 受阻；真实 Web 旧 Plan CANCELLED | `test_m401_02_confirmed_correction_reuses_task_control_and_replays_once`；最终 S1 `JOURNEY.json.correction` |
| AP-M401-03 假设讨论 | 符合预期；无提议和业务状态变化 | 参数化 Hypothesis 测试；最终 S1 `JOURNEY.json.hypothesis` |
| AP-M401-04 否定、同义、混合目标 | 最终固定意图 Gold 符合预期；原 v1 两条漏判保留 | `runs/intents-20261022T171607Z-c0fa8d67` 8/10；`runs/intents-20261022T171819Z-ce631d9c` 10/10 |
| AP-M401-05 重复确认 | 符合预期；同一消息/Run 回查，不创建第二次关键输入；确认/取消并发只有一方获胜 | M401-02 重放、`test_parallel_confirm_and_cancel_have_one_atomic_winner`、评估重放测试 |
| AP-M401-06 提议版本过期 | 符合预期；409 TASK_CONTROL_STALE，无新消息/Run | `test_m401_06_stale_proposal_is_rejected_after_control_revision_changes` |
| AP-M401-07 取消 | 符合预期；Domain 持久取消、重新登录读取不改变 Task；未单独进行取消状态的 OS 重启实验 | `test_m401_07_cancelled_proposal_survives_reload_without_task_mutation`、取消/确认竞争测试；确认状态的实际进程重启另见 AP-M401-11 |
| AP-M401-08 身份/终态/资源边界 | 符合预期；拒绝 approver、跨租户、已终止、真实完成交付的 Task；绑定资源不变 | `test_m401_08_non_owner_cannot_assess_or_confirm_a_proposal`；新增 safety 文件的跨租户与两个终态用例；最终 DOMAIN_SNAPSHOT |
| AP-M401-09 事实不变 401 | 符合预期；新 Run 请求 `dded2cb7053fea53` 实际 401，S1 Gate 由当前事实决定 | `runs/web-20261022T172814Z/s1_401/TRACE.json` 与 DOMAIN_SNAPSHOT |
| AP-M401-10 独立准备真实 403 | 符合预期；请求 `3df5d6657b582e5d` 的 Probe/Scope Evidence/Decision/Receipt 一致；Scope 写入为 0 | 最终 S2 PREPARATION、TRACE、DOMAIN_SNAPSHOT |
| AP-M401-11 刷新/服务重启 | 符合预期；两组同库同 Task/Session/Run 读取；页面显示实际结束提示 | 最终两组 `SERVICE_RESTART.json`、`RESUME.json`、截图 03/04/05 |

新增 M4 定向 15/15 和最终全量 242/242 的日志分别在 `runs/targeted-03/pytest.log`、`runs/full-04/pytest.log`。确定性测试的分类模型替身只用于 HTTP/Domain 边界；Provider Gold 和浏览器运行另列，互不冒充。
