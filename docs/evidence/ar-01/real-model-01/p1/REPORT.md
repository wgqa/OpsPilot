# AR-01-RM-01-P1 实施方验收候选

用户现在拿到第一批**真实模型**新旧 Agent 决策对照，而非模拟效果推断。五对全部完成：两组都能根据 202/503 改变后续调查并区分 Event；同时真实暴露出 B 的答案格式交付失败和 A 的合法混合目标遗漏。没有为追求某组胜出而调整 Prompt 或重跑。

例如同样问“我认为回调投递失败了，请查清是不是这样”：202 初态下两组都交付“已受理、接收方 QUEUED，不能认定处理完成”；503 初态下都交付“首次传输临时失败、重试已安排，不能声称最终失败或已恢复”。E1/E2 题均明确 E2 PROCESSED 不能证明 E1；目标当前状态未知属于合理交付。完整原答复见每组 `*.result.json`，不以此摘录替代原文。

## 正式核验入口

- Repo / Branch：`wgqa/OpsPilot` / `codex/ar01-free-agent`。
- Base `88e8e8ab7577e02b960a27667950515e7c5e0c5a`；冻结 `d667762e4a6feccf8701c0d6ec94bee22142b80e`；真实执行源码 `ff8fb4c48aca609c73d0aa77c4647b30c960c7f0`。
- Candidate HEAD 是包含本报告的最终证据提交（精确 SHA 见提交回报；避免文件自包含其自身哈希）。Base→HEAD 为线性实验代码/证据 Diff，无 main 合并或生产/治理文件变更。
- 实际读取 North Star、AGENTS、Skill；Blob 分别 `1f737712c7a36ceb34433ac09c3fbba3c3305542`、`32c45506cceeaa8c76a5c56bf8360ff476b58856`、`d405c8d413d633824b279202cc1503dab4cf0b03`。结束时再次执行 Skill C，记录于 `SKILL_EXECUTION.md`。
- 合同：原 AR-01 CASES/Gold/PARITY，RM01/HF-01 费用预检、PROBE-01 原始响应、本轮 PLAN 与当前用户明确 P1 授权。Stage B HOLD、浏览器 STOP、M2 延期门禁及 Domain 安全合同继续有效。
- 本报告是**实施方本人执行并离线核验**。未代表主 Agent 独立复跑/签字；真正独立验收仍待执行。

## 实际结果

10 个初始 Run / 28 次真实 Provider / 27 次真实 MCP Attempt。91,870 Token（输入 84,228 / 输出 7,642），逐请求向上取整的峰值无缓存费用账本 USD **0.034451**，不是供应商已核实账单。最大输出 806 Token，无截断/未知收费/自动重试。

28 条 HTTP 响应、完整输入与 Tool Schema、Completion ID、Fingerprint、Usage、Tool Calls、原始 MCP 观察、Domain Observation/Attempt/Run 关联均保存。规范化脱敏 Trace 含所有请求，未保存 Key/Authorization。实际返回模型 alias 为 deepseek-flash，同 fingerprint；精确服务端实现只能以官方映射说明，不能从 alias 独立断言。

实施方按冻结目标粗评 A、B 各 4/5（含合理未知交付），见 `COMPARISON.md` / `EVALUATION.json`。B 在材料题原始解释正确但实际 Fallback 失败；A 在 scope 题安全但漏合法目标。新标准 Loop 有实际调查能力，**未证明优于旧方案**。建议任务卡情况 B：表现接近、有不同缺口；由主 Agent 裁决，不自签胜负。

MCP 拒绝 1 次越域历史查询后 B 继续合法部分。10 个 Run 的受保护业务表前后快照相同；没有 DiagnosisReceipt、修复、审批、ActionIntent、Ledger、Handoff 或工单写入。Attempt/Observation/Context/实验账本等执行审计记录是预期写入，不冒充业务结果。

## 最小源码改动

- `experiments/ar01_free_agent/provider_budget.py`：增加独立 2048 请求策略与输出校验，复用旧单飞、结算、未知保留、去重；不改旧 512/legacy 账本。
- `real_model.py`：P1 配置/显式授权匹配；通用模型适配发送实际 2048；首对协议审计不筛掉目标失败；批次观察入口。
- `agent.py` / `harness.py`：仅可信 output_limit 参数传递、可选 Trace/结果回调。不改变 A/B 决策、Prompt、Context 或工具描述。
- `p1.py`：固定五对一次性入口，复用原 batch；持久逐事件日志、源码/案例/Schema 检查。无独立费用服务或新 Agent 框架。
- `tests/local_provider.py` / `tests/test_p1.py`：免费响应/截断/未知/授权与首对门禁验证。

生产 Investigator、Domain、Web、权限、Gate、TaskControl、Gold 均未修改；没有增加合法工具序列约束。参数 2048 是本次正式授权的独立实验配置，不是回写旧探测。

## 免费测试与证据范围

| 本次实际执行 | 结果 | 原始日志 |
| --- | --- | --- |
| 付费前新 P1 测试 | 5 passed | runs/01-local-preflight.log |
| 原实验回归 | 77 passed | runs/02-existing-experiment-regression.log |
| S1/S2/S3 必要安全子集 | 72 passed | runs/03-safety-regression.log |
| 首对语义失败不筛样本单测 | 1 passed, 5 deselected | runs/04-semantic-failure-gate.log |
| 最终源码 P1 免费复跑 | 6 passed | runs/06-final-focused.log |
| 唯一付费批次 | 10 组完整执行，exit 0 | runs/05-live.log |

前五行有重叠，不把它们相加包装为独立测试总数；最终覆盖为 6 项新测试、77 项旧实验、72 项必要安全测试。没有新鲜全仓 pytest，明确 NOT_RUN。完整命令/环境及 exit 保存于 RESULTS；06 日志带原始命令头。确定性 Provider 结果与真实模型结果分别存放在 TRACE 的 local/regression 与 live 目录。

## 公平性、风险与局限

相同六工具与权限、每对独立等价事实已核验；真实 API 不提供任意 SQL、URL 或额外写能力。Prompt/Context、多工具提议执行、cache、固定 A→B 顺序不同；不能作 Loop 单因果比较。共五对一次，不是统计结论；无真实 UI、多轮目标接续、Memory 收益或 Skill 收益证明。没有用付费模型评分。

既有解析器把 B 材料题的有用解释变为无关 Fallback，是实际交付缺陷；A scope 提前结束是策略/产品缺陷。其他措辞与多余读取均如实列于 FAILURES，不以“安全通过”抵消产品失败。不在本任务修生产解析、Prompt 或扩大样本。

## 学习与面试表达

- **原理→业务**：Function Calling 的工具建议与实际执行是两层；受限 MCP、TaskBinding、Domain 负责权限，模型决定是否查、查什么和何时回答。scope B 的一次真实拒绝与后续合法查询是具体例子。
- **Context→结果**：A/B 同模型同工具并不等于同条件，专用 Prompt/Context 与调用批处理会影响决策。少 Token 或少工具不能脱离任务完成评效率。
- **源码→失败**：`Candidate.run()` 复用 `s3_delivery.parse_response()`；原始合理语言不等于用户得到合格结果。material B 是格式/接口失败，而非简单把它归为“模型不智能”。
- **评测→面试**：“怎样比较自主 Agent？”先冻用户目标与禁止结果，保证事实/工具/授权等价，保留所有模型选择、观察、交付、预算与失败，独立区分模型决策、程序守卫、Fallback；多路径都可合理，未知也可正确。再承认 Prompt 与 Context 混杂，不从五对声称架构优胜。
- **实践等级**：真实 Provider/MCP Loop 已接入隔离实验并有观测证据；相对旧架构的稳定收益、正式产品迁移和跨轮连续能力尚未证明。

## Skill 六问收口

**用户变化：** 获得五对可核查的真实 A/B 决策与交付证据，无新生产能力。

**Agent 决策：** 两组实际选择工具、解释或停止；B 零工具解释、A 提前停止都如实保留。

**观察驱动：** 202→QUEUED 与 503→临时失败/重试，E2 成功不冒充 E1，见真实轨迹。

**新增约束：** 独立 2048 配置、授权/次数/单飞/费用检查保护付费范围；本地双向验证合法调用、截断/未知阻断，不限制合法工具顺序。

**简化结果：** 沿用原预算与 Runner，只参数化默认 512 的输出限制；未宣称删除生产条件或替换架构。

**证据与停止线：** 实施方真实执行与离线审阅，旧失败保留；全仓/浏览器/账单/重复样本未核验。五对后停止付费，不合并 main、不进入 AR-02。

提交状态：**ACCEPTANCE_CANDIDATE**。主 Agent 独立审查仍待进行。
