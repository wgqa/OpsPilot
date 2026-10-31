# 免费预检记录

## SDK、请求与配置

- Python 3.14.0；openai==3.33.0；httpx2==2.13.1；requirements.lock.txt 未修改。
- OpenAI SDK 默认异步 Client 是 openai._base_client.AsyncHttpxClientWrapper，且为 httpx2.AsyncClient 子类；默认 transport 是 httpx2.AsyncHTTPTransport。默认 trust_env=True、TLS 验证开启、SDK 默认跟随重定向。探针包装该 Client 实例的 send，限制调用数，并显式以 follow_redirects=False 发送，避免跳转到第二个 URL。
- 脱敏配置：API Key 存在（值未记录）；模型 deepseek-flash；Base URL 主机 api.deepseek.com、路径 /v1。预期地址 https://api.deepseek.com/v1/chat/completions。
- 本地 HTTPX2 MockTransport 实际序列化 POST /v1/chat/completions，Body 132 bytes，消息只有冻结短句；字段含 model=deepseek-flash、max_tokens=64、thinking.type=disabled；不含 tools、tool_choice 或 max_completion_tokens。HTTPX2 x-stainless-retry-count 为 0。见 TRACE/local-httpx2-preflight.json。
- 本地 ConnectError 注入链为 openai.APIConnectionError → httpx2.ConnectError，HTTP 响应为空；它仅是本地模拟，不代表真实 Provider 行为。

## 网络、代理与证书

- 当前进程没有 HTTP_PROXY、HTTPS_PROXY、ALL_PROXY、SSL_CERT_FILE、SSL_CERT_DIR 或 REQUESTS_CA_BUNDLE；WinHTTP 为直连。没有记录代理主机值。
- 对唯一允许主机 api.deepseek.com:443 做不发送 HTTP 的 DNS/TCP/TLS 检查：DNS PASS（2 个地址），TCP/TLS PASS，TLS 1.3，系统证书验证通过，密码套件 TLS_AES_256_GCM_SHA384。HTTP 与 Completion 请求数均为 0。见 TRACE/network-preflight.json 和 TRACE/proxy-sanitized.json。
- 当前诊断不能回溯证明 HF-02 中历史 P1 的网络故障原因。

## 官方协议与费用

截至 2026-11-01，DeepSeek 官方文档列出的 OpenAI Base URL 为 https://api.deepseek.com，模型 ID 为 deepseek-flash，当前版本为 DeepSeek-V4.1-Flash-1017。Chat Completions 定义 max_tokens 为生成上限，thinking.type=disabled 为非思考模式开关；OpenAI SDK 中 thinking 通过 extra_body 发出。来源：[模型与价格](https://api-docs.deepseek.com/quick_start/pricing/)、[Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)、[Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)。

官方当前高峰费率（不使用缓存折扣）：输入 cache miss USD 0.30 / 1M tokens，输出 USD 1.20 / 1M tokens。按 512 输入 / 64 输出估算：512×0.30/1,000,000 + 64×1.20/1,000,000 = USD 0.0002304。发送前应用账本预留 USD 0.01，只允许一条请求。该预算依赖供应商执行 max_tokens；USD 0.01 不是供应商账户硬扣费封顶。返回 Usage 是实际 token 的唯一来源。

UTF-8 请求 Body 为 132 bytes，低于 512-byte 输入检查线；这不是官方 tokenizer 的精确 token 数，费用仍按 512 输入 token 保守估算。若 Usage 缺失、超出冻结范围、模型异常或 HTTP/Completion 无法关联，标为 UNKNOWN/FAIL，保留预留并停止。

## 一次性发送资格

- 最终预检使用默认 OpenAI SDK HTTPX2 Client，将 transport 临时换成本地 httpx2.MockTransport，验证路径、Body、Usage 解析与异常链。
- 本地持久性测试记录 ATTEMPT_RESERVED 后拒绝第二次 permit。当前真实账本 .runtime/ar02-conn-01/single-use-ledger.sqlite3 不存在。真实执行时原子创建并提交 reservation；崩溃后记录存在即失败关闭。
- 原 P1 数据库 SHA-256 与 HF-02 留存值一致：222f9cd2e4b909a7a26ee110101f039417786c8030751e2000b59694a7092899。本轮未打开旧数据库。

## 结论

免费预检满足单请求授权：请求参数、HTTPX2 路径、证书/代理状态、费用预估和本地持久单次门禁均可核查。预检时尚未发送真实 Completion；结果见 RESULTS.json 与 TRACE。

## 最终补记：授权执行上下文中预检未能隔离（以上结论已被本节取代）

普通上下文里的 MockTransport、请求参数和单次账本模拟均通过；但获批执行命令进入授权执行上下文后，预检 MockTransport 未拦截 SDK 请求，DeepSeek 返回了 HTTP 401。请求发生在 `ATTEMPT_RESERVED` 持久化之前，且 SDK 错误栈显示它发生在 `local_mock_success()`。所以“免费预检满足发送资格”不成立，最终预检为 **FAIL / STOPPED**。

该请求的 AsyncOpenAI 客户端使用脚本中的本地占位凭据 `LOCAL_MOCK_ONLY`；用户 `.env` 凭据没有用于这次请求。没有捕获实际 HTTPX2 wire URL/headers/body，也没有 Usage 或有效 Completion ID。Provider 返回的 request ID 为 `9fa30b48-920e-48f8-ba86-442971054b2a`；账单状态 UNKNOWN。没有再次发送请求，且本次单请求授权已消耗。MockTransport 为何在不同执行上下文中失效仍为 UNKNOWN；本报告不推断代理、SDK 或网络根因。详见 `FAILURES.md`、`TRACE/unexpected-preflight-401.json` 及原始日志。
