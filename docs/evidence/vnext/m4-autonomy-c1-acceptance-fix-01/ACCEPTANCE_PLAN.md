# C1-REV1-ACCEPTANCE-FIX-01 验收冻结

**冻结基线：** `dddcacfea08c657c70888749dc96a1115b595d0d`  
**主线基线：** `main@77ea80e87e538f0f1fae8118ef231ec622601755`  
**候选分支：** `codex/m4-autonomy-c1`  
**冻结范围：** 只修复 `S3Nodes.report()` 中只读补查与模型预算耦合导致的 Diagnosis 写入缺陷。

## 合同与审查基线

- `PROJECT_NORTH_STAR.md`：从冻结基线重新读取，Blob `1f737712c7a36ceb34433ac09c3fbba3c3305542`；第 8 节要求硬限制同时验证危险路径和合法路径，并区分安全失败、产品失败和策略问题。
- `AGENTS.md`：从冻结基线重新读取，Blob `30319000ed0054007e9b7b6b46bf98b1493c8179`；要求以当前合同为准、保留历史失败，并执行真实日志和回归。
- 既有 C1 合同：`docs/evidence/vnext/m4-autonomy-c1/FROZEN_PLAN.md`、`REV1-ACCEPTANCE-ADDENDUM.md`。旧 Gold、历史 RED、REV1 报告和 Web/Provider/MCP Trace 均保持不变。
- 当前代码观察：`report()` 的 `readonly_followup` 路径与 `attempt_counts(...)["MODEL"] < MAX_MODEL_CALLS` 共用一个条件；条件为假时会执行普通 `persist_s3_diagnosis()`。

## 冻结验收用例

### FIX-01：Task MODEL 预算耗尽的只读补查

准备一个已有冻结 S3 Diagnosis 的 Task，创建并 claim 合法的同 Task 只读 INVESTIGATE Run，将该 Task 的累计 MODEL attempts 置于上限。直接执行该 Run 的报告节点。

通过条件：

- 不调用模型 Provider，也不超过预算。
- 只读追问结果被持久化为 `PARTIAL` 或 `NOT_COMPLETED`，含明确 `FOLLOWUP_BUDGET_OR_PROVIDER_EXHAUSTED` 原因。
- 不调用普通业务 Diagnosis 写入路径；Diagnosis 数量、已有正文和 digest 不变。
- Task 状态、TaskControl revision 不变。
- Approval、Plan、ActionIntent、ActionLedger、S3 Handoff Queue/Receipt 和 Domain Outbox 不新增业务副作用。
- 结果记录标记 `diagnosis_persisted=false`，来源仍关联原始用户消息与同一 Task/Run。

旧代码预期 RED：达到 MODEL 上限后绕过 readonly 分支并进入 `persist_s3_diagnosis()`，造成只读结果缺失或业务 Diagnosis/Task 状态变化。

### FIX-02：预算充足且已有当前来源时直接解释

在同一只读报告节点提供已经通过当前 Knowledge 版本核验的来源引用；预算有余量。模型解释被调用且不需要新增 MCP 工具调用。

通过条件：得到有来源的 `ANSWERED` 只读结果，不创建或修改正式 Diagnosis/Task 状态，不强制额外工具调用。

### FIX-03：预算充足时合法自主取证路径保持可用

新鲜运行既有 `test_follow_up_investigation_uses_real_mcp_and_persists_a_readonly_result`，用确定性模型替身验证合法选择 `search_callback_knowledge`、同 Run 观察和来源回答仍成功。该测试不是 Provider 自主性或真实模型证据，不固定通用的工具顺序合同。

## 实施边界

- 最小代码改动仅限 `opspilot/s3_investigation.py::S3Nodes.report()`：只读模式无条件返回只读结果；MODEL 预算仅控制是否尝试可选解释调用。
- 不提升模型预算、不重置 Attempt、不改 Prompt 语义、不加新 Guard/Runtime，不改 Gold、历史证据、TaskControl 或 Diagnosis 合同。
- E2E-02/E2E-03 和原 C1 冻结 RED 作为历史失败保持原样。新增验收日志置于本目录 `runs/`。

## 验收顺序与停止线

1. 先运行 FIX-01 与 FIX-02 定向 RED，保留原始输出和退出码。
2. RED 复现后提交最小源码修复。
3. 新鲜运行 FIX-01/02 GREEN、FIX-03 MCP 补查、S3/HF/TaskControl 关联回归及全量 pytest；排除只要求旧实现失败的历史预实现 RED 文件，并保持其原断言和日志不变。
4. 核对本补丁 Diff 只含必要源码、定向测试及本目录证据；提交并推送当前 C1 候选分支。
5. 停止于 `ACCEPTANCE_CANDIDATE`，由主 Agent 独立验收；不进入 C2/C3/C4。

