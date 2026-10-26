# M4-CONT-UX-01 阶段 A：验收候选

用户现在可以在**新建 S3 Task** 中，完成初次调查后继续提出合法调查请求；初始 Run 用满额度不会耗尽整个 Task 的全部调查机会。已完成的确定性接口演示是：初次查到同 Event `QUEUED` → 查询当前协议解释 HTTP 202 → 接住“刚才引用的那份”直接解释 → 新 Run 重新取得同 Event `PROCESSED`。每次请求有持久 Message、Operation、Run、结果和来源；两种合法工具次序均运行。

实际逐句答复、完整 ID 与累计活跃时间见 [JOURNEY.md](JOURNEY.md)，原始来源是 [TRACE.jsonl](TRACE.jsonl)，不是重写的对话脚本。演示使用确定性模型替身；HTTP/MCP stdio、FastAPI API、Worker、LangGraph 和 SQLite 实际运行。**不把它宣称为真实 Provider 或真实浏览器体验。** 此前替身错误引用协议版本的两条轨迹保留为失败，最终旅程以 `full-active-02` 为准。

## 提交前核验与证据等级

| 项目 | 实际值 / 范围 |
|---|---|
| Repo / 工作流 | `wgqa/OpsPilot`；复用已有 detached 集成工作树，正常推送 `HEAD:main`；未新建分支或 PR，未切换用户主目录。 |
| Base | `37df7236ae3ce6fe7125cda671d1a28a3409f830`，开工 fetch 与远端 main 一致；最终推送前另核对远端。 |
| 冻结提交 | `9abc4898d9accce1819460d6d4cdce24afae34bc`，先于 RED 与实现。 |
| RED 保存提交 | `476f0de36f994bca4d7aa86a045d31a9c14656ec`、`4c836bb9700ac94e9049d7645176f985485b9ce1`、`c45f6702e70e4c880eed567755f0c18d213fe62e`。 |
| 业务源码提交 | `27a96c1e7ffbb4e836cec15421d24b731dff13b0`；7 个业务源码文件。 |
| 替身版本修正 / 最终测试目标 | `fcfb8f99e8b9209d61a737ab1e7b4af696f58595`；仅测试与本轮证据，业务源码仍等同 `27a96c1`。 |
| 最终证据提交 | 包含本文件的 Git commit；提交推送后在交付回复给出真实 SHA，避免自引用伪造 SHA。 |
| 总纲 / AGENTS | 本会话实际读取、提交前再次全文读取；Blob `1f737712c7a36ceb34433ac09c3fbba3c3305542` / `30319000ed0054007e9b7b6b46bf98b1493c8179`，均未修改。 |
| Skill | 实际读取用户原 ZIP 中 `opspilot-slice-review/SKILL.md`，按 A/B 与 C 的实施方提交核对执行。目标 main 没有该项目 Skill 路径；不声称自动发现、已安装或主 Agent 已执行独立验收。 |
| 合同 / 遗留门禁 | 阶段 A 任务卡及补充优先于阶段 0 的旧授权标签；阶段 0 Gold 不改。实际读取 C1/HF、VS01、EG01/HF、M2 延期门禁及权限/状态/恢复合同，见 READ_RECORD 和 DELIVERY_READ_RECORD。 |
| 本人实际运行 | 新定向 RED/GREEN、未过滤全量与适用全量、双连接 SQLite、真实 OS 崩溃/恢复、本地 HTTP/MCP、确定性模型接口旅程；具体命令、退出码和测试源版本见 RESULTS。 |
| 未执行 / 无法证明 | 真实付费 Provider、真实浏览器、J1–J4、阶段 B 时间线、真实模型准确率与 Token/费用收益均 `NOT_RUN`。主 Agent 独立核实和独立复跑不由本报告签署。 |

本次提交范围无合并历史，不改总纲、AGENTS、前端、旧 Gold、旧 RED、历史报告和不可变回执。源码差异见 [SOURCE_DIFF.patch](SOURCE_DIFF.patch)，保护范围及逐文件检查见 [SCOPE_AUDIT.json](SCOPE_AUDIT.json)。用户主工作区和七类旧未跟踪 cache/basetemp 保留；只提交本任务文件，不提交测试数据库或 basetemp。

## 用户旅程实际结果

两条最终旅程的每个完整结果都必须非空、有正确引用且完成该轮目标；第 3 轮以实际 `CURRENT_APPLICABLE` Knowledge 引用的版本为准。初始和三个 Follow-up 共 **9 Investigator MODEL / 6 MCP**；辅助 **3 分类 / 1 Chat / 0 Compression**，共 13 次确定性模型调用/预留，付费 Provider 0。模型替身出站输入、分类输入、Chat Manifest、Observation 与 Attempt 均在 Trace；不是仅数 Run `SUCCEEDED`。

第 4 次请求前，测试准备程序独立将 Receiver 从 QUEUED 改为 PROCESSED，并递增其真实 `version`；Trace 明确标记 `INDEPENDENT_TEST_PREPARATION`。Agent 未获得写 Receiver 的工具，只能通过新 Run 的真实 MCP 观察读取该变化；不会用先前 Run 的 202、QUEUED 或旧 Evidence 冒充当前已处理。只读三轮结束后，原正式 Diagnosis 正文/digest、Task、TaskControl、Plan、Approval、ActionIntent、Ledger、Handoff Queue/Receipt 快照不变，普通执行/答复 Outbox 允许增长。

四种 OS 故障用例刻意预留未知结果以耗尽 Run，恢复后的 `PARTIAL` 只是**恢复合同成功、用户目标未全部完成**。它们不计入完整旅程成功；额度耗尽路径交付真实已有事实、未取得的新事实和准确限制层级，不能用非空 PARTIAL 制造产品 PASS。

## 最小源码与迁移

| 职责 / 文件 | 变更 |
|---|---|
| `database.py` | v16→v17，仅给既有 `task_execution_budgets` 增加 `policy_version` 和 `aux_provider_limit`。已有行默认 LEGACY_V1，原 limits/时间/Attempt 不改；不迁移业务或 Receipt 表。 |
| `task_control.py` | 仅可信新 Task 创建事务按 S3 service 选择 CONTUX_S3_V1：24/18、辅助 8。S1/S2 仍 legacy8/6；重放原创建请求不升级旧 Task，不改状态机。 |
| `execution_budget.py` | 从既有 Attempt 表投影 Task/Run 已用与有效剩余；Run 类型取持久 C1 记录。分类、Chat、Compression 跨三张既有表合计，所有状态都计数，无新预算平台。 |
| `d2.py` | 同一 BEGIN IMMEDIATE 内核验可信 policy、Run/Task/Control 和剩余额度后插入 Attempt。caller `limit=999` 不能扩大新 policy；失败或 RESERVED 不退款，恢复不重置。 |
| `investigation_updates.py` | 分类预留前核对辅助额度；耗尽时持久失败 Assessment 和原 Chat Run 的明确限制说明，不新增调查 Run、不永久 Pending。 |
| `chat.py` | Chat/Compression 预留共用辅助计数。耗尽或终止重试时保存明确“程序生成、未提交模型最终答复”的说明与失败状态；不伪造 Provider Attempt、Manifest、成功答案或新业务事实。 |
| `s3_investigation.py` | 工具可用性、下一步和报告读取同一两级预算。执行入口以原子预留裁决；保留有来源的事实降级。已有有效最终回答即使最后一次 MODEL 已用完仍直接保存，不强制报告调用。 |

Schema 迁移仅在本任务隔离测试 DB 中实际执行；没有打开或升级用户正在使用的主工作台数据库。旧 Task 不自动升级，旧底层 legacy caller-limit 行为和原受信隔离预算实验入口保留。实验入口只允许首次 Investigator/辅助 Attempt 前显式准备历史 8/6、12/8 或 16/10，未暴露给 Web/MCP/模型，也不是运行中新 policy 提额接口。

旧测试的历史额度场景使用小型 `tests/legacy_budget_support.py` 显式恢复 legacy fixture，原安全业务断言不变；迁移版本断言随真实 Schema 同步至 17。这些兼容改动和初次回归失败都保留，不将 fixture 调整冒充生产能力。废弃 C1 `READONLY_FOLLOWUP` Intent RED 原文件未改，未增加旧 Intent 生产兼容。

## RED、GREEN 与回归

| 运行 | 实际结果 | 归因 |
|---|---|---|
| red-01 | 11 failed | 新请求饥饿、调用方 cap、两级/辅助计数缺口；Schema 字段尚未实现另列。 |
| red-02 | 5 failed / 2 passed | 初始 OS 恢复两项通过，Follow-up 恢复超过新 4 次额度、混合辅助超额；两个旅程先因准备字段名错误失败，不算业务 RED。 |
| red-03 | 2 failed | 修正准备字段后，两种次序均在旧 Task MODEL8 限制下退为 PARTIAL；有效用户旅程 RED。 |
| green-01 | 18 failed | 本轮实现漏改 Schema 支持版本 guard，修正为 17；失败日志保留。 |
| green-02 / 03 / 04 | 12 passed；21 passed/1 failed；3 passed | 03 剩余失败为测试错误要求已有 API 返回未承诺的 replayed 字段，改为对照实际持久 ID，未更改 API。 |
| regression-01 / green-05 | 142 passed/6 failed → 31 passed | 保留 legacy fixture 与版本断言的修正；31 包含 25 新例与 6 先前失败回归。 |
| full-unfiltered-01 | 399 passed / 1 failed | 唯一失败为保留的废弃分类契约 RED；业务源码目标 27a96c1。 |
| full-active-01 | 399 passed / 1 deselected | 仅排除上述历史 RED；不能据此忽略随后人工逐句发现的替身引用错误。 |
| fixture-version-red-01 → green-01 | 2 failed → 2 passed | 精确版本断言复现测试替身硬写 2.0.0；替身从真实出站当前引用读取 2.1.0，生产代码不变。 |
| **full-active-02** | **399 passed / 1 historical RED deselected** | 最终测试目标 fcfb8f9，25 项阶段 A 新用例全部通过；包含 C1、VS01、Context、S3/HF/TTL、M1-HF 与 S1/S2 安全回归。 |
| 环境检查 | compileall exit0；pip check exit0 | 无依赖或 lock 变更；完整环境见 RELEASE。 |

每次命令、退出码、时耗、源 SHA 和原始日志 SHA 在 [RESULTS.json](RESULTS.json)。所有失败、断言不足和修复经过见 [FAILURES.md](FAILURES.md)，未覆盖任何运行目录。最终全量使用独立 `--basetemp`，适用全集只排除一个明确旧契约用例，不隐藏新失败。20 条原 Gold 的阶段适用性逐项列在机器结果中：阶段 B 的 12/13 及真实 Provider/浏览器验证仍未完成，不能称整个切片通过。

覆盖的双向约束包括：新 Follow-up 正常预留但同 Run 恢复不能补额；同 Operation 回原 Message/Assessment/Run，不同 Operation 同文不合并；Run 最后一格与 Task 24/18 最后一格的两个独立连接只能一个获胜；分类/Chat/Compression 混合竞争合计不超 8；失败、RESERVED 和未知结果仍计数；正式纠错确认前不能启动新调查，确认后新 8/6 Run 仍共享 Task 总额；原活跃时间 300000ms 到期后没有新 MODEL/MCP；组合合法补查两种次序可用满 4/3 并复用终答复。旧权限、TTL、撤销、来源及业务事务负例由本次适用全量新鲜复跑。

完整重跑示例（在本仓库，使用锁定环境；每次标签必须新建）：

```powershell
python docs/evidence/vnext/m4-cont-ux-01/stage-a/record_pytest.py rerun-a tests/test_m4_cont_ux_stage_a.py
python docs/evidence/vnext/m4-cont-ux-01/stage-a/record_pytest.py rerun-current -k "not test_explicit_protocol_followup_is_accepted_as_same_task_readonly_run_before_ttl_fix"
```

本次实际 Python 为 3.12.14，pytest9.1.1、FastAPI0.137.1、LangGraph1.2.16、MCP2.3.0；实际完整命令/绝对路径以各 COMMAND.json 为准。测试设置 dummy key 和非 Provider loopback endpoint，未读取本地真实模型密钥。旧测试有硬编码历史 Trace 输出；runner 将本次真实追加完整归档在新 runs 中，再还原旧文件原字节，并记录前后 hash，不把新增观察抹掉。

## 限制、成本与尚未证明

- 本轮只改善新 S3 Task；旧 Task 和 S1/S2 不提额。4/3 对复杂但合法目标仍可能不足，测试证明两种三工具组合可完成，不能保证任意目标完成。辅助 8 和原 300000ms 也可能限制更长对话，实际未完成要如实统计。
- 所有模型回答来自确定性替身，无法给出真实 Token、美元费用、自然语言理解准确率或模型相对 R/H/A 增益。32 是 Task 24 Investigator + 8 辅助请求上界，不是 Token/费用封顶。已有调用配置静态核对为 Investigator/Chat `max_tokens=512`、分类 `256`、`max_retries=0`；未发起付费请求验证模型模式/Usage/真实结算。
- 候选 J1–J4 的 64 请求、USD1.50、单在途约束保留，未借用 EG01 预算；正式实验预留/结算/释放仍待阶段授权前有限核验。本轮没有费用平台。
- 阶段 B 时间线、刷新后 UI 顺序和真实浏览器交互均未验证；四轮 API 可获答复不等于最终工作台体验通过。没有实施阶段 B。
- 本地单实例 Worker + SQLite 演示不等于生产 IAM、分布式预算服务或跨提供商费用保证；受信数据库被特权直接篡改不属于本轮已证明范围。
- 没有重新运行付费历史 smoke；全量中的真实本地 HTTP/MCP/OS 与 Provider 替身必须分别阅读。S1/S2 业务结果语义未改，不能把执行态或只读结果称为恢复/交接。
- 早期 `red-01/02/03`、`green-01` 的 COMMAND 未采集 HEAD 字段，汇总明确为 null，不事后反填；冻结/RED 提交和原始源码差异可用于审查顺序。最终全量在调用前采集了真实 HEAD 与工作树 hash。打包器的这一兼容失败也已记录。

## 六问与提交裁决

1. **用户变化：** 新 S3 Task 的合法后续请求能在共享总额内继续调查；四请求确定性接口旅程有完整正确答复，初始耗尽后新 Run 亦可预留。真实模型和 Web 用户体验未在本阶段证明。
2. **Agent 决策：** 保留解释、补查、澄清、工具与结束选择；测试替身走了两种合法次序，不以强制唯一顺序验收。不宣称模型智能质量提高。
3. **观察驱动：** 有有效协议即可直接解释 202；问当前完成状态则新 Run 查询，同 Event 从 QUEUED 到真实新 Observation 的 PROCESSED 支持不同回答。变化由独立测试准备，不是 Agent 写操作。
4. **新增约束与合法影响：** Run 小窗口为后续请求留资源，Task/辅助硬上限阻止无限消息或恢复绕额；正反测试同时验证新请求、重放、并发、耗尽和组合查询。过紧预算导致合法目标未完成仍属于产品风险，不算完整成功。
5. **简化结果：** S3 分散的 Task-only 比较统一为既有预算模块投影；实际权威归 reservation 写事务，辅助复用三表计数。保留授权、Gate、TaskControl、恢复和业务动作守卫；未新建 Runtime/Planner/Guard/Memory/费用平台。
6. **证据与停止线：** 实施方本人运行的确定性 API/HTTP/MCP/SQLite/OS 与完整回归已交付，旧 RED、首次失败和替身错误保留；付费与浏览器 NOT_RUN。源码学习/面试材料见 [SOURCE_LEARNING.md](SOURCE_LEARNING.md)。

**实施方状态：`ACCEPTANCE_CANDIDATE`。** 提交推送后停止，等待主 Agent 独立核实和裁决；不自行签 PASS、不进入阶段 B、不启动真实付费实验，也不扩大业务权限。
