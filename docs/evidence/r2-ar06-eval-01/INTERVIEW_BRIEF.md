# R2-AR06-EVAL-01 · 校招面试简报

## 两分钟讲解

我把 OpsPilot 的 R2 用户旅程整理成 6 类工作、每类开发集 D 和留出集 H，共 12 个冻结案例，另有 4 个独立安全负例。Gold 记录用户目标、可信初态、允许资料、可接受决策、必要证据和禁止行为；它只供离线评估器使用，不进入 Assistant 的 Prompt、MCP 或业务数据库。

我复用了正式 FastAPI/Worker/Assistant、Domain SQLite、LangGraph Checkpoint 和本地 Mock MCP。评测文件保留每个 Session/Task/Run、回答关联、当前 Evidence/Observation、模型请求与工具 Schema 摘要；聚合器只读显式评定的 PASS/PARTIAL/FAIL/NOT_RUN/UNVERIFIED，不会把 `Run=SUCCEEDED` 等同于业务完成。

Phase A 使用确定性 Fixture，不是模型质量实验。**Phase A 离线工程覆盖评定为 6/12 PASS（50%），不是当前 Agent 的真实任务成功率。** 原始状态保留为 6 PASS、3 PARTIAL、3 NOT_RUN。执行一致性核对发现：仅 E01-D 逐字使用冻结输入并由新独立测试执行；8 例是 `MAPPED_EXISTING_TEST`，3 例未运行；H 留出独立执行为 0/6。另有 3/4 安全负例通过，恶意文档指令案例尚未运行。Provider 请求为 0。最有价值的发现是 S2 测试表面 pytest 通过，但底层正式聊天 Run 因 Fixture 缺少工具绑定接口而 FAILED；随后 Task 调查和用户明确提交的交接回执成功。因此 E11 记 PARTIAL，而不是用 Task 成功掩盖聊天失败。

历史真实模型数据独立列出：AR-03 Real LLM 02 用 5 次 Provider 请求取到 PROCESSED 观察，却因工具预算没有交付最终回答；AR-04C ON 场景把旧观察说成本轮重读，仍是历史 FAIL。旧 M2-02 的 R/H/A 48 条成绩使用不同 Gold 和 Runtime，不能和本轮相加，也不足以替当前六类旅程证明 Agent 优势。

## 面试追问

### 1. 为什么不只做单元测试？

单元测试不能证明用户消息从 Session 入库后，能经过 Context、正式 Assistant、工具调用、Observation、回答持久化和 UI 可读路径完成目标。本评测沿用 API/Worker/Domain 链，检查最终用户成果与业务回执。

### 2. Gold 如何构造，为什么有 D/H？

用六类用户工作定义 12 个 Gold：普通问答、协议升级、材料分析、实时调查、连续协作、可信处置；每类各有 D 开发集和 H 留出集。冻结输入、初态、必要证据和禁止行为在 `CASES.json`。Phase A 复用旧 AR-03/04/05 工程测试，只有 E01 完成逐字的独立执行；其余非逐字案例明确标成 `MAPPED_EXISTING_TEST`。H 有 6 例但 0 例独立留出执行，因此当前 H 结果不能用于泛化判断；缺夹具就保留 NOT_RUN/PARTIAL，不改 Gold。

### 3. 如何避免模型提前看到答案？

Gold 和 Rubric 只由记录/聚合脚本读取。新 E01 测试仅从 Gold 取用户题面发送，预期 Outcome 不传给模型。模型请求另存消息与工具 Schema 摘要，便于审计实际输入。

### 4. 如何分别评分任务、来源、决策、Outcome 和安全？

M1 报 `Phase A 离线工程覆盖评定：6/12 PASS`，PARTIAL 不算 PASS；这不是模型真实成功率。M2 追踪材料、文档版本、同 Event Observation、来源当前性及无依据确定性。M3 单独评合理工具/澄清/停止决策。M4 记录 `QUEUED`、`PROCESSED`、`HANDOFF_READY`、Receipt、`DELIVERED` 等业务结果。M5 分开 Provider Usage 和 Fixture 估算。M6 把越权、未经批准动作和来源复活作为独立负例。

本轮 Fixture 的语义由测试断言覆盖，M3 没有独立人工/模型评分，所以没有报告自主性分数。

### 5. 如何证明 Agent 根据 Observation 调整，而不是固定工具顺序？

本轮 Fixture 只能证明链路可以按 Observation 生成 QUEUED 和 PROCESSED 两种不同结论，不能证明模型自主选择。历史 AR-03/AR-04C 有真实工具选择 Trace，但样本少且保留了预算失败与来源当前性失败。下一次真实实验需观察模型面对相同合法工具时是否根据结果继续、澄清或停止。

### 6. R/H/A 如何公平？哪些数据不足以支持“Agent 更好”？

本轮不伪造 R/H/A 对照。冻结协议说明当前 Base 没有共享当前工具/Prompt/预算/评估器的等价 R 和 H Runtime。未来对同一冻结子集用相同事实、权限、预算和评估器比较；无法匹配则只做案例研究。旧 M2-02 的 48 条不是本轮同一 Gold，不能推导当前 A 优于 R/H。

### 7. Memory/Skill 收益与 Token 成本如何对照？

AR04B Fixture 的 ON 3 个模型请求选择了同一 Memory ID/version，OFF 3 个请求没有注入；当前业务观察工具与回答一致。它证明选择/关闭/来源边界，不证明回答质量提升或成本收益。E03 按需加载了协议 Skill，但没有 Skill ON/OFF 配对实验。Fixture Usage 不是 Provider Token。

### 8. 一个真实失败及定位过程是什么？

R2 Phase A 发现 S2 pytest 测试漏断言前置 Assistant Run 状态。隔离 DB 显示 `CHAT_READONLY=FAILED`、`ASSISTANT_STOP:NotImplementedError:`，fixture call `UNKNOWN` 且无响应；真实 Provider 请求为 0。S2 Investigator 后续成功，明确提交后才产生本地 PENDING_REVIEW Receipt。我们把案例评为 PARTIAL，并保留两次 Trace，不改生产功能，也不把测试误绿写成 PASS。

历史真实失败另有 AR-03 PROCESSED 未交付最终回答，以及 AR-04C Memory ON 对旧 Observation 当前性的错误陈述。

### 9. 样本与真实模型请求有多少？结论适用于什么范围？

冻结集 12 例，Phase A 离线工程覆盖 6/12 PASS、3 PARTIAL、3 NOT_RUN；只有 1/12 冻结输入精确且独立执行，H 独立执行 0/6。另 3/4 安全负例通过，N04 未验证。真实 Provider 请求 0，因此本轮不支持真实模型成功率、Token 成本或质量推断。AR-03、AR-04C 等历史真实模型失败按各自 Base、模型、费用和 Trace 独立引用，不能合并成一个成功率。

### 10. 如何准备下一轮真实模型评测？

先冻结每个案例实际发送的逐字输入、附件和可信初态；每例使用新的隔离 Domain/Checkpoint，不继承旧 Session、Memory、Grant 或费用账本。保持候选 SHA、模型/配置、Knowledge、Tool Schema 和预算可追溯，每例只记录首次结果，失败不选择性重跑。Provider Usage 与 MCP/Observation 从真实 Trace 和账本读取；用冻结 Rubric 分别评分来源、决策和业务 Outcome，`Run=SUCCEEDED` 不等于 PASS。只有 D/H 均有独立执行、权限和事实匹配时才报告模型结果；缺样本就写明限制。

## 可复现材料

- [评测报告](EVAL_REPORT.md)
- [逐案执行一致性审计](EXECUTION_FIDELITY.md)
- [Phase B Live 准备清单](PHASE_B_READINESS.md)
- [冻结案例](CASES.json)、[Rubric](RUBRIC.json)、[执行协议](EVAL_PROTOCOL.md)
- [逐次运行 JSONL](runs/RUNS.jsonl)、[聚合结果](RESULTS.json)
- [E11 失败诊断](runs/E11_S2_ASSISTANT_FIXTURE_FAILURE.json)
