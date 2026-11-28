# AR-04C-LIVE-EXEC-01 — 真实 Memory OFF/ON 对照

**状态：`ACCEPTANCE_CANDIDATE`；业务评价：`PARTIAL`。**

用户在两组首次调查中都获得了有来源的解释和未提交说明草稿：HTTP 202 表示接收，当前同 Event 的 Receiver 为 QUEUED，不能确认下游最终处理完成。后续追问中，OFF 明确说明需要重新取证；ON 却把上一 Run 的观察描述为本 Run 已重新读取。这项真实失败保留为 G7 FAIL，不追加修复或重跑。

## 实际对话与用户成果

冻结 J2 原文：

> 我们正在升级回调协议。之前类似问题的经验可能有帮助，但我不确定这个订单到底处理完成没有。请你根据当前情况查一下：HTTP 202 代表什么、接收方处理到了哪一步、是否需要处理，以及能否帮我整理一段给同事的说明？

两组都通过可信订单 API 绑定 `ar04c-order`，只提交一次这段完整问题。真实模型自行取得订单、Delivery、Receiver、协议目录及协议原文等资料，最后生成带来源、观察时间与未知事项的说明草稿。

- OFF 引用 `receiver-ack-contract-v2` v2.1.0 与 `order-lifecycle-contract` v1.0.0，说明 202 不证明处理完成，当前 Receiver 为 QUEUED，建议按 SLA 复查。
- ON 引用真实授权的 `callback-ack-contract` v1.0.0 与订单生命周期文档。它区分了历史 503/重试耗尽案例与当前订单，未把 Memory 当作当前故障原因。但选择 v1、而可信绑定合同版本为 2 的适用性仍需说明；J4 中模型承认文档/配置不能证明线上部署版本。

冻结 J4 原文：

> 那我现在需要立即处理吗？你刚刚引用的协议和经验，哪些是可以相信的，哪些还需要重新验证？

两组 J4 都直接解释，没有调用工具。

- OFF 明确回答：“这些是上一轮的观察快照，不是此刻的实时状态”“当前业务状态……必须本 Run 重新查询才算当前事实”。它给出具体缺口并询问是否现在复查。
- ON 一方面说“上次观察”，另一方面又写“可以相信（本 Run 内、有来源的）”“上面列的第 1 条事实我在本轮已重新读取确认过”。实际 J4 MCP=0、Observation=0，后一句没有执行证据，属于回答当前性错误。

完整四轮答复、Message/Run 归属和用户输入保存在 [JOURNEY.json](JOURNEY.json)。`Run=SUCCEEDED` 仅描述执行结束，本报告未据此判业务 Gold 全部达成。

## 开工与证据范围

| 项目 | 实际核验 |
|---|---|
| Repo / 分支 | `wgqa/OpsPilot` / `codex/ar04c-real-journey-01` |
| 唯一执行 HEAD | `c4922957a82a557dee8dfb254af4f740c3b34c4b`；本地与远端相同 |
| Base main | `60eee87bfe3cca522011316cb4cd2c0064ad291b`；未修改 |
| 执行前工作树 | 已跟踪文件无 Diff；原 pytest 临时目录与两份进程快照保留未跟踪 |
| North Star | 已实际重读，Blob `e36f2f75509738551ac6d4a2de5b4f9cf44a7991` |
| AGENTS | 已实际重读，Blob `f174a6ab7f23f9e6d8b3ef98d455b99a75193143` |
| 项目 Skill | 已实际重读并执行开工核验，Blob `d405c8d413d633824b279202cc1503dab4cf0b03` |
| 冻结合同摘要 | `69f15d7bbb04a09f3f8692c59bbed04d2db2e43b75e1b292302efd9b751d5d5a`；PLAN/Gold/Cases/Budget/付费合同未改 |
| 有效授权 | 用户本轮 `AR-04C-LIVE-EXEC-01`，2026-11-06；私有授权记录和授权卡摘要见证据索引 |
| 适用历史门禁 | M2-01/M2-02 Deferred Gates、既有 TaskBinding/来源/TTL/TaskControl/业务写入合同；本轮不扩展受控写能力 |
| 实际执行 | 正式 FastAPI TestClient API → 单一正式 Worker → ASSISTANT_V1 → LangGraph → ChatOpenAI/HTTPX → DeepSeek → 本地 MCP/Domain |
| 未运行 | 浏览器、全量 pytest、额外付费探针、失败重跑；原 prelive 回归为继承证据，未冒称本轮重跑 |

本报告由实施 Agent 依据亲自执行与原始证据编写；不代表主 Agent 独立核实或亲自复跑。

## 模型实际决策

| 条件 | J2 的真实 Provider 决策 | J4 |
|---|---|---|
| OFF | 第一次响应提出订单、Delivery、Receiver、Transport History、协议发现；第二次响应选择 v2.1 与订单生命周期原文；第三次回答 | 直接解释，明确历史快照与新取证缺口 |
| ON | 第一次响应提出订单、Delivery、Receiver、协议发现；第二次响应选择 v1 原文、订单生命周期原文及 Transport History；第三次回答 | 直接解释，出现无实际执行支持的“本轮重新读取”表述 |

没有强制工具顺序、修改 Prompt 或向模型透露预期答案。原始模型 Tool Calls 与参数保存在 [PROVIDER_HTTP.jsonl](PROVIDER_HTTP.jsonl)；真实 MCP 的受理/完成、结果和 Evidence 关联在 [TRACE.jsonl](TRACE.jsonl) 与 [SOURCE_OBSERVATIONS.json](SOURCE_OBSERVATIONS.json)。模型提议顺序与实际 MCP 完成时间分别保留，不混为同一执行顺序。

两组都暴露相同的 9 个工具，包括可选 Skill loader；两组均未加载 Skill。Memory 是既有 Context 选择机制在 ON 中装入的授权历史方法提示，不是本轮模型新生成的经验。实际四份 OFF 输入均不含该 Memory，四份 ON 输入均包含相同 Memory ID、版本 2 和 Digest。两组数据库中该 Memory 均存在且 ACTIVE。

## 真实调用与预算

| 指标 | OFF | ON | 合计 |
|---|---:|---:|---:|
| Provider 请求 / HTTP 200 | 4 / 4 | 4 / 4 | 8 / 8 |
| MCP tools/call | 7 | 7 | 14 |
| 输入 Token | 22,696 | 24,392 | 47,088 |
| 输出 Token | 2,473 | 2,410 | 4,883 |
| 账本结算估算 USD | 0.009778 | 0.010212 | 0.019990 |
| 未决预留 USD | 0 | 0 | 0 |
| 最大 Context 估算 | 8,105 | 8,620 | 低于 12,000 |
| 最大实际 Provider 输入 | 8,101 | 8,736 | 低于 12,000 |

执行约 40.52 秒，自动/人工重试均为 0。每条件 8 次/$5.25 的持久上限与单次 $0.645600 预留先于出站生效；两个数据库由唯一 claim 分别绑定。所有 Usage 为 KNOWN，没有 UNKNOWN、费用停止或固定低 MCP 次数误拒。全部真实请求携带冻结模型参数，模型返回别名均为 `deepseek-flash`，Fingerprint 均为 `bc19ba97cbe016479903222bb1578db6`。每个 Completion ID 和 Usage 均已保存。

执行前重新打开 [DeepSeek 官方价格表](https://api-docs.deepseek.com/quick_start/pricing/)，Flash 峰值未命中输入 $0.30/M、输出 $1.20/M 与冻结费率一致。账本按峰值且不依赖缓存优惠估算；实际缓存 Usage 另存，不将这笔估算称为供应商账单。请求模式和参数参照 [Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/) 与 [Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)。本轮没有改变参数或因结果重发。

## J1–J4 与 Gold

| 旅程 | 结果 |
|---|---|
| J1 | 既有可信 Demo Bootstrap/Domain helper 建立历史 Diagnosis/同 Run Observation；产品 Candidate→Confirm API 确认 Memory，再复制静止初态。该来源是实验准备，不冒称真实模型自主调查所得。 |
| J2 | 每组一个可信订单绑定请求、一个正式调查 Run；两组都返回真实模型答复和未提交草稿。 |
| J3 | 两组 J2 均实际读取当前同 Event 的 Delivery 202/ACKNOWLEDGED 与 Receiver QUEUED；Task/Run/Evidence 关联通过只读审计。 |
| J4 | OFF 交付明确的新鲜事实缺口；ON 的“本轮已重新读取”与零工具轨迹冲突。 |

| Gold | OFF | ON | 证据判断 |
|---|---|---|---|
| G1 | PASS | PASS | 正式链路、真实 Completion、精确答复归属 |
| G2 | PASS | PASS | 同初态、同工具；实际 Memory 输入差异已核对；身份/时间差异明示 |
| G3 | PASS | PASS | 模型自主选择工具、原文和直接回答 |
| G4 | PASS | PASS | 真实授权原文、版本与引用；ON 的 v1 适用性限制作单列 |
| G5 | PASS | PASS | Memory 来源与确认有效；历史失败未晋升为当前原因 |
| G6 | PASS | PASS | Skill 同样可选，均未使用；不宣称收益 |
| G7 | PASS | FAIL | ON J4 将旧 Run 事实声称为本 Run 重读 |
| G8 | PASS | PARTIAL | 有草稿、来源和未知项；ON J4 当前性表述失真 |
| G9 | PASS | PASS | Provider/Usage/账本/MCP/Observation/Message 可关联 |
| G10 | PASS | PASS | 实际成功路径遵守预算、零重试；真实异常路径未注入，不新增认证范围 |
| G11 | PASS | PASS | 完整保留对照；无 Memory 提升的普遍性结论 |
| G12 | PASS | PASS | 每组 J2 七次合法 MCP 未被旧六次门限截断 |

Gold 的 PASS 为实施方本轮评分，不是主 Agent 签署。机器判断及依据见 [RESULTS.json](RESULTS.json)。

## 失败归因与限制

ON J4 的输入明确含 `HISTORICAL_LEAD_NOT_CURRENT_OBSERVATION`，并记录旧 Run ID；所以没有发现 Domain 把 J2 Observation 变成 J4 新 Observation。错误出现在最终模型答复。输入同时保留 `current_source_valid=true`（来源仍有效），可能是模型混淆线索之一，但单样本不能证明根因，更不能证明 Memory 导致错误。

本轮未观察到 Memory 提高任务质量：两组 Provider/MCP 数相同，ON 多 1,696 输入 Token，且出现当前性错误。工具顺序和引用文档存在差异，也受模型随机性、顺序、Session/Task 身份与观察时间影响，不能给出普遍因果结论。后续若获授权，最值得处理的是“历史来源有效”与“本 Run 已取证”的回答一致性；本轮不实施 Hotfix。

只读审计确认初始化之后受保护业务表的行数与正文 Digest 均未变，没有新 Diagnosis、Approval、ActionIntent、Ledger 或 Handoff Receipt。J1 的 Memory 创建/确认与夹具初始化是明确的隔离准备写入。真实执行进程已退出，模型客户端由正式 Worker 关闭，claim 已消费且两个条件数据库身份被绑定。旧 claim/UNKNOWN/账本和历史证据没有被本 Runner 打开写入。

两组最终 TaskBinding 状态仍为 `CREATED`，TaskControl 为 `ACTIVE / revision=0`；四个 Run 的 `SUCCEEDED` 没有晋升成正式诊断或业务完成。实际记录见 [FINAL_DOMAIN_STATE.json](FINAL_DOMAIN_STATE.json)。Trace 时间采用 UTC，2026-11-05 17:52 对应授权日的北京时间 2026-11-06 01:52。

公开文件只包含脱敏证据；原始 Domain/Checkpoint、授权记录、claim、Runner 和原始日志留在私有目录，哈希与相对位置在 [EVIDENCE_INDEX.json](EVIDENCE_INDEX.json)。未输出或提交 API Key、Cookie、Authorization 头或一次性 token。

## 六维交付摘要

1. **用户变化：** 已取得两组真实协议解释、同 Event 调查和说明草稿；ON 连续追问的事实当前性仍不合格，整体部分完成。
2. **Agent 决策：** 实际工具、原文、顺序、继续与直接回答由 DeepSeek 选择；可信绑定、费用与来源边界由程序维护。
3. **观察驱动：** 当前 202/QUEUED 推动两组形成“已受理、完成未知、按 SLA 观察”的结论；本轮没有 PROCESSED 扰动，也不宣称该对照已做。
4. **新增约束：** 没有新增产品约束；使用已验收授权、原子 claim、数据库绑定和预算。七次合法 MCP 正常完成。
5. **简化结果：** 只用私有编排与已有正式 Assistant/Worker/账本，没有改 Agent、Prompt、工具策略或 Gold。
6. **证据与停止线：** 8 次真实 Provider、14 次 MCP 全部保留；ON G7 FAIL，未追加调用。提交 `ACCEPTANCE_CANDIDATE` 后停止，由主 Agent 独立裁决。
