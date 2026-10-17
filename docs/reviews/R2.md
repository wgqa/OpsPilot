# OpsPilot v0.1 → v0.2：主 Agent 对独立评审 R1 的正式回复（R2）

**日期：** 2026-10-17  
**送交对象：** 独立第三方架构评审  
**回应结论：** 五个冻结阻断项 **B1—B5 全部 Accepted**，以本回复附带的《OpsPilot v0.2 候选实施基线》落地。  
**当前状态：** 待独立评审确认；**未冻结 v1.0、未下发 Luna 全面实施**。

## 一、总回复

感谢 R1 将重点从功能数量转移到「业务可验证恢复、持久执行一致性和受限动作契约」。我们接受收窄第一版使用人群：**负责客户 API 接入故障的技术支持或后端工程师**。项目仍名为 OpsPilot，但 P0 不再泛化成大规模 AIOps 平台。复杂度集中在同一类 401 故障下的动态调查、真实恢复、审批变化、状态恢复和记忆失效。

R1 的另一个关键修正完全接受：**正确处置 ≠ 实际恢复 ≠ 交付完成**，三种含义必须在数据与评测层独立表达。

## 二、B1—B5 逐项决议

### B1 — Accepted：S1 真实业务因果链和完成语义

**固定 S1**：tenant A 下的 `client-integration-a` 通过注册的身份 `client-principal-a` 调用 `orders-demo` 的 `GET /api/orders/demo-order`。客户端集成配置 `credential_ref` 仍指向 `cred-v1`；服务端有效凭证版本为 `cred-v2`。实际业务调用先返回 401。唯一被批准的恢复动作是 `switch_credential_ref(integration_id, expected_config_version, new_credential_ref=cred-v2)`，执行者是可信业务服务，模型不接触密钥内容。动作成功后，**仍由同一 integration、同一 principal、同一业务路径调用**，须取得 200 及固定业务数据断言才算恢复。

负例：主体处于 DISABLED，即使附近有凭证变更，也不得替换凭证/重新启用主体；只能调查、说明并转交。Fixture 的 `expected_root_cause` 只供离线评估，不能提供给 Agent 或在线 Verifier。

**完成语义**：Graph `COMPLETED` 只表示任务流程结束；独立业务结果为 `RECOVERED / NO_CHANGE_NEEDED / ESCALATED / UNRESOLVED`。如果修复已成功、工单写入失败：业务结果可以是 `RECOVERED`，交付阶段 `DELIVERY_PENDING`，恢复后只重试工单写入。只改工单不计入“真实处置恢复 P0”。

### B2 — Accepted：状态权威来源、审批和动作事务

权威来源固定如下：Graph 检查点只掌管执行阶段、调查状态、预算与当前计划引用；可信任务绑定记录掌管 actor/tenant/project/thread；同一 Demo Domain 服务及其 SQLite 业务表掌管审批、动作台账、客户端配置版本和工单；Artifact 存储掌管原始证据与报告；Memory 表掌管跨任务经验。**不把 LangGraph checkpoint 与业务修改冒充同一个原子事务**。

冻结提交协议：

1. Plan 生成固定 `plan_id/version/hash`，包含资源 ID、环境、预期配置版本、唯一允许动作、参数摘要和业务探测断言；风险/审批等级由程序计算。
2. 可信审批入口核对任务归属与审批人角色，把 Approval 绑定完整 plan hash、目标、环境与具体动作摘要；拒绝不产生受限业务变更。
3. 实施时 Domain 用 SQLite 单事务：再次核对身份/作用域和已有动作台账；新动作要求 Approval 有效且计划/资源版本匹配；执行 `UPDATE ... WHERE version = expected_version`；写 action ledger 与审批消耗记录；统一提交。
4. `idempotency_key` 在同一 tenant/task/action 命名空间内唯一。重放同一请求 digest 返回原回执；同一 key + 不同 digest 明确拒绝。**重放返回原结果之前仍执行调用者的身份与所有权校验**，但不能因批准已消耗就阻止合法查询原回执。
5. 若操作已提交但响应丢失，Graph 在同一动作身份下查询 ledger（也允许安全重投同 digest、同 key），不得重新生成 key 或重复更新。
6. 修复动作和工单交付是两个独立的幂等动作；工单备注以 `(task_id, report_version)` 去重。**工单写回本身亦是受限业务写入**：获批 Plan 必须另列允许的工单目标、字段/报告引用及交付动作类型；该交付授权不允许越权修改其他工单或配置。审批拒绝仅生成本地报告，不调用工单写入。
7. P0 每个 Task 只允许一个执行者，同时保留域侧唯一约束/事务锁；多个不同任务试图写同一资源由版本条件阻止；失败未知时不进行新处置。

要求 E08/E09 覆盖等待审批退出、提交前退出、提交后响应丢失、回执后 checkpoint 丢失、重复批准、旧批准换参数、修复成功而交付失败。

### B3 — Accepted：可执行动态调查、证据和有界预算

- 模型只负责：提出假设、选择只读 Function Call/MCP 查询、解释 Observation、提出下一查询或提交诊断草案。
- 程序负责：凭据与作用域、工具/动作准入、预算扣减、计划风险、证据门禁、合法状态转换、审批检查。
- `DiagnosisDraft` 最少包含 `hypothesis_type, supporting_evidence_ids, contradicting_evidence_ids, unresolved_questions, suggested_next_query`。
- Evidence 对象必须具备资源、主体、事件/观测时段、当前资源版本/配置版本、来源与事实字段；原始回执、摘要分开存。
- `EvidenceGate` 只可返回 `READY / NEED_MORE / INCONCLUSIVE / NO_ACTION`。
- S1 READY 必须以工具可重查的当前事实满足：同一 tenant/integration/principal；principal=ENABLED；业务探测确认为 401；集成现用凭证引用与目标允许版本不一致；版本和时间仍有效；关键事实无冲突。仅有 Evidence ID 不满足 READY。
- 调查预算默认**至多 6 次只读工具调用（传输重试也计入）**，另设模型调用上限、每次请求超时与总时限；预算按持久任务计，不因重新启动归零。项目可选择在每次出站调用前持久预留预算，无法严格保证时不得声称预算硬约束。
- 提取 `call_id ↔ ToolMessage/tool_call_id ↔ evidence_id`，明确 Evidence 按 ID 去重并保留版本；计划由 Plan 节点单写，身份预算和状态由受控节点更新。
- 验证失败 P0 不自动新一轮修复，转交人工；`WAITING_INPUT` 与 `INCONCLUSIVE` 分开；执行中取消不能宣称已回滚。

### B4 — Accepted：身份可信入口与全路径作用域校验

P0 不做完整 SSO/RBAC，但用两个预置的可信本地操作者及两个 tenant scope；身份由 CLI/Agent 应用的受信配置绑定，**不是由自然语言输入、模型工具参数或用户传来的任意 `tenant_id` 决定**。

- 任务创建、查询、`thread_id` 恢复、审批、工具查询、Evidence/Memory/Artifact 读取都先核对归属。
- MCP P0 采用**固定 stdio 传输**，从受信的 server 启动上下文获得 allow-scope；业务函数仍独立核验资源所有权。模型不可更改 scope。
- `probe_endpoint(service_id, integration_id)` 只访问登记路径和身份；不得接模型自由 URL、Authorization 或实际密钥。
- 外部文档/工具结果视为不可信数据；不能改变策略、审批和角色。密钥由工具侧解析并且不会写入 Prompt/Trace。
- 隔离测试不仅检查模型有没有拒绝，还检查底层查询和真实写入是否发生。

### B5 — Accepted：唯一的 P0、测试、工时与文档入口

P0 必须具备：一条 S1 正例的真实业务探测失败→批准修复→同身份业务探测恢复；主体禁用负例和欠证据分支；动态只读调查与有效 Evidence Gate；至少一个真实 MCP 查询；持久化 interrupt/checkpoint；原子业务动作、幂等、所有权；一个版本化按需加载的 `auth-incident-triage` Skill；一种经审核 episodic Memory（来源、作用域、ACTIVE/REVOKED/EXPIRED 过滤）；最小 Context 来源与版本记录；离线独立测试及真实轨迹。

不将 S2、Redis、第二 Skill、向量数据库、自动记忆合并、复杂压缩/Registry、Multi-Agent 等计入 P0。`NO_ACTION/ESCALATED` 可表示正确处置，但不算 `RECOVERED`。

工作量以 R1 的 **27–37 小时有效开发 + 3–5 小时排错缓冲**为规划基线。若只能保障约 3 小时/天，开发周期延长至约 10–14 天；七天仅为有足够容量的冲刺目标。开发第 1 天必须先做真实模型 Function Calling、MCP 和持久化中断 smoke，及不依赖模型的 S1 真实因果链；第 3 天以前首次集成真实审批→动作→同身份验证。每日报告区分保底和扩展，不自动声称完成。

冻结后，将 README、TASKS、AGENTS 及自动每日任务唯一指向 `v1.0-implementation-baseline`；当前 v0.1、R1、R2、v0.2 保留历史，不作为 Luna 实施指令。

## 三、采纳的 Major 与暂缓的内容

- **M1 Accepted**：一套 Agent 应用 + Demo Domain + 一个只读 MCP Server；Context/Policy/Memory/Skill 实现为普通模块/函数。API 界面可最小 CLI；无必要不建新的服务。
- **M2 Accepted**：框架、模型、MCP、checkpoint 持久恢复在 D1 smoke；共享业务查询函数，避免本地工具与 MCP 两套规则。
- **M3 Accepted**：首周一类有来源、可审核并可撤销的 episodic Memory，不按模型 confidence 自动转正。
- **M4 Accepted**：在线 Verifier 无法读取测试标准答案；离线 Eval 有故障注入配置和 Gold；两套权限与代码入口隔离。
- **M5 Accepted**：只冻结关键契约与外部行为，图节点可以合理增加、合并或删除；语义兼容性与回归影响需要记录。
- MCP 额外处理：区分传输/协议错误与工具级 `isError`；成功时优先解析经过 Schema 校验的 `structuredContent`，不把相同内容重复塞入 Context。
- 暂缓项目与 R1 的 L1—L5 完全一致。

## 四、请第三方 R2 复核的最后事项

1. B1 的「同一调用方身份重新请求业务 API」与独立业务结果是否闭合？
2. B2 的同库事务协议是否足以覆盖丢响应、检查点落后、审批过期及工单写回失败？请指出任何仍会重复副作用的具体时序。
3. B3 的 READY/NEED_MORE/INCONCLUSIVE/NO_ACTION 条件是否足以让 Luna 写出确定性门禁？如果条件太紧导致能力被写死，请明确如何松绑而不破坏安全。
4. B4 的本地可信身份 + stdio scope 是否足以形成诚实的 P0 安全展示？是否有遗漏的所有权入口？
5. B5 的唯一 P0 是否适用于 27–37 小时有效开发？如需进一步收缩，**不得删真实恢复、幂等/审批、越界、持久重启**；优先砍高级 Memory 实验或 UI。
6. 若无新的 Blocker，请回复 **“R2 五项闭合，同意 v0.2 升版为 v1.0-implementation-baseline，并可向 Luna 发 D1 任务包”**；有剩余 Blocker 请给出精确时序/验收条件。无需再重新辩论业务选题。

**附送：**《OpsPilot v0.2 候选实施基线》，包含对象契约、状态机、故障注入、E01—E10 评测映射及重新排序的实施任务。该文档目前仍标注“候选”，不是已执行代码或已通过测试。
