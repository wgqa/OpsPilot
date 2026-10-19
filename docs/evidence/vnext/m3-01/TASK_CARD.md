# OpsPilot vNext — Luna M3-01 正式开发任务卡

**主题：可信案例经验 → 人工审核 → 跨 Task 实际使用 → 撤销停止使用**  
**签发角色：主 Agent（独立规划 / 代码与证据验收）；执行 Agent：Luna**  
**固定审查基线：`main@e46d99231f5ef259754228683a1504bf18cea79f`（2026-10-19 核对）**  
**阶段状态：本卡授权 M3-01 的有限范围实施；M3-02（长对话压缩）与 M4 均未授权。**

---

## 0. 为什么这一阶段值得做（北极星与停止条件）

OpsPilot 是**面向 API 接入支持工程师的对话式故障调查与受控处置 Agent**，不是通用 Memory 中间件。M1/M2 已证实连续对话、纠错、MCP/HTTP 证据、S1 可信修复及 S2 可信诊断/本地受控交接。M3-01 新增的**唯一主要用户价值**是：

> 支持工程师完成一个真实可信案例 A 后，能提出经过来源验证的**具体、有限适用范围**的经验，交给有权人员审核；在独立任务 B 中，Agent 能把批准的经验作为**调查方法提示**实际纳入并选择工具，但始终以当前 TaskBinding、MCP、HTTP、Domain Gate 为权威；经撤销/过期/作用域变化后，后续调用不得再使用它。

本阶段完成以下可演示用户链即停止：`可信 A → Candidate → APPROVER 确认 → 新 Task B 调查（含 provenance）→ 撤销 → B 后续模型出站/恢复不再载入该经验`。用 Memory ON/OFF 配对实验报告真实增益或无增益，不能以“模型 Prompt 中出现 Memory”替代“有用”。

**明确不做：** M3-02 的 ≥20 轮长对话压缩、SummaryChunk/ContextCache 完整递归依赖图、通用向量库/embedding 检索平台、知识图谱、自动自我修改、训练/微调、多 Agent、远程知识系统、外部审批平台、自动 Scope 授权、重写 M1/M2 Harness。可以实现 M3-01 所需的最小历史消息失效检查；不可借口“先建底座”扩大范围。

## 1. 开工前实际环境和优先级

1. 先核对真实仓库根目录、`git status --short`、`git rev-parse HEAD`、`git remote -v` 与 `origin/main`，记录 SHA；若主线已前进，立即报告差异，不擅自套用旧基线。保护用户本地未暂存 `AGENTS.md`、`PROJECT_NORTH_STAR.md`、`开发目录/`、既有 `runs/`、`.pytest-*` 等；严禁 `git reset --hard`、`git clean` 或强行覆盖。
2. 若本地 `PROJECT_NORTH_STAR.md` 存在则阅读；同步阅读 `AGENTS.md`、`docs/handoff/vnext/OpsPilot-vNext-v0.3-product-architecture-contract.md` 的 M3/N3/N4，尤其此前 M1/M2 已冻结的安全边界。`AGENTS.md` 若含旧的“仅 M1/S1”范围限制，先辨别其历史阶段意义，**不得自行突破仍生效的安全约束**。
3. 检查现有 `opspilot/domain/episodic_memory.py`（D5）、`opspilot/domain/investigation_context.py`、`opspilot/domain/chat.py`、`opspilot/investigator.py::_prompt_messages`、`opspilot/domain/database.py`（当前 `user_version=8`）、`opspilot/domain/s2_diagnosis.py`、`opspilot/domain/s2_handoff.py`、`opspilot/web/app.py`、`frontend/src/App.vue`、`tests/test_d5_context.py`。复用已有能力，先给出代码入口地图。
4. 在**独立冻结标准提交**中保存 `docs/evidence/vnext/m3-01/ACCEPTANCE_PLAN.md`、`GOLD.json`、`RUBRIC.json`、`EVAL_PROTOCOL.md`、`DATA_CONTRACT.md`、`ACCESS_MATRIX.md`、`API_CONTRACT.md`、`SOURCE_BASELINE.md`、冻结摘要清单及本卡。至少列出 **M301-01～M301-14** 的精确 PASS/FAIL/NOT_RUN 标准；先冻结评估 Task B、模型预算、来源与可选工具，再写实现或看评测结果。
5. 完整流程：`冻结提交 → RED（保留原始失败）→ 最小实现提交 → GREEN / 新鲜真实评测 → 证据提交 → 推送 main → 停止`。不能回写已冻结 Gold 或 M1/M2 历史分数；修订评估器必须独立版本和记录原因。

## 2. 现有代码事实，必须以此设计而非从零造轮子

- `episodic_memory.py` 已提供 `create_memory_candidate`、`confirm_memory`、`revoke_memory`、`list_applicable_memories`、`insert_context_provenance_in_transaction`。当前 `PROBLEM_TYPE='auth_401'`、`MEMORY_SUMMARY` 为固定的通用 401 建议，`_source_for_task()` 强依赖 S1 已提交 REPAIR + HTTP 200 + VerificationReceipt + Frozen Report。不能把这种固定文字当作“案例经验生成已完成”。
- 现有 `d5_memories` 列 `source_report_ref`、`source_verification_id` 非空，且 `d5_memory_events` 外键关联它；**S2 的 DiagnosisReceipt/HandoffReceipt 不是 S1 的 Report/VerificationReceipt**。迁移需诚实表达多种来源，不能向旧字段填假的 S1 receipt 字符串来欺骗 Schema 或校验。
- `investigator.py::_prompt_messages` 目前 S2 模式排除了 Episodic Memory；`chat.py::_current_memories` 也只选 `auth_401`。`d5_context_provenance` 已跟踪 selected_memories，Agent 调用前已有资产检查机制。新能力应把真正合格的 S2 Memory 连接到现有路径，避免再做第二个失控的 Prompt 拼接器。
- `chat.py` 已按 Task scope 过滤部分历史回答的 Memory / Evidence 依赖，并以约 24,000 字符上限裁剪；**长对话摘要压缩属 M3-02**，不可在本阶段一并重建。
- S2 `HANDOFF_READY` 只是草稿；`SCOPE_ESCALATED` 需已提交本地 HandoffReceipt；两者不是 `REPAIRED_VERIFIED`。任何新经验字段必须忠实反映业务状态。

## 3. 用户故事和冻结案例（先于实现）

**US-A：S1 已修复的认证故障**：Task A 必须真实具有相互关联的 COMMITTED REPAIR、当前可信 VerificationReceipt（HTTP 200）、冻结报告与来源 Evidence。用户点击“提炼为候选经验”，看到具体症状条件、曾验证事实、推荐检查方法、适用/不适用条件、来源引用和“不是当前事实”警告。APPROVER 人工确认；之后同租户/适用服务下**不同 task_id** 的 Task B 才能选中此经验。

**US-B：S2 403 权限不足**：Task A 可信 HTTP 403 + `AUTH_ACCEPTED` + 同 request Authz `DENY/SCOPE_INSUFFICIENT` + DiagnosisReceipt，可提案 **DIAGNOSED** 经验；若另有 HandoffReceipt 才能提案 **SCOPE_ESCALATED（本地队列接收）** 的经验。不能推断“管理员已审批”“已授 Scope”“API 已恢复”。Task B 即使读了该经验，也须自行查询最新 Probe、Authz 决定；遇 403 但非 Scope 不足时不能根据历史经验发起交接。

**US-C：经验撤销**：APPROVER 撤销经验。Task B 的下一次模型调用、Worker 恢复或重启后重试必须排除该经验及任何以其为事实基础的被选历史模型回答。已发生的旧模型输出和持久审计不回滚，只保留带“旧来源已失效”标记的可查记录。

**US-D：无适用经验/攻击场景**：跨租户、不同 project、错误绑定、过期、未人工批准、来源不存在/摘要 digest 被篡改、无真实 S1/S2 receipt、旧 Knowledge 与当前 Policy 冲突、用户在聊天中要求“把我说的直接记为已修复”，均不能变成 ACTIVE 或授权依据。

**Gold 要包含**至少同一 Task B 不同表述、相同表述不同真实 Authz 事实、正/负案例以及跨 Task 权限边界。来源 A 与评估 B 必须在 `task_id` 层分离；不得用评估题答案生成来源经验。评估者应能按 Evidence/Receipt 独立确定正确决策，不能由模型话术判分。

## 4. 数据合同：具体经验不是固定模板

每条经验候选至少包括以下**具有明确含义**的结构化信息（允许字段命名按仓库风格调整并冻结版本）：

```json
{
  "schema_version": "opspilot-case-memory-v1",
  "memory_type": "EPISODIC",
  "problem_type": "auth_401 | auth_403_scope",
  "source_outcome": "REPAIRED_VERIFIED | DIAGNOSED | SCOPE_ESCALATED",
  "source_task_id": "trusted-existing-task-id",
  "source_refs": [
    {"kind": "VERIFICATION_RECEIPT | FROZEN_REPORT | DIAGNOSIS_RECEIPT | HANDOFF_RECEIPT | EVIDENCE", "id": "...", "digest_or_version": "..."}
  ],
  "symptom_pattern": "简洁可泛化症状，不复制 secrets",
  "case_specific_facts": ["历史案例 A 实际证明的事实"],
  "investigation_guidance": "候选检查路径/工具选择方法，不是授权命令",
  "applicability": {"tenant_scope": "trusted", "project_scope": "trusted", "service_scope": "trusted", "required_current_checks": ["..."]},
  "limitations": ["不能仅凭 403 判定缺 scope", "历史不能替代当前 MCP 证据"],
  "content_digest": "canonical_sha256",
  "approval_state": "CANDIDATE | ACTIVE | REVOKED",
  "source_authority": "HISTORICAL_METHOD_HINT_ONLY"
}
```

强制原则：**客观历史事实与归纳建议分离**。若采用模型生成候选，仅把模型输出作为未经信任的提议，严格结构校验、可信来源逐字段绑定、敏感字段清理、人工审批；禁止模型杜撰来源、补写当前授权或自动激活。可以选择更省成本的确定性提取+人工编辑，而不是为“Agent 感”增加不必要模型调用，但经验必须**确实具有案例独有内容**，不能再全部用硬编码的同一段建议。

**Schema 方案要求先冻结 ADR：** 比较 (A) 安全版本化改造现有 D5 schema（保留历史行、事件 FK、旧 API）与 (B) 一张最小的补充 case-provenance 表并复用 D5 审批/撤销主入口的成本与风险；选择较小且可诚实表达 S1/S2 不同回执的方案。数据库当前 v8，若新增迁移应为**明确的 v8→v9 增量**、可重复初始化、旧 S1 记录兼容、无失真 sentinel，无破坏性数据重建。不得为了 schema 简化重写已有 D3/S2 业务来源表。未经主 Agent 授权不得创建新的 Memory 微服务或独立记忆数据库。

## 5. 工作包（每包具体验收）

### WP0 — 先冻结计划、数据选择、RED 与源码地图

- 提交 §1 指定冻结文件和版本 SHA/hash，记录现有 D5 正负例与源代码行级入口。
- 特别冻结 8 组 **Task B** ON/OFF 配对实例、环境 snapshot、数据来源 A、评分规则、模型和预算；包括：S1 正例 2、S2 正例 2、旧经验与现有权威事实冲突 2、无匹配/跨边界负例 2。允许测试实例在设计期调整，但**首次模型评估之前必须完整冻结**；不得事后删题。所有 8 组各 ON、OFF 一次，理论计划分母 **16 真实试次**，若运行失败要按实际分母和原因记录，不能捏造成功。
- 先在旧实现上 RED：S2 无可用经验、固定 401 summary 不体现案例独有方法、Web 无经验治理入口、跨任务效果未知。保留退出码和错误原始日志。不能删旧测试、改旧 Gold。

### WP1 — 可信 S1/S2 源验证和候选经验

- 复用 S1 `_source_for_task` 验证链；新增 S2 DiagnosisReceipt 的真实 tenant/task/request/decision/evidence 绑定检查；若经验声称“实际交接”，还需正确 HandoffReceipt + immutable digest。**DIAGNOSED 与 SCOPE_ESCALATED 是两个不同等级**，禁止默认 S2 已恢复。
- Candidate 一次生成后有确定的版本/digest、来源、限制、失效时间（可复用 D5 的 ≤30 日约束）、状态记录与 audit event；同一来源/类型/版本重复提交要么幂等同一候选，要么明确冲突，不得静默多份同源事实。
- 不泄漏密钥、Token、原始 Authorization、其它租户任务正文和不该跨 owner 传播的隐私字段；案例经验可共享**经审查的方法与非敏感的必要条件**，不能默认共享 A 的全量原始日志。

### WP2 — 用 D5 实际审核/撤销，最少 Web UI

- 重用可信 registry 与现有 SUPPORT owner / APPROVER 职责（**谁可以创建候选、谁可以审批，按 ACCESS_MATRIX 冻结并在 Domain 重查**）。禁止从请求体接受 actor_id/role/tenant；写入口必须 Session/CSRF/Origin + request idempotency。
- 仅需最小 UI：Task A 中候选预览/创建、APPROVER 列表/详情/确认/撤销、Task B 的本次上下文 Memory ID、版本、采用/排除原因。可以是一个简洁的“经验与来源”面板，不开发通用资产后台。
- 候选、审核和撤销均可查事件/返回版本；确认/撤销持久状态重启后保持；跨租户/非授权角色不得枚举。
- “用户说记住这次”“模型说批准”只能被视为意图提议，不能绕过人工确认。

### WP3 — Task B 受限检索、适用决策和真实 Investigator 集成

- 使用可信 TaskBinding 限定 tenant/project/service 与问题种类，剔除过期、撤销、摘要 digest 变化、无效来源、版本不适配；S1 和 S2 都可按业务事实选到相应记忆，但不能串用。可复用 D5 的 `list_applicable_memories` 接口或其可兼容扩展。
- Memory 只能是低信任的历史调查方法提示，按独立字段注入 `investigator.py::_prompt_messages`；不能放入当前 Evidence、Skill 系统指令或 Action 许可。任何最终业务 Gate 继续使用当前可信 HTTP/MCP/Domain。
- **实际使用证明**至少包括：`selected_memory_ids/versions/digests` → `ContextManifest` → 模型/工具尝试 → evidence/Gate；对匹配任务 B，至少一项对照中可观察到被合法采用的记忆对调查工具顺序、排除无效工具或合理澄清决策的影响。不得把“LLM 自述我用了记忆”单独算成实际效用证据；若没有可观察差异/增益，记录 `UTILITY_NOT_PROVEN` 而非造假。
- 为严谨对照实现运行时 Memory ON/OFF **测试级开关**，不得通过删数据库或移除真实工具来实现 OFF。禁用 Memory 仅去掉候选历史建议，不得改变现有 Skill、Knowledge、权限、证据 Gate 和本次 Task 事实。

### WP4 — 撤销与来源失效：阻止未来污染

- 在 **模型出站前**核验 Memory ACTIVE、版本、scope、TTL、source receipts；对 Worker 暂停/恢复、Task 新 Run、新聊天回答均生效。Prompt 构建→调用注册的 TOCTOU 走现有 `insert_context_provenance_in_transaction` / `reserve_attempt` 或等价事务检查；失效时重建不含该 Memory 的上下文或安全停止，不得带旧 prompt 直接出站。
- 对已记录的历史 `AssistantMessage`：若其依赖被撤销的经验，在新 Context 中不得作为有效回答重新注入；允许原历史 UI 展示，并明确历史依赖已失效。**完整 SummaryChunk/多级摘要依赖图留给 M3-02**；本阶段不可生成无 lineage 的新摘要。
- 已经发往 Provider 的请求无法撤回，撤销只约束后续调用；已 COMMIT 的 S1 Repair 或 S2 HandoffReceipt 不能因撤销历史建议而抹除。
- 跨租户、跨项目、其它用户/来源失效、版本替换、TTL、未知来源时 fail-closed。保留负例 trace。

### WP5 — Memory ON/OFF 真实效果评估

- 冻结 8 对、16 次真实执行的 **paired design**：同模型、Prompt 主版本、合法 MCP 工具、Skill/Knowledge、来源 A、Task B 初始事实、预算、观察窗口；两策略使用独立但等价的测试 DB snapshot，不能让 ON 的运行副作用污染 OFF。尽量交替或固定记录执行顺序，记录随机性和 Provider 波动，不得宣称因果或统计显著。
- 分开报告**安全/决策正确性**、**模型是否真实看到记忆**、**调查动作是否受影响**、**任务 Outcome**、**模型请求、MCP、Tokens、耗时**、**错误**。即使 ON 比 OFF 差也必须保留。Source Task A 不进入 Task B 的 Gold/Prompt，不允许把 Gold 标签泄露到候选记忆正文。
- 给出一次完整正例 Trace（A→B）和一次反例 Trace（经验与当前事实冲突，正确不服从历史结论），以及撤销前后 Trace；报告 `UTILITY_PROVEN` / `UTILITY_NOT_PROVEN` 限定于样本。不得仅比较总 Token 而不比较完成质量。
- 运行**真实 Provider deepseek-flash + 真实 MCP stdio/HTTP** 的至少一条 Web 用户链（Support A → Approver → Support B → revoke → no-use），固定真实模型、真实业务事实与脱敏网络/SSE/Domain provenance；单纯 CLI mock 不代替 Web 用户体验。

### WP6 — 最小安全回归及总结

- 全量 `pytest`（不少于上一阶段 186 项，实际按新增测试增长），M1/M1-HF/M2-01/M2-02-HF-01/M2-03 全链兼容；真实 S1 401→200、S2 403+handoff、MCP stdio、Vue build/lint 与 Web 回归。不得动历史评测分母。
- S1 审批等待后的 Evidence TTL / Revalidation 安全债务 **依然单独登记**。M3-01 不新增 REPAIR、DELIVER、Scope、Queue 写动作，且绝不能让 Memory 解锁这些动作。
- 产出 `docs/learning/vnext/m3-01/STUDY_NOTES.md` 与 `INTERVIEW_QA.md`：至少讲明 (1) S1/S2 不同来源证据 (2) Memory/Knowledge/Skill/Context 区别 (3) Memory 撤销与 Provider 出站控制 (4) ON/OFF 效用证明与局限，附源码入口和真实试次。

## 6. 冻结验收矩阵（14 项；WP0 首个提交需补成完整 Gold/Rubric）

| ID | PASS 标准（不是提交自评） | 失败定义 |
|---|---|---|
| **M301-01** | 独立冻结标准 SHA、摘要、8 对评测集、RED 早于实现；历史 M1/M2 证据不改写 | 标准晚于实现、改旧 Gold、事后删题 |
| **M301-02** | D5 旧 S1 Candidate/Active/Revoked 与老数据 v8→v9（若新增迁移）兼容 | 破坏旧资产、构造假 S2 report/verification ref |
| **M301-03** | S1 经真实已验证恢复产出带案例具体内容的候选，来源完整 | 固定通用 summary 冒充案例抽取；未验证恢复 |
| **M301-04** | S2 Diagnosis 与真实已交接是可区分来源；无 HandoffReceipt 不写 ESCALATED，更不写 RECOVERED | 凭草稿冒充交接或 Scope 已授 |
| **M301-05** | 人工批准前不检索；APPROVER 审核/撤销真实持久；错误角色拒绝 | 模型文字或 SUPPORT 越权直接激活 |
| **M301-06** | 同租户、同项目、适用问题的不同 Task B 确实检索并选入合法 Memory；provenance 绑定真实来源 | 同 Task 冒充跨 Task、只有界面记录无模型上下文 |
| **M301-07** | 经验和当前 MCP 事实矛盾时当前事实优先，业务 Gate 不用 Memory 授权 | 旧经验导致错误 403/401 处置、错误修复/交接 |
| **M301-08** | 撤销/TTL/失源/版本变更后后续模型调用和新 Chat 不带 Memory 或依赖它的历史回答 | 旧提示被缓存再次注入 |
| **M301-09** | Worker 恢复/进程重启、Prompt 构建后撤销的竞态安全停止或重建 | 出站使用已经撤销的资产 |
| **M301-10** | 跨租户、跨项目、不同角色/owner、伪造来源/摘要/请求体被拒，敏感字段零泄漏 | 越界检索/激活/读取，模型输出泄露 secrets |
| **M301-11** | Web 真流程 A 提案→APPROVER 审核→B 使用→撤销→B 下轮不使用；新鲜浏览器+Provider/MCP/Domain Evidence | mock UI/CLI 替代或无真实连续用户闭环 |
| **M301-12** | 8 对 16 次真实 ON/OFF 冻结 trial 全部纳入分母；真实 Token/时延/工具动作/Outcome，失败如实保留 | 只展示成功、靠 memory prompt 直抄正确答案、改 OFF 基线 |
| **M301-13** | 产出“经验影响调查选择”的证据及独立冲突负例；效果未提升也明确 NOT_PROVEN | 仅靠 LLM 自述或表面引用宣称收益 |
| **M301-14** | 新鲜全量 pytest、MCP/HTTP、S1/S2 回归、前端构建/lint、必要安全 smoke，原始失败保留 | 无新鲜证据或硬安全门未过 |

任何跨租户信息泄露、绕过 Domain Gate、Memory 变成授权/写工具、来源造假、撤销后新 Provider 请求仍带撤销内容，属于**M3-01 BLOCK**。普通效用没有提升不是安全失败，但必须原样标记 `UTILITY_NOT_PROVEN`，不能继续无限扩大架构寻找好看的分数。额外愿望例如 20 轮压缩或 Semantic Memory 平台 **不纳入 M301 分母**。

## 7. 产物与证据路径

在 `docs/evidence/vnext/m3-01/` 至少提交：

- `ACCEPTANCE_PLAN.md`、`GOLD.json`、`RUBRIC.json`、`EVAL_PROTOCOL.md`、`DATA_CONTRACT.md`、`ACCESS_MATRIX.md`、`API_CONTRACT.md`、`SOURCE_BASELINE.md`、`FROZEN_SHA256SUMS.txt`（先冻结）；
- `REPORT.md`、`RESULTS.json`、`TRACE.json`、`FAILURES.md`、`RUN_INDEX.md`；
- `runs/` 下真实 Provider/MCP/HTTP、Memory ON/OFF 配对记录、源码/模型/Skill/Knowledge 版本、Token 真实 usage、ContextManifest 选中/排除、Receipt IDs/digests、浏览器测试与**实际截图**、安全负例、迁移日志、完整 pytest、lint/build、S1/S2 smoke 原始日志；
- `docs/learning/vnext/m3-01/STUDY_NOTES.md` 与 `INTERVIEW_QA.md`。

结果文件必须区分 `IMPLEMENTED`、`TESTED`、`REAL_MODEL_OBSERVED`、`UTILITY_PROVEN`，不能用测试 PASS 暗示有 Memory 效用。任何真实模型和 MCP 未运行项目按 `NOT_RUN` 或 `PARTIAL` 报告，不得拿 fixture 或历史跑过的试次补分母。发布证据要脱敏 API keys、cookies、CSRF、口令和无权读取的 Task 内容。保留早期 RED 与所有失败尝试，不做“清理历史失败”操作。

## 8. 有边界的开发权和返回主 Agent 的格式

本卡授权在 M3-01 范围内：扩展 D5 的案例资产与来源校验、v8→v9 增量 Schema（若需要）、最小 Experience API/UI、Investigator/Chat 的受控检索与出站前确认、冻结评测和相应测试。禁止自动替用户审批，禁止改变 S1/S2 的真实业务写入与原始验收合同。

完成后提交并推送 `main`，汇报以下**可复核事实**：冻结 SHA、RED SHA、实现 SHA、证据 SHA 和 `origin/main`；总 pytest 数；8 对 ON/OFF 的分组成绩及 Token/MCP；S1/S2 来源、撤销与隔离负例；真实 Web Task A→B 旅程与 screenshot；已知限制/未修复项与本地未提交文件状态。即使未达到所有门禁也如实停下，以 `PARTIAL/BLOCKED` 交还主 Agent。

**最终停止规则：完成 M3-01 即停止。未获得主 Agent 独立验收和用户新一轮授权，不得进行 M3-02、M4 或通用 Memory 平台开发。**
