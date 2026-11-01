# AR-02-JOURNEY-P0 实施报告

**状态：`ACCEPTANCE_CANDIDATE`**

**Repo / Branch：** `wgqa/OpsPilot` / `codex/ar02-live-01`

**基线：** `09613b2d858313a0b11ff865ee2dfeb66dd52e09`

**冻结验收提交：** `4b19e60c65df041ab20e8eb0d442f51cd1861cb8`

**实现提交：** `9f04c15109e8d222b7365079b5b345a7a40bf573` (`feat(ar02-journey-p0): wire formal assistant to explicit httpx`)

**本地缓存 `origin/main` 快照：** `ec8c3582f6d145eec9979c43607302731411ead8`

**最终证据提交 SHA：** 由最终交付消息给出。GitHub 443 连接曾阻止远端 SHA 复核，最新远端状态仍需在 push 时核实。

## 用户这次实际完成了什么

S01 用户询问 HTTP 202 是否表示订单回调已经处理完成。正式 API 接受消息，正式 Worker 执行 `ASSISTANT_V1`；确定性离线模型直接给出解释，说明 HTTP 202 只表示受理，没有当前 Event/Receiver 观察就不能确认处理完成。答复写回原 Session 并关联源问题。

S02 在同一 Session 连续提交五轮：用户提供一个未经验证的 E1/Event/Request 示例；助手实际检索并引用本地 `receiver-ack-contract-v2` 2.1.0；用户通过受信订单资源 API 确认 `ar02-order`；助手读取真实绑定订单取得 HTTP 200、状态 `COMPLETED`，再结合目标 Event 的 Delivery HTTP 202 和 Receiver `QUEUED`，明确“受理不等于处理完成”；最后生成处理说明草稿，区分本 Run 当前观察和历史答复，并写明 Receiver 完成状态仍未知、草稿未提交且未创建工单。

不同 Receiver 状态的成对验证使用冻结 Schema 可表达的 `QUEUED` 与 `NOT_RECEIVED`。当前 SQLite 合同不允许字面 `UNKNOWN` 状态，所以没有伪造一个 `UNKNOWN` 行；Unknown 仍作为缺失当前事实时的回答语义。

## 模型替身与可信程序分别做了什么

- `JourneyFixtureModel` 是确定性测试替身，提供工具选择/最终答复；这只能验证正式执行链路，不证明真实 LLM 自主性或智能效果。
- MCP 工具调用由现有 MCP stdio Client/Server 实际执行。订单读取经过带认证的 loopback HTTP API 和当前 TaskBinding；Knowledge 返回真实本地授权文档记录。Trace 包含持久 Run、Message、Answer 来源、Assistant call、Observation 和业务版本关联。
- 未绑定时，用户文字请求别的订单不会创建 TaskBinding 或执行订单业务读取；受信 UI/Domain 绑定之后，同范围只读查询成功。
- Gate、审批、ActionIntent、REPAIR、Ledger、Handoff、Receipt 和外部业务写入都没有执行。

## 实现变更

- [opspilot/assistant.py](../../../../opspilot/assistant.py)：`create_assistant_model()` 支持成对注入显式 HTTPX async/sync transports，并始终用显式 HTTPX client 构造 `ChatOpenAI`。默认配置保持关闭；环境中只有 API Key 不会创建模型。HTTPX 环境代理继承关闭、重定向关闭、传输重试 0，LangChain 重试 0，冻结模型仍发送 `max_tokens=2048` 和 `thinking.type=disabled`。
- [opspilot/web/worker.py](../../../../opspilot/web/worker.py)：正式 Worker 在 `ASSISTANT_V1` Run 结束后关闭模型工厂创建的 async/sync clients，避免单例 Worker 每个 Run 泄漏客户端；确定性 FixtureModel 无 client 时不受影响。
- `tests/test_ar02_journey_p0.py`：冻结旅程通过正式 API、单实例 Worker、`ASSISTANT_V1`、测试 MCP stdio、真实 loopback HTTP 和独立 SQLite 完成；并验证绑定前拒绝、知识命中/空结果、不同 Receiver 状态及副作用为零。
- `tests/test_ar02_smoke_provider_factory.py`、`tests/test_ar02_live_budget.py`、`tests/test_ar02_live_hf02.py`：成功构造 Provider 的离线测试必须提供显式 MockTransport；捕获 SDK 实际请求路径与序列化 body，不再通过 SDK 隐式默认 client 进行测试。

## Provider 协议与依赖

Python 3.14.0；依赖来自 `requirements.lock.txt`：pytest 9.1.1、LangChain 1.4.1、langchain-core 1.6.12、langchain-openai 1.7.2、LangGraph 1.2.16、MCP 2.3.0、HTTPX 0.28.1、FastAPI 0.137.1、Pydantic 2.14.1。

实际 LangChain SDK 的出站序列化由 `httpx.MockTransport` 捕获，覆盖 DeepSeek 路径 `/chat/completions` 与带 `/v1` 路径，断言 `deepseek-flash`、`thinking.type=disabled`、`max_tokens=2048`、`tool_choice=auto`、`parallel_tool_calls=false`、可用工具 Schema 和没有 `max_completion_tokens` 别名。HTTP 请求只进入进程内 MockTransport；真实 Provider HTTP 请求数与付费请求数均为 0。

## 验证结果

- 改动前相关 AR-02 基线：58 passed。
- 最终定向 Provider/旅程/HF-02：38 passed，29.73 秒。
- 全量 pytest：489 passed、4 failed，512.04 秒，退出码 1。失败及隔离复跑见 [FAILURES.md](FAILURES.md)。这些失败没有被隐去，实施方不签全量回归通过。
- `TRACE.jsonl`：6 个持久 Run（均 SUCCEEDED）、12 个 Session Message、6 条 Answer 来源关联、16 条 Assistant call 记录、5 次 MCP 调用及 4 条 D2 tool Observation。实际目标事件接收状态为 QUEUED，不是已处理。
- GitHub HTTPS 443 在本轮环境不可用，远端更新状态和 push 结果不得伪称已确认。实施代码未合并 main。
- 浏览器自动化、真实 Provider、真实 Agent 自主效果、正式业务写入均按授权为 `NOT_RUN`。

## 主 Agent 六问与停止线

1. **用户变化：** 可在正式 API/Worker 里完成协议说明、授权资料引用、可信订单绑定、订单/回调查询和未提交的处理草稿。
2. **Agent 决策：** 本轮工具选择由 FixtureModel 代替真实模型；仅证明执行接线，不把模拟选择宣传成自主智能。
3. **观察驱动：** 同一目标下，真实 `QUEUED` 与 `NOT_RECEIVED` Observation 得到不同回答；订单 200、Delivery 202 与 Receiver 状态分别表述。
4. **约束与合法路径：** 未绑定时文字不能授权订单读取；绑定后同 Task 合法查询通过。没有新增业务 Gate 或写权限。
5. **简化：** 复用唯一 `create_assistant_model`、正式 Worker 和 MCP/Domain；仅补显式 transport 注入与每 Run 客户端释放，没有另建 Assistant、Runtime 或预算体系。
6. **证据与停止：** 38 项目标回归通过；全量 pytest 有 4 项明确失败，浏览器/真实 Provider 未运行。停在 P0 候选，不恢复 P1、不提交付费调用、不合并 main、不进入 AR-03。

**验收边界：** 当前只提交 `ACCEPTANCE_CANDIDATE`。真实模型连续调查、浏览器和全量回归的独立裁决均留给主 Agent。
