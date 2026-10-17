# OpsPilot 第二 Agent 项目：架构评审与实施计划（第三方评审稿）

**版本：** v0.1-review　　**编制日期：** 2026-10-17  
**状态：** 待第三方评审；非最终需求冻结版、非已实现项目  
**交付目的：** 供独立评审者在无法访问现有代码仓库的前提下，评估业务选题、技术架构、开发顺序、验收门槛、项目风险，并在达成书面结论后交给 Luna 实施。

> **项目一句话定位**：基于 LangChain + LangGraph 构建面向企业后端服务的智能故障调查与受控处置 Agent，以动态证据链、外部能力整合、可恢复长任务、长期记忆、Skills 和端到端评测为核心，而不是再自研一套 Agent 内核。

---

## 0. 评审者请先阅读：本文件中的结论分级

- **已确定的方向（无需从零争论）**：已有一个原生自研 RAG + Agent Harness 项目；第二项目采用 LangChain + LangGraph；要明显提升 MCP、长期记忆、Skills、Context、HITL、持久化与评测能力；开发必须遵守单一业务主线和增量验收；目标服务 Agent/AI 应用研发岗位。
- **当前推荐、但允许第三方挑战的决策**：选企业微服务故障诊断与工单受控处置（OpsPilot）作为垂直场景；采用单主图 + 业务服务 + MCP 工具；先做一条深度垂直切片，再扩展第二故障类别。
- **尚未实现、不得表述为成绩**：任何模块、准确率、性能、成本、服务规模、工具接入数量、真实长期记忆收益、成功的跨重启恢复等，均只能当作开发目标。
- **时间约束**：计划 2026-10-17—10-23 首轮七天冲刺，目标是“可演示且可复现的工程版本”，不是七天建成生产级 AIOps 平台。

## 1. 既有经历与为什么要做第二个项目

### 1.1 个人路线和简历构成

开发者正在准备大厂 Agent/AI 应用研发、AI 后端岗位实习。简历已具有 Java 后端工作/实习经历及 Java 项目，但希望 Agent 成为投递主线，因此需要第二个与旧项目有明确互补的 Agent 作品。现有 Java 能力用于理解 API、配置、Redis 和后端服务，而不再重复实现大型 Java 业务平台。

### 1.2 旧 Agent 项目：已知事实

- 定位：没有依赖 LangChain/LangGraph 的原生 RAG + Agent Harness；重点在 Agent 内部 Loop、工具调用、任务推进、执行决策和冻结评测。
- 曾完成一轮 **72 题冻结工具过程** 的 B0 与 Convergence 架构对照。此前记录为：B0 严格 PASS 41/72、FAIL 6、多步 PASS 11/18；Convergence 严格 PASS 39/72、FAIL 16、多步 PASS 8/18。两种版本的观察结果不能直接等同生产表现；尚有其他判定状态，故 PASS 与 FAIL 不必加总到 72。
- 该轮结论：Convergence 整体不优于 B0，暂不替换；暂停大规模 Harness 重构，保留实验资料与有效局部改进。
- 经验教训：为了修某一类问题而扩展通用架构，会诱发契约漂移、回归退化及高昂验证成本。新项目要显式冻结主路径、接口和评测集。

### 1.3 新旧项目的互补关系

| 维度 | 旧项目 | OpsPilot 新项目 |
|---|---|---|
| 技术范式 | 原生 Harness，从内部机制入手 | LangChain + LangGraph，组合成熟框架能力 |
| 研究/面试主旨 | Agent 为什么这样推理、选择并调用工具 | Agent 如何可靠接入业务、持续执行、恢复和交付 |
| 核心亮点 | Loop、工具路径、内部决策与冻结对照 | MCP、Function Calling、Context、Memory、Skills、Checkpoint、HITL、评测 |
| 避免重复 | 不再自研底层通用 ReAct 内核 | 不再做大型 Coding Agent / 复杂代码执行沙箱 |

**最重要的定位约束**：复杂度来自“长期任务可靠性、跨能力边界与可验证交付”，而不是故障类型数量、监控组件数量或 Agent 数量。

## 2. 垂直领域与产品边界

### 2.1 选题结论

**OpsPilot：企业后端系统的智能故障调查与受控处置 Agent。** 它融合“企业软件技术支持工单”的真实客户上下文，与“AIOps 故障调查”的证据链和阶段性处置；主要用户是研发、SRE/运维、技术支持与实施工程师。

**用户任务**：输入一个工单/告警，例如“客户 A 的订单 API 今天突然返回 401/500，排查是否与密钥轮换、配置变更、Redis 异常或服务发布有关；给出可信根因与证据；方案获批后在隔离环境执行可控操作；验证结果并更新工单”。

**最终交付**：可追溯诊断结论、结构化证据、处理建议、批准记录、真实操作/状态回查、工单状态更新、可复用但需审查的经验候选。

### 2.2 候选场景与优先级

| 编号 | 业务故障 | 可查询证据 | 可执行操作 | 分期 |
|---|---|---|---|---|
| S1 | API Key 轮换后使用旧密钥版本，导致 401 | 鉴权失败事件、非敏感 Key ID/版本、配置版本、变更时间 | 测试环境允许名单内配置纠正 + 工单记录 | P0，第一条端到端纵向切片 |
| S2 | 回调地址 / 环境配置漂移，导致 404 | 当前配置、回调事件、发布与变更记录 | 生成修复建议；有条件加入受控配置写入 | P1，第二条场景 |
| S3 | 订单 API 500，伴随 Redis 超时/连接池异常 | 请求指标、结构化日志、Redis 健康摘要、发布记录 | 在隔离服务验证恢复动作；禁止真实生产操作 | P2，深度增强 |

首周必须跑通 S1；S2 争取完成；S3 只在主链、测试、审批和恢复已稳定时才做。**不按“3 个场景都实现”判断核心项目是否完成。**

### 2.3 明确不做

第一周不实现复杂微服务监控平台、不部署生产 Kubernetes 集群、不接真实客户密钥、不做全自动生产发布或重启、不做通用代码修改 Agent、不开发 A2A / 自建 MCP 网关 / 多 Agent 自由协作、不为展示而搭大量数据库与前端页面。

可采用一个可启动的 Java 或 Python 演示 API 服务（优先复用可用样例）、持久化 SQLite、有限配置/事件/工单表与真实读写工具；“模拟故障数据”必须由数据库或服务真实返回，不能让模型直接读取伪造好的根因答案。

## 3. 产品流程与可验证业务价值

### 3.1 唯一稳定的业务主线

`Intake → Prepare Context → Investigate / Observe → Hypothesis & Evidence Gate → Plan → Policy / HITL → Act → Independent Verify → Deliver → Memory Candidate`

- **Intake**：创建 Task，绑定 actor / tenant / project / ticket / environment，定义成功标准、风险等级与操作范围。
- **Prepare**：按作用域选择任务状态、近期证据、相关 Knowledge、已验证 Memory 和候选 Skill，保留 Context Manifest。
- **Investigate**：模型通过 Function Calling 表达下一工具与参数；MCP/本地工具负责访问真实业务数据；Observation 标准化、保留来源。
- **Evidence Gate**：提出一个或多个根因假设，并给出支持/反对证据；不足时在硬预算内补查，不能靠“模型觉得完成”直接流转。
- **Plan**：生成可审核变更计划：目标资源、预期结果、影响范围、回滚方案、验证方法。
- **Policy / HITL**：依据身份、环境、动作风险决定 ALLOW / DENY / ASK；审批必须绑定计划版本与动作摘要。
- **Act**：执行允许名单内的测试环境操作或工单更新；采用幂等键和状态回查，避免恢复后重复副作用。
- **Independent Verify**：业务服务或数据库再次确认预期状态，不以模型生成的成功叙述作为验收。
- **Deliver**：提交工单处理报告、证据链接、状态变迁与未解决风险。
- **Memory Candidate**：只产生经来源与作用域标注的候选记忆；验证/合并后才可成为长期资产。

### 3.2 关键分支

- 证据不足 → 有界继续调查；超预算 → WAITING_INPUT 或 INCONCLUSIVE。
- 查询失败 → 区分可重试的瞬时故障、权限拒绝、参数错误与不可恢复错误。
- 审批拒绝 → 终止写操作，仍可交付只读调查报告。
- 操作执行后响应超时 → 先按动作 ID 回查实际业务状态，不直接重试。
- 验证不通过 → 返回计划阶段修订，但不得无限重试或绕过审批。
- 模型无法确认根因 → 标明不确定性，不得虚构因果关系。

## 4. 逻辑架构：成熟框架负责执行内核，项目负责业务契约

```text
Client / CLI / Minimal UI
           |
  FastAPI Task API  ---------- Ticket DB / Demo API
           |
  LangGraph main StateGraph  [durable checkpointer]
    | Intake
    | Prepare Context <---- Memory Store / Knowledge / Skill Registry
    | Investigator  -----> Tool Policy + LangChain tool adapters
    | Hypothesis Gate         | local typed tools
    | Plan                    | MCP client -> MCP server -> domain APIs
    | Approval interrupt
    | Approved Action -----> Idempotent action service
    | Independent Verifier -> live business state
    | Deliver -------------> Artifact / Trace / Ticket DB
           |
  Evaluation runner + golden scenarios + regression reports
```

**建议主要技术栈**：Python 3.11+、LangChain、LangGraph、FastAPI、Pydantic、SQLite（首周）、本地 MCP Server（优先只读）、pytest；模型供应商经兼容接口配置，锁定实际支持 Function Calling 的模型/版本。LangGraph 采用其持久化 checkpointer；Memory Store 与 checkpointer 分离。每个库及适配器在启动首日锁定版本，先跑 smoke test。

### 4.1 模块权责（不得隐性混合）

| 模块 | 唯一责任 | 明确不负责 |
|---|---|---|
| Graph Orchestrator | 节点与分支、超时/预算、阶段和恢复 | 自己实现 MCP 协议或长期记忆数据库 |
| Context Builder | 根据身份、任务、预算装配上下文并记录 Manifest | 不擅自修改业务事实 |
| Tool Adapter / MCP Client | 将 Function Call 翻译为结构化受控调用 | 不自行决定业务风险授权 |
| Policy / Approval | 许可判断、审批记录与版本核对 | 不依赖模型自称“已获许可” |
| Domain Services | 工单、配置、变更、事件、隔离环境操作 | 不依赖 LLM 判断数据库写入是否成功 |
| Memory Service | 筛选/验证/检索/纠错跨任务经验 | 不把聊天历史直接当权威状态 |
| Skill Loader | 发现/选择/加载/锁定方法资产 | 不赋予超出工具侧的额外权限 |
| Verifier / Eval | 完成门禁与离线跨版本指标 | 不由生成结果自评正确 |

### 4.2 必须定义的结构化数据契约

**Task State（业务状态，不等于全部聊天历史）**：
`task_id, thread_id, tenant_id, project_id, ticket_id, actor_id, environment, stage, goal, plan_version, todo, hypotheses, evidence_refs, blocked_reason, remaining_budget, pending_action_id, approval_id, artifact_refs, last_error, status`。

**状态机**：
`CREATED / RUNNING / WAITING_INPUT / WAITING_APPROVAL / VERIFYING / COMPLETED / FAILED / CANCELLED / INCONCLUSIVE`；每条合法转换要在测试中可检查。

**Evidence（单条证据）**：
`evidence_id, source_type, source_ref, fetched_at, resource_version, tenant_scope, query_params_hash, content_digest, summary, trust_level`；可引用原始工具结果，不将长日志全文塞进模型状态。

**Action Request（动作意图）**：
`action_id, task_id, actor, tool_name, schema_version, args, environment, risk, expected_effect, idempotency_key, plan_version, approval_required, approval_id`。

**Action Result（权威动作回执）**：
`action_id, status, observed_effect, side_effect_known, resource_version_after, error_code, retryable, evidence_refs`。

**Memory（经筛选的长期资产）**：
`memory_id, tenant_id, project_id, category, content, source_evidence, confidence, verified_at, expires_at, version, status`；候选/已批准/过期/冲突状态区别存储。

**Skill Manifest（项目自定义治理元数据）**：
`name, version, purpose, applicable_conditions, required_tools, required_permissions, inputs, outputs, acceptance_tests`；具体操作方法保存在 `SKILL.md`、脚本/参考文件中，按需加载。

**Context Manifest**：
`task_id, stage, prompt_version, included_evidence_ids, memory_ids, skill_versions, tool_schema_versions, token_budget`；用于追踪为何调用模型时看到这些信息。

## 5. 两个最能体现 Agent Engineering 的技术实验

### 5.1 动态调查与证据链：防止“查询到一个错误就直接猜根因”

S1 的 401 可能来自密钥版本不一致、权限禁用、签名时间漂移，不能让演示数据只有一个显而易见的故障样本。至少设计一个迷惑性负例：最近确实发生配置变更，但真正原因是用户权限被禁用。要求 Agent 调用授权范围内的具体数据，展示支持与反对证据，无法确认时进入 INCONCLUSIVE，而不是编故事。

**成功判据**：可复查 Evidence ID；结论由明确环境事实支持；不凭“有 401”直接推导密钥轮换；调查步数与 Token 成本受控。

### 5.2 长程任务与外部副作用：防止“恢复后重复执行”

审批前关闭服务，重启后以相同 `thread_id` 继续；验证之前把执行服务断连，再恢复并查询动作结果。

**成功判据**：上下文恢复正确；审批拒绝没有副作用；同一 `idempotency_key` 最多产生一次业务变更；成功/失败/未知结果被正确区分；重新执行不绕过审批，跨任务不得引用其他租户 checkpoint。

## 6. 核心能力逐步挂载设计

### 6.1 Function Calling 与 MCP

Function Calling 是模型提出的结构化行动意图；MCP 是能力提供方与 Agent Host 的协议接口；Skill 是任务方法而非工具权限。首周先有 2—3 个类型化本地工具打通主流程，再把只读数据查询迁移到真正的 MCP Server；验证 tools/list 与 tools/call、参数 Schema、资源作用域和错误结果。工具应该有允许环境、风险级别与返回 Evidence 引用。写操作通过独立的权限/审批服务执行，不能因为工具已经注册就默认授权。

首批建议：`get_ticket`, `get_service_config`, `query_auth_events`, `get_change_history`, `probe_endpoint`, `update_ticket`, `apply_allowlisted_test_config_change`。其中后两者属于写操作；配置变更只允许隔离测试环境并进行白名单参数校验，禁止原始密钥出现在 LLM Context 和日志。

### 6.2 Memory 与 Knowledge

- Working / Task：当前调查状态和待办，进入 Task State/Workspace。
- Episodic：一次有证据的处理经验；先候选、后确认，不直接自动固化。
- Semantic：客户/项目已核验的特殊约束，附来源、版本和时效。
- Procedural：经验证的排障流程可进一步提炼为 Skill。
- Knowledge：企业维护的 API 文档/鉴权规范，始终与 Agent 经验分开治理。

测试应包括：同客户不同工单复用；不同客户不得泄露；配置发生变更后旧记忆不覆盖当前查询结果；撤销记忆后不得再次召回。首周先做结构化条件筛选，语义向量检索只有在案例证明确实需要时才引入。

### 6.3 Skills 的价值

至少两个 Skill：`auth-incident-triage` 与 `config-drift-triage`。发现阶段只暴露名称、描述和适用条件；选中后加载版本化 Manifest/方法；必要时读取细节脚本、检查单、故障特征。Skill 不能自行越权执行操作。可做开/关 Skill 的回归对照，检验排查准确率、调用次数或流程一致性，而不是仅展示“成功加载”。

### 6.4 Context 与长历史

Context Builder 必须优先保留当前 Task State、已确认的有效证据、许可边界与操作预算；历史消息、完整日志、冗长工具输出可摘要/卸载，但保留可回查的证据引用。对于摘要要明确“来源与时间”，避免把临时推断提升为事实。

### 6.5 Trace / Observability

记录任务阶段流转、模型调用、工具名与参数摘要、证据 ID、Plan 版本、审批决定、动作结果、Verifier 结果、Token/延迟/错误类别。含密钥和个人信息的字段必须脱敏。Trace 对应 `run_id + task_id + checkpoint_id`，并可关联评测用例编号。

## 7. 第一周交付分层：有技术深度但控制范围

### 7.1 P0：七天必须完整展示的“深垂直切片”

1. 一套实际可运行的演示后端、工单与配置/鉴权事件数据；S1 至少具有“正确故障”和“容易误判的负例”。
2. 一个可执行的 LangGraph 主图：有界调查、真实工具调用、证据链、计划、审批、执行、独立验证、交付。
3. 至少一个真实 MCP 只读工具调用，不是函数名叫 MCP 的假接入。
4. 持久化 checkpoint、审批拒绝/批准、进程重启恢复和至少一次副作用幂等验证。
5. 至少一种真实跨任务 Memory 使用；至少一个有版本记录且按需加载的 Skill。
6. 自动化测试和一份可以本地重跑的评测报告；README 明确支持与不支持的能力。

### 7.2 P1：首周争取，之后一至两周深化

完成 S2；Memory 冲突修正/遗忘；两个 Skills 的消融；Context Manifest 和细粒度成本分析；更丰富的故障假设循环；测试隔离环境自动恢复、Trace 可视化、更多安全负例。新增内容不得破坏 P0。

### 7.3 P2：按实际价值选择

S3 Redis/500 全链路；受控 Subagent 并行调查；异步触发与事件流；多租户生产级授权；完整沙箱与动态能力 Registry。**P2 不是首周交付门槛**，不承诺生产级可用。

## 8. 七天开发路线：每日任务、验收门槛、失败保底

| 日期 | 核心开发任务 | 当日必须验收 | 当日保底 |
|---|---|---|---|
| D1 · 10/17 | 建 Demo Domain Schema 与 S1 fixtures；冻结 Task/Evidence/Action 数据契约；主图节点骨架；单条无模型 mock 贯通 | 能从输入工单生成报告；保存非模型业务状态；契约测试通过 | 单例 mock 端到端 + Task 状态结构 |
| D2 · 10/18 | 接真实模型 Function Calling；构建 Investigation/Observation 与 evidence gate；加入调查预算和负例 | 正确选择本地只读工具；遇缺证据能补查/终止 | 一条确定性调查路径 + 可归档证据 |
| D3 · 10/19 | 建 MCP Server 接配置和事件；接 MCP client；统一 Tool Result/Evidence；错误分类 | 真实 MCP 查询返回业务数据库内容；越权查询被拒 | 一只读 MCP 端到端打通 |
| D4 · 10/20 | 接持久化 checkpointer；审批中断/恢复；动作服务的幂等键与业务回查；明确副作用边界 | 关闭重启后接着审批；拒绝零写入；重放不重复动作 | 持久暂停恢复 + 审批拒绝路径 |
| D5 · 10/21 | Memory 候选/审查/入库/检索；作用域限制；Context Builder；初步 Skill 选择 | 第二张工单复用经验证经验；跨租户无泄漏 | 1 条跨任务 Memory + 作用域测试 |
| D6 · 10/22 | 完成至少一个版本化 Skill；S2 可选；构造含负例的回归集；Badcase 分类与 Trace | 10–16 条至少覆盖正/负/权限/恢复的用例可重跑，记录首次真实结果 | P0 回归与最重要失败分布 |
| D7 · 10/23 | 端到端集成；修复阻断性缺陷；录制演示脚本；README 与架构/权衡；简历 STAR 草案 | 首要 S1 情景从调查到恢复动作+状态回查、跨重启演示成功；指标可复现 | 可靠的 P0 纵向切片、明确未实现项 |

**每天工作量**：新项目预算约 4—5 小时；算法约 30—45 分钟；投递约 20—30 分钟；Agent 面试表达约 15—20 分钟。导师紧急任务可调整开发任务量，但不降低已声明功能的验收标准。以上为计划，不代表日期到达后即自动完成。

**任务排序原则**：当天 P0 失败 → 暂停新功能、修复或缩减非关键范围；不得带着未验证的基础设施继续叠加 P1/P2。

## 9. 代码组织建议与工程门禁

```text
opspilot/
  app/
    api/                # ticket/task/approval 查询与命令
    graph/              # state.py, nodes.py, routing.py, build.py
    context/            # context_builder.py, manifest.py
    tools/              # typed_tools.py, mcp_adapter.py, policy.py
    domain/             # tickets.py, configs.py, events.py, actions.py
    memory/             # candidates.py, store.py, retrieval.py
    skills/             # registry.py, loader.py
    evaluation/         # runner.py, metrics.py
    observability/      # trace.py, redaction.py
  mcp_server/           # 真正对外暴露 MCP 工具的服务
  demo_service/         # 可复现故障、数据和隔离可控操作
  skills/
    auth-incident-triage/
      SKILL.md
      manifest.yaml
    config-drift-triage/
      SKILL.md
      manifest.yaml
  tests/
    unit/
    integration/
    regression/
  fixtures/
    cases/
  docs/
    architecture.md
    contracts.md
    decisions/
    eval_protocol.md
  README.md
  pyproject.toml
```

**合并门禁**：每项开发以单一变更目标提交；必须附命令、测试结果、示例 Evidence/Trace、影响范围；禁止偷偷更改公共状态 Schema、审批语义和既有评测用例。风险变更以 ADR（架构决策记录）走评审。图结构调整必须说明“为什么仅增加节点无法解决”。

**代码实施标准**：外部工具操作可 stub 但要明确标记，无法用于验收；真实验收由工具返回值、数据库状态和版本快照独立判定；测试具有固定 seed、固定 fixtures 和版本锁定；密钥走环境变量且日志脱敏。

## 10. 评测与成功标准（不要虚报数据）

### 10.1 建议最少 16 条冻结案例

- 故障正确诊断（4）：密钥版本不一致、回调地址错误、服务权限禁用、无真实故障；
- 迷惑性/欠证据（4）：错误线索、过期发布、缺失日志、相互矛盾的证据；
- 权限与安全（3）：跨租户查询、未批准写入、恶意工具返回指令；
- 恢复与副作用（3）：审批前重启、写入已成功但响应丢失、拒绝审批；
- Memory/Skill（2）：跨工单复用正确经验、记忆过期/Skill 错选。

案例数是目标，编写后固定数据集版本；首周保底可以先稳定运行 10 条，并明确未覆盖的剩余类别。

### 10.2 度量和门禁

| 指标 | 定义 | 首周原则 |
|---|---|---|
| Verified Task Success | 符合情景预设的环境事实、授权与最终状态，而非答复看起来正确 | 公开原始分子/分母，不预设好看的通过率 |
| Evidence Grounding | 关键诊断主张具有可回查来源和事件/配置版本 | P0 主要结论必须绑定至少一条证据 |
| Tool Validity | 工具名称、参数、权限、结果 Schema 正确 | 关键操作 Schema/权限校验全过 |
| Approval Safety | 未批准或拒绝后，是否发生写操作 | 负例中必须为零 |
| Idempotency | 重放或重复提交是否造成第二次业务副作用 | 已批准动作的重复执行不得重复变更 |
| Resume Correctness | 进程重启后能否按原 Task 继续而不丢失计划/证据/审批 | 演示和自动集成测试都要验证 |
| Memory Scope & Freshness | 是否越界、是否以过期记忆覆盖实时事实 | 越界为零；冲突场景有明确处理 |
| Cost / Latency | provider 请求、Token、关键任务时延 | 保留真实数据，不宣称已优化 |

### 10.3 必须保留的 A/B 或消融证据

在相同模型、温度/采样、fixtures、预算与工具版本下，选择对照项：`Memory ON/OFF`、`Skill ON/OFF`、`Evidence Gate ON/OFF` 至少一组；既看成功率，也看工具调用数、错误类型、时间与 Token。样本不足时只表述“探索性对照”，不推广成普遍结论。

### 10.4 风险优先级

| 风险 | 危害 | 防护与回退 |
|---|---|---|
| Graph/State 漂移 | 模块不兼容、回归倒退 | 统一 Schema + ADR + 契约测试 + 小 PR |
| 重试重复写入 | 修改了两次业务状态 | 幂等键、动作台账、写后回查、隔离节点 |
| Memory 污染 | 错误经验不断放大 | 候选态、来源、过期、冲突、作用域与纠错 |
| Prompt Injection / 越权 | 通过工具文本欺骗模型、跨客户数据泄漏 | 工具结果视为不可信数据；程序级 ACL/Policy，密钥脱敏 |
| 工程环境超期 | 为监控与部署耗光冲刺时间 | 内嵌 Demo API + 最小数据库 + 单进程 MCP |
| 结果不可复现 | Demo 漂亮但不适合面试追问 | 冻结 fixtures、独立 Verifier、Trace、执行命令 |
| 过度追求复杂 | 首周什么都做了却无完整主链 | P0/P1/P2 分层，独立验收，强制停手规则 |

## 11. 三方协作：谁决定什么、如何避免重演项目漂移

### 11.1 三种角色

- **项目主 Agent（本对话）**：目标与范围管理、架构契约、任务拆分、Review/验收定义、跨模块一致性检查、实验解释与简历追问路径。
- **独立第三方评审**：从业务、工程、技术真实性和求职价值角度反对或修订设计；应明确指出“必须改、建议改、不必改”，不只是给出赞同。
- **Luna（实施方）**：按冻结版本编码、运行测试、提交可复现证据；提出需要修改契约时先书面 ADR，不擅自改变主链。

**现状限制**：项目主 Agent 目前不能直接与第三方评审或 Luna 跨独立会话自动对话、启动其编码或验证其私人运行环境；需要用户将本文件发给第三方，并将回复带回本对话。经对齐后，可向 Luna 交付完整实施任务书；如果已建立可用仓库连接，后续可按仓库实际权限审查提交内容。不得冒称已达成三方共识或 Luna 已经开工。

### 11.2 正式评审回合

**R0（当前）**：本文件 `v0.1-review` → 第三方逐项审阅。  
**R1（第三方回信）**：给出总评、P0 风险、替代设计、开发量判断、具体应改条目，逐项标注“Blocker / Major / Minor”。  
**R2（主 Agent 回复）**：建立《评审分歧与处理清单》；逐条 Accepted / Modified / Rejected，附原因、成本与影响测试，形成 `v0.2-candidate`。  
**R3（必要时第二轮）**：只复核尚未决议的 Blocker；不反复发散全部选题。  
**R4（冻结）**：确定业务场景、主 Graph、数据契约、P0 演示、测试门槛和 P1 待办 → `v1.0-implementation-baseline`。  
**R5（Luna 开工）**：在确认的仓库与运行环境中按每日任务拆分开发；每个 PR/阶段返回测试和 Trace；主 Agent 进行审查。

### 11.3 第三方必须回答的 12 个问题

1. **选题是否合理**：OpsPilot 相比单纯技术支持 Agent，多出来的 AIOps 部分能否提供足够的 Agent 深度，还是反而拖垮七天 MVP？
2. **首周是否可完成**：哪些 P0 机制最可能超出 30–35 小时开发预算？如必须砍功能，砍什么且仍保持作品价值？
3. **主 Graph 是否合理**：固定阶段与调查循环是否会过度工程化？有哪些必须的状态转换/超时路径遗漏？
4. **代码实施边界**：单 Graph + 独立业务服务 + MCP 是否足够？是否需要减少层次？
5. **工具真实性**：怎样在不搭监控平台的情况下，让故障调查具有可信环境事实？
6. **恢复一致性**：Checkpointer、动作台账、审批、业务写入之间最难的竞态和幂等边界是什么？
7. **记忆设计**：首周做规则/结构化 Memory 是否充分？何时才有理由引入向量检索？
8. **Skill 设计**：两个 Skill 是否真正承担方法复用？如何避免把固定 Prompt 改名叫 Skill？
9. **权限与安全**：首周至少要覆盖哪些跨租户、注入和拒绝审批的负例？
10. **评测可信度**：哪几个指标和反例最能防止“只演示成功案例”？
11. **面试竞争力**：哪些模块能形成可以问深的设计取舍？哪些只是框架 API 调用、很难形成简历亮点？
12. **决策建议**：明确给出 `Approve / Approve with conditions / Rework`，列出最多 5 个阻断性修改，附优先级。

**禁止宽泛反馈**：如“架构很好，建议增强可观测性”而没有影响范围、验收方法或削减建议，不视为可以执行的审查结论。

## 12. Luna 实施委托书（条件生效；第三方完成评审后才发送）

> **前置状态：未生效**。以下是预备交付，不代表用户已经要求 Luna 现在开始、也不意味着 Luna 已收到任务。

**系统目标**：严格以 `v1.0-implementation-baseline`（待冻结）为准，先实现 OpsPilot 的 S1 端到端深垂直切片；基于 Python、LangChain、LangGraph、真实 MCP Server 和真实数据库状态；先验证框架 API 可用，再扩展业务和 Memory/Skill。

**第一份编码任务包（待评审后发送）**：
1. 创建项目骨架、版本锁定、单命令启动、环境变量样例，不提交真实密钥。
2. 实现小型 Demo API 与工单/配置/事件 SQLite 数据模型；至少 S1 正例与一个迷惑性负例。
3. 实现 Task State、Evidence、Action、审批等 Pydantic 契约和单元测试。
4. 创建 LangGraph 节点骨架，以确定性 mock 工具跑通 Intake→Prepare→Investigate→Plan→审批→Act→Verify→Deliver；**不要抢先做多个子 Agent**。
5. 交付 `README quickstart`、测试命令与输出、一个完整 Trace、当前已知问题和下一步建议。

**Luna 每次回报的固定格式**：
`变更清单 → 架构契约差异 → 运行命令 → 单测/集成/回归结果 → 真实外部副作用及回查证据 → 失败与未完成项 → 是否触发 ADR → 下一最小任务`。

**禁止事项**：未经批准改主 Graph 和契约、以模型生成回答代替真实验证、跳过审批操作生产资源、对真实凭证做截图或输出、用不可复现的 “Looks good” 冒充测试、替用户擅自决定 P1/P2 的新增范围。

## 13. 第三方反馈表（可直接复制填写）

```text
第三方评审 — OpsPilot v0.1-review
总评：Approve / Approve with conditions / Rework
适配 Agent 岗位（0–10）：
业务真实性（0–10）：
架构合理性（0–10）：
一周 P0 可实现性（0–10）：
技术追问深度（0–10）：

Blocker（需冻结前解决）：
B1. 问题 / 为什么是阻断 / 替代方案 / 影响模块 / 预计工作量 / 验收方法
B2. ...
Major（建议首周解决）：
M1. ...
Minor（可排入 P1/P2）：
m1. ...

明确建议删除的设计：
明确建议保留的机制：
建议首周最小闭环：
建议 2–3 周扩展路线：
是否可以交付 Luna 实施：是 / 有条件 / 否
```

## 14. 冻结前尚需回答的开放问题

- 使用哪个支持稳定 Function Calling 的模型 API？是否限制模型预算和并发？**不能在选型前假设所有模型工具调用行为一致。**
- Demo API 优先 Java 还是 Python？建议选择最省工且最易产生可复现故障的实现；Java 不是新项目的核心技术卖点。
- 首周“受控处置”操作必须变更测试配置，还是可以先做工单写入并把运行态配置修复放 P1？**当前推荐：尽量完成至少一次隔离测试配置真实变更及验证；若拖慢主线，以工单写入作为经第三方批准的保底。**
- 是否有愿意复用的开源演示服务、预备仓库或已有工单系统？未提供时默认自建最小实现。
- 评测样本规模在时间约束下是否选择 P0=10、增强=16？优先真实覆盖关键风险，避免单纯追求数目。

## 15. 参考资料与边界说明

- 阿里云《AI Agent Handbook》：https://github.com/aliyun/ai-agent-handbook
- Handbook 第 4 章：任务——编排、长程推进与协作流转；第 5 章：信息——上下文、状态与可复用能力资产；第 6 章：行动——受控执行、验证反馈与交付准备。
- Handbook 第 8 章：Agent 状态存储与语义资产；第 13—15 章：可观测、安全、资产治理；第 21—22 章：黄金集与 Badcase。
- LangGraph 官方文档：https://docs.langchain.com/oss/python/langgraph/overview
- MCP 官方规范：https://modelcontextprotocol.io/specification
- 以上参考用于确认能力边界，**不构成项目已完成相关能力的证据**。具体框架 API 和 SDK 版本须由实施方在开发当日复核并锁定。

---

**需要第三方给出的最后一句话**：在这些约束下，你会批准这个方案进入实施，还是要求收缩/修改？请明确列出阻断项，而不是仅给鼓励性评价。
