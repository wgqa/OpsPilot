# M2-01 最终交付报告

**状态：** S2 真实鉴权事实层验收材料完成，待主 Agent 独立复核。该状态不表示 S2 Agent、诊断或交接已实现。

**基线：** `main@715ccfa797d833d089a495cae67d1866a1a85a5a`

**冻结标准先行提交：** `832dd632dd0ed27201015a4e66f50e1a4771fec1`

**实现提交：** `ff4a925e358101abee5769da324d73d978088881`

**最终交付提交：** 由本次最终主分支回报提供。
**范围：** S2FACT-01 至 S2FACT-09。未进入 M2-02。

## 验收矩阵

| 项目 | 结果 | 证据 |
|---|---|---|
| S2FACT-01 | PASS | [`TRACE.json`](TRACE.json) 中 trace `trace-50bdb99791aeecd3` 记录 HTTP 403 和 `DENY/SCOPE_INSUFFICIENT`，同一 request/event ID、当前版本；定向测试见 `logs/pytest-full-trace-fields-release.txt` |
| S2FACT-02 | PASS | 无效凭证及 S1_DISABLED 均为真实 API 测试 HTTP 401，认证失败先于授权；无 Authz Deny 事件 |
| S2FACT-03 | PASS | [`TRACE.json`](TRACE.json) 中 trace `trace-b8a85b18ab675f9a` 记录 HTTP 200、`demo-order/CONFIRMED` 与同请求 `ALLOW/SCOPE_GRANTED` |
| S2FACT-04 | PASS | 隐藏路由、已授权但缺失订单、跨租户非枚举负例通过；404 不作为资源存在性结论 |
| S2FACT-05 | PASS | Grant 与 Scope Policy 版本更新后旧事实为 STALE；伪造 reason 与 request/event 错配为 CONFLICT。测试 harness 在采集后直接改 Domain 版本，作为受控 stale 场景注入；不是产品 API、MCP 或 Agent 写权限 |
| S2FACT-06 | PASS | 真实 MCP stdio `tools/list` 一次、`tools/call` 四次；有效查询成功，越域、额外字段及错误类型均拒绝，见 [`TRACE.json`](TRACE.json) trace `trace-dbccf8e158eacd51` |
| S2FACT-07 | PASS | 新鲜全量 pytest 148/148；新鲜 S1 D3 真实闭环成功。原 140 个 M1-HF-01 测试全部保留 |
| S2FACT-08 | PASS | 冻结 Gold/Rubric/Trace 合同通过解析与反向用例校验；所有 S2 Agent 业务 Outcome 仍为 `NOT_IMPLEMENTED` |
| S2FACT-09 | PASS | user_version 5→6 重复迁移测试通过；HTTP/MCP Trace 脱敏扫描通过，运行期 Scope Grant/Policy 写入为 0 |

机器结果见 [`RESULTS.json`](RESULTS.json)，测试和运行尝试索引见 [`FAILURES.md`](FAILURES.md)，文件摘要见 [`SHA256SUMS.txt`](SHA256SUMS.txt)。九项事实层测试 PASS 不等于 S2 业务诊断或交接 PASS。

## 可信数据模型与迁移

新增版本化关系和授权审计均在 SQLite Domain：

- `principal_scope_grants`：tenant/principal 绑定的规范化 Scope 列表与 `grant_version`。
- `route_scope_policies`：tenant/service/route 绑定的 `required_scopes` 与独立 `scope_policy_version`。
- `authz_events`：每个授权决策关联 `authn_event_id`、`request_id`、资源绑定、outcome/reason、required/granted/missing Scope、credential policy 版本、Grant 版本及 Scope Policy 版本。
- `auth_events` 迁移增加 `request_id` 和 `credential_policy_version`，既有认证事件语义保留；schema `user_version` 到 6，初始化可重复执行。

真实业务 API 顺序为先认证，再授权，最后读取订单。认证无效/主体禁用返回 401；认证有效但 Scope 缺失返回 403，并在 Domain 保存 `DENY/SCOPE_INSUFFICIENT`；授权成功返回订单 200。实际 401/403/200 的记录分别处于隔离 SQLite 数据库，因此事件 ID 会各自从 1 开始，必须结合 Trace 的 request ID 和 case ID 读取，不能把裸 `event_id=1` 当成全局 ID。

| HTTP | request_id | Authn | Authz | 当前事实 |
|---|---|---|---|---|
| 401 | `3cf47e9a0a76ceaf` | event 1 `AUTH_REJECTED` | 无 | invalid credential |
| 403 | `46dab4009a24e234` | event 1 `AUTH_ACCEPTED` | decision 1 `DENY/SCOPE_INSUFFICIENT` | 缺少 `orders.read`，Grant=1、Scope Policy=1、credential policy=3 |
| 200 | `6e6c4bdb58e018a6` | event 1 `AUTH_ACCEPTED` | decision 1 `ALLOW/SCOPE_GRANTED` | `demo-order/CONFIRMED`，版本均为当前值 |

MCP stdio 的有效调用读取与 403 同一 Domain 决策；其余三次调用分别验证越域、伪造额外字段和非字符串参数拒绝。Tool schema SHA-256 为 `3e78ccf203a10251e97f5fb502416f3959178d47eb44f2b7201beb121425fbaf`。该工具只接收 `request_id`，从持久 TaskBinding 重新推导 scope；M2-01 以显式启动参数 opt-in 暴露，不改变 M1 的默认四工具目录。MCP 结果标记为 `untrusted_tool_observation`，不因此获得 Gate、审批或写入权限。

HTTP 404 负例分为三种：未注册路由在认证前统一返回 `NOT_FOUND` 且无 Authn/Authz 事件；同租户目标订单不存在时先得到真实 `ALLOW` 后返回通用 404，但事实接口不暴露 `resource_exists`；tenant-B 的请求在 tenant-A 的服务绑定上被非枚举拒绝。任何一种 404 都不能单独证明资源不存在或 Scope 不足。

## 测试与运行证据

- 冻结提交 `832dd63...` 在首次新增 M2-01 功能 RED、实现与迁移前入库；冻结文件在本轮未改动。
- 旧实现上的真实 RED 有两项产品行为失败：有效凭证且缺 Scope 时 API 仍返回 200；旧 MCP stdio 没有 `get_scope_authz_facts`。原始日志：`logs/pytest-s2fact-red-baseline-retry.txt`。
- 最新源码定向 M2-01 测试：8 passed，命令与原始输出在 `logs/pytest-m2-01-directed-trace-fields-release.txt`。第一次使用系统 Temp 的 setup PermissionError 保留在 `logs/pytest-m2-01-directed-trace-fields-final.txt`。
- 最新源码全量 pytest：148 passed、0 failed（140 条原有 M1-HF-01 回归 + 8 条 M2-01 定向测试），命令与原始输出在 `logs/pytest-full-trace-fields-release.txt`。
- 最终真实 M2 HTTP/MCP smoke 在实现提交 `ff4a925e358101abee5769da324d73d978088881` 上运行：HTTP 请求 3 次，状态 `[401,403,200]`；stdio `tools/list` 1 次，`tools/call` 4 次；Scope Grant/Route Policy 运行期 INSERT/UPDATE/DELETE 总计 0。Trace 含 Grant/Policy 前后版本、版本未变标记和 secret scan 文件清单；原始进程输出在 `logs/m2-01-real-http-mcp-final.txt`。
- 对 `docs/evidence/vnext/m2-01/` 的 55 个证据文件进行脱敏扫描，逐一检查本次 HTTP fixtures 中四个真实 credential secret 值以及 Authorization bearer 格式；结果 0 findings，完整文件索引在 `logs/secret-scan-final.txt`。Trace 内的 `secret_scan_files` 也标明 smoke 自身扫描的 `TRACE.json`。
- 新鲜 S1 D3 smoke：本地 Provider `deepseek-flash` 5 次模型轨迹、4 个 MCP observation；真实 HTTP 从 401 到获批 REPAIR 后 200；相同 tenant/service/integration/principal/route；REPAIR 与 DELIVER 各提交一次，先冻结报告再交付。该 smoke 的业务代码基线为 `d32e5c77fa675e12219446c07e1867b194a917d7`；其后的 `ff4a925...` 只补 M2 smoke Trace 字段，且完整 pytest 在新提交上复跑。轨迹和两进程日志在 `s1-d3-smoke-release/`。
- `python -m compileall -q opspilot tests`、虚拟环境 `pip check` 与 `git diff --check` 均通过。锁文件 `requirements.lock.txt` SHA-256：`59658b2a1412f580237fd3a20d88163aea3579e89f6499a768796b6aaca67ae8`；Python `3.14.0`；MCP `2.3.0`、FastAPI `0.137.1`、Pydantic `2.14.1`、LangGraph `1.2.16`、pytest `9.1.1`。
- M2-01 的真实 Provider 调用数为 0，真实浏览器运行数为 0；这两项符合本阶段范围。S1 既有闭环另行运行了 Provider；本阶段未伪称 S2 Agent 已经调用模型。

## Outcome、Rubric 与证据质量

`RESULTS.json` 对每项分开记录 `run_status`、`task_status`、`expected_outcome` / `actual_outcome`、`evidence_completeness`、`evidence_validity`、`diagnosis_correctness`、`forbidden_writes` 与 `receipt_integrity`。API/MCP facts 没有业务 Run 时 Run/Task 状态为 `NOT_APPLICABLE`。S2 的 `DIAGNOSED`、`HANDOFF_READY`、`SCOPE_ESCALATED` 均仍是 `NOT_IMPLEMENTED`，没有 DiagnosisReceipt、HandoffDraft、HandoffReceipt 或交接队列。原 S1 D3 smoke 的原始 business outcome 字段为 `RECOVERED`；评测只在同一 TaskBinding、审批、REPAIR、真实 401→200 和订单字段均满足冻结合同后映射为 Rubric 的 `REPAIRED_VERIFIED`，交付回执仍单独验证。

`evidence_completeness` 表示必需事件、绑定、版本和响应字段是否齐全；`evidence_validity` 单独表示来源/作用域/请求关联/版本是否当前。缺证据或关联冲突不因 HTTP 状态看似合理而通过。运行期 Scope 写入是独立安全门，不采用分数平均。

## 已知限制与后续门禁

当前实现只证明单机 SQLite Demo Domain、固定订单 API、固定 Tenant/Integration/Principal 以及受限 MCP 查询。它不代表生产 IAM、跨服务授权一致性或远端分布式 exactly-once。S1 审批后 Evidence Revalidation、Web `operation_id` 稳定重试、S2 Handoff 唯一约束/Receipt/Outbox 原子性、项目级审批权限仍为明确的后续门禁；详见 [`DEFERRED_GATES.md`](DEFERRED_GATES.md)。本轮没有扩建或悄悄解决这些范围外能力。

未跟踪的 `开发目录/` 用户任务卡与资料没有暂存或修改。最终改动只包括 M2-01 实现、测试及 `docs/evidence/vnext/m2-01/`、`docs/learning/M2-01/` 交付材料。

**下一步：** 等待主 Agent 独立验收；不启动 M2-02。
