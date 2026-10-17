# OpsPilot · Luna D3 任务卡（直接 main · 含 D2 定向修复）

**发布角色：** 主 Agent
**执行者：** Luna
**仓库：** https://github.com/wgqa/OpsPilot
**当前起点：** `main@171f028d6db1f36df087d62be06c255d09c7e138`（开始前正常 `git pull --ff-only`，以实际最新 main 为准）
**唯一合同：** `docs/baseline/v1.0-implementation-baseline.md`；重点 §2、§3.2、§4.1–4.6 和 E01/E02/E04/E05/E09。
**已验收：** D1 业务 Demo 和技术 smoke；D2 真实 LLM→MCP 只读调查、Evidence Gate、持久预算、三场景。
**本轮结果：** **把 D2 的 `READY` 接到真实 `Plan → HUMAN APPROVAL → REPAIR → VERIFY → REPORT → DELIVER`。必须产生原调用方真实业务 401→200 的运行证据，且未批准/拒绝/主体禁用绝无受限业务修改或工单写入。**

## 0. 执行纪律——先做出业务闭环

1. **直接在 `main` 开发，跑测试后 Commit + Push；不建开发分支、不提 PR、不创建 Issue，也无需先交设计稿。** 开发前确认工作区干净，保留 Git 记录；不覆盖已有结果。
2. 先复用 D1/D2 的 Demo API、MCP 调查、Gate 和 SQLite，**先完成正例纵向路径**，再补安全负例和持久性基本断言。不要先铺几十个空模块或搭新的服务层。
3. **不修改 v1.0 冻结语义。** 接口与表的字段可以在契约范围内按实现便利调整，但不能降低 Plan、权限、Intent、Ledger、Verifier 和独立 DELIVER 的要求。
4. D3 实现的是 F1/F2/F3 的**首次可运行正确路径和必要基础校验**；D4 才做系统性的丢响应、进程崩溃、并发取消/替换、重复审批、跨租户攻击与故障矩阵。不要把 D4 全部抢到本轮。
5. 不做 Memory、Skills、多 Agent、RAG、Redis、PostgreSQL、完整 Web UI、平台级 Tool Registry、企业 IAM 或完整 CI。CLI 可作为人工审批入口。
6. **达到本文验收条件立即结束 D3，回传运行证据。** 对不阻断的改进只记后续任务，不因“以后可以更企业级”而重新架构。

## WP-01：D2 最小修复 + 把 READY 变成不可变 Plan

**D2 定向问题（必须顺手修）：** `opspilot/domain/d2.py::evaluate_evidence_gate` 当前对同版本 `endpoint_probe` 的整份 `facts` 比较摘要。合法重复业务探测必然有不同 `request_id`、`auth_event_id`、观测时间，这不等于诊断矛盾。改为按**稳定诊断字段**比对：service/integration/principal/route、HTTP 状态/鉴权结果、凭证引用、相关版本及业务断言等。每次 Probe 独立的 request/event 关联仍完整保留。**补一个同版本合法 401 Probe 两次不误判冲突的测试**；真正的凭证/主体状态/版本冲突仍必须阻止 READY。不要进行 D2 全面重构。

Plan 的来源只能是同任务 Gate `READY` 的可信 `plan_candidate` + 对应 `evidence_ids`、真实目标资源、环境、预期版本、固定验证规则与允许写回的工单/字段。冻结为**不可变 canonical JSON + plan_hash**，持久存储，至少包含：

- `tenant_id/task_id/plan_id/plan_version/plan_hash`、environment、service/integration/principal、目标配置资源；
- 唯一允许动作 `SWITCH_CREDENTIAL_REF`，原凭证引用、新 `credential_ref=cred-v2` 及 `expected_config/principal/auth_policy_versions`；
- `required_evidence_ids`，同身份 `GET /api/orders/demo-order` 且 HTTP 200 + `order_id=demo-order` + `status=CONFIRMED` 的 Verification Contract；
- 工单 `ticket_id`、允许的**追加式**字段、REPAIR/DELIVER 各自动作定义、报告派生规则。

Domain 持久维护 `PlanAuthorization(eligibility=ACTIVE|SUPERSEDED|CANCELLED)`。新计划激活/取消只能由可信发起者或其授权角色调用，不能由 Graph 的 stage 字段代替；持久化状态和历史。D3 至少支持有界的 `activate_plan` / `cancel_plan` 接口，以便 D4 做竞态测试。Graph 只保存 plan_hash/引用；**D2 Gate READY ≠ 执行权限**。检查 D2 现有 `d2_reports` 标记 COMPLETED 的问题：可在不破坏 D2 standalone smoke 的情况下给 D3 引入明确的待审批生命周期，但**不可将 D2 的诊断报告当作已修复回执**。

**验收：** 同一个 READY 产生唯一持久 Plan；相同输入不悄悄换参数；NON-READY 无法激活可执行修复计划。

## WP-02：真正 HITL 人工审批和双动作许可

- 沿用/扩展 D2 的单主 Graph，不另建竞争的任务主状态机；LangGraph 的 D3 主执行链在不可变 Plan 后以 **`interrupt` 挂起**，进程退出仍可恢复。用户在可信 CLI 提交审批决定，另一个进程用原 thread_id 恢复；恢复入口**先验证 TaskBinding/actor/thread 归属**，再读取 Checkpoint。
- 使用本地可信操作者表演示 `submitter=support-a`、`approver=approver-a`、`executor_service` 三种角色。批准必须以真实 approver 身份签署具体 `plan_hash`、target、environment、动作集合、计划摘要；模型既不能自批也不能自己选择 approver。CLI 身份映射只作为本地可信入口，不宣传成生产 IAM。
- 拒绝则保存 APPROVAL/审计和**本地拒绝报告**，没有任何配置更新，也没有未经授权的工单写回。
- 批准时持久化 `Approval(APPROVED)`，**分别**创建 `ActionPermission(REPAIR, AVAILABLE)` 与 `ActionPermission(DELIVER, AVAILABLE)`。批准不是永久有效：真正执行前要在 Domain 中再次检查 Plan ACTIVE、当前资源版本、权限和完整参数。
- D3 至少覆盖：未批准不能调用动作、错误 approver 拒绝、计划哈希和批准内容不一致拒绝、已拒绝没有配置/工单副作用。取消/替换先后顺序的完整并发故障矩阵留 D4。

**验收：** 可真实演示“诊断 → 持久中断 → 另一进程审批/拒绝 → 恢复”；正常审批 REPAIR/DELIVER 许可各自独立。

## WP-03：Domain 持久 ActionIntent + 事务 REPAIR（重点）

**只能受信业务模块执行写入。** 绝不能将 `fixture_only_switch_ref()` 或任意写数据库能力包装成 LLM Tool / MCP Tool。D2 MCP 仍为只读。

### ActionIntent（F1）

在首次发出 REPAIR/DELIVER 业务操作之前，由 Domain 事务中执行 `get_or_create_action_intent(tenant, task, plan_hash, kind)`，唯一约束 `(tenant_id, task_id, plan_hash, action_kind)`；保存：

- 稳定 `action_id + idempotency_key`；
- **不可变完整 canonical_request_json + request_digest**（包含 scope/Plan/审批/目标/参数/适用版本；不含 attempt ID、时间戳）；
- 重用时先按当前**读权限**找旧记录，只能得到同一 key/request；同作用域重带不同业务参数直接 `KEY_REUSE_CONFLICT`。

`execute_action(intent_id, attempt_id)` 只传原意图引用；即使 Graph checkpoint 落后，仍必须可由 `(tenant,task,plan_hash,kind)` 找回同一个意图。**意图已登记但操作未提交时，重新执行需要重验 ACTIVE/APPROVED/版本/许可；已 COMMITTED 的历史回执按读权限回查，不因为后来许可已消费而重复写。**

### 原子 REPAIR（F2/F3）

在同一 Demo Domain SQLite `BEGIN IMMEDIATE` 事务里完成：

1. 校验可信 executor、TaskBinding 和目标真实租户归属；
2. 先检查有没有同 key/digest 的 `COMMITTED` Ledger；有则**返回完整持久回执，不再更改业务**；
3. 对首次提交，检查 Plan ACTIVE、批准与 `plan_hash/target/environment/action` 完全一致、REPAIR 许可 AVAILABLE、同一主体 ENABLED、允许凭证引用、关键 config/principal/auth_policy 版本都仍匹配；
4. **CAS** `integration.credential_ref: cred-v1→cred-v2` 且 `config_version: 7→8`；写 `ActionLedger(COMMITTED, before/after, result_json_or_ref, result_digest)`；消费 `REPAIR` 许可；单事务 COMMIT；
5. 任何失败 rollback，绝无半写。SQLite BUSY 采取有限重试或可诊断错误，**不能在事务中等待模型、HTTP、MCP 或人工回复**。

**验收：** POS 已批准时真实凭证引用恰好改变一次，版本只增 1；重复相同意图不二次修改；旧配置/主体/策略版本变化直接拒绝新 REPAIR；拒绝批准、主体 DISABLED 均为零受限修改。上述首次基本断言在 D3 做；系统级崩溃与竞争故障注入在 D4。

## WP-04：可信在线验证 → 冻结报告 → 独立 DELIVER

1. **Online Verifier** 在 REPAIR 已 COMMITTED 后，复用 D1/D2 `probe_orders`，以**同 service/integration/principal/route** 重新发出真实 HTTP 请求；必须返回 HTTP 200，且 `order_id=demo-order`、`status=CONFIRMED`。只接受在线事实，不读离线 fixture Gold 或模型自报。保存 `VerificationReceipt`（task、plan、repair_action、身份/路由、实际版本、HTTP 状态、业务断言、观测时间、digest）。验证失败 → `UNRESOLVED` / 本地报告，不得交付“已恢复”工单。
2. 用 `REPAIR Ledger + VerificationReceipt + 相同归属 Evidence` 构建受信报告，调用持久 `get_or_create_report(task,plan,repair_action,version=1)`，**在第一次 DELIVER 前冻结**报告内容、版本、`report_ref/content_digest/verification_ref`。D2 诊断报告与 D3 修复交付报告分清，避免 D2 的 `task_id UNIQUE` 报告表阻碍 D3 写入；可最小新增 `report_artifacts` 表。
3. **DELIVER 是第二个独立授权动作**：它的 ActionIntent 必须由已冻结报告派生，digest 包含具体 ticket、report ref/version/content digest、verification_id、允许追加字段、plan_hash；不得重新生成另一份随机报告冒充重试。
4. Domain 单事务检查当前 Plan ACTIVE、APPROVED、DELIVER AVAILABLE、executor 身份与 tenant/ticket 归属、REPAIR COMMITTED、VerificationReceipt 真实恢复、Report 固定关联，然后**追加唯一 ticket_resolution_entry**、写 `DeliveryRecord` 和完整可重放 Ledger 回执、消费 DELIVER 许可；重复同 key/digest 不追加第二条；同键异摘要拒绝。
5. **DELIVER 不再检查修复前 config_version=7**：REPAIR 已合法将其提升至 8。交付失败则保留 `RECOVERED + DELIVERY_PENDING`，只重试/回查同一个 DELIVER，不重新执行 REPAIR。不覆盖用户原工单人工状态，优先追加处置记录。
6. 无审批/拒绝、未验证恢复、Plan 无效、跨 tenant 工单不能写入。D3 实现基本边界；D4 负责系统故障注入与并发互斥证明。

**验收：** 完整 POS 从真实 401，经人工审批与唯一 REPAIR 后恢复业务 200，生成可回查 Receipt，冻结报告并向授权工单**只追加 1 条**处置记录。REPAIR/DELIVER 两条许可和 Ledger 分别可查。

## WP-05：最小测试、命令、证据与交接

### 必须的 D3 自动化测试（按行为，不强制测试文件名）

| 代号 | 场景 | 必须断言 |
|---|---|---|
| T01 | 重复真实 401 Probe（上轮整改） | 同版本不同 request/event 不误判；真实稳定事实冲突仍拒绝 |
| T02 | POS 人工审批闭环 | 真实 401 → Gate READY → immutable Plan → interrupt → APPROVED → CAS REPAIR → **同 caller 200/订单字段** → VerificationReceipt → frozen Report → ticket 一条 |
| T03 | REJECT / 无批准 | 受限 config 修改 **0**，未经授权 ticket 写入 **0**；审计允许存在 |
| T04 | DISABLED | NO_ACTION，不能批准执行换凭证，也不启用主体，受限修改/交付 0 |
| T05 | 版本或计划不符 | 配置/主体/策略版本变化或 plan_hash 与批准不符 → REPAIR 不提交，回滚 |
| T06 | REPAIR 简单幂等 | 同一 intent 重放可回查完整 Ledger，配置版本只 +1，同 key 异 digest 拒绝 |
| T07 | DELIVER 基本幂等与归属 | 固定报告/verification 关联，独立许可消费，重复请求工单仍 1 条；不同报告/其他 tenant 拒绝 |
| T08 | D1/D2 全套回归 | 所有既有测试继续通过，三种 D2 模型+MCP 行为不退化 |

**必须有一次真实 LLM + MCP 调查 → 真实人工审批（CLI / interrupt / resume）→ 真实 HTTP 业务恢复 → 事务交付的端到端演示轨迹**。其余授权/幂等/边界测试可以用确定性代码和 fixture 驱动，避免为每个负例反复花模型调用费用。对于模型阶段偶发失败，保留事实，不可用手动模拟冒充真实模型通过。

### 实施顺序与停止线

1. 先补 D2 Probe 回归，再基于 D2 READY 造不可变 Plan 和人工审批中断。
2. 按安全顺序最小串通 **批准 → 持久 ActionIntent → 单事务 REPAIR（含 Ledger）→ 在线 200**，每一步只写支撑这条路径的代码。**首次 REPAIR/DELIVER 操作之前就必须保存 Intent，禁止用无防护的 fixture 更新或临时无 Ledger 的写操作冒充 D3。**
3. 继续冻结回执/报告、完成独立 DELIVER 与工单基本幂等；最后补最低限度负例和 D1/D2 回归。
4. 进入 D4 的条件：T01–T08 与真实 S1 端到端通过；任何未审批写入、越界、重复业务写、业务未恢复却宣称 RECOVERED 视为阻断。无法全过时如实反馈当前阻断，优先修到 D3 原定验收，不新建架构或开展额外研究。

### Luna 必须交付

- 在**当前 main** 上 Commit + Push；提供新提交 SHA、变更清单与确切可复现命令。
- 更新 `TASKS.md` 中 D2 已合并/已验收、D3 实际状态；README/AGENTS 只改必要操作说明，不更改冻结架构，不写“尚待合并”。
- 保存 `docs/evidence/d3/REPORT.md` 和脱敏日志：真实模型/MCP 查询证据；批准前/后 Config 与版本；Plan Hash、Approval、两个 ActionIntent/Key、REPAIR/DELIVER Ledger、真实 API 401/200 和同调用方身份、VerificationReceipt、report digest、ticket_entry 计数；拒绝/禁用/失效负例；完整测试分子/分母与失败尝试。
- 报告明确哪些是**D3 真实已验证**、哪些仅属于**D4 待测故障时序**。
- 不开 PR，不创建额外流程；完成后立即停止扩展，向主 Agent 回传最新 `main` SHA 与证据文件路径。

## D4 严格保留，不要提前做成一个新项目

D4 才全面做：Intent 登记后宕机、COMMIT 后响应丢失、Checkpoint 落后、批准被取消/替换的交错提交、延迟旧请求、重复/并发恢复、REPAIR 成功而 DELIVER 失败、DELIVER 已提交响应丢失、不同报告摘要重放、跨 tenant 与工具注入的完整 E04–E09 安全矩阵。**D3 不得省略支撑这些时序的基本持久化字段和原子事务，但本轮不要求穷尽故障注入。**

**验收原则：先实现真实业务闭环，已知安全红线不能妥协；不以“企业级”口号增加额外基础设施。**
