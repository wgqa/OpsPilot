# OpsPilot · Luna D7 最终交付与防漂移审计任务卡

> 任务状态：**待执行**；本文件是开发指令，**不是 D7 已完成的证据**。  
> 唯一实施合同：`docs/baseline/v1.0-implementation-baseline.md`。  
> 本轮起点：`main@28c3e1a65e46ca7992ccf6b783d96f00c0ce2e4d`（D6 已完成）。  
> 模式：**单人直接开发**。在 `main` 完成、测试、Commit、Push；不创建 PR / 分支 / Issue。  
> 角色：Luna 执行；主 Agent 做实现验收；随后**仅一次**独立第三方实现与漂移审计；用户最终亲自审阅。

## 0. 任务的唯一目标和停止条件

**将已完成的 D1–D6 项目变成可以从干净环境独立复现、能看懂源码、能如实展示边界、可供第三方审查的最终交付包。**

本轮**不再增加 Agent 能力**，不新增功能场景、不开发评测平台、不重构架构。D7 到此是本轮 P0 的**开发终点**，不是 D8 / 新架构讨论的起点。

验收停止线：

1. 在**与历史 D1–D6 工作目录隔离**的全新演示目录和数据库，从记录的锁定依赖运行 D3 真实模型+MCP+HITL 的完整业务闭环：原请求 HTTP 401 → 冻结 Plan → 独立审批 → 一次 REPAIR（配置 v7→v8）→ **同 service/integration/principal/route** HTTP 200 + `demo-order / CONFIRMED` → 冻结报告 → 单条 DELIVER。保留实际命令、exit code、独立进程信息、脱敏运行证据。**不复用旧成功数据库或旧 checkpoint 冒充新鲜运行。**
2. 用现有 D4 故障注入/恢复用例证明至少一条真实进程退出后的同动作身份恢复，回查同一 COMMITTED Ledger，版本仍只增加一次且工单最多一条。已存在的 D4 tests 可以作为复现入口；**不为“单命令演示”再开发调度平台**。
3. 从干净环境执行全量 pytest、`pip check`、必要语法检查，真实记录通过数、失败和环境。D2 主体禁用/证据不足至少复用本轮新鲜隔离运行或确切 D6 冻结轨迹；如果本轮未重新跑，明确标注复用证据的 SHA/时间，不假装新跑。
4. README 提供**初学者可按步骤实际操作**的最短主路线，包括依赖安装、配置 `.env`（不记录密钥）、一条完整 E01 演示命令、查看证据的方法、人工 HITL 的两进程命令及一条 D4 恢复测试命令。可以写 PowerShell 操作说明，**禁止新增无必要启动框架**。
5. 交付审计包：**冻结目标 → 实际代码 → 对应测试 → 真实日志 → 限制/偏差**，供无仓库访问权限的第三方审查。见 WP-C，不能只提供自述式报告。
6. STAR、面试追问和源码阅读地图忠于事实；E10 原始失败为 `PARTIAL`，D6 原始 5 次模型 smoke 4 PASS/1 FAIL、64/64 pytest、40 模型调用 / 33 MCP / 102725 Provider tokens **不得洗白、回填、重写历史**。D7 新测试结果以 D7 独立分母报告，不覆盖 D6 历史。

若安全红线暴露缺陷：停止宣称 P0 验收通过；只做与复现直接对应的**最小修复和重跑**，必须留下前后证据，禁止借机大重构。

## WP-A｜干净环境的真实交付复现（先做）

- 按锁定 `requirements.lock.txt` 建立干净 Python 环境。默认使用已有已验证的 Windows/CPython 3.14 组合；其它 Python 版本可标记未验证，**不做兼容性矩阵**。
- 使用全新 `.runtime/d7-*` 数据与 checkpoint 文件，以及**新的** `docs/evidence/d7/` 证据目录；不清理/覆盖 D6 历史目录。密钥只取本地忽略的 `.env`，不得落盘到审计包。
- 运行 `python -m opspilot.cli d3-smoke --db ... --checkpoint-db ... --evidence-dir ...`。要求真实模型请求、真实 stdio MCP、独立进程人工批准、受控动作、真实 HTTP 验证、冻结 Report 和独立 DELIVER 全部有证据。逐条复核 13 个既有 E01 断言，写出版本、订单字段、Intent/Ledger/Report/DeliveryRecord 引用和副作用数量。
- D4 恢复演示复用 `tests/test_d4_recovery.py` 中**真实 OS 子进程**的至少一个 after-COMMIT-before-response 或 stale-checkpoint 用例，显示 crash PID / exit code、重试 PID、重用 Ledger ID、配置与工单数量。若 tests 无法复现，则修**明确的阻断问题**，不新增复杂 CLI。
- 全量测试与依赖检查。关键失败**保留原始输出**；如果第三方可以运行项目，说明运行的外部依赖和必要环境变量。对于真实模型偶发异常，最多一次隔离数据的定向重跑用于定位，不能悄悄丢掉失败。

## WP-B｜以源码为中心的交付说明（最小改动）

- 更新根 `README.md`、`TASKS.md`，把 D1–D7 的实际状态、当前最终 SHA、D6 的 9 PASS + 1 PARTIAL 和 D7 新鲜测试结果分开写清；`AGENTS.md` 安全条款原则上不改。
- 写 `docs/evidence/d7/REPORT.md`：执行环境/版本、所有复现命令、退出码、测试分子分母、真实 Provider/MCP 的证据索引、唯一业务变更/交付条目、失败与限制、最终实现 SHA。
- 写 `docs/evidence/d7/DEMO.md`：不超过一个屏幕的最短演示叙述 + 可以复制执行的命令，附实际输出字段（非硬编码“PASS”）。清楚区分**自动演示中由测试程序模拟可信角色批准**与人工在真实 CLI 独立作出决定。
- 写 `docs/evidence/d7/CODE_READING_MAP.md`：给用户逐段读源码的入口和依赖关系，至少包括：① TaskBinding 和双租户边界 ② LangGraph 调查+MCP ③ Evidence Gate ④ Plan+独立 HITL ⑤ ActionIntent/事务 CAS/Ledger ⑥ Verification/Report/DELIVER ⑦ crash-replay ⑧ Memory/Skill/Context Provenance ⑨ E01–E10 评测。**标具体文件、函数、可提问的责任边界、可运行的对应测试**。避免把所有源码贴进 README。
- 写 `docs/evidence/d7/INTERVIEW.md`：两个简历 STAR 候选（完整业务闭环、可靠性/恢复）+ 10 个有参考函数与证据的面试追问。不得夸大：Memory 只证实跨任务上下文注入/撤销，固定通用内容未证实效率提升；本地 SQLite 是单机事务，不是生产 exactly-once / IAM；E10 D6 首次失败保留；不宣称通用多 Agent 平台。

## WP-C｜第三方**实现审查 + 漂移审计**交接包（硬交付）

写 `docs/review-handoff/d7/`，至少包含：

1. `REVIEW_BRIEF.md`：第三方任务、冻结范围、预期输出格式、审查截止点、最终 SHA、环境与如何复验。强调**本次审查对象是实际代码和证据，非重做架构选型**。
2. `DESIGN_TO_CODE_MATRIX.md`：逐项映射冻结合同中 S1、F1–F3、Context/Memory/Skill、E01–E10 与实现状态：**实现文件及函数 → 可跑测试 → 真实证据路径 → 已知局限 → PASS/PARTIAL/NOT_IMPLEMENTED**；只写可验证事实，不能因为有文件就视为满足。
3. `RISKS_AND_DEVIATIONS.md`：**必要、非修辞**的三列：`原定基线` / `已实现差异` / `是否有证据证明差异合理`。明确正向改进、实际偏移、未实现项及谁决定接受。把 `E10 PARTIAL`、D5 通用 Memory、`ACTION_OUTCOME_UNKNOWN` 人工对账、只有本地 SQLite、没有生产分布式幂等、D6 E07 分类勘误、缺公平消融等写入。
4. `SOURCE_AND_EVIDENCE_INDEX.md`：关键源码路径/函数、D1–D7 报告与日志索引、当前提交 SHA、相关测试和重现命令。
5. `REVIEW_INPUT/`：**考虑第三方可能不能访问仓库**，生成可脱离 GitHub 阅读的紧凑附件（压缩包或目录）：冻结实施合同、当前根 README/AGENTS/TASKS、上述审计矩阵、核心源码片段或明确完整源码文件、测试、D6 RESULTS/CASES、D7 证据概要及必要脱敏 TRACE。能访问 GitHub 时也可附 URL，但**不能只给 GitHub 链接**；不要提交 API key、`.env`、真实秘密、`.runtime/*.sqlite3`、大规模重复日志或无关历史文档。附件的每项文件注明其来源 SHA、是否节选，以免第三方误认完整性。
6. **请不要伪造第三方意见或提前写“APPROVED”**。只提交准备就绪的交接包；第三方审查在用户/主 Agent 获得 D7 实际交付后执行。

如果全部源码连同 D1–D7 日志太大，优先保留关键 `.py` + 核心测试 + 必要脱敏 TRACE 与测试摘要；在索引中标注审查仍需额外文件的范围，不能声称提供了完整仓库镜像。

## 独立第三方要答的问题（不可改写成泛泛“优化建议”）

1. 实现是否还是唯一 S1 401 凭证引用故障的 Agent，而非套壳多 Agent / 多业务框架？有没有新增未在 v1.0 中的无收益设施？
2. **调查 → Evidence Gate → Plan → Approval → Intent → Domain CAS → HTTP Verification → Frozen Report → DELIVER** 是否真的贯通？外部服务、测试 helper、模拟动作是否被虚称真实实现？
3. F1 首次执行前的 Intent 与相同请求摘要重放、F2 计划失效竞态、F3 REPAIR/DELIVER 单独审批、工单幂等是否有源码与**实际失败注入**支持？
4. 作用域、Tool 输入、租户隔离、Memory/Skill 不扩权、Gold 不泄漏、恢复后撤销检查等控制是否确实在代码路径而不只是 Prompt 中？
5. D6 分母和 E10 PARTIAL 是否有任何“挑成功样本”“把安全停止算恢复”“把控制测试冒充真实模型”的口径漂移？
6. 哪些能力只能在本地 Demo 成立，哪些尚未实现？是否存在**能导致未经批准写入、重复外部副作用、越权读取、伪造回执**的具体可复现缺陷？
7. 能否从干净环境按照 D7 步骤复现；如果不能，是**真正阻断**还是环境/凭证限制？
8. 整体项目是否对校招 Agent Engineering 有足够可讲清楚的工程主线？指出最多 3 个真正会改变最终结论的缺陷，**不要提供“未来可建设 XX 平台”的功能愿望清单**。

评审结论限定为：`ACCEPT` / `ACCEPT_WITH_LIMITS` / `BLOCKED`，每个重大问题必须提供**代码位置 + 复现/证据 + 合同条款 + 影响面 + 最小处理建议**。没有证据的直觉建议写 `UNVERIFIED`，不作为重构命令。冻结范围以外的特性统一写 `P1 Backlog`，不得开启新开发阶段。

## 明令禁止 / 防漂移条款

- 禁止新增 D8、第二 Skill、第二 Memory 类型、向量检索、RAG、多 Agent、A2A、Redis、微服务、K8s、前端/可视化面板、生产 IAM、CI 矩阵、通用故障注入平台、重做 LangGraph 或替换存储。
- **第三方审查一次即可**。若有真实 P0 阻断缺陷，仅就对应源码/测试定向修复、提交和复审该条；不是进行第二轮全面架构评审。
- 不因“文档更专业”复制几十份报告；优先现有 `docs/evidence/d1`–`d6`、已有代码和测试。D7 新增文件应是导航/审计索引和新鲜演示证据。
- 不要求 PR、Issue、额外审批流程；直接 `main`、可审计 Git commit。
- 禁止将第三方报告、人工最终审阅**预先标为完成**。D7 由 Luna 完成后，主 Agent再提交真正的外部审查。

## 最终向主 Agent 回报（Luna 必须填写真实值）

```text
[D7 FINAL / main@<FINAL_SHA>]
是否通过 D7 可复现：PASS / FAIL / PARTIAL
实际代码改动（有无触及 Agent/Domain 核心执行逻辑，为什么）：
新鲜隔离业务演示：命令、PID、退出码、HTTP 401→200、配置版本、订单字段、Ledger 和工单数：
崩溃恢复：测试名、进程退出码、原始 action_id / ledger_id、重复副作用计数：
干净环境全量 pytest：<passed>/<total>，环境/版本：
E01–E10：D6 历史 9 PASS + E10 PARTIAL；D7 本轮独立观察（不能混淆）：
与 v1.0 冻结合同的偏差（证据及能否接受）：
E10 首次失败及日志保留：
交付入口：README / docs/evidence/d7 / docs/review-handoff/d7 / REVIEW_INPUT：
未实现能力与项目适用边界：
是否仍有 P0 阻断：
最终 Commit SHA：
```

**结束语：D7 做完立即停止开发，提交主 Agent 验收；下一步是一次第三方实现/漂移审计和用户亲自读源码，而不是 D8。**
