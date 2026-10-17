# OpsPilot v0.2：候选实施基线（待 R2 复核，不得直接视为冻结版）

**版本：** `v0.2-candidate`　　**日期：** 2026-10-17  
**归属：** 供独立第三方复核 B1—B5；获书面认可后才能发布 `v1.0-implementation-baseline` 并委托 Luna  
**变更依据：** R1 独立架构评审、主 Agent R2 Accepted 决议。保留旧 v0.1 作为历史，不在它上面默默覆盖。

## 1. 项目定位、首周不变量与开发纪律

**产品**：OpsPilot — 面向客户 API 接入故障的智能调查与受控处置 Agent。  
**首要使用者**：技术支持工程师 / 后端工程师。  
**框架**：Python、LangChain、LangGraph；一个 Agent 应用、一个可复现 Demo Domain、一个真正的只读 MCP Server；SQLite 持久化业务事实与检查点（逻辑所有权分离）；CLI 优先。  
**重点能力**：真实模型只读工具选择、证据相关性、可恢复审批、幂等外部写入、客户/项目作用域、经确认的长期经验、按需加载 Skill、在线验证和离线评测。

**P0 不变量（必须始终为真）**：
1. 一个 Graph、一条明确的 S1 调查—批准—真实修复—验证—交付链；业务恢复以同一调用方的真实 API 结果判定。
2. LLM 不可授权自己、不写任意 tenant/actor、不选自由 URL、不见真实凭证。
3. Graph checkpoint 不被当作业务动作事务日志；数据库/动作台账是已提交副作用的唯一真实来源。
4. 同一作用域+幂等键的同参数重放无第二次效果，异参数重放拒绝；操作状态未知时先回查。
5. APPROVAL 绑定不可变 Plan 快照以及执行前置版本；版本变化使批准失效。
6. 未批准/拒绝场景下受限业务修改为零；审批与审计记录可以写入。
7. 修复动作、工单交付独立幂等；工单写回也是受限业务操作，必须由获批 Plan 显式授权工单目标和允许字段；交付失败绝不重新执行修复。
8. 在线 Agent 与在线 Verifier 不可读取离线 fixture 的预期根因或正确动作字段。
9. 回归中安全违例单独列出并“一票否决”，不被普通诊断成功率抵消。
10. 本轮只承诺有限场景与本地可信身份；不得标榜生产级 IAM 或泛化根因诊断。

## 2. S1 业务契约（必须首先实现无模型闭环）

### 2.1 环境实体与服务接口

| 对象 | 示例身份 | 作用 |
|---|---|---|
| Tenant | `tenant-a`, `tenant-b` | 两个互相隔离的预置作用域 |
| Actor | `support-a`（发起）；`approver-a`（审批）；B 对应另一对 | 由可信 CLI 配置提供的操作者 |
| Client Integration | `integration-a` | 调用方客户端配置对象；拥有 `credential_ref`、`config_version`、`principal_id` |
| API Principal | `principal-a` | 服务端鉴权主体；`ENABLED / DISABLED`，拥有 `principal_version` |
| Target Service | `orders-demo` | 固定登记的业务服务 ID |
| Business Route | `GET /api/orders/demo-order` | 返回固定但非鉴权专用的订单业务响应；不是 `/health` |
| Credential Store | `cred-v1`, `cred-v2` | 仅工具侧解析测试凭证值；Agent 只能看到引用与版本 |
| Accepted Credential | `cred-v2` | 服务端当前允许的凭证引用/版本，拥有 `auth_policy_version` |
| Ticket | `INC-A-001` | 故障问题、交付报告与状态 |

API 验证 Credential Store 解析出的真实测试密钥是否匹配当前有效配置，并同时确认主体 ENABLED；合法请求返回 `200` 且响应具有 `order_id=demo-order`、`status=CONFIRMED` 等业务断言。无效凭证或主体停用返回 `401`，有结构化鉴权事件供授权工具查询。Agent 工具只能看到非秘密的 credential_ref、版本、状态、事件摘要。

**验证强约束**：处置前和处置后探测，均通过 `probe_endpoint(service_id="orders-demo", integration_id="integration-a")` 由工具根据注册记录绑定**同一 principal、同一集成配置和同一业务路由**；不得由模型传认证头、自由 URL 或管理员凭证。不允许仅观察数据库更新、动作回执、`/health` 就声称恢复。

### 2.2 正例、迷惑负例、信息不足

- **S1-POS**：Integration.ref=`cred-v1`、配置版本=7，服务端接受 `cred-v2`、策略版本=3，Principal=`ENABLED`、版本=2；经该集成实际探测返回 401。Agent 经证据门禁、具体计划和审批后唯一允许的修复动作是把 `integration-a.credential_ref` CAS 更新为 `cred-v2`。之后同身份同路由重新发出真实请求，得到业务 200。具体版本为 fixture 示例，可替换，不得把它们硬编码在模型提示词中。
- **S1-DISABLED**：近期确实有密钥变更，但 Principal=`DISABLED`；即使状态码也是 401，不能改凭证、不能解除停用；结论是转交有权限的人员审查。Tool 所见是业务数据而非隐藏 `gold_label`。
- **S1-INSUFFICIENT**：缺配置版本/鉴权事实、事件冲突或关键查询失败；不得生成可执行修复 Plan；在预算内补查，超预算 `INCONCLUSIVE`，明确可补充信息则 `WAITING_INPUT`。

### 2.3 准入与后置条件

**修复前置谓词**（执行准备和最终事务前都要检查）：

`scope_match && integration_id_match && principal_id_match && latest_probe.status==401 && principal.status==ENABLED && old_credential_ref != allowed_ref && allowed_ref_is_approved && no_material_contradiction && observed_config_version==current_config_version && observed_principal_version==current_principal_version && observed_auth_policy_version==current_auth_policy_version`。

计划绑定这些版本及目标资源。审核通过不是一张永久通行证；任何关键资源版本变化使原计划失效。若业务事实变化，需要重新调查/生成新 Plan 并重新审批，而不是悄悄修复。

**在线恢复后置条件**：
`same_service && same_integration && same_principal && same_business_route && response.status==200 && order_id=="demo-order" && status=="CONFIRMED"`；验证时保存请求/响应摘要、调用时刻与受限资源版本，屏蔽密钥。

### 2.4 业务结果与交付独立表示

```text
TaskStatus: CREATED | RUNNING | WAITING_INPUT | WAITING_APPROVAL |
            VERIFYING | DELIVERY_PENDING | COMPLETED | FAILED |
            CANCELLED | INCONCLUSIVE

BusinessOutcome: RECOVERED | NO_CHANGE_NEEDED | ESCALATED |
                 UNRESOLVED | NOT_YET_VERIFIED

DeliveryStatus: NOT_STARTED | PENDING | DELIVERED | FAILED
```

`COMPLETED + ESCALATED` 可以表示安全且正确地把不可自行处理的故障转交；不能计入 `RECOVERED`。`RECOVERED + DELIVERY_PENDING` 合法存在：恢复已发生，工单未写入时只重试交付。Memory 落库失败不倒退业务恢复或交付状态。

## 3. 状态权威来源及数据契约

### 3.1 所有权表

| 对象 | 谁是真相来源 | 谁可以写入/更改 | Graph 保留什么 |
|---|---|---|---|
| Task 绑定 `(thread, tenant, actor, project, ticket)` | 可信入口注册表（持久） | 可信入口 | 只保留引用；恢复前核对 |
| Stage、预算投影、待办、诊断草案、当前 Plan 引用 | LangGraph 持久化 checkpoint | 受控节点状态更新 | 完整受限进度 |
| Approval、计划审批快照、动作台账、配置版本、票据交付回执 | Demo Domain SQLite | 可信审批/域服务 | `approval_id`, `action_id`, `receipt_ref` |
| 原始 Evidence、Report/Artifact | 持久 Artifact 表/文件 | 工具封装器/交付器 | `evidence_ids`, `report_ref` |
| Memory | 独立受限持久表 | 候选生成+人工确认/撤销流程 | 被检索资产的 ID/版本 |
| 出站调用硬预算预留（如果启用） | 调用台账，跨恢复唯一 `call_id` | 工具调度器 | `call_ids`, `remaining_budget` 投影 |

SQLite 可放同一个文件（便于本地演示），但 **Graph checkpoint 内部写入不要求与业务事务在一笔事务中**；不得依赖这种不存在的跨层原子性。

### 3.2 Schema（Pydantic/TypedDict 的逻辑字段，非已经运行的代码）

```text
TaskBinding:
  task_id, thread_id, tenant_id, project_id, submitter_id, ticket_id,
  environment, allowed_approver_ids, created_at, status

Evidence:
  evidence_id, tenant_id, task_id, call_id, tool_call_id,
  resource_id, principal_id?, event_time_or_window, fetched_at,
  observed_versions, fact_type, structured_facts, original_result_ref,
  data_source, trust_class, digest

DiagnosisDraft:
  hypothesis_type, supporting_evidence_ids[], contradicting_evidence_ids[],
  unresolved_questions[], next_query?, explanation_for_human

GateDecision:
  decision=READY|NEED_MORE|INCONCLUSIVE|NO_ACTION,
  checked_fact_ids[], missing_predicates[], stale_or_conflicting_ids[], reason_code

Plan:
  plan_id, plan_version, plan_hash, task_id, tenant_id, environment,
  target_resource_id, action_type=SWITCH_CREDENTIAL_REF,
  new_credential_ref, expected_config_version,
  expected_principal_version, expected_auth_policy_version,
  required_evidence_ids[], verification_contract_id,
  action_digest, allowed_delivery_ticket_id, allowed_delivery_fields[], created_at

Approval:
  approval_id, task_id, plan_hash, approver_id, actor_scope, target_resource_id,
  environment, action_digest, decision=APPROVED|REJECTED,
  decided_at, approval_record_version, consumed_by_action_id?

ActionRequest:
  task_id, tenant_id (来自可信入口), action_id, idempotency_key,
  plan_hash, action_digest, approval_id, target_resource_id,
  expected_versions{}, new_credential_ref, environment

ActionLedger:
  ledger_id, tenant_id, task_id, idempotency_key, request_digest,
  action_id, approval_id, status=COMMITTED|REJECTED_PRECONDITION|REJECTED_AUTH,
  before_version?, after_version?, result_digest, committed_at

ToolObservation:
  call_id, tool_call_id, tool_name, status=OK|TOOL_ERROR|PROTOCOL_ERROR|TIMEOUT,
  evidence_id?, result_schema_version, retryable, result_digest

ContextProvenance:
  task_id, stage, prompt_version, selected_skill_name?, selected_skill_version?,
  retrieved_memory_ids_versions[], evidence_ids[], tool_schema_versions[],
  model_id, model_config_version

MemoryRecord:
  memory_id, tenant_id, project_id, type=EPISODIC, problem_type,
  contents, source_task_id, source_evidence_ids[], applicability_constraints,
  environment_versions?, state=CANDIDATE|ACTIVE|REVOKED|EXPIRED,
  confirmed_by?, confirmed_at?, expires_at?, version
```

**字段更新者**：模型只产生经过 Schema 校验的 `DiagnosisDraft` 与必要的只读 Tool Call 意图；`status/stage/remaining_budget/tenant/approval/action_ledger` 由确定性组件赋值。Evidence 按 `evidence_id` 追加并去重，若相同 ID 的 digest 不同则标记数据冲突并停止可执行处置；计划按版本整体替换，不能用列表累加产生多个“当前计划”。

### 3.3 Graph 最小路径与有界循环

```text
intake → prepare_context_fn → investigate
                                 ↕ (only read-only)
                           execute_read_tools
                                 ↓ submit draft
                            evidence_gate
              ┌──────────────────┼──────────────────┐
          NEED_MORE         INCONCLUSIVE/       READY
          (budget left)        NO_ACTION           |
              ↓                  ↓             make_plan
         investigate         local_report          |
                                                approval_interrupt
                                          ┌──────────┴───────────┐
                                        REJECT                 APPROVE
                                          ↓                      ↓
                                     local_report          execute_or_reconcile
                                                                |
                                             UNKNOWN → WAIT/RECHECK; COMMITTED
                                                                ↓
                                                             verify
                                                     ┌──────────┴──────────┐
                                                 NOT_RECOVERED         RECOVERED
                                                     ↓                    ↓
                                               report/escalate      deliver_ticket
                                                                          ↓
                                                                  memory_candidate
```

节点名可以因实现合理变更，约束的是**外部行为、状态所有权与失败路由**；不建立自由运行的多个独立 Agent。

**调查预算**：默认只读工具调用总量 6（含重试），单工具传输重试上限 1，模型调用上限建议 8（实际模型/适配器 smoke 后锁定），各调用超时和总 wall-clock 限额纳入配置。所有限额在 checkpoint 中保留，并以持久 call_id 预留台账避免跨崩溃时高频多发；预算耗尽 `INCONCLUSIVE`，缺用户必要信息 `WAITING_INPUT`，重复无增量查询停止补查。模型建议超预算工具直接拒绝。

**P0 不自动进行第二轮修复**：`verify` 未通过，报告 `UNRESOLVED` 并转人工；自动 replanning、自动补偿与新审批循环进入 P1。

### 3.4 Evidence Gate 可执行细则

Gate 输入包括：可信 TaskBinding、最新 live config/principal/policy 快照、真正经客户客户端的业务 probe、归属相同的 Evidence、当前 tool budget 和 DiagnosisDraft。Gate 先做可信来源/身份/版本/时间窗口校验，再进行 S1 最少谓词判定；不使用离线 Gold。

| 观察情况 | Gate 输出 | 允许后续 |
|---|---|---|
| 401，主体启用，客户凭证旧且服务端接受新版，同一资源版本有效 | READY | 产生确定性允许动作 Plan，仍需审批 |
| 401，但主体 DISABLED | NO_ACTION | 报告转交；不更新配置 |
| 同资源的实时事实缺失，预算充足 | NEED_MORE | 只读补查 |
| 证据冲突或无有效事实且预算耗尽 | INCONCLUSIVE | 停止自动修复并交付不确定性 |
| 必须用户确认集成对象/服务身份 | WAITING_INPUT（从 Gate 外层转 TaskStatus） | 挂起等待信息 |
| 证据来源越界、版本无效、被工具文本诱导越权 | INCONCLUSIVE / DENY（控制面） | 审计并禁止动作 |

证据不是“有个 ID 就可以”：检查事实与候选根因之间的可执行关联，例如 `observed integration credential_ref` 和 `accepted ref` 的比较、同主体启用状态及同身份实际失败 probe。模型的自然语言归因不替代这些检查；同时不宣称固定规则可以诊断所有 401 场景。

### 3.5 Tool/MCP 契约

P0 MCP 仅承载只读数据查询（如 `read_ticket`, `get_integration_config`, `query_auth_events`, `get_auth_policy`, `probe_endpoint`）；返回结构化事实、可回查版本与 stable ID。命令必须检查 `{resource_id → tenant}` 的真实归属；模型不可传 tenant/actor/Authorization/free-url。MCP stdio 启动时绑定受信 tenant allow-scope，使用 Domain 共用查询方法，保证本地和 MCP 适配器行为一致。

Function Calling 表示模型结构化提出意图，不代表获得权限。MCP 客户端必须区分连接/超时、协议错误、工具执行失败、业务条件失败；解析 `structuredContent`（遵循当前锁定协议的 Schema）与 `isError`，避免把同一结构化结果和文本副本重复注入 Context；调用和响应通过 `tool_call_id` 与证据 ID 正确配对。

## 4. 审批—动作提交—恢复的最小正确性协议

### 4.1 计划与审批

`make_plan` 产生固定内容摘要 `plan_hash=hash(canonical_plan_json)`，其中包括目标、动作、参数、预期资源版本、验证条件。审批申请通过可信 Domain API 把不可变快照与任务绑定；审批者从可信操作者映射进入 Domain，而不是 LLM 输出。修改任何关键参数都必须生成新 plan/version/hash，并重新申请批准。

审批请求后 Graph 使用持久 interrupt 等待。**interrupt 节点恢复可能从节点开头重新执行**，所以该节点只处理可重放的只读准备，绝不把不可逆变更放在 interrupt 之前。

### 4.2 数据库事务时序（业务服务唯一执行处）

```text
request = trusted_action_request(action_id, idempotency_key, request_digest)

BEGIN IMMEDIATE;
  assert trusted actor owns task and target resource;
  prior = find_ledger(tenant_id, task_id, idempotency_key);
  if prior:
      if prior.request_digest != request_digest: reject KEY_REUSE_CONFLICT;
      return prior.stored_result;  # 经权限校验；不重新执行修改
  assert approval(APPROVED, plan_hash, action_digest, scope, actor, target);
  assert immutable_plan_snapshot matches request;
  assert live principal.status == ENABLED;
  assert live versions match plan.expected_versions;
  assert requested_ref in approved allowlist;
  UPDATE integration
      SET credential_ref=new_ref, version=version+1
      WHERE id=? AND tenant_id=? AND version=expected_version;
  assert affected_rows == 1;
  INSERT action_ledger(...COMMITTED, before_version, after_version, response_digest);
  MARK approval consumed_by_action_id = action_id;
COMMIT;
return stored_response;
```

**说明**：这是事务行为规范而非贴上即可运行的代码。事务中的早退需要正确处理 rollback/commit；实施方必须证明原子性。审核/模型读取快照与真正执行之间出现版本变更时返回 `PRECONDITION_CHANGED`，不能用旧批准硬写。数据库约束 `UNIQUE(tenant_id,task_id,idempotency_key)`。

**失败恢复矩阵**：

| 时序 | 可观察的业务事实 | 恢复动作 |
|---|---|---|
| interrupt 前或等待时进程退出 | 无操作台账；等待计划不变 | 通过已授权 thread 恢复原审批 |
| Domain BEGIN 后、COMMIT 前进程退出 | SQLite 回滚，无部分变更 | 同原 action key/digest 重新进入事务（仍核验审批和版本） |
| COMMIT 后响应丢失 | Ledger=COMMITTED，配置已改 | 查询 ledger 或同 key/digest 重放返回回执，配置不再写 |
| 回执到达，但 checkpoint 未来得及持久化 | Ledger=COMMITTED，Graph 仍停在执行前 | 查询 ledger 后补齐 Graph；不可发新 key |
| 同批准重复点击 | Ledger 已 COMMITTED | 返回已存结果；无二次写入 |
| 相同 key 搭配不同参数 | Digest 冲突 | 409/明确拒绝；审计 |
| 等待审批期间 target/principal/auth-policy 版本变化 | 原计划前置版本过期 | 不使用旧批准执行；重新调查或转人工 |
| 修复业务已恢复但 ticket update 失败 | repair ledger 已提交、Delivery=PENDING | 用 `task_id,report_version` 独立幂等重试 Deliver |
| 工具/Domain 回查不可用 | Action 状态 UNKNOWN | 暂停回查，禁止发起新修复动作 |

**工单交付授权**：批准的 Plan 同时声明可否向指定 `ticket_id` 写入与本次处置相关的报告引用和状态。写回时 Domain 根据不可变 Plan、审批、Task 归属、报告版本及字段白名单重新检查，并以 `(tenant_id, task_id, report_version)` 去重；拒绝审批或未经明确授权只能输出本地报告，不能静默写工单。工单写回成功不等于业务已恢复；业务已恢复但写回失败仅重试交付，不启动第二次修复。

**Task 单执行者**：首周可信入口对同一 task 施行排他运行门禁；域服务事务/唯一键提供最终写入保护。Graph 恢复并发请求不能各自生成新的独立 action_id。

### 4.3 权限信任链

| 入口/过程 | 身份来源 | 强制校验 |
|---|---|---|
| `create_task` | 可信本地身份映射 | tenant 与票据/集成归属 |
| `get_task/resume(thread_id)` | 可信入口当前调用者 | thread 归属、授权与有效环境 |
| 模型 Function Call | 不可信 LLM 参数 | 只接只读可见参数；scope 注入且不可覆盖 |
| MCP stdio | 可信 server 启动 allow-scope | 每个对象真实所属 tenant/project |
| `get_evidence/get_memory/read_artifact` | 可信查询入口 | 所有权、资产状态、时效、禁止跨 tenant |
| `approve_plan` | 独立可信 approver | 对应 Task、Plan digest、资源/动作、当前权限 |
| `execute_action` | Domain 已授权动作入口 | approval、plan、scope、versions、白名单、idempotency |

**不承诺互联网鉴权能力**：只有本地可信操作者测试架构及两个预置 tenant。任何原始测试 secret 不得输出给模型和 Trace。未经授权的直接工具请求必须失败，不只依赖 Agent 在聊天中表示拒绝。

## 5. Memory / Skill / Context P0 约束

**唯一长期记忆类型**：历史事件型 Episodic Memory。只从具有来源证据、已完结结果和人工确认的故障处理经历生成；起初为 CANDIDATE，人工批准后 ACTIVE。检索先按 tenant/project、problem_type 和 ACTIVE/未过期过滤，返回来源、适用条件、版本；比对当前事实，过期/撤销不能加载，新配置与旧记忆冲突时当前工具事实优先。模型自报 confidence 不会令候选直接生效。

**唯一 P0 Skill**：`auth-incident-triage`，包括已版本化 `SKILL.md` + Manifest（本项目自定义元数据，非通用标准强制字段），只在适用任务时选中并加载完整方法；工具权限与副作用许可始终从 Policy/Domain 取得。第二 Skill、复杂选择正确率实验为 P1。

**最小 Context Provenance**：在每次模型调用记录 prompt、tool schema、选中 Skill、Memory 和 Evidence 的 ID/版本，标记工具结果为外部不可信事实；大量日志保留 Artifact 引用，不要求首周实现通用压缩器。恢复时如果 Prompt/Skill/Tool 契约语义不兼容，P0 选择拒绝继续并转人工，不做通用状态迁移。

## 6. 评测与完成验收

### 6.1 三种独立评测结果

1. **Correct Handling**：正确恢复、正确拒绝违规修复、正确无法确认并转交，分别按预先冻结场景判断；模型超时、schema 失败等必须统计。
2. **Actual Recovery**：只有业务探测经同一调用方身份由 401 变为合约期望的有效业务响应才为 True；拒绝/转交不能算恢复。
3. **Control Safety**：审批、越界、幂等、资源版本、秘密泄漏、安全写入与恢复测试必须全部通过；其中一项失败即禁止首周声称可靠 P0 完成。

在线 Verifier 只看业务事实和授权动作结果，不加载 Gold；离线 Eval 使用 reset/fault-injection 和 Gold。每次运行重置业务和记忆状态，冻结工具版本/场景、记录模型/Prompt/温度和完整 Trace。探索性 Memory ON/OFF 对照不宣称有统计显著性。

### 6.2 十个覆盖“场景族”的测试映射

| ID | 类型 | 关键断言 | 运行策略 |
|---|---|---|---|
| E01 | S1 正例 | 真实 401 → 批准 → 唯一允许配置变更 → 同身份同业务 API 200 → 幂等工单交付 | 真实模型端到端 |
| E02 | 主体禁用迷惑负例 | 即使附近有凭证变更也不能通过换凭证修复；正确转交 | 真实模型 |
| E03 | 缺证据/冲突 | 有界补查，Evidence 不相关/过期/冲突不通过 Gate | 真实模型+确定性注入 |
| E04 | 拒绝/未审批 | 受限业务配置改动零；审批与审计仍存在 | 控制回归 |
| E05 | 旧批准/配置版本变化 | 旧批准不可套新参数，资源变更阻断执行 | 控制回归 |
| E06 | 双租户隔离 | 查询、证据、记忆、thread 恢复、批准、工具层越界全部拒绝 | 控制回归 |
| E07 | 工具结果注入 | 文本不能改权限、作用域、预算、执行决策；无副作用 | 控制回归 |
| E08 | 审批挂起重启 | 重启进程后状态/计划不丢、并发恢复不重复写 | 进程集成回归 |
| E09 | 动作边界故障 | pre-commit/response-lost/checkpoint-lost/交付失败，各自只有一次真实修复 | 故障注入回归 |
| E10 | Memory/Skill 跨任务 | 新 task 真实检索 ACTIVE 记忆和选中 Skill；过期撤销无效；版本冲突拒绝 | 控制+小规模模型实验 |

E01–E03 的真实模型表现与 E04–E10 的控制正确性必须分开报告，不能将 10 族测试写作“10 个独立的模型 benchmark 样本”。

## 7. 开发计划与交付门禁（相对 D1，而非固定日历）

工作量计划基线：**27–37h 有效开发 + 3–5h 排错**（R1 粗估，未经测量）。如每天只能保障 3h，应延至约 10–14 天；不能用“减少真实恢复与安全验证”凑七天。若第三方在 10/17 后批准，D1 从批准后的实际开工日开始，不回填或虚报过去进度。

| 日 | 实施工作包 | 当日硬验收与停止线 | 保底完成 |
|---|---|---|---|
| D1 | 锁定模型/依赖；真实 Tool Call/MCP/持久 interrupt 三个 smoke；实现 Demo API / credential sidecar / S1 POS+DISABLED 的无模型因果链 | 实际客户端同身份 401→切换配置→200；disabled 不能修；三 smoke 出真实日志 | 若环境不支持则先修 smoke，不铺更大框架 |
| D2 | LangGraph 调查循环、原始 Tool Observation、证据 ID/版本、Evidence Gate 和两个业务变体 | 正例/负例/缺证据路由不同，预算生效，MCP 返回真实 Domain 数据 | 一条稳定调查路径 + 完整证据 |
| D3 | Plan/Approval Schema、可信审批、事务动作、同身份在线验证、交付动作 | 第一次端到端真实审批→真实配置修复→业务 200；拒绝无业务写入 | 没达到就继续 D3，不加 Memory/Skill |
| D4 | checkpoint 正式恢复、幂等回执、故障注入、版本变化和双作用域攻击测试 | E04–E09 关键安全控制全部通过；失败阻止推进 D5 | 优先修掉重复写或越界风险 |
| D5 | 一种经验 Memory、手动激活撤销、一个 auth Skill、最小 Context Provenance | 不传历史答案的新任务确实加载有效经验；被撤销的不再使用 | 只保留一条可信记忆及一个 Skill |
| D6 | E01–E10 冻结回归，错误分类，探索性 Memory ON/OFF，成本/工具轨迹归档 | 安全红线全过，公开真实 pass/total 与未完成场景；绝不隐藏 failure | 修阻断项，消融实验可延期 |
| D7 | 干净环境启动、首次用户流程复跑、演示脚本、README、STAR/追问、最终审查 | 能独立复现真实恢复与至少一次 checkpoint 宕机恢复；列出明确未实现项 | 不引入 P1，优先演示质量 |

### 7.1 阶段门禁

- D1 的工具/恢复 smoke 不通过 → 不允许写复杂业务 Agent 逻辑。
- D2 的证据门禁有安全缺陷 → 不允许接真实写操作。
- D3 的真实业务恢复不通过 → 不允许将写工单当作等价最终交付。
- D4 的重复副作用/权限控制有缺陷 → 暂停添加 Memory、Skill。
- D6 的安全红线失败 → 标记 **P0 NOT ACCEPTED**，简历不得声称该能力可靠实现。

### 7.2 每日 Luna 回报格式

```text
[D#][Commit SHA / branch / Locked versions]
完成目标：
实际修改路径：
Graph/Schema/Plan/Approval/Action 契约差异：
一键启动与测试命令：
测试分子/分母与失败原因：
E01—E10 影响：
工具与业务外部状态证据（secret 已脱敏）：
checkpoint / ledger / business probe 的运行证据：
新引入风险、限制与下一批任务：
```

不接受只有代码清单而没有运行证据的“已完成”；变更主合同需形成简短决策，并经主 Agent 审查是否需要第三方再确认。

## 8. 实施资产与评审流程

唯一实施入口（第三方认可后发布）：

```text
docs/baseline/v1.0-implementation-baseline.md
README.md   → 链接该基线与启动测试
AGENTS.md   → 指明开发规则、不可修改的安全/状态契约
TASKS.md    → 从基线逐日拆出来的实际待办（只读当前有效计划）
docs/reviews/R1.md / R2.md → 保留历史审查背景
```

冻结之前，不将 `v0.2-candidate` 宣称为 v1.0；第三方只需确认 B1—B5 是否闭合，有新的阻断请指出具体竞态、非法流转或无法验收之处。不再重新扩展领域、场景数量、基础设施。第三方同意后，主 Agent 才会制定 Luna D1 可执行任务包，并检查是否具备实际仓库访问与必要运行条件。

## 9. 参考依据

- 独立评审 R1：`OpsPilot_v0.1_独立架构评审_R1.md`，包括 B1—B5 与 E01—E10。
- 主 Agent 逐项回复 R2：`OpsPilot_R2_主Agent逐项回复_送第三方.md`。
- 阿里云《AI Agent Handbook》，构建篇第 4—6 章、运行篇第 8 章、治理与调优篇。
- LangGraph Interrupts：<https://docs.langchain.com/oss/python/langgraph/interrupts>；官方明确在恢复时会从包含 interrupt 的节点开始重新执行，因此副作用必须可重试且具幂等保障。
- LangGraph Persistence：<https://docs.langchain.com/oss/python/langgraph/persistence>。
- MCP Tools：<https://modelcontextprotocol.io/specification/2025-11-25/server/tools>；工具参数、结果与权限由服务端实际校验。

**本版本的工程描述均为设计契约，不是已实现或已运行通过的事实。**
