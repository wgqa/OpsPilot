# AR-04C-REAL-JOURNEY-01 — 冻结计划

**状态：** Phase A/B/C 免费准备；Phase D 真实 Provider 未授权。  
**Base：** `60eee87bfe3cca522011316cb4cd2c0064ad291b`  
**分支：** `codex/ar04c-real-journey-01`  
**冻结日期：** 2026-11-05

## 用户目标

让支持人员在同一条真实用户旅程里结合已确认的历史经验、适用协议、TaskBinding 范围内当前回调 Observation，得到对 HTTP 202、Receiver 阶段和下一步行动的有来源解释；再比较 Memory Guidance ON/OFF 是否改变了真实模型行动或用户结果。

真实模型可自行查询 Knowledge、Skill、Memory、MCP，或直接回答、澄清、继续和停止。冻结条件不规定唯一工具顺序。Run `SUCCEEDED` 不代表 Gold 完成。

## 固定旅程

1. **J1 历史经验：** 在每个隔离条件环境中，从可信 S3 Diagnosis、同 Run Observation 与证据来源形成 Episodic Memory 候选；通过既有 Candidate → Confirm API 生命周期确认。记录来源 Task、Outcome、Evidence、确认角色、版本和 Digest。
2. **J2 新任务：** 为同一冻结用户问题创建独立 Session/Task，并通过可信 `assistant/order` API 绑定 `ar04c-order`。不将自然语言订单名视为授权。
3. **J3 当前事实：** 当前目标 Event 的 Delivery 为 HTTP 202 / `ACKNOWLEDGED`，Receiver 为 `QUEUED`；处理完成未知。无 Repair、Handoff Receipt 或工单提交。
4. **J4 连续追问：** 同一 Session/Task 使用 CASES.json 原文继续追问；历史 Memory/Knowledge 可作为有来源的参考，任何当前状态必须由新鲜 Observation 重新核验。
5. **ON/OFF 对照：** 两组使用相同业务输入、授权、项目文档、Skill 暴露、工具、模型、Agent Prompt 与预算。OFF 仍保有已确认 Memory，但不把 Memory Guidance 选入 Provider 消息；ON 允许相同 Memory 进入有界 Context。模型可自行选择是否使用，不强迫加载或引用。

## 本轮验证等级

- OFFLINE：正式 API → Worker → `ASSISTANT_V1` → ChatOpenAI 序列化 → 显式 HTTPX MockTransport → MCP stdio → Domain Observation → Session 回答。
- OFFLINE 测试仅证明接线、状态与授权边界，不证明真实模型自主性或 Memory 收益。
- LIVE Provider、真实 Usage、真实费用、真实模型选择与浏览器均 `NOT_RUN`，须另行授权。

## 预算与停止

每个隔离条件最多 8 Provider dispatch、每条件应用预算 USD 5.25；两条件合计最多 16 dispatch、USD 10.50。MCP 有持久计数与时间/任务边界，不设固定低次数 Gate。按 DeepSeek 官方 Flash 峰值价格更正后的单次最坏保守预留为 USD 0.645600；Usage 有效后结算并释放未用预留。两个独立数据库分别拥有 USD 5.25 额度，16 次完整最坏预留合计 USD 10.329600，仍低于 USD 10.50。MCP、Provider、费用、UNKNOWN、撤权、时间和并发保护见 [BUDGET.md](BUDGET.md)。

不自动重试。Provider UNKNOWN、Usage 缺失/违规、费用越界、来源失效或权限异常时停止实验，保留预留。正式付费 one-shot claim 不在无用户授权阶段生成。

## 六问

1. **用户变化：** 目标是获得对当前回调问题的连续、有来源解释；本阶段只证明离线产品链路，真实模型成果未发生。
2. **Agent 决策：** 模型保有知识、Skill、只读工具、澄清、继续和停止选择；确定性测试替身会预设行动，不作为自主性证据。
3. **观察驱动：** 当前同 Event `202/ACKNOWLEDGED + QUEUED` 应导致“已受理、处理未知”的有限答案；后续 PROCESSED 不属于本次 Gold。
4. **限制影响：** 半额 Campaign 上限防止两个 SQLite 各自花费完整预算；OFF 只排除 Memory Guidance。正例验证授权任务、同 Event 查询和 Memory ON/OFF 都能通过，负例验证越权、UNKNOWN、超额及无 claim 时 fail closed。
5. **职责简化：** 复用 Experiment Ledger、D2 Attempt Ledger、现有 `_prepare_context`、Skill/MCP、Domain 绑定与 LangGraph Worker，不增加新的 Agent Runtime 或 Memory 生命周期。
6. **证据与停止线：** 冻结 J1–J4、Gold、预算与输入；完成定向 MockTransport/SQLite/API/Worker 回归后提交候选。任何真实 Provider、浏览器、业务写入和 main 合并均不在本阶段。

