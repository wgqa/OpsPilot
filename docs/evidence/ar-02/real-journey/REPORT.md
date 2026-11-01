# AR-02-REAL-JOURNEY 免费准备报告

**当前状态：** `PREPARATION_CANDIDATE / WAITING_FOR_SEPARATE_PAID_AUTHORIZATION`
**实现基线：** `d576bb9dbad8ee96500de14bd215fcf26e1fb527`
**冻结验收提交：** `ec3faeb`
**源码提交：** `d77efb9796408935560ca12fa504cd28d06f47ef`
**付费调用：** 0；**真实 S01/S02：** `NOT_RUN`；**浏览器：** `NOT_RUN`。

## 用户当前能实际完成什么

本轮免费验证了正式 FastAPI `POST /api/sessions/{id}/assistant/messages` → 单一 Worker → `ASSISTANT_V1` → SQLite 费用记录 → 持久 Session 回答路径：用户问题以 HTTP 202 受理，确定性 `FixtureModel` 的回答随 `SUCCEEDED` Run 写回原 Session，回答保留原 `source_message_id`。这只证明正式入口与新实验预算身份接线成功；不是冻结 S01/S02 的模型表现、真实 Provider 结果或浏览器体验。

真实用户仍未获得一次新的 DeepSeek S01/S02 结果。S01/S02 要等独立付费授权后执行。

## 本地 API/Worker Trace

真实测试观察见 [`TRACE.jsonl`](TRACE.jsonl)，原 pytest 输出见 `runs/formal-worker-trace-02.zip`。该次记录：

- API 受理 HTTP `202`；Run `SUCCEEDED`。
- Session `session-7963c64d-6b40-4c98-893c-aa4f7e92b169`。
- 用户 Message `message-16920d25-4244-4f8a-972a-4f43dfcd03de` → Run `run-53e47aa1-a704-4425-9a76-ee66d505ef0e` → Assistant Message `message-1d671932-3e04-43bf-bfbd-f2db7508cbda`。
- Assistant 结果的 `answer_source_message_id` 与用户 Message ID 相同。
- Provider 网络请求 `0`，实际 MCP `tools/call` `0`，REPAIR/DELIVER/Approval/工单写入 `0`。
- 本地账本在新 ID 下记到 1 个确定性模型 Attempt；该 fixture 结果只验证执行和记账，不属于 Provider 用量或费用。持久答复为：“HTTP 202 只表示受理，不能证明处理完成；不判断当前订单。”

## 最小实现

修改仅限：

- `opspilot/domain/assistant_experiment.py`：新增精确 ID `AR-02-REAL-JOURNEY-01`，同一 SQLite dispatch 机制下建立独立 budget row；复用 16 Provider / 12 MCP / USD 10.50 / USD 0.645600 单次预留规则。未建立新费用服务。
- `opspilot/assistant.py`：Provider 构造仍默认关闭；仅明确 Provider 开关、被精确 allowlist 的 Experiment ID、固定模型和端点及凭据同时符合时才能构造。测试只使用 `httpx.MockTransport`，不发网络请求。
- `opspilot/web/app.py`：允许正式 App 通过精确 ID 初始化新实验账本，并继续拒绝未知实验 ID。正式 Worker 逻辑和 MCP 工具权限没有改动。
- `tests/test_ar02_real_journey_budget_scope.py`：新旧 ledger 隔离、旧 schema fail-closed、Provider 工厂 opt-in、正式 App 与确定性模型 Worker 路径。

新 SQLite schema 只允许两个精确实验 ID。既有 `AR-02-LIVE-01` 数据库不会自动迁移；若仍是只允许旧 ID 的 CHECK schema，启动新身份会明确 `AR02_LIVE_SCHEMA_ID_NOT_SUPPORTED`，现有旧行和历史 UNKNOWN 不更改。新实验必须使用新的 Domain DB 与 Checkpoint DB；计划中规定全新隔离路径。

## RED / GREEN / 回归

- 冻结的新 ID RED：4 failed，暴露旧预算模块、Provider 工厂、正式 App 都只接受旧实验 ID，及旧 Schema 的边界；原日志保存在 `runs/frozen-red.zip`。
- 错误解释器的首次补测 `3 passed, 1 failed`（缺 `langchain`）完整保留为环境错误，不计入产品 RED/GREEN。
- 仓库 `.venv`（供依赖执行；当前代码仍来自隔离 worktree）下的新范围测试先后 4 passed 和 5 passed。
- 含新范围、AR-02-LIVE 预算、Provider wire、P0、HF01、HF02 和连接失败回归的定向套件 `47 passed, 0 failed`，最终耗时 45.89 秒。完整日志位于 `runs/regression-02.zip`。
- 本轮未运行全量 pytest。此前 `489 passed / 4 failed` 是历史记录，不冒充本轮结果。

Python/依赖：CPython `3.14.0`；`langchain 1.4.1`、`langchain-core 1.6.12`、`langchain-openai 1.7.2`、`httpx2 2.13.1`、`mcp 2.3.0`、`pytest 9.1.1`。依赖取自仓库根工作区已有 `.venv`，没有执行安装或修改该环境。

## 预算、权限与停止条件

- 实验级最多 16 次 Provider、12 次 MCP `tools/call`、应用侧 USD 10.50；每次按 USD 0.645600 预留。16 次全未知总预留 USD 10.329600，低于应用侧限额。来源和公式见 [`PREFLIGHT.md`](PREFLIGHT.md)。
- 限额不保证 Provider 违反公开上界或 Usage 口径时绝不产生额外费用。旧 P1 的 USD 0.645600 UNKNOWN 不被抵扣、释放或合并；若最终计费，最多另有这一笔历史未知支出，不属于新账本上限。
- 价格以 2026-11-01 官方价目表为参考；真实付费前必须重新核对 DeepSeek [价格](https://api-docs.deepseek.com/quick_start/pricing/)和[接口参数](https://api-docs.deepseek.com/api/create-chat-completion/)。
- 未获付费授权时 Provider 请求必须为 0。未来运行时任何未知/超时/响应丢失保留预算且不重试；配置偏移、Usage 异常、授权问题、越域、意外业务写入或预算到限即停止，不自动修复或补跑。
- `ar02-order` 的本地准备事实（COMPLETED、合同 v2、目标 Event 202、Receiver QUEUED）来自旧冻结 fixture；本轮没有使用它做新的真实调查，也没有将它写为 Agent Observation。

## 六问摘要

1. **用户变化：** 现阶段得到正式 Assistant 的可运行免费接线；真实用户仍未得到新的模型调查结论。付费旅程获批后才可产生 S01 和同 Session 五轮 S02 的真实结果。
2. **Agent 决策：** 免费测试使用确定性 FixtureModel，只证明持久 API/Worker 路径；没有关于真实模型决策的结论。
3. **观察驱动：** 目标 Event 的同 Event 事实、当前授权和新 Run Observation 才能支持业务结论。冻结样例日志不能作为事实。
4. **限制与正常路径：** 精确 ID 与旧 Schema fail-closed 阻止任意 campaign/旧库复用；正向测试证明新 ID 的正式 API/Worker 与零工具回答仍可运行。没有扩权限或写操作。
5. **简化：** 复用现有单个 SQLite attempt ledger、模型工厂、FastAPI App 和 Worker；没有增加服务或状态平台。
6. **证据/停止：** 当前状态只是免费准备候选。预算和真实用户旅程通过另行授权后执行；本轮在付费请求前停止。

## 未验证与下一步

- 真实 DeepSeek S01 与 S02 五轮均未运行；真实模型工具策略、自主性、Usage 与实际费用未验证。
- 浏览器体验未运行且未解除原 STOP。
- 本轮完整 pytest 未运行。
- 远端 `main` 未能刷新：GitHub HTTPS 443 连接失败，main HEAD 标记 `UNVERIFIED`；本轮不修改 main。
- 新真实旅程运行必须先由用户单独批准精确请求数、MCP 次数、费用上限、未知收费处置和停机条件。当前此报告不构成授权。

结论：**免费准备已完成，可供主 Agent 审查；真实模型阶段未开始。**
