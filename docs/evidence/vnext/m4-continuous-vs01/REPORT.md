# Continuous Investigation VS01 · 验收候选

## 用户现在实际能完成什么

用户可以在绑定订单的同一个 Task 查询回调过程、更正所指 Event、重新取证并继续追问。已通过真实工作台走过如下对话（全文、截图与关联 ID 在 [Web 证据](runs/web-02/JOURNEY.json)）：

> 用户：订单接口返回 200，但下游说没收到回调。请先核对当前事实。
>
> Agent：最近事件 `event-8ff99f8e4545` 的接收状态为 PROCESSED；同时声明本轮没有展开更早 Event 的完整历史。
>
> 用户：更正：我说的是 `event-9fb9c5c30f42`，不是最近那次……请核对前一个事件的实际发送历史，以及它现在是否处理完成。
>
> Web 显示提议 → SUPPORT 确认 → TaskControl 受理新 Run → 真实 MCP 查询。
>
> Agent：E1 有一次真实 503 发送记录；当前接收记录属于 E2，不能证明 E1 完成；E1 当前状态 UNKNOWN。无记录也不等于没有发送。

关联：Task `task-bfbec733-f041-4a68-95e6-60773741f6d6`；原 Run `run-dc22e2e3-73c2-4da1-88a3-b9369486408b`；纠错 Run `run-1a551517-bf91-4b33-9af9-153ec58d8440`；新控制版本 2。E1 原 Transport Request 为 `transport-b61d9bfd-bc24-472c-a5cf-a478b6cc2961`，不是 E2 的成功 Request。

相同初始描述下，另一个真实订单的同一 Event 有两次独立请求 503→202、接收状态 QUEUED，调查选择了历史和协议查询，交付“已接受、尚未证明完成”。这一例用尽默认额度后走了明确标记的事实降级，不能计为正常模型完成。

最终响应保留修复后又用一个非留出默认 Web Task 验证：

> 用户：上次回调失败了，后来怎么样？请查清 `event-7965ae03fc4d` 的真实回调过程，再核实现在是否处理完成，并说明来源与未知事项。
>
> Agent：同 Event 第一次 503、第二次 202；当前接收状态 QUEUED；引用 `receiver-ack-contract-v2@2.0.0`；分别列出实际 HTTP 时间、业务事件时间和 Request ID，并对重试计划时间与实际发送时间的差异明确保留未知。
>
> 用户：你刚才引用的那份协议，为什么 HTTP 202 不能证明接收方已经处理完成？
>
> Agent 续接了上轮真实 Run 与协议引用，并把旧 Evidence 标为 HISTORICAL_RUN_ONLY。该次解释含一处错误 SLA 限定，下面如实列为产品质量失败。

最终 Task `task-1734be3c-5d50-4462-80c5-d4199b3bbcc8`，调查 Run `run-8ecfed84-188d-436a-9cac-6b9bc2c011e4`，实际 6 MODEL / 5 MCP、正常 MODEL 答复，随后 1 次分类与 1 次可见 Chat Provider。刷新后答复与历史来源仍可查。[全文](runs/web-03/01-final-source-investigation.txt)、[来源续接与质量问题](runs/web-03/02-followup-explanation.txt)、[截图](runs/web-03/screenshots/03-user-journey-result.png)。调查答复与正式业务诊断分开：没有读取 Gate 所需全部事实时，用户问题可以得到有来源回答，正式 Diagnosis 仍为 INCONCLUSIVE，不能据此 Handoff。

## 前置核验与证据等级

| 项目 | 实际范围 |
|---|---|
| Repo / 工作流 | `wgqa/OpsPilot`；复用从 main 建立的 detached 集成工作树，直接推送 `HEAD:main`，无新功能分支/PR |
| Base | `85be293342529de85b40507b9c90c75bc1a77b38` |
| 冻结 / 初始 RED | `dbb62337eac4e242f38659f940823522ac318ad5` / `a25a354e58f52c6058d037ee62f7460899bbba71` |
| 初始实现 / 最终源码 | `209a3b7` / `7cd86e81c2ac3e6be5838285dddce4d17516971e` |
| 重要修正 | `b7b7b5e` 测试接收协议；`1132846` 补查 Run 继承已应用纠错高水位；`7cd86e8` 完整有界响应解析 |
| Diff | Base 到最终源码的线性新增提交，无 merge commit；旧合同/Gold/历史证据不变 |
| North Star / AGENTS | 开工从 Base 读取；提交候选前又从 `7cd86e8` 实际读取，North Star Blob `1f737712c7a36ceb34433ac09c3fbba3c3305542`，AGENTS Blob `30319000ed0054007e9b7b6b46bf98b1493c8179` |
| 当前合同 | 原任务卡、最新“最终实施补充”、[冻结计划](ACCEPTANCE_PLAN.md)、[实验补充记录](EXPERIMENT_AMENDMENT.md)，以及 C1、TTL、HF、原 S1/S2 不变量 |
| 实际执行者 | 本实施 Agent 运行 pytest、HTTP、真实 MCP stdio、DeepSeek、浏览器；主 Agent 独立核验/独立复跑均为 NOT_PERFORMED |

沿用已集成的 Codex 工作树；`D:/学习/agent新项目` 的用户未跟踪资料、`开发目录/` 和旧 C1 工作树均未覆盖、清理或暂存。原主目录本地 main 仍是旧提交，远端 main 的推送不等于原目录被强制 checkout。未发现本目标提交中存在仓库评审 Skill 文件，不声称已执行该 Skill。

## 模型、程序与真实事实的分工

- Agent 根据观察选择合法工具、参数、协议、澄清和结束；剩余候选与原 Call/Tool ID 回送下一次正常决策，可保持、修改、放弃。一次观察后没有额外 Planner/Reviewer/Reflection 请求。
- 执行层只执行当前第一个候选，保留其他建议的来源；持久累计 Task 预算与 Run-scoped Observation，校验 Context、来源、恢复和权限。
- Domain 复核绑定、当前授权、版本、事实 digest、TTL、Event/Request 关系，并保持正式 Diagnosis/Handoff 权威。模型回答不能生成业务权限。
- `s3_delivery` 交付层复核当前答案来源与同 Event processing_claim，来源有效的最终回答直接复用；额度或 Provider 限制时交付有来源的事实与具体未知。它不验证任意自然语言全部语义。

真实观察改变了下一步：QUEUED 分支查协议/SLA；PROCESSED 分支可以较早回答；E1/E2 不同事件的历史使模型回到 E1 查证并交付 UNKNOWN。Knowledge 确实进入后续模型输入并被引用；本切片没有证明新 Skill 或 Memory 的业务增益，不以空选择/加载能力冒充效果。

## 源码变化与简化

| 职责 | 文件与最小变化 |
|---|---|
| 真实 Transport Attempt | `domain/s3_history.py`：追加不可变观察，保存 Event、独立 Request、序号、版本、请求/响应 digest 与真实 HTTP 时间；测试 Sender 不向模型开放 |
| 受限 MCP / 当前性 | `domain/s3_mcp.py` 增加一个绑定订单内历史查询；`domain/s3.py` 为该 fact 复用原授权、Run/Attempt/Observation/TTL/当前版本核验，原 Gate 谓词不改 |
| 决策与交付 | `s3_investigation.py` 以 `next_step()` 替换 S3 旧 `after_gate()` 的 DIAGNOSED/无增量混合终止；候选和观察回送模型；有效终答复用；无合法继续能力时交付事实/未知 |
| 用户可见结果 | `domain/s3_answers.py` 用 Run 主键保存不可变用户答复及来源，区别于正式 Diagnosis；原只读补查仍用 C1 表。`chat.py` Inspector 读取，`investigation_context.py` 复用既有有界历史装配与来源校验 |
| 累计预算 | 现有 execution budget 行新增持久 model_limit/mcp_limit，默认 8/6；实验仅可在首次 attempt 前设 12/8、16/10；新 Run/重启不清零 |
| 纠错续接 | `task_control.py` 创建只读补查 Run 时，在原事务中复制已应用纠错高水位；不删校验、不修改 Task 状态、不重置预算 |
| 局部解耦 | 原文本脱敏/规范化移到 `model_io.py`；原 Context budget 函数公开到既有 `context_engineering.py`；Investigator 保留兼容 alias，S3 不再调用它的私有函数 |
| Web | 答复、来源、时间与降级展示；同一答复不再同时展开成两份正文；历史答复注明刷新不会重取证；不增加业务写入口 |

新增 S3 用户答复表是必要的窄交付产物：原 Diagnosis 会拒绝无模型/不匹配 Gate 的正文，不能为显示降级而放宽业务回执合同。SQLite v15→v16 保留既有业务记录；未添加依赖。没有新 Planner、Goal Manager、Memory、通用 Runtime 或 S4。

新观察状态不需要分别给 Gate、结束路由、报告加 Case 例外。正式 Gate 继续判断业务资格；Agent 判断最新用户目标是否已满足。重复有效事实刷新与无进展反馈保留区别；重复无益调用仍消耗现有有界预算。

## 新鲜测试与失败

最终有效回归：**364 passed / 364，exit 0**，见 [原始日志](runs/regression-final-05/pytest.log)。覆盖原 M1/M1-HF、S1/S2、S3/HF/TTL、C1/Context 及新增连续调查。新定向最终组合 **39 passed**，纠错/TaskControl/HF 组合 **49 passed**。前端最终构建与改动文件 ESLint 通过。

本轮还原样执行过未过滤 pytest：**359 passed、1 failed，exit 1**，见 [full-01](runs/full-01/pytest.log)。失败是保留的实现前 `test_m4_autonomy_c1_red.py`，仍使用早期调用约定；未改它的断言或历史日志。最终有效回归仅排除这个历史文件，不能宣称仓库不带任何条件的 pytest 已全绿。全局 ESLint 另有旧 `e2e/m4-03-s3-journey.mjs` 两项错误，未修改历史脚本来掩盖；新改动文件单独 lint 为 0。

实际命令均在独立 basetemp 运行，日志入口见 `RESULTS.json.tests`。最终命令：

```powershell
$env:PYTHONPATH=(Get-Location).Path
$env:PYTHONUTF8='1'
# 真实运行使用已锁定依赖的 Python 3.12.14 venv；测试进程使用 deterministic-no-provider 配置。
python docs/evidence/vnext/m4-c1-hf-01/runs/capture_pytest_utf8.py docs/evidence/vnext/m4-continuous-vs01/runs/regression-final-05/pytest.log -q --ignore=tests/test_m4_autonomy_c1_red.py --basetemp ../ci-vs01-regression-final-05
```

该命令是当次记录；重跑应换新日志和 repo 内 `.runtime/repro/<unique>`，避免覆盖旧证据或在学习根目录生成临时目录。完整环境见 [ENVIRONMENT](ENVIRONMENT.json)，失败过程见 [FAILURES](FAILURES.md)。

源码和文档 `git diff --check` 通过；包含原始日志的完整检查因 pytest 原输出的尾随空白/Windows 回车返回 2。保留原日志字节，不为格式检查清洗失败证据。

## 有界真实实验与成本

全部原始尝试保留：首组准备缺陷 10 个、修正后预算/RHA 10 个、公开 Gold 的 R-only 8 个、封存留出 4 个，共 32 个实验 Task；另有真实 Web 3 个 Task。HTTP 测试准备与 Agent 调查分别记账。

预算/RHA 下表是 `b7b7b5e` 一代的修正准备组，仍含后来发现的 2000 字符响应预览问题，**不是最终 `7cd86e8` 的完整性能评测**。每格一次，不做统计显著性或泛化领先声明。

| A 配置 | QUEUED：MODEL/MCP、交付、延迟 | PROCESSED：MODEL/MCP、交付、延迟 |
|---|---|---|
| 默认 8/6 | 6/5，MODEL ANSWERED，23.73s | 4/3，MODEL ANSWERED，18.29s |
| 实验 12/8 | 8/5，MODEL ANSWERED，36.24s | 5/4，MODEL ANSWERED，21.90s |
| 实验 16/10 | 6/5，MODEL ANSWERED，25.26s | 16/6，事实降级 PARTIAL，109.80s |

R 两例各 0 MODEL / 2 MCP，1.33–1.51s，交付实际历史与状态。H 两例各 1 MODEL / 3 MCP，3.96–11.63s；归一化焦点实际影响首选工具，但遗漏历史目标，不能仅凭运行时 ANSWERED 标签计为完整履约。A 没有普遍胜过 R/H，增大预算也没有稳定收益。默认工作台配置不调整。

四个 P2/P3 留出只在 `e42087e` 运行一次：3 个 MODEL、1 个事实降级，结果含 1 ANSWERED / 3 PARTIAL；均保留原始输出与未授权业务写入为零的记录。之后基于更早 Web 开发例修了响应截断，**没有重跑留出，也未用于 Prompt 调优；最终版本的新独立留出效果未证明**。P1/P4/P6 的公开 R-only 事实覆盖不能冒充 A/H 全六对评测。P1-failed 冻结 expected=QUEUED 与其两次 503 准备导致 NOT_RECEIVED 存在不一致，未改 Gold 或算成正确率 PASS。

全局真实 Provider **160/180 请求，160 条 usage 可得，共 1,052,650 Token**（889,304 输入、163,346 输出，含 Provider reasoning usage）。按已核对的 [DeepSeek 官方峰值无缓存单价](https://api-docs.deepseek.com/quick_start/pricing/)保守估算 **USD 0.4628064**，不是账户实扣账单。所有失败、分类、H 归一化、可见 Chat、Investigator 均在 `PROVIDER_LEDGER.jsonl`；没有被隐藏 Chat sidecar 消费的模型调用。

早期每例 `RESULT.provider_requests` 使用相同 label，含此前累计记录，不能直接相加；最终成本用唯一 ledger request_id 与各真实 d2 usage 重算。初期 SDK 512 参数并非可靠输出上界，已按官方最大输出修正测试包装器的在途费用预留，原 ledger 不改。最终新默认 Web 样例证明完整结果复用，但不以单例替代整套预算对照。

## 仍存在的产品质量问题与未验证范围

1. 最终 Web 协议追问成功续接正确文档和历史 Run，却额外说处理完成须“且过了 SLA”。这不准确：同 Event 的当前 PROCESSED 可在 SLA 前证明完成；SLA 用于 QUEUED 超时处理方向。保留全文，归为 **产品解释质量失败**，不称其语义完全正确；未改变 Gate、权限或造成写入，也未用关键词白名单修饰结果。
2. R/H/A 单次少量样本、留出版本和上述 Gold 不一致限制均不可隐去；不声称 A 稳定领先、全部 Gold 通过或最终版本完成独立留出验收。
3. 历史只是已捕获的本地观察；发送到落库之间仍有缺口。测试 Receiver 的后续 PROCESSED 是独立标记的可信准备投影，HTTP 202 本身始终只回 QUEUED。不是企业生产发送审计或真实远端集成。
4. 当前 Receiver 是订单最新事件的状态，没有任意旧 Event 的独立当前查询能力；目标 Event 不匹配时必须 UNKNOWN。未增加重发、外部日志、审批或 Handoff 工具。
5. 本轮没有新跑完整 S1 的付费模型审批演示、Memory/Skill 增益或任意故障窗口穷举；相应旧能力靠新鲜回归验证，不能用历史证据当本轮真实演示。

## 六问与六维交回

1. **用户变化：** 同 Task 能查真实发送过程、纠正 Event 后重新取证，取得可见有来源结果或明确缺口；刷新/服务重启不丢记录。
2. **Agent 决策：** 模型选择合法调查顺序、候选处置、协议检索和结束；不是固定扫描所有工具。绑定、预算、当前性、正式业务资格仍由可信程序控制。
3. **观察驱动：** 同 Event 的重试、不同 Event 的成功、QUEUED/PROCESSED 和历史缺口导致不同动作或结论，E2 不能为 E1 背书。
4. **新增约束：** 同 Event claim 核验、历史读取范围和原 20000 字符交付边界阻止错误证明/无界内容；正常长答复、直接解释、候选修改、新 Run 真正复查有正例。只读调查不新增业务写许可。
5. **简化结果：** S3 结束职责与 Gate 解耦；纯函数和 Context budget 共享；未叠加逐案例 Guard/Reviewer，也不把普通问题全部升为业务调查。
6. **证据与停止线：** 机器结果、真实 Provider/MCP/HTTP/Web、全部 RED/失败和学习材料已交付；质量与版本限制如上。测试服务与本轮标签已关闭，未触碰用户其他服务。停止本切片，不启动下一阶段。

**实施方状态：ACCEPTANCE_CANDIDATE。** 主 Agent 的 PASS / ACCEPT_WITH_LIMITS / HOLD / BLOCK、是否进入后续阶段，均待独立裁决。直接推送 main 不代表功能已获 PASS。
