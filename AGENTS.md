## vNext 当前开发总纲与正式评审前置要求

> **正式规划、范围变更或验收前，主 Agent、实施 Agent 和评审 Agent 必须从本次目标提交实际重新读取 `PROJECT_NORTH_STAR.md` 与 `AGENTS.md`，并记录该提交 SHA 及文件版本/Blob。** 旧聊天、历史报告和记忆不能代替本次读取；没有实际打开并核对内容，不得声称“已读取”。开始代码、测试、提交前，也先核对当前 Git 状态与目标 SHA，并按第 8 节准备冻结合同、遗留门禁和证据范围。
>
> 普通答疑和小型进度更新不要求完整评审格式；当交流形成正式规划、范围或验收决定时，再执行上述读取和记录。正式评审的起始核验区块、六个自问、双向限制验收、证据等级和固定裁决，以 [PROJECT_NORTH_STAR.md 第 8 节](PROJECT_NORTH_STAR.md#8-工作协议切片管理独立评审与防-workflow-漂移) 为准。入库后由主 Agent 独立核对实际 HEAD、Diff、入口链接与规范一致性；实施方自报不能替代这项核验。关键基线或证据缺失时必须 HOLD/UNVERIFIED。

> **重要：** 任何开发 Agent 开始规划、编码、测试或提交前，必须先阅读仓库根目录 [PROJECT_NORTH_STAR.md](PROJECT_NORTH_STAR.md)，特别是 2026-10-22 修订的用户目标和 2026-10-24 加入的切片管理与评审协议。
>
> OpsPilot 当前的首要产品目标是：构建用户可感知的、能够通过连续自然语言对话正确推进真实业务任务的 Agent。工程可靠性、安全授权及 Domain 事务是不可突破的底线，而不是替代 Agent 智能体验的开发目标。
>
> **学习目标同样属于正式要求：** 项目服务于用户的大厂校招 Agent Engineering / AI 应用研发准备。Context Engineering、上下文分层与压缩、分层 Memory、Knowledge、Skills、MCP 等应形成“白皮书原理 → 业务需求 → 源码实现与取舍 → 实验/失败证据 → 面试表达”的实践链。不能只因当前 S1/S2 暂不需要就删除核心学习内容；可提出有界业务扩展或标注清楚的能力实验，实施前仍须阶段授权。
>
> **当前补差方向：** 业务中的智能决策和连续任务体验仍落后于治理能力。后续任务卡须说明能力如何进入实际调查、影响合法下一步，以及用户如何持续推进任务；分别验收“已理解/复现”“已接入业务”“已证明效果”。不得用新增治理模块代替体验进展，也不得为展示智能制造无意义的推理步骤。
>
> 本文件下方的 D1–D7、M1 阶段说明属于历史开发约束。其中“仅 S1”“不做 S2”“当前只实施 M1-03”等旧阶段限制，不得用于阻止已经批准的新阶段。
>
> 当前实施范围由 `PROJECT_NORTH_STAR.md`、已冻结的阶段任务卡以及主 Agent 的最新验收和用户授权共同决定。安全不变量依然有效；若存在矛盾，停止相关变更并请求主 Agent 裁决。
>
> 不得擅自进入下一阶段、修改冻结 Gold、绕过 Gate/TaskControl/Approval/ActionIntent/Ledger，或扩建多 Agent、通用 Agent 平台。

---


# AGENTS.md — OpsPilot v1.0 工程规则（Luna 与其他代码实施 Agent 必须遵循）

**唯一执行合同：** `docs/baseline/v1.0-implementation-baseline.md`。第三方 R5 已批准设计；实现仍需逐阶段验收。开发进度见 `TASKS.md`。

## 不可违反的边界

1. P0 只承诺 S1：真实调用方仍用旧 `credential_ref` 导致业务 API 401；获批后配置 CAS 更新，并由**同一 service / integration / principal / route** 的真实业务调用恢复到业务 200。主体 DISABLED 是迷惑负例，禁止自动启用或替换凭证。
2. LLM 只能建议只读调查工具/假设。`tenant_id`、actor、审批、Policy、资源授权、风险、预算扣减和状态转换来自可信程序；模型不能自由输入密钥/URL/Authorization。
3. Graph checkpointer 管执行进度，Domain SQLite 管 PlanAuthorization/Approval/ActionPermission/ActionIntent/ActionLedger/业务事实/交付回执。**不能把 checkpoint 当成外部副作用的唯一状态证据。**
4. `get_or_create_action_intent` 必须**先于 REPAIR/DELIVER 首次调用**持久化同一 canonical request、action_id/key/digest；同键异摘要拒绝，历史 COMMITTED 回执可回查。计划失效与新提交在同一 Domain 事务内裁决。
5. REPAIR 与 DELIVER 分别审批消费。修复验收在线真实探测；报告/验证收据先持久冻结，DELIVER 用独立 ActionIntent 幂等追加工单。工单写入失败不能重新 REPAIR。
6. 外部证据、记忆、Skill 内容均不可信任为策略指令；真实凭据仅工具侧处理。在线 Verifier 不能接触离线 Gold/fixture expected labels。
7. 两个可信本地租户/操作者足以展示隔离边界，但绝不可宣传为生产级 IAM。未经批准，**受限配置与工单业务写入均为零**。
8. 不得为展示而新增 Redis、S2/S3、多 Agent、A2A、自建网关、复杂前端、向量 DB 或监控平台。初版代码以一个 Agent app、一个 Demo Domain、一个只读 MCP Server 为范围。
9. 每个任务必须附真实测试日志、执行命令、Trace 与已知失败；不得把 mock 成功或文档冻结当作已实现。不许杜撰指标。
10. 节点重命名/合并并非问题；如触及状态兼容性、执行/审批语义或 E01–E10 行为，先提出简短设计变更，由主 Agent 审查。

## 开发流程

- **D1**：真实模型 Tool Call、MCP stdio tools/list + tools/call、持久 interrupt/跨进程 resume 三 smoke；无模型 S1 真实因果链。**不要在 D1 提前做 D3/D4 业务事务完整系统。**
- **D2**：动态调查、Evidence Gate 与只读工具；不通过不能接真实写入。
- D2 Investigator 的事实读取必须经过 TaskBinding 作用域下的真实 MCP Client/Server；D1 `get_demo_service_info` 聚合工具只用于 D1 回归，不得进入正式 Investigator 工具集。
- D2 模型不能指定 tenant、actor、Authorization、凭证值、任意 URL 或 thread ID。MCP Server 从持久可信 TaskBinding 取得 scope；Domain 每次查询均重新核验 task/resource 归属。恢复 checkpoint 前必须先校验 thread 所有者。
- D2 只读循环的程序预算默认最多 8 次模型请求、6 次 MCP `tools/call` attempt；每次外发前持久登记，重试/恢复重放都计数。Gate 只返回 `READY`、`NEED_MORE`、`NO_ACTION`、`INCONCLUSIVE`，只用类型化、同租户、同任务、同资源、版本兼容且足够新的 Evidence；模型文字不能直接决定 Gate。
- D2 的 `READY` 只允许生成诊断与 Plan 候选，不执行配置或工单写入。主体 `DISABLED` 返回 `NO_ACTION`；缺失事实在预算内可 `NEED_MORE`，冲突、重复无增量或耗尽预算则安全停止为 `INCONCLUSIVE`。
- **D3**：只从同任务 `READY` 与其 Evidence 生成不可变 canonical Plan；Gate 本身不授予执行权。沿用 D2 单主 Graph，以 `interrupt` 等待可信 CLI 审批；Graph checkpoint 只保存 Plan/Intent/Receipt 引用，Domain SQLite 保存计划资格、Approval、分开的 REPAIR/DELIVER Permission、ActionIntent、ActionLedger、VerificationReceipt、冻结 ReportArtifact 和 DeliveryRecord。
- D3 的 REPAIR/DELIVER 首次业务写入前必须各自持久化 ActionIntent；动作入口只接受 Intent ID，由同一 Domain `BEGIN IMMEDIATE` 事务检查当前 Plan/审批/版本/许可并提交 CAS 或追加工单。事务内不调用模型、MCP 或 HTTP。
- D3 恢复证明必须由同一 TaskBinding 的 service/integration/principal 对固定业务 route 发出真实 HTTP 200，并校验 `order_id`、`status` 与版本；验证成功后先冻结报告，再执行独立 DELIVER。未审批、拒绝、DISABLED、过期版本或验证失败时不得产生越权配置/工单写入。
- D3 的本地 `support-a` / `approver-a` / `executor-a` 仅演示信任角色；D4 才完成系统性崩溃窗口、并发取消/替换、响应丢失与重复恢复矩阵。
- **D4**：恢复、动作身份回查、取消/替换、授权消费、工单去重、越界及响应丢失故障注入。
- **D5**：一个 `auth-incident-triage` Skill、一类经批准 Episodic Memory、最小 Context Provenance。
- D5 Memory 只能从可核对的同任务 COMMITTED REPAIR、在线 RECOVERED VerificationReceipt、冻结 ReportArtifact 和来源 Evidence 创建 CANDIDATE；仅同租户可信 APPROVER 可确认或撤销。查询按可信 TaskBinding 推导的 tenant/project、当前 DB state 与 expires_at 过滤；Memory/Skill 只能给调查方法，不能改 Evidence、Gate、Plan、权限或审批。
- D5 的每次模型调用均在出站前持久记录 Prompt/Tool schema digest 和实际选用的 Skill/Memory ID 与版本。Prompt 每次从当前 SQLite 重新检索，checkpoint 不得保存后再注入已撤销的记忆文本；继续任务须重新校验 Skill digest/version。
- **D6**：冻结 E01–E10 回归、成本/错误记录及探索性对照。
- **D7**：干净环境演示、文档、可重跑报告、面试追问。任何硬门禁失败则不向下一层叠加功能。

## 每次提交必附

`Commit/branch`、锁定依赖、实际改动、运行命令、测试分子/分母、失败明细、业务事实证据、外部副作用/审批/安全影响、下一步与是否需变更基线。

**本地已有 AGENTS.md 时，本稿是合并目标，不要抹掉原有安全条款或机器环境说明；冲突必须由主 Agent 裁决。**

## 从原工作区保留的约束

- 旧项目和其他学习任务仅作只读参考，不修改其中的代码或资料。
- 在 D1 中只完成 D1 范围；不以常规实现选择为由引入额外审批，也不扩展到 D2 及后续阶段。
- 归档文件中的旧方案和任务卡仅供溯源。实施时只按根目录本文件、`TASKS.md`、当前阶段任务书及唯一有效的 v1.0 基线执行。

## vNext M1-03 的范围衔接

- v1.0 基线继续约束 D1–D7 历史能力及其回归；vNext 任务不得覆盖或重写这些冻结合同。
- vNext/M1-03 的范围依据 `docs/handoff/vnext/OpsPilot-vNext-v0.3-product-architecture-contract.md`、`docs/baseline/{API_CONTRACT,STATE_TRANSITIONS,ACCESS_MATRIX,EVENT_RECOVERY,MEMORY_LINEAGE}.md` 与用户本轮提供的 M1-03 任务卡。`docs/baseline/vNext-product-baseline-candidate.md` 是待审实现快照，不表示第三方签字或 M1 总体验收。若合同冲突，停止相关变更并提交变更说明，由主 Agent 裁决。
- M1-01 与 M1-02 均已通过主 Agent 独立验收。当前用户授权只实施 M1-03；按单人工作流直接在 `main` 开发、测试、提交并推送，不新建分支或 PR。M1-03 完成后停止并等待主 Agent 审查，不自行进入 M1-04/M1-05。
- M1-03 交付 Vue 工作台与持久真实只读聊天。CHAT_READONLY 不进入业务 Investigator Graph，不改变业务 Task/审批/Plan/ActionIntent；TaskControl、LangGraph、D3 Domain 继续是唯一业务状态权威。不得把 Graph checkpoint 当作 Task 权限事实来源；用户关键纠错仍是未信任输入，不能提升为 Evidence 或审批授权。
