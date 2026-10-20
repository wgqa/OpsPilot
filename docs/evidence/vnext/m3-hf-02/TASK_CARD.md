# OpsPilot｜M3-HF-02 最终补强与学习证据任务卡

**任务类型：** Context / Memory 证据闭环、真实摘要失效实验、可靠性专项审计  
**执行者：** Luna / Codex  
**主 Agent：** ChatGPT  
**代码基线：** `main@c2f71e9b4e3db9fdc3cd522115f304e6a53dfaae`  
**起始状态：** M3 工程实现 ACCEPT_WITH_LIMITS；严格 E2E PARTIAL  
**授权方式：** 在本任务卡范围内连续实施，无须逐项等待用户确认

## 0. 本次任务的总目标

现有 M3 Context/Memory 模块主要工程功能已经实现。

本轮不开发新的 Memory 类型，也不增加新的 Agent 业务场景。

目标是补齐三方面：

1. **真实 Provider Payload 的可核对证据**：证明当前 Context/Memory 选用与排除结果，和实际发出的模型请求一致。
2. **真实长上下文摘要依赖与撤销实验**：让 Episodic Memory 真实进入模型上下文、影响 AssistantMessage、参与 Summary，再验证撤销传播。
3. **有限可靠性审计与学习交付**：分析历史 Worker 失败，整理完整源码学习链路和剩余风险。

按照以下 A → B → C 顺序连续执行。A 完成后可以进入 B，不必等待用户确认。

不得为了追求 PASS 修改旧 Gold、提高模型重试预算、伪造 Provider 请求或重构无关模块。

---

# A 阶段：Provider Payload 真实观测修复

**优先级：P0，必须先完成。**

## A1. 查明实际模型调用传输链

先确认当前真实依赖及请求路径：

- `langchain_openai.ChatOpenAI`
- OpenAI SDK 对应版本
- 实际使用的 `httpx2` / Transport
- Investigator 的 `ainvoke`
- Chat Worker 的 `ainvoke` / `astream`
- 压缩模型请求的真实调用路径

以前失败的观测器保留原始记录，不覆盖、不修改成所谓成功结果。

优先选用官方支持的客户端或 Transport 注入点。如需针对当前版本包装 HTTP 客户端，仅作用于独立验收进程，不将猴子补丁引入业务生产代码。

不得升级依赖来绕过本轮观测问题。

## A2. 先验证观测器本身

在隔离测试环境中，使用一个预先约定、完全非敏感的测试标记发起真实模型请求。

要求：

- 实际请求成功到达 Provider 并返回响应。
- 观测器确实看到发往 Provider 的序列化请求内容。
- 观测结果能够关联 Model Attempt、Run ID 和 Provider Response ID。
- 观测器不修改消息、请求参数、Tool Schema、超时或重试行为。
- 观测器不会记录 API Key、Authorization Header、Cookie 等敏感数据。

**禁止记录完整原始 Prompt 到 Git。**

允许在临时内存中检查原始请求内容，保存脱敏字段、必要的限定文本片段、内容摘要及校验结果。

必须说明：捕获的是实际 HTTP 传输前的请求体、SDK 构造的消息，还是应用构造的 Prompt。不能把后两者冒充网络请求体。

在完成上述独立校验之前，不得开展正式 Episodic 复验。

## A3. 新鲜验证 Episodic Memory 选用

在独立环境中运行当前代码。

优先复用 M3-CLOSEOUT-01 已有的合法业务场景准备方法，但必须生成新运行记录。

建立：

- 有可信业务来源的 ACTIVE Episodic Memory。
- 不同 Task 的真实模型调查。
- 当前有效 MCP Evidence。
- Context Provenance 与实际 Provider 请求的对应关系。

验证实际请求中确实包含适用的历史方法，并明确其非权威属性。

不能仅搜索 Memory ID，还要核对内容是否与选定版本、Digest、来源一致。

同时确认没有将 Task A 的历史 HTTP200、修复回执或授权错误地提升为 Task B 的当前事实。

## A4. 撤销后实际请求核对

通过原有 Web 审批路径撤销该 Episodic Memory。

随后发起：

1. 新 Chat Provider 请求。
2. 新 Investigator Provider 请求。
3. 至少一次带真实 Checkpoint 的跨进程恢复。

实际 Provider 请求体必须经过观测器核对：

- 旧 Memory 不再进入有效上下文。
- 依赖旧 Memory 的 AssistantMessage 不再作为有效历史使用。
- 相关 Summary 若存在，必须经过来源校验。
- Manifest 的排除原因与实际请求一致。
- 新请求仍保留可信任务状态与必要当前事实。
- 中断或恢复不得重置既有预算。

对发送内容的排除检查不应只用单一关键词判断；应结合实际请求消息结构、Memory 版本、受影响内容、来源依赖及完整选用/排除集合验证。

保留观测器覆盖范围和不能证明的部分。

### A 阶段验收

只有实际传输层的选用和撤销后排除均得到可核对证据，才能将原 E2E-03 的 Provider Payload 缺口标为已补齐。

若观测器再次失效，不要反复重跑完整业务流程。先单独修复观测器，再考虑业务复验。

**A 阶段若发现真实撤销后仍向 Provider 发送了失效 Memory，应判定为安全阻塞，优先最小复现与修复，不进入 B。**

---

# B 阶段：真实 Memory → Summary 依赖失效实验

**优先级：P1，属于学习必修专项；不追溯性修改原冻结 Gold。**

## B1. 实验目标

本轮要实际验证：

`Episodic A → AssistantMessage B → Summary C → 新 Context D`

当 A 被撤销后，C 是否通过依赖校验失效，以及新模型 Context D 是否排除了不再可信的内容。

这不只是一次单元测试。

需要通过真实 Web、实际模型压缩、真实 Domain、已有摘要持久化和 Context Builder 完成。

## B2. 实验条件

使用独立测试数据和当前正式实现。

在测试开始前冻结：

- 当前 Context 策略：HYBRID。
- 输入 Token 预算与输出预留。
- Task / Session 的来源与目标。
- Memory ID、Version、Digest。
- 摘要触发条件与预期依赖。
- 最多允许的实际 Provider 重试次数。

可以设置较低的测试 Token 预算以真实触发压缩，但不能在失败后不断提高预算直到成功，也不能人工修改数据库标记为“已压缩”。

禁止直接向 Summary 表插入伪造摘要。

## B3. 构造真实长对话

在 ACTIVE Memory 有效期间，让 Agent 产生至少一条真正依赖该 Memory 的 AssistantMessage。

随后通过真实 Chat 逐步积累有效对话历史，使 Context Builder 达到压缩条件。

需要真实观察到：

- 模型产生 Summary。
- Summary 持久化。
- Summary 关联了正确的原始 Message / AssistantMessage。
- AssistantMessage 的来源链指向 ACTIVE Episodic Memory。
- Summary 曾经被一次后续模型调用有效选用。

如果压缩了其他历史，却没有形成目标依赖关系，不能算本实验成功。

同时检查摘要没有将历史业务修复误写成当前修复，也没有丢失关键用户纠错、否定条件和未完成任务。

## B4. 撤销与失效传播

用独立 APPROVER Web 身份撤销 Episodic Memory。

随后新建 Chat Run，真实调用 Provider。

验证：

1. 旧 Summary 由于传递依赖失效，不再被直接复用。
2. 派生 AssistantMessage 不能绕过失效。
3. 系统选择有效来源重建，或者在预算不足时安全停止。
4. 失效判断由 ID、版本、Digest 和依赖关系完成，不依赖文本替换。
5. 新 Provider Payload、Manifest 和当前 Domain 状态一致。

随后重启 Worker，使用持久化状态继续，检查旧 Summary 是否复活。

### B 阶段验收

要求提供完整的来源依赖图、摘要版本、撤销事件、新请求与恢复轨迹。

如果真实实验受当前压缩策略或预算约束无法形成指定依赖，应明确报告技术原因，不得无限增加聊天轮数或重试次数。

原冻结测试仍保持不变；本实验作为新的补充学习证据单独报告。

---

# C 阶段：可靠性审计与学习交付

**优先级：P2。A 阶段安全门禁通过后，可在 B 阶段完成或受预算限制停止后开展。**

## C1. 有限调查历史 Worker 失败

历史记录存在两次：

`WORKER_RETRY_EXHAUSTED`

且当时 Provider/MCP 调用数均为 0。

本轮只允许：

- 根据现有日志、TaskRun、Worker Lease、Outbox 和状态记录复盘。
- 检查 Worker claim、重试分类、异常传播与持久化边界。
- 使用可控的故障注入进行最小复现。
- 判断是否与 M3 Context/Memory 修改直接相关。
- 如发现本轮范围内的明确缺陷，先冻结 RED，再执行最小修复及 GREEN。

不允许为了彻底消除所有 Worker 风险而重写任务调度器。

若无法复现或无法明确根因，记录 `ROOT_CAUSE_NOT_PROVEN`，不得猜测性修改生产代码。

## C2. Context / Memory 源码审计

对当前实现开展一次不扩功能的专项审查：

- Context Builder 中可信块和可选块的优先级。
- Token 估算与实际 Provider Usage 的偏差。
- Summary 构造、重试、持久化与恢复。
- 摘要来源的递归依赖与有效性检查。
- Episodic/Semantic 的作用域、版本、过期及撤销。
- Chat 与 Investigator 的来源校验是否有不一致。
- Checkpoint 恢复后是否重新构建可信 Context。
- Manifest 是否真实反映模型输入。

将发现的问题分成：

`P0 安全 / P1 正确性 / P2 可靠性或体验 / P3 后续优化`

只有与本轮验收直接相关的 P0/P1 明确缺陷可以最小修复。

其他发现进入后续审计清单，不自动扩大开发。

## C3. 为用户生成系统学习材料

用户暂时不会逐行跟进开发，因此本轮必须为之后的集中复盘提供可独立阅读的资料。

建立：

`docs/learning/M3-REVIEW/`

建议包含：

**ARCHITECTURE.md**

完整 Context/Memory 架构及职责，包括 Working、Session、Episodic、Semantic、Procedural、Knowledge、Skill 和 Checkpoint 的边界。

**SOURCE_WALKTHROUGH.md**

从 Web 创建 Task/Chat 到 Context 构建、Memory 选择、Provider 调用、Summary 写入、撤销、Checkpoint 恢复的源码阅读路线。必须包含真实函数名、文件和调用关系。

**DESIGN_DECISIONS.md**

明确区分阿里云《AI Agent Handbook》中的参考思想、OpsPilot 的具体工程实现和实际实验结论；解释为什么采用 Hybrid、来源 DAG、可信状态独立存储。

**FAILURE_STUDIES.md**

结合真实案例分析摘要被挤出、正式纠错丢失、撤销后来源传播、Provider 观测器挂错以及未知中断请求。

**INTERVIEW_QA.md**

至少 15 组 Agent Engineering 面试追问，覆盖设计原理、替代方案、源码、故障、评测与取舍。不要只写名词定义。

材料必须区分已经实现、自动化验证、真实端到端验证、尚未证明四种状态。

---

# D. 禁止开发漂移

本轮明确禁止：

- 启动 S3 或扩大业务覆盖；
- 新增 MCP 工具；
- 引入 Multi-Agent；
- 重构 LangGraph 主执行链；
- 新增 Memory 类型或独立 Memory 服务；
- 增加 Redis、向量数据库、消息队列；
- 修改既有业务审批、Gate 或 Ledger 语义；
- 为提高成功率而修改原 Gold；
- 将测试 Fixture 动作记为 Agent 的自主业务成果；
- 将已知的 Mock 结果包装成真实 Provider 或 MCP 结果。

**生产代码修改原则：原则上不改；只有获得最小复现证据的直接阻塞缺陷才允许最小修复。**

如需修改已经冻结的业务安全合同，停止并报告，不得自行决定。

---

# E. 最终验证和交付

新建证据目录：

`docs/evidence/vnext/m3-hf-02/`

至少保存：

- `SCOPE.md`
- `REPORT.md`
- `RESULTS.json`
- `FAILURES.md`
- `TRACE.json`
- `PROVIDER_OBSERVATION.md`
- `SUMMARY_LINEAGE.md`
- `SOURCE_AUDIT.md`
- `runs/` 中的新鲜原始日志及脱敏证据

真实实验需记录 Task、Session、Run、Attempt、Memory、Summary、Message 和 Provider Response 的关联。

记录每次 Provider 调用的实际 Usage；中断未确认的请求标记 UNKNOWN，不按零计费。

最终执行：

- 完整 pytest；
- Context/Memory 定向回归；
- 前端 typecheck、build、lint；
- 既有 S1/S2 安全回归；
- 独立核对本次 Git Diff 是否越界。

保留 M3-CLOSEOUT-01 的 PARTIAL 原始报告，不覆盖旧证据。

新报告明确标注：

- A 阶段是否 PASS；
- B 阶段是否有真实 Summary DAG 证据；
- C 阶段发现了什么，哪些未解决；
- 严格 E2E-03 是否具备 PASS_CANDIDATE 条件；
- 还有哪些证据或技术限制；
- 最终代码 SHA。

如果 A 阶段证据完整、必要安全门禁通过，并且原冻结 E2E-03 其余条件仍满足，可以提交 `PASS_CANDIDATE`，等待主 Agent 裁决。

B 阶段属于本轮追加的学习实验，不以实验未成功为理由追溯修改旧 M3 Gold。

最终交付后停止，不自动进入新业务开发。

**执行总原则：优先把原有能力证明清楚，再深入研究真实上下文失效，最后整理成用户能够系统学习的工程知识。**

本卡授权范围内可以连续推进，不必逐项请求用户确认；但任何超出范围的架构变更必须停止。不得让额度刷新或剩余资源成为无边界扩张的理由。