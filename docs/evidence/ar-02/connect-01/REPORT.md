# AR-02-CONN-01 单请求连通性验证报告

**提交状态：`ACCEPTANCE_CANDIDATE`（探测结果：`FAIL / STOPPED_NO_RETRY`）**

## 结果摘要

本次一次性授权没有产出有效 DeepSeek Completion。获批命令进入 `local_mock_success()` 预检时，HTTPX2 MockTransport 未能拦截请求；OpenAI SDK 收到来自目标配置服务的 HTTP 401。Provider 错误 request ID 为 `9fa30b48-920e-48f8-ba86-442971054b2a`。这是单次调用后的停止记录，不能作为连通性通过。

该错误发生在正式 `ATTEMPT_RESERVED` 和 USD 0.01 预留之前，属于发送前控制失效。错误栈表明本次客户端使用代码中的测试占位凭据 `LOCAL_MOCK_ONLY`，而不是 `.env` 中用户凭据；没有有效 Completion ID、模型输出、Usage 或计费数据。账单状态 UNKNOWN。任务授权只允许一次请求，本次授权现已消耗，任何 Provider 重试或换网重试均禁止。

MockTransport 为什么只在授权执行上下文中漏拦仍未知。实际 HTTPX2 原始请求/响应 hook 尚未安装，因此实际 wire URL、header、完整 body、线级重试计数及 HTTP 响应原文未捕获。本报告仅记录 SDK 401 异常、其错误 ID、堆栈阶段和已知配置，不推断代理或 DeepSeek 服务根因。

## 实际执行证据

- Base：`606adea415962f74d53db67cf55493c1bcb59bc9`，分支：`codex/ar02-live-01`；远端 main 与候选分支在开始前分别核实为 `ec8c3582f6d145eec9979c43607302731411ead8` 与 Base SHA。
- 执行入口：`docs/evidence/ar-02/connect-01/probe_once.py send-once`。保存原始输出于 `runs/provider-single-request-01.log`，退出码 `1`。
- 依赖：Python 3.14.0、openai 3.33.0、httpx2 2.13.1；任务锁文件未改。
- 免费网络检查只对 `api.deepseek.com:443` 进行了 DNS/TCP/TLS，未发送 HTTP；DNS、TLS 1.3 和证书验证通过。
- 普通运行上下文的本地 MockTransport 预检曾观察到 `/v1/chat/completions`、`deepseek-flash`、`thinking.type=disabled`、`max_tokens=64`、无 tools 的本地合成请求。它不能证明正式授权执行上下文的真实请求已被 mock 隔离；后者证据恰好反证该假设。
- Provider 401 是唯一观察到的外部响应。`TRACE/unexpected-preflight-401.json` 记录已知事实；`TRACE/live-result.json` 与 `TRACE/single-use-ledger.json` 记录无 Completion、Usage 和无预留；`TRACE/STOPPED_NO_RETRY.json` 为仓库内持久停止标记。
- `probe_once.py` 已增加停止标记检查：只要此证据目录存在 `TRACE/STOPPED_NO_RETRY.json`，就会在本地预检或网络调用之前拒绝进入发送流程。未再次执行探针。
- 原 P1 数据库 SHA 前后记录均为 `222f9cd2e4b909a7a26ee110101f039417786c8030751e2000b59694a7092899`；原 dispatch `UNKNOWN` 与 USD 0.645600 保持不变。本轮 MCP 调用、浏览器操作、业务写入、S01/S02 均为 0 / NOT_RUN。

## 费用与安全结论

获批的应用侧预留上限是 USD 0.01，但请求外发前持久预留并未发生，因此不能声称费用门禁执行成功。DeepSeek 官方高峰费率估算只说明按假定 512 输入 token 与 64 输出 token 的估值约 USD 0.0002304，并非 Provider 硬上限；此次无 Usage，实际费用未知。冻结费率与口径见[DeepSeek 官方价格文档](https://api-docs.deepseek.com/quick_start/pricing/)。

本次发送前预检失败，单请求授权已消费。后续不得用同一授权重试、切换网络、修改参数或换凭据。若要继续连通性验证，必须先由主 Agent 核实安全隔离与持久 reservation 缺陷，另行冻结方案并取得新的明确授权。

## 文件与范围

仅新增/修改隔离实验分支下的 `docs/evidence/ar-02/connect-01/` 证据及探针停止保护。生产 Agent、Domain、Web、数据库模式、main 和历史 P1 证据未修改。所有原始预检日志和失败记录保留；旧“免费预检通过”记录由 `PREFLIGHT.md` 的最终补记明确作废，而非删除。

## 六项收口

**用户变化：** 没有完成一次可用的模型对话；只确认配置执行上下文中的预检隔离失效并观察到 401。

**Agent 决策：** 没有有效模型调用，也没有可评价的模型行动。

**观察驱动：** MockTransport 逃逸并收到 401 后，停止标记阻断后续探测；没有通过换网或重试继续。

**新增约束：** 仓库内停止标记用于防止耗尽的一次性授权被重用；本次没有证明它能替代真实发送前 reservation。

**简化结果：** 仅在既有探针入口加入停止标记检查；没有改生产路径或历史费用/业务状态。

**证据与停止线：** 原始 SDK 401 栈、脱敏状态 Trace、普通上下文 mock 日志和网络预检均留存；wire hook、Usage、计费、精确根因未验证。现停止，不再发出请求。

**裁决申请：`HOLD`。** 本次探测失败；提交仅用于主 Agent 独立审查该执行控制缺陷和原始证据，不代表连接验证通过。未经新的授权，不得继续 Provider 测试。
