# 正式调用链与预算职责

```text
用户 Web Session
  -> POST /api/sessions/{session_id}/assistant/messages 或 /assistant/order
  -> admit_task_message / create_task_with_initial_run
  -> task_runs(kind=CHAT_READONLY 或受控任务 Run), assistant_runs(ASSISTANT_V1)
  -> FastAPI lifespan 启动单个 run_worker
  -> _dispatch_run 识别 ASSISTANT_V1，claim Run，调用 assistant_model_factory()
  -> server.main 注入 create_assistant_model
  -> 开关/实验范围/授权/模型配置验证，创建 ChatOpenAI + HTTPX client
  -> run_assistant / _run_assistant 建 MCP client 和合法工具列表，装配 Context/来源
  -> LangGraph create_agent Loop.awrap_model_call
  -> domain.assistant.reserve(assistant_calls 持久登记)
  -> [仅 experiment_id 非空] assistant_experiment.reserve_dispatch(费用/次数持久预留)
  -> Provider Handler
  -> 模型工具调用 -> Loop.awrap_tool_call -> domain.assistant.reserve
  -> [TaskBinding 存在时] 既有 Task/D2 Attempt 预算与 MCP/Domain 授权校验
  -> MCP Observation/Evidence 持久化，来源在每次模型调用与 API 回显前复核
  -> 后续模型选择或停止 -> complete_chat_attempt / chat_run_answers 写入用户答案
  -> Worker finally 关闭每 Run HTTPX client
```

## 关键源码入口

- `opspilot/web/server.py:11-29`：唯一正式服务入口；创建 `create_app(assistant_model_factory=create_assistant_model)`，只绑定 loopback、单 Uvicorn Worker。
- `opspilot/web/app.py:147-175`：App 注入点，解析可选实验 ID；`app.py:191-223` 初始化 Domain、仅对实验 ID 初始化 Campaign Ledger，并启动 Worker。
- `opspilot/web/app.py:678-715`：普通 Session 消息、订单绑定入口、Session 来源读取。
- `opspilot/web/worker.py:511-545`：ASSISTANT_V1 Run 归属判断、领取、模型工厂创建、`run_assistant` 分派和 HTTPX client 关闭。
- `opspilot/assistant.py:896-954`：Provider 总开关、授权/实验 ID 范围、模型和 DeepSeek endpoint 校验。
- `opspilot/assistant.py:966-1043`：HTTPX retry=0、`trust_env=False`、redirect=false、30 秒 timeout、ChatOpenAI 参数与客户端生命周期。
- `opspilot/assistant.py:1176-1255`：Context 准备、来源与 Memory 再验证。
- `opspilot/assistant.py:1266-1415`：每轮模型发送、持久 `assistant_calls`、实验费用预留/结算/UNKNOWN 处理。
- `opspilot/assistant.py:1417-1518`：模型工具调用记录、工具暴露检查、TaskBinding 与 MCP 处理、结果和 Observation 持久化。
- `opspilot/assistant.py:1520-1541,1878-1965`：任务时间包装、Graph/agent 执行以及最终 Session Answer 写入。
- `opspilot/domain/assistant.py:564-617`：默认普通 Run 8 MODEL/6 MCP；`reserve` 原子记录及幂等，`finish` 保存状态/Usage/Observation。
- `opspilot/domain/assistant.py:619-707`：来源当前性、撤权和绑定状态核验。
- `opspilot/domain/assistant_experiment.py:31-83,85-117`：实验 allowlist、实验预算与 schema。
- `opspilot/domain/assistant_experiment.py:204-248,270-367`：固定实验预算初始化、参数一致性和发送前原子预留。
- `opspilot/domain/assistant_experiment.py:410-545`：Usage 结算、违规、UNKNOWN 预留与实验级停发。

## 两类保障不能混为一谈

`assistant_calls` 是 Run 级调用事实和重放保护；它不跨 Session 累计钱。`assistant_experiment` 是实验级费用池/调用池，但当前表只接受固定实验 ID，Worker/Loop 也仅在 `experiment_id` 非空时调用它。正常产品 Profile 的身份、持久预算 scope 和生命周期尚不存在。

当前 Provider 工厂在开关关闭时返回 `None`。开关打开时，要求受支持实验 ID；因此 `assistant_experiment_id=None` 的普通正式 App 无法通过这个工厂发起真实 Provider 请求。FixtureModel 通过注入工厂证明离线产品链路，不能证明正式普通用户真实付费路径已开放。

身份还由两个位置传递：App/Worker 把 `resolved_experiment` 显式传入 Assistant Loop；`create_assistant_model` 则另外从进程环境重新读取 `OPSPILOT_ASSISTANT_EXPERIMENT_ID`。这体现的是进程级实验配置，不是绑定到用户或 Session 的产品运行授权。未来产品 Profile 应由可信服务端解析后沿工厂/Worker 显式传递，不应伪造实验环境变量。
