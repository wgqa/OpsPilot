# M2-01 源码学习笔记：鉴权事实与只读 Scope 查询

## 阅读入口

本笔记将实现映射到本地源码与本次真实 Trace，可离线阅读。白皮书对照使用阿里云《AI Agent Handbook》： [官方目录](https://aliyun.github.io/ai-agent-handbook/contents.html)、[第 4 章：任务与完成证据](https://aliyun.github.io/ai-agent-handbook/build/chapter-04.html)、[第 5 章：上下文](https://aliyun.github.io/ai-agent-handbook/build/chapter-05.html)、[第 6 章：工具调用](https://aliyun.github.io/ai-agent-handbook/build/chapter-06.html)、[第 10 章：运行时](https://aliyun.github.io/ai-agent-handbook/run/chapter-10.html)、[第 14 章：安全与权限](https://aliyun.github.io/ai-agent-handbook/governance/chapter-14.html)、[第 16 章：验证](https://aliyun.github.io/ai-agent-handbook/governance/chapter-16.html)、[第 21 章：评测数据](https://aliyun.github.io/ai-agent-handbook/optimization/chapter-21.html)、[第 22 章：失败分析与回归](https://aliyun.github.io/ai-agent-handbook/optimization/chapter-22.html)。

核心源码：

- `opspilot/domain/database.py`：Scope Grant、Route Requirement、Authz Decision 表；schema migration；`authorize_business_request()`。
- `opspilot/domain/api.py`：固定 `/api/orders/demo-order` 的服务端路由、认证/授权调用顺序、通用错误响应。
- `opspilot/domain/d2.py`：`get_scope_authz_facts_fact()` 从可信 TaskBinding 重验事件、归属、版本和 Scope 差集。
- `opspilot/domain/schemas.py`：严格 Scope Authz 查询输入类型。
- `opspilot/mcp_server.py`：Task-scoped MCP server；`get_scope_authz_facts` 需显式 opt-in，只读且参数只有 `request_id`。
- `opspilot/smokes/m2_01_facts.py`：隔离 SQLite fixtures、真实 HTTP 和 MCP 子进程、Scope 写审计与脱敏 Trace。
- `tests/test_m2_01_facts.py`：S2FACT 行为、负例、版本失效、迁移和 S1 回归测试入口。
- `docs/evidence/vnext/m2-01/TRACE.json`：真实请求与事件、版本、工具调用记录；`RESULTS.json` 链接冻结标准和测试结果。

## 1. Framework Graph 与 Domain 授权是两层权威

LangGraph 管理节点执行、暂停及恢复，TaskControl 管 Run/Task 的可信控制。M2-01 没有让 Graph 推导授权，也没有新增 S2 Gate。业务服务的认证与 Scope 授权直接由 Domain SQLite 依据当前 Principal、Grant、Route Policy 和固定 route 计算。真实代码入口在 `authorize_business_request()`；HTTP handler 只负责把服务器验证过的 Tenant/Integration/credential 传给 Domain，再按服务端决策返回 401、403 或 200。

这和 Handbook 第 4、10 章的完成语义相呼应：进程/Run 结束不等于业务恢复。Trace 中 HTTP/API facts 没有业务 Investigator Run，因此 `run_status` 和 `task_status` 是 `NOT_APPLICABLE`；S2 的 `actual_outcome` 仍是 `NOT_IMPLEMENTED`。只有既有 S1 获批后真实同身份业务 200 的闭环可记作 `REPAIRED_VERIFIED`。

## 2. Authn 与 Authz 不同

认证回答“这是哪个已注册调用身份，凭证是否有效，Principal 是否启用”；授权回答“认证后的 Principal 是否拥有访问本 route 所需的 Scope”。实现顺序是先 Authn，再 Authz：凭证无效或 Principal disabled 先写 Authn rejection 并返回 401，不生成 Scope不足决策；认证通过而 `required_scopes - granted_scopes` 非空，写 `DENY/SCOPE_INSUFFICIENT` 并返回 403；差集为空才读取订单并返回 200。

本轮真实 Trace 中：`f80b3a77ba19c01b` 绑定 Authn event 1 与 Authz decision 1，决策为 `DENY/SCOPE_INSUFFICIENT`；`2f17092ed338a044` 绑定有效认证和 `ALLOW/SCOPE_GRANTED`，响应订单为 `demo-order/CONFIRMED`。401 请求 `deeca45b19158794` 只有 Authn rejection，没有 Authz decision。这些 ID 只在各隔离数据库与 Trace case 内唯一。

Handbook 第 14 章强调认证与权限控制是不同边界。HTTP 状态只是调用观察：403 不自动证明 Scope 是根因，必须核对可信 Authz Decision、reason、同一 request/event、tenant/principal/service/integration/route 与当前版本。模型输出和 MCP JSON 都不能取代这些判据。

## 3. Scope 差集、版本和只读 MCP

Domain 从当前 `principal_scope_grants` 读取 granted scopes，从 `route_scope_policies` 读取 required scopes。决策和证据分别带有 credential policy version、grant version、scope policy version；credential policy 与 Scope Policy 是独立版本，不共用一个整数。`get_scope_authz_facts_fact()` 每次用 TaskBinding 重验租户、任务、service、integration、principal、route，并检查请求关联、资源绑定、当前 Grant/Policy 版本和 Scope 差集。更新 Grant 或 Policy 后，历史决策仍用于审计，但状态变为 STALE；request/event、reason 或 Scope 差异不一致则为 CONFLICT。

新增 MCP tool 是事实读取接口，不是授权授予接口。它只接收 `request_id`，不接收 tenant、base URL、Authorization、token、Grant 或 arbitrary Scope 参数；Domain 仍根据数据库里的 TaskBinding 推导范围。返回内容的信任标记仍是 `untrusted_tool_observation`。stdio Trace 有 1 次 `tools/list`、4 次 `tools/call`：一个成功读取，三个拒绝（越域请求、额外伪造字段、非字符串 request_id）。Grant/Policy 没有运行期修改接口，审计计数为 0。

这对应 Handbook 第 5、6 章的上下文与工具边界：工具能从有界上下文读取数据，不等于它能改变策略或成为可信控制点。真实权限事实必须由工具执行侧从 Domain 重新验证，而不是信任 Prompt 或工具返回的自我声明。

## 4. 为什么 HTTP 404 不是资源事实

非枚举响应可以隐藏资源是否存在。M2-01 分别验证未知 route 在认证前被统一处理，同租户缺失订单只在当前授权允许后返回通用 404，而 Authz facts 不暴露 `resource_exists`；tenant-B 请求放到 tenant-A 服务/TaskBinding 上会安全拒绝。即使 HTTP 404 是真实观察，也只能说明调用方看到了 404，不能证明“资源不存在”，更不能证明 Scope 不足。越域拒绝时不能向调用方披露内部 Scope 差集或外租户身份。

Handbook 第 14、16 章的安全与验证原则在这里落地为负向测试：需要明确证明敏感查询未成功、没有隐藏租户数据泄漏，并用可信 Domain 事件确定决策，不由 HTTP 文本推断原因。

## 5. 冻结 Rubric/Gold 再实现

`ACCEPTANCE_PLAN.md`、`S2_GOLD.json`、`S2_RUBRIC.json`、`TRACE_SCHEMA.json` 与 `DEFERRED_GATES.md` 在先行提交 `832dd632dd0ed27201015a4e66f50e1a4771fec1` 冻结，早于 M2 功能 RED 与实现。这样失败后不能为了迎合当前实现而更改 expected facts。Gold 是离线测试预期，不进入服务端、Prompt、MCP 或 Evidence。

Rubric 将 `run_status`、`task_status`、业务 `Outcome` 与证据质量分开。`evidence_completeness` 是字段/事件是否齐备，`evidence_validity` 是来源、Task/tenant scope、request/event、版本与时效是否可信。安全失败不能被其他正确项的平均分抵消。Handbook 第 16、21、22 章分别提供验证、Gold 评测集及 badcase 回归的参照；本次最初 RED 和失败重试保存在 `docs/evidence/vnext/m2-01/logs/`。

## 6. 版本时效与后续门禁

Scope Authorization facts 当前性受 Grant/Policy 的版本约束；S1 的 Evidence TTL、审批后的重新验证另有更细的跨阶段门禁。它们在 `DEFERRED_GATES.md` 中冻结为未来实施条件，M2-01 没有修改 D3 审批、Plan 或 Action 提交路径，也没有把 TTL 风险说成已解决。Web `operation_id` 稳定重试、S2 Handoff 唯一性/Receipt/Outbox、项目级 Approver 权限也仅登记为后续门禁。

## 7. Demo 的适用边界

本轮运行的是单机 SQLite Domain、固定 demo 订单 API、本地可信 actor/tenant fixture 与本地 MCP stdio 子进程。它验证因果、作用域和决策证据，不代表企业目录、生产 IAM、跨服务一致性、网络级安全模型或分布式 exactly-once。审批角色仍是本地 Demo 角色；M2-01 没有新权限写入，也没有自动修复 S2 Scope。
