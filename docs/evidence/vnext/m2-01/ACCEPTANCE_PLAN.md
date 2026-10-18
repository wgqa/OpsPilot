# OpsPilot vNext M2-01 冻结验收计划

**冻结状态：** 本文件与同目录的 `S2_GOLD.json`、`S2_RUBRIC.json`、`TRACE_SCHEMA.json`、`DEFERRED_GATES.md` 必须先于任何 S2 功能测试、S2 实现或数据库迁移提交。此提交只冻结合同，不表示功能已实现或通过。

**基线：** `main@715ccfa797d833d089a495cae67d1866a1a85a5a`
**范围：** M2-01 / S2FACT-01～09；真实授权事实和只读 MCP。M2-02/M2-03/M3/M4 不在本轮。

## 1. 业务结果合同

评估记录始终分开记录 `run_status`、`task_status`、`business_outcome` 和证据质量。HTTP/API 与 MCP facts 测试没有业务 Investigator Run 时，前两项写 `NOT_APPLICABLE`，不能通过制造 Run 状态解释业务结果。

- S1 的 `REPAIRED_VERIFIED` 只表示原 S1 Plan 经授权 REPAIR 后，同一 TaskBinding 身份对固定 route 的真实业务 HTTP 200 与订单字段核验通过；交付再单独记录。S1 语义不可被 S2 改写。
- S2 阶段定义供后续阶段使用：`DIAGNOSED` 需有受信诊断与 DiagnosisReceipt；`HANDOFF_READY` 仅表示冻结草稿；`SCOPE_ESCALATED` 必须有真实持久 HandoffReceipt。任何 S2 结果都不能记为 `REPAIRED_VERIFIED`。
- M2-01 只验证服务端 Authn/Authz/HTTP/MCP facts，不实现 Agent diagnosis、DiagnosisReceipt、draft、HandoffReceipt 或 queue。因此本阶段 S2 评估记录的 `expected_outcome` 与 `actual_outcome` 均固定为 `NOT_IMPLEMENTED`；`result_status=PASS` 只表示对应的事实契约断言通过，绝不表示业务 Outcome 已完成。
- `NOT_RUN`、`PARTIAL`、`UNVERIFIED`、`NOT_IMPLEMENTED` 保持原值，不折算成 PASS。安全维度不采用平均分抵消失败。

## 2. 冻结的评估记录与 Rubric 引用

每个 case 的结果必须至少含以下键，字段类型/枚举见 `S2_RUBRIC.json`：

`case_id`, `scenario`, `release_ref`, `run_status`, `task_status`, `expected_outcome`, `actual_outcome`, `evidence_completeness`, `evidence_validity`, `diagnosis_correctness`, `forbidden_writes`, `receipt_integrity`, `trace_ref`, `failure_reason`, `attempt_id`, `result_status`。

`release_ref` 必须包括：Git SHA、Python 版本、锁文件 SHA-256、model ID（本阶段为 `null`）、Prompt/Skill/Tool Schema 版本（不适用时为显式 `not_applicable`）、Gate/预算策略版本（不适用时亦显式填写）。结果评估只读 Gold；Gold 不得进入在线 MCP/API 或模型上下文。

Rubric 独立评分 `evidence_completeness` 与 `evidence_validity`。HTTP 403/404 不是 diagnosis correctness。只有服务端 Authz Decision 与相同 request/tenant/principal/service/route、当前 Grant/Scope Policy 版本、可信 TaskBinding 都关联且有效时，`evidence_validity=CURRENT`。旧版本只能标 `STALE`，关联冲突标 `CONFLICT`；事实不足不得记作有效 Scope 根因。

## 3. Gold 不变量

Gold case 的真实事实必须由隔离测试数据库的 Domain 表、固定真实本地 HTTP route、服务端事件及 MCP 查询共同产生。JSON Gold 只作为离线期望判据，不能被运行时代码读入、返回或用作答案。Scope fixture 写入只允许在计数基线建立前的受控 setup；计数开始后 S2 请求路径对 Grant 与 Route Requirement 的 INSERT/UPDATE/DELETE 必须为 **0**。

- 有效凭证 + ENABLED principal + 缺失 required scope：真实 HTTP 403；Authn accepted；同 request_id 的真实 Authz Decision 为 `DENY/SCOPE_INSUFFICIENT`；当前 `scope_policy_version`、`grant_version` 相符且 Domain scope 差集非空。凭证认证用的 `auth_policies.policy_version` 另记为 `credential_policy_version`，绝不与 Scope Policy 版本混用。
- 无效凭证或 DISABLED principal：HTTP 401；认证先失败；不得生成或返回 `SCOPE_INSUFFICIENT` Authz Decision。
- 有效凭证 + ENABLED + scope 满足：真实 HTTP 200，订单 `demo-order/CONFIRMED`，Authz `ALLOW`，Grant/Scope Policy 版本相符；Credential Policy 版本另行关联。
- 路由未知、同租户资源缺失、跨租户/错误 TaskBinding：只允许保守非枚举响应；客户端/Tool 不泄漏被隐藏资源、内部 scope 差集或其他租户是否有对象。404 单独不能形成资源不存在结论。
- Grant/Scope Policy 更新后，对旧 decision/evidence 的查询标注 `STALE`/`CONFLICT`；request_id、event_id、身份、route 或版本不匹配不产生可信当前诊断。
- MCP 是 TaskBinding 下只读查询。`tools/list` Schema 不接受 tenant、任意 URL、Authorization/token、Grant 或 Scope 写入参数。合法调用事实与 HTTP/Authz/Domain 行一致；错资源/跨租户以非枚举受控错误拒绝。
- S2 无 scope mutation endpoint/tool，M2-01 运行期授权表写入计数为零。没有 Handoff/Diagnosis receipt，Outcome 均为 `NOT_IMPLEMENTED`。

## 4. 冻结验收矩阵 S2FACT-01～09

| ID | 预置输入/真实动作 | 必须观察到的 PASS 条件 | 计划定向测试 / 证据 |
|---|---|---|---|
| S2FACT-01 | 新鲜 S2_SCOPE_DENIED DB；有效凭证真实 HTTP 请求 | 403；Authn accepted；可信 Decision `DENY/SCOPE_INSUFFICIENT`；同 Request/Event 与当前版本；missing scopes 非空；写计数 0 | `test_m2_01_s2fact01_http_403_has_current_scoped_authz_decision`，HTTP/Domain Trace |
| S2FACT-02 | 无效凭证、旧 S1_DISABLED 及新 S2 fixture 的真实请求 | 401；认证先于授权；不产生错误 SCOPE_INSUFFICIENT；S1_DISABLED 原语义保留 | `test_m2_01_s2fact02_authn_failures_remain_401_before_scope` |
| S2FACT-03 | S2_SCOPE_ALLOWED 的真实请求 | 200；`demo-order/CONFIRMED`；Decision ALLOW；事件与 scope policy/grant 版本匹配 | `test_m2_01_s2fact03_scope_allow_returns_order_and_bound_decision` |
| S2FACT-04 | 真实未知路由/订单、跨租户 TaskBinding 与越域标识 | 非枚举拒绝；不暴露隐藏资源；没有成功敏感查询或 Scope/Handoff 写入；404 不单独判根因 | `test_m2_01_s2fact04_hidden_and_cross_tenant_resources_are_non_enumerating` |
| S2FACT-05 | 先采集 Decision fact，再仅在 setup 中递增 Grant 或 Scope Policy 版本；错配 request/event | 旧事实 STALE/CONFLICT，不再称为当前；冲突关联不会成为有效 SCOPE_INSUFFICIENT | `test_m2_01_s2fact05_old_or_unmatched_authz_facts_are_not_current` |
| S2FACT-06 | 独立 MCP stdio 子进程 `tools/list`+`tools/call`，含合法及越域输入 | 实际 stdio 调用；仅 TaskBinding 只读 Scope/Authz 参数；结果与真实 HTTP/Domain 对齐；越域受控拒绝 | `test_m2_01_s2fact06_stdio_scope_facts_are_task_bound_and_read_only`，脱敏 stdio Trace |
| S2FACT-07 | 原有 S1_POS、S1_DISABLED、TaskControl、D3 与 M1-HF-01 全套 pytest；新鲜 S1 HTTP 401→获批 REPAIR 后同身份 200 的既有 smoke | 140 个起始基线测试不得减少；S1 原业务行为及 ActionIntent/REPAIR/DELIVER 幂等不退化 | 全量 pytest、已有 S1 D3 smoke；分别报告执行次数和日志 |
| S2FACT-08 | Gold/Rubric/Outcome/Trace 合同解析及反向 Gold | S1/S2 共用字段齐全；`ESCALATED != REPAIRED_VERIFIED`；M2-01 S2 Agent Outcomes NOT_IMPLEMENTED；not-run 不作 Pass | `test_m2_01_s2fact08_outcome_rubric_gold_trace_contract_is_valid` |
| S2FACT-09 | migration 双次 initialize、运行期写审计、秘密扫描、全部真实 trace/结果复核 | migration 幂等；Grant/Requirement 写计数 0；Authorization 与 scope 不泄密；fresh directed/full suite 通过，RED 与失败保留 | `test_m2_01_s2fact09_migration_is_idempotent_and_scope_write_count_is_zero`、全量 pytest、静态检查 |

所有计划测试名称在新增实现/测试时只能在不改变判据的前提下调整；调整需先在本冻结文件留痕，再开始相应执行。Gold 判据不能因 RED 后的实现不便而修改。

## 5. 必须单独覆盖的反向用例

1. Scope denied 使用与 Domain 认证策略一致的有效凭证；凭证不匹配只应测 401，不能伪造 403。
2. 跨租户/越域查询不能把 HTTP 404 作为真实资源不存在证据。
3. 向 MCP 请求尝试加入 `tenant_id`、`base_url`、`Authorization`、`granted_scopes` 或伪造 request/event/reason/version；Schema/Domain 校验须拒绝或标为不可信，不能成为 Authz Decision。
4. Grant 或 Scope Policy 版本变化后，先前 Domain Observation 不能再被标为当前事实。
5. 同租户合法 Task 也不得查询错误 service/integration/principal/route；拒绝发生在敏感读取之前。
6. Scope grants 与 required-scope policies 的运行期写入计数严格为 0；setup 写入另行计数。

## 6. 运行与证据纪律

所有测试使用新鲜 `.runtime/m2-01/<run-id>/domain.sqlite3`，不复用默认演示库或 M1-HF 数据库；stdio MCP 使用独立子进程和随机 loopback 端口。原始 stdout/stderr、退出码、HTTP request/response 摘要、MCP request/response 摘要、DB 版本/计数、测试依赖、失败重试均落在本目录 `logs/` 和 `TRACE.json`。脱敏前扫描 secrets，任何 Authorization/secret/token 值不得写 trace。

全量测试基线是 M1-HF-01 的 140 项。本轮另外分列目标测试数、完整 pytest 数、真实 HTTP 请求数、MCP tools/list 与 tools/call 数、Provider 次数、浏览器次数。Provider 本阶段不要求；未执行写 0/NOT_RUN，不能称 Pass。只读 HTTP/MCP 测试不创建或暗示 Diagnosis/Handoff receipt。

冻结先行 SHA 以本文件、Gold、Rubric、Trace schema、Deferred Gates 均入库的独立 `main` commit 为准。该提交之后才可新增 S2 功能 RED 测试；RED 完整保留以后再实现。
