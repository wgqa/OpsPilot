# OpsPilot R4：主 Agent 对 R3 一致性复核的定向回复

**时间**：2026-10-17  
**收件人**：独立架构评审  
**回应范围**：只处理 R3 剩余 F1、F2、F3 和 C1–C5，不重开 B1/B3/B4/B5，不增加 P0 业务范围。  
**决定**：**F1 Accepted，F2 Accepted，F3 Accepted**。三项实现契约已经合并写入同一份 [`OpsPilot_v0.3_统一候选实施基线_待F1-F3定向复核.md`](OpsPilot_v0.3_统一候选实施基线_待F1-F3定向复核.md)，当前仍是候选稿，未实施、未运行测试、未下发 Luna。

## F1 — Accepted：选 Domain 持久 get-or-create Action Intent

**确定的方案**：以 `(tenant, task, immutable plan_hash, action_kind)` 作为唯一业务动作意图键，`action_kind` 只能是 `REPAIR` 或 `DELIVER`。首次业务发送前，Domain 在 SQLite 事务中 `get_or_create_action_intent`，保存不可变 canonical request JSON、由 Domain 计算的 request digest、`action_id` 和 idempotency key。Graph 崩溃后凭可信 task/plan/action_kind 再次取得**同一意图与相同请求内容**，不能在重启执行节点中创建新的 K2。网络 attempt_id 可以改变，但不进入稳定动作 digest。

**历史结果**：Domain Ledger 存 `result_json_or_ref`，不再只有 `result_digest`。首次 COMMIT 后响应丢失、Graph 尚未持久保存任何回执时，新进程可以按 Intent/Ledger 查询得到原 COMMITTED 结果。合法历史读取先检查当前读权限；已提交结果不因计划后来撤销而删除，也不会重新执行业务操作。同一 key 异摘要明确拒绝。

**验收**：E09 必须通过“持久意图已登记→业务提交→丢响应→杀 Agent 进程→重启原 task→找到原动作完整回执→继续真实业务探测，且 config version 只增加一次”。验证异摘要冲突拒绝。

## F2 — Accepted：Domain 权威计划执行资格 + 同库串行裁决

**确定的方案**：Domain 维护轻量 `PlanAuthorization.eligibility = ACTIVE / SUPERSEDED / CANCELLED`；它只描述本次 Plan 是否仍能发起新业务动作，**不是复制 Graph 状态机**。P0 支持可信本地发起人在业务动作尚未提交前取消或替换 Plan；取消/替换与 REPAIR/DELIVER 的业务 COMMIT 在同一个 SQLite 数据库事务控制下串行判断。

- 取消/替换**先提交**：即使 config/principal/auth_policy 版本没变化，旧计划的新 REPAIR 和 DELIVER 都不能提交。
- 动作**先提交**：历史 ActionLedger 回执保留；取消只能禁止后续**未提交动作**，不得对已经发生的副作用报告“未执行”或“已经撤回”。
- 已提交动作的原请求同 digest 重放只允许读取回执，检查当前读取身份，但不再次执行。
- `submitter`、`approver`、`executor_service` 分开定义，不能硬编码为同一 actor。
- P0 不承诺“按时间到期的审批”，只验证计划资格撤销和业务资源版本变化。

**验收**：E05/E08 注入“P1 已批→取消/替换提交→旧 REPAIR 延迟抵达，配置仍 v7”，要求零配置更新；反向时序先 COMMIT 再取消，应报告已发生的事实及可回查 Ledger。

## F3 — Accepted：两条独立许可、VerificationReceipt 与固定 Report

**确定的方案**：同一不可变批准计划产生两条动作许可 `ActionPermission(REPAIR)` 与 `ActionPermission(DELIVER)`，分别消费。修复 COMMIT 消费 REPAIR，但不能阻断后续 DELIVER。DELIVER **不再检查修复前旧配置版本**；需要校验同一 task/plan 的已提交 REPAIR Ledger、可信 Online Verifier 保存的真实业务验证回执、不可变 ReportArtifact、工单目标及字段白名单，以及当前仍有效的 Plan/权限。

**报告固定点**：在线真实业务探测成功后，Verifier 独立保存 `VerificationReceipt`（task/plan/repair_action/同一 principal/integration/业务路由/时间/版本/业务断言）。Report Builder 据此 `get_or_create_report`，**先持久化**第一版 report_ref、version=1、content_digest、verification_ref 和不可变正文，然后才能预登记 DELIVER Intent 和外发。不能因为重启生成新报告版本绕过去重。

**交付提交**：Domain 在一个事务中检查许可与回执，向指定工单追加本任务处置记录，同时写 `DeliveryRecord + ActionLedger + DELIVER permission consumed`。同 delivery key + 相同 digest 返回已有回执；相同 key + 不同报告正文、版本、引用或内容摘要返回 `KEY_REUSE_CONFLICT`。修复成功、交付失败只重试 DELIVER，不重做 REPAIR。

**验收**：E09 检查 REPAIR 已消费后 DELIVER 仍能正常提交；交付 COMMIT 后响应丢失重启仅一条工单记录；跨 task/tenant 验证收据或报告不可用于交付；拒绝批准零受限配置修改和零未经授权工单写回。

## C1–C5 的一并处理

| 项目 | v0.3 明确口径 |
|---|---|
| C1 | P0 **启用持久化 attempt 预留计数**（含失败/重试），工具总预算 6、模型调用预算 D1 smoke 后锁定；人工审批等待不消耗活跃调查 wall-clock 期限；token 只记实际可得用量。 |
| C2 | Gate 只有 `READY / NEED_MORE / INCONCLUSIVE / NO_ACTION`；`WAITING_INPUT` 与 `DENY` 在外部任务/策略层；动作结果未知用 `blocked_reason=ACTION_OUTCOME_UNKNOWN`。 |
| C3 | 任务恢复和每轮模型输入重新检查 Memory 撤销/版本/过期；实时事实查询必须留证据和计预算，不把程序门禁后台查询冒充模型自主调查。 |
| C4 | Domain 事务内读取、比对同库可变版本及许可，任何业务版本更新单调递增；禁止等待 LLM/MCP/HTTP/审批；BUSY/rollback 有明确失败处理。 |
| C5 | **此轮仅做设计文档。** 真正发布 v1.0 时再同时同步项目 README、TASKS、AGENTS，统一入口并修正引用路径；`credential sidecar` 改称工具侧本地凭证模块，不增加服务。每日提醒与实际代码仓库状态需在发布时核对。 |

## 请求第三方的最后一轮定向复核

只需检查下述三项，不必重新评价选题或整体主 Graph：

1. F1：新进程是否总能在旧 Action 已提交但 Graph 丢失回执时，重取原始 ActionIntent 和完整结果？同键异内容是否封锁？
2. F2：Domain 的 ACTIVE/SUPERSEDED/CANCELLED 与动作 COMMIT 是否形成清楚的先后分界？是否有已取消计划还能新提交的遗漏路径？
3. F3：REPAIR/DELIVER 授权是否独立消费？报告在 DELIVER **首次业务发送前**是否固定，重复提交是否只能附加一次且可追溯在线恢复证据？

如果三项成立，请返回：**“F1–F3 设计契约闭合，认可 v0.3 升版 v1.0；可以在同步实施入口后交 Luna D1 任务。”** 若仍有阻断，请只指出具体步骤、条件与 E05/E08/E09 的失败时序。

**本轮结论仅代表设计修订，不代表实际运行通过。** 在获得定向确认之前，仍不启动 Luna 全面开发，也不把 `v0.3-candidate` 冒称为冻结版。
