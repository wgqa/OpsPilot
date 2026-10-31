# AR-02-LIVE-01-HF-02 失败与诊断记录

## RED-01：Run 已失败但 Assistant Chat Attempt 仍为 STREAMING

- **命令：** `D:\学习\agent新项目\.venv\Scripts\python.exe -m pytest -q -s tests/test_ar02_live_hf02.py --basetemp=.runtime/hf02/pytest-red-01`
- **退出码：** 1；3 passed, 1 failed。
- **失败断言：** `test_assistant_connection_failure_closes_attempt_and_keeps_unknown_reservation` 中 Task Run 为 `FAILED`，对应 Chat Attempt 实际仍为 `STREAMING`，预期 `FAILED`。
- **环境：** 隔离 `demo_db`、单测 worker owner、真实本地 stdio MCP；模型由锁定 OpenAI SDK 调用 HTTPX MockTransport，不访问供应商。
- **保留原始日志：** `runs/red-01.log`、`runs/red-01.exit`；失败 DB 状态快照：`TRACE/red-runtime-state.json`。

## RED-02：锁定默认传输的捕获盲区及失败收尾

- **命令：** `D:\学习\agent新项目\.venv\Scripts\python.exe -m pytest -q -s tests/test_ar02_live_hf02.py --basetemp=.runtime/hf02/pytest-red-02`
- **退出码：** 1；6 passed, 1 failed。
- **协议观察：** OpenAI SDK `3.33.0` 默认内部客户端属于 `httpx2.AsyncClient`，不是 legacy `httpx.AsyncClient`。对默认 `/v1/chat/completions` 发送的本地模拟请求，HTTPX2 MockTransport 捕获一次，而 legacy `httpx.AsyncClient.send` hook 捕获零次。
- **故障注入：** HTTPX2 MockTransport 在返回 HTTP 响应前抛出 `ConnectError`，SDK cause chain 为 `OpenAIConnectionError -> APIConnectionError -> ConnectError`；该本地结果不说明历史真实请求失败在网络哪一层。
- **状态复现：** Run 为 `FAILED`，Chat Attempt 为 `STREAMING`，Dispatch 为 `UNKNOWN`，reserved 为 USD 0.645600、settled 为 USD 0；程序消息正文含内部 `ASSISTANT_STOP` 标识。新的断言首先在 Attempt 状态处失败，后续提示检查由同一 RED 数据库快照直接观察到，不把未执行到的断言描述为 pytest 独立失败。
- **保留原始日志：** `runs/red-02.log`、`runs/red-02.exit`；完整脱敏 SDK/运行快照：`TRACE/red-02-runtime-state.json`。

## RED-02：连接错误提示暴露内部异常标识

RED-01 测试同时冻结了安全 UI/API 语义：现基线程序提示预期会暴露 `ASSISTANT_STOP:OpenAIConnectionError`，修复目标是向用户展示可理解的连接失败说明，同时保留该错误码在 Run、Attempt 与实验 Dispatch 的内部字段中。该断言在 RED-01 首个失败断言之后尚未执行；以实际捕获到的原始数据库消息为证，不将后续断言包装成已运行失败。

## 免费预检与诊断命令失败

- 第一次配置检查误用了隔离目录不存在的 `.venv\Scripts\python.exe`，PowerShell 报“不是 cmdlet”；没有运行 Python 或访问网络。
- 下一次试图用 `python-dotenv` 解析 `.env`，隔离解释器没有该可选包（`ModuleNotFoundError: dotenv`）；未读取密钥值、未访问网络。随后改用 Python 标准库安全解析，只输出变量是否设置及 URL scheme/host/path。
- 沙箱内 DNS 成功，但 TCP 连接被策略拒绝：`PermissionError`, errno 13。获准的提升权限诊断随后 DNS/TCP/TLS 成功，TLS 1.3；整个诊断没有发送 HTTP 请求或 Provider Completion。日志分别保存在 `runs/config-path-failure.log`、`runs/dotenv-tool-failure.log`、`runs/tcp-sandbox-denied.log`、`runs/tcp-tls-diagnostic.log`。
- 一次只读 SHA 对照命令使用了手写错误的期望值，短暂显示不匹配；随后改为从原始 `dispatch-01.json` 读取记录值再比较，原 P1 数据库当前 SHA 与该记录完全一致。过程见 `runs/p1-db-hash-initial-typo.log` 和 `TRACE/original-p1-db-preservation.json`。

## 历史 P1 连接原因的证据等级

- P1 真实运行保留 `OpenAIConnectionError`、HTTP 捕获器零观测、应用 Dispatch `UNKNOWN` 和 USD 0.645600 未结算预留；HTTP 抓取器只覆盖 `https://api.deepseek.com/v1/chat/completions`。
- 本仓锁定的 `openai==3.33.0` 默认客户端通过本地 runtime introspection 确认是 `httpx2.AsyncClient` 子类；P1 报告的捕获器只 monkeypatch `httpx.AsyncClient.send`。在相同锁定依赖下，MockTransport 实验确认默认 HTTPX2 客户端经过 HTTPX2 transport 时，旧 HTTPX send hook 调用数为 0。因而 P1 “零捕获”不能表示请求没有进入 SDK transport；若捕获器确如报告所述实现，其类型不兼容已足以造成观测盲区。
- 当前锁定 SDK 的 MockTransport 证明：base URL `https://api.deepseek.com` 产生 `POST /chat/completions`，而 base URL `https://api.deepseek.com/v1` 产生 `POST /v1/chat/completions`。因此该历史捕获器对根 base URL 存在盲区。
- 当前原工作区 `.env` 的脱敏状态为 DeepSeek base URL 路径 `/v1`；隔离候选 worktree 没有 `.env`，其进程环境也没有模型变量。原 P1 没有持久记录其精确 base URL 快照，故不能证明历史运行使用了哪个 path，也不能把捕获器盲区断定为实际原因。
- 当前捕获器的 transport 类型不兼容已被证实为 P1 零捕获的重要观测缺陷；但它不能反推历史请求是否到达 DNS/TCP/TLS，也不能定位真正连接失败层。当前 DNS/TCP/TLS 成功只能描述本轮网络状态，不能回溯证明 P1 当时状态。历史 Provider 连接失败的网络层根因仍是 `UNKNOWN`；本地 MockTransport 连接异常只证明 SDK→transport 的异常包装路径。
