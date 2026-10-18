# M2-01 技术面试追问与回答

## 1. HTTP 403 是否足以证明用户缺少 Scope？

不足。状态码只是观察，根因需要服务端 `AuthzDecision`。`authorize_business_request()` 在 Domain SQLite 计算 `required_scopes - granted_scopes` 并持久化 outcome/reason；`get_scope_authz_facts_fact()` 再核对 request_id、关联 Authn event、TaskBinding 身份、当前版本和资源绑定。可看 `tests/test_m2_01_facts.py::test_m2_01_s2fact01_http_403_has_current_scoped_authz_decision` 和 `TRACE.json` 的 S2FACT-01。若只有 403、没有对应可信决策，评测结果应是证据不足，不能诊断 Scope。

## 2. 为什么缺少 Scope 返回 403，而错误凭证返回 401？

服务端顺序必须先认证后授权。无效凭证或 disabled Principal 在 Authn 阶段拒绝，没有 Authz Scope Deny；有效凭证通过后才做 Scope 差集。`test_m2_01_s2fact02_authn_failures_remain_401_before_scope` 覆盖无效凭证和 S1_DISABLED；S2FACT-01 用与当前认证策略相符的有效 credential ref，隔离验证授权不足，不会把 credential mismatch 错报成 403。

## 3. 怎样防止历史授权证据继续作为当前事实？

决策记录 credential policy、scope policy 与 grant 三套版本。每次 facts 查询从当前 Domain 重读版本，对历史事件标记 STALE；对 reason、request/event 或 Scope 差集不一致标记 CONFLICT。`test_m2_01_s2fact05_old_or_unmatched_authz_facts_are_not_current` 先采集真实 HTTP 403，再变更 Grant/Policy 版本并验证旧事实失效，同时注入 reason 与 request event 冲突，确认不能形成当前 Scope 根因。

## 4. 为什么 MCP 参数只有 request_id？

tenant、service、integration、principal、route 是可信 TaskBinding 的属性，不应让模型或客户端自由指定。工具需要输入一个可查的事件关联标识，Domain 再核对请求是否处于当前 TaskBinding 范围。`build_task_server()` 在显式 opt-in 时注册 `get_scope_authz_facts`，Schema 只含 request_id；实现还检查原始 MCP 参数中的额外字段，不能依赖客户端只遵循 JSON Schema。S2FACT-06 的真实 stdio 用例验证有效读取、跨租户/越域拒绝、伪造字段拒绝和类型拒绝。

## 5. 一个有效 MCP tool call 能否授权修改 Scope？

不能。Tool 是只读查询；授权决定来自 Domain 当前 grant 与 route policy，Scope 的 grant/policy 在本阶段没有任何运行时写端点或 Agent tool。模型、Tool response、Gold 都不是策略权威。真实 smoke 对 Scope Grant 和 Route Requirement 的 INSERT/UPDATE/DELETE 安装审计触发器，得到运行期写计数 0。

## 6. HTTP 404 能否作为“订单不存在”的证明？

不能单独作为证明。404 可能为了非枚举隐藏未知 route、外租户资源或无权资源。S2FACT-04 将未注册 route、同租户真实缺失订单和跨租户请求分开测；同租户缺失订单在合法授权后能观察通用 404，但 Authz facts 不返回 `resource_exists`。跨租户请求不会泄漏 tenant-B 是否存在目标订单。

## 7. 为什么 Run 完成不表示 Task 已恢复？

Run status 表示一次执行生命周期，Task status 表示业务工作流进度，business outcome 则要求独立业务事实和回执。M2-01 API/MCP 事实 smoke 没有 Investigator Run，所以两个状态是 `NOT_APPLICABLE`；S2 outcome 是 `NOT_IMPLEMENTED`。S1 `REPAIRED_VERIFIED` 必须有获批 REPAIR 后同一身份真实 HTTP 200 与订单字段，DELIVER 仍有独立回执。Gold/Rubric 和 `RESULTS.json` 分开记录三者。

## 8. 为什么先冻结 Gold 和 Rubric，再实现？

冻结先行提交确保 expected facts、失败门槛与 Outcome 语义不因实现不便而漂移。M2-01 的 Gold 明确 401/403/200、版本冲突、非枚举、Scope 写入为 0，同时要求所有 S2 Agent/Handoff outcomes 保持 NOT_IMPLEMENTED。真实 RED 证明旧 API 把“有效认证、缺 Scope”返回 200，也证明默认 MCP 没有新 tool；这些失败没有通过修改 Gold 来消除。

## 9. Grant 与 Scope Policy 为什么要分开版本？

Grant 是某个 Principal 的当前授权事实，Scope Policy 是某个 tenant/service/route 的要求；两者的变化来源和失效范围不同。credential policy version 又属于认证规则。分开版本可明确哪一类事实发生变化，避免把一个整数错误地解释为所有授权事实都同步。版本兼容性由当前 Domain 复核，不能相信 Model 提交的版本号。

## 10. M2-01 是否证明生产级 IAM 或分布式 exactly-once？

没有。测试使用单机 SQLite、固定路由、两个本地 Tenant/Actor fixtures 和本地 MCP stdio。它验证的是本地 Demo 的权限事实可追踪、越域查询 fail-closed 及写入为零。M2-01 不做生产身份目录、项目级审批、远端 API/数据库并发协议或分布式队列。后续操作必须先通过 `DEFERRED_GATES.md` 冻结的 Evidence Revalidation、operation_id 和 Handoff 唯一性门禁。

## 11. 第一次运行失败如何处理？

先区分环境失败与产品失败。初次 old-code RED 有两个产品失败，保留为 `pytest-s2fact-red-baseline-retry.txt`；它们证明缺少 403 与受限 MCP。一个早期 pytest temp-dir 读取报 Windows PermissionError，测试尚未执行，保留原始日志，之后通过仓库内唯一 `.runtime/m2-01` basetemp 运行。首次实现集成全量测试暴露 19 个回归失败，原因是默认 MCP catalog 增加工具破坏 M1 四工具契约，以及旧 migration 测试仍断言 schema 版本 5；修复为 opt-in 注册和更新版本断言后再跑全量。每次失败都保留在日志索引中，没有删除失败记录。

## 12. 怎样解释本次 S1 回归与 S2 未完成可以同时成立？

S2FACT-07 独立复用既有 S1 smoke：模型/MCP 调查得到 S1 401，人工批准后一次 REPAIR，在线同身份 200，冻结报告后独立 DELIVER。M2-01 新增的事实 API/MCP 能力不等于 S2 的 Investigator、DiagnosisReceipt 或 Handoff 队列。本次 S1 trace 可以是 `REPAIRED_VERIFIED`，但 S2 traces 的 actual business outcome 仍必须是 `NOT_IMPLEMENTED`。
