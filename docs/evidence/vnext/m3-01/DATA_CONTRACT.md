# M3-01 Episodic Memory 数据合同（冻结版）

## 资产语义

复用现有 d5_memories Candidate→Active→Revoked 生命周期和 d5_memory_events 审计表。每条新资产使用 schema_version=opspilot-case-memory-v1、type=EPISODIC、source_authority=HISTORICAL_METHOD_HINT_ONLY，并把客观历史事实与归纳调查建议分离。

必需内容：

- problem_type：auth_401 或 auth_403_scope。
- source_outcome：REPAIRED_VERIFIED、DIAGNOSED 或 SCOPE_ESCALATED。
- source_task_id 与 source_refs；来源 Task 与每个目标 Task 必须不同。
- symptom_pattern、case_specific_facts、investigation_guidance、applicability、required_current_checks、limitations。
- source_evidence_ids、content_digest、approval_state、version、expires_at。
- source_refs 项含 kind、id、digest_or_version；S1 可含 VerificationReceipt/FrozenReport/Evidence，S2 含 DiagnosisReceipt/Evidence；只有真实 HandoffReceipt 才允许 SCOPE_ESCALATED。

不得把模型/用户文本直接写成可信事实。M3-01 使用可信 Domain 数据的确定性投影/抽取来生成历史事实和具体条件；任何建议仍是低信任候选，须由人工 APPROVER 审核。不得复制 secret、Authorization、完整用户对话或其他租户内容。经验中的事实始终标注为“历史事实”，不是当前 Evidence。

## 来源不变量

S1 候选仅接受同一 tenant/task 的 COMMITTED REPAIR、匹配的在线 HTTP 200 VerificationReceipt、不可变 FrozenReport 及仍可校验的来源 Evidence；Outcome 为 REPAIRED_VERIFIED。

S2 候选仅接受可信 DiagnosisReceipt、其同 Run/Request 的 Probe Evidence 与 Authz Decision，证明 HTTP 403、AUTH_ACCEPTED、DENY/SCOPE_INSUFFICIENT 且版本/request/event 关联一致；Outcome 为 DIAGNOSED。只有另有同一 Draft 的已提交 HandoffReceipt、Queue Entry、不可变摘要和匹配审计时，Outcome 才是 SCOPE_ESCALATED。

S2 行的 S1 专用 source_report_ref 与 source_verification_id 必须为 SQL NULL；禁止填哨兵字符串或伪造 Report/Verification Receipt。

## 内容摘要与适用性

Canonical JSON 使用 UTF-8、键排序、紧凑分隔并用 SHA-256。审核、查询、Reserve 和历史依赖校验均重新核对 version/digest、source refs、状态、expires_at、tenant/project/service/problem_type。

对已有 v8 D5 行设置 legacy schema 标记并原样保留旧 summary 与 S1 refs；不得把固定 MEMORY_SUMMARY 改称案例抽取。旧数据可按原有安全边界继续作为历史方法提示；新案例统计与旧行分开。

## Schema 决策

ADR-001 选择对现有 d5_memories 作无损 v8→v9 兼容迁移，使 S1/S2 共用同一 Memory identity、Candidate/Active/Revoked 生命周期、审批/撤销事件和检索入口。保留历史 D5 行及事件外键；把 S1 专用 receipt 字段改为 nullable，并增加结构化 outcome/source refs/experience/version digest 字段。v9 初始化必须可重入；v8→v9 旧行数量、字段、event FK 和校验结果不变。详见 ADR-001-memory-source-schema.md。
