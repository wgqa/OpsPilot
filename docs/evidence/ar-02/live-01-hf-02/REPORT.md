# AR-02-LIVE-01-HF-02 报告

- **状态：** `ACCEPTANCE_CANDIDATE`
- **任务基线：** `codex/ar02-live-01@204cd2ec1dc292954e1c0b09da129fcab4476d57`
- **冻结 RED 提交：** `98bef3490027e4bfd8f2e87a3004e8078c9d6225`（验收计划、测试、首轮原始失败与诊断快照）
- **RED 原始日志提交：** `8b0246cffb628ab08e389b52801368591855d977`
- **实现提交：** `dae50427890f2b6f1d6f11b9a9267b130ecb9cf1`
**最终证据提交：** 以本报告所在分支 HEAD 为准，并在提交推送后于交接记录给出完整 SHA。

## 结论

本轮**没有确认**原 P1 的真实网络故障根因。已确认锁定 OpenAI SDK 的默认 HTTP 客户端使用 `httpx2.AsyncClient`，而 P1 的捕获钩子补丁 legacy `httpx.AsyncClient.send`；本地 MockTransport 证实该钩子无法观察默认客户端。SDK 路由还会随 Base URL 是否带 `/v1` 而在 `/chat/completions` 与 `/v1/chat/completions` 间变化。捕获盲区解释了历史“零捕获”不能作为“请求未进入传输层”的证据，但不能证明原请求实际到达 DNS、TCP、TLS 或 Provider。

Run/Attempt 不一致已最小修复：终止的 Assistant 失败现在在同一 SQLite 写事务内关闭 Chat Attempt、保留原错误码并失败 Run、写入一个程序通知。HTTP API 将通知标成 `PROGRAM_LIMIT`；已预留但结果未知的实验 Dispatch 保持 `UNKNOWN`，USD 0.645600 预留未释放、未结算。相同失败收尾和相同 Operation 重放均未再发送请求或产生第二条模型答复。

## 连接诊断与证据等级

- 锁定依赖：`langchain-openai==1.7.2`、`openai==3.33.0`、`httpx==0.28.1`、`httpx2==2.13.1`；Python `3.14.0`。
- 对 SDK 真实构造出的默认客户端进行类型检查与 MockTransport 请求捕获：默认客户端为 HTTPX2；对当前原主工作区 `.env` 的脱敏快照显示 base URL path 为 `/v1`，对应 `/v1/chat/completions`。使用根 URL 的正反测试对应 `/chat/completions`。候选 worktree 没有 `.env`；测试使用假 key、本地 MockTransport，无真实 Provider 请求。
- 对 HTTPX2 MockTransport 在响应前注入 `ConnectError`，SDK 异常链为 `OpenAIConnectionError → APIConnectionError → ConnectError`，没有 HTTP 响应。这只证明本地 SDK 包装路径。
- P1 当时精确 URL、代理与证书环境快照未保存。当前 DNS/TCP/TLS 检查成功（TCP 443、TLS 1.3），没有发 HTTP 请求；这不能回溯确定 P1 根因。沙箱内 TCP 探测被拒绝、授权的提升权限诊断成功，原始记录保留。
- HTTPX 默认 `trust_env=True`，会读取代理和证书环境设置；默认启用证书验证。[HTTPX 环境变量文档](https://www.python-httpx.org/environment_variables/)、[HTTPX TLS 文档](https://www.python-httpx.org/advanced/ssl/)。OpenAI SDK 当前发行线对 HTTPX2 的说明见 [openai-python HTTPX2 文档](https://github.com/openai/openai-python/blob/main/httpx2.md)。

## 状态修复

修复前 RED：`Run=FAILED`、`ChatAttempt=STREAMING`、`Dispatch=UNKNOWN`、预留 `645600` micro-USD、结算 `0`，没有模型 Answer；原程序通知正文含 `ASSISTANT_STOP:OpenAIConnectionError`。

修复后 GREEN：Run 与 Attempt 均为 `FAILED`，`ended_at == completed_at`；Run `blocked_reason` 与 Attempt `error_class` 关联到同一失败；API 消息为 `PROGRAM_LIMIT`，正文说明连接失败、任务未完成、计费结果未知且不会自动重试，没有泄露 `ASSISTANT_STOP` 或 `OpenAIConnectionError`。Dispatch 仍为 `UNKNOWN`，预留和结算数值不变，模型 Answer 数仍为 0。重复收尾与相同幂等键请求返回既有结果。

此修复只为专业 Assistant 的明确终止失败调用现有 `fail_chat_attempt(..., terminal_reason=...)`；原 Worker 普通 Chat 的默认可恢复失败路径没有改成终态。共享程序通知 helper 允许传入同一事务时间与用户安全文案；已有路径默认文案不变，重复失败不再重复写 Run 失败 Outbox 事件。

## 新鲜验证

- HF-02 定向：7 passed（SDK URL、legacy hook 与 HTTPX2 差异、本地异常链、真实 Assistant Runtime + 本地 MCP/SQLite、API 程序提示、UNKNOWN 账本保持和幂等）；最终运行使用 `green-focused-05`。
- AR-02 与恢复回归：最终运行 82 passed，覆盖 `test_ar02_runtime.py`、`test_ar02_assistant.py`、`test_ar02_live_budget.py`、`test_ar02_hf01.py`、`test_ar02_knowledge.py`、`test_ar02_smoke_provider_factory.py` 及 `test_m4_cont_ux_stage_a.py`；使用 `regression-focused-02`。
- RED 仍完整保留：RED-01 `3 passed, 1 failed`；RED-02 `6 passed, 1 failed`。RED-02 首个有效失败断言是 `STREAMING != FAILED`。
- 当前原始 P1 数据库 SHA-256 与原 Trace 记录值相同：`222f9cd2e4b909a7a26ee110101f039417786c8030751e2000b59694a7092899`。

完整命令、退出码和运行日志见 `RESULTS.json`、`runs/`；脱敏的状态与 SDK Trace 见 `TRACE/green-runtime-state.json`。

## 未验证与限制

- 没有真实 Provider Completion 请求；真实 Provider 费用请求数为 0。
- 未重跑 S01/S02、未运行浏览器、未执行业务写入，也未合并 `main`。
- 原 P1 网络故障的 DNS/TCP/TLS/代理/证书或远端拒绝层级仍为 `UNKNOWN`。要改变该结论需要另行授权的一次受控 Provider 请求；本轮不含此授权。
- 没有重置、释放或结算历史 UNKNOWN 预留。模型调用可能计费的风险仍由原账本保留。

## 主 Agent 六问交接

1. **用户变化：** 连接故障不再让对话留下永久流式中状态；用户收到明确的程序失败说明。
2. **Agent 决策：** 本轮不增加 Agent 自主性；真实模型调用仍由现有 Assistant 决策入口发起。
3. **观察驱动：** 本地 SDK 传输实现与 MockTransport 观察确定了捕获器盲区；原历史网络故障仍不可定位。
4. **新增约束与合法行为：** 没有新增业务 Gate。终止失败会关闭对应 Attempt；普通 Worker Chat 的可恢复失败和 Assistant 成功路径由回归覆盖。
5. **简化结果：** 复用现有 Attempt/Run/程序通知事务，无新状态管理器、预算服务或 Runtime。
6. **证据与停止线：** 新定向 7 项和相关回归 82 项通过；付费请求、S01/S02、浏览器与全量 pytest 未执行。候选已提交后停止，等待独立验收。
