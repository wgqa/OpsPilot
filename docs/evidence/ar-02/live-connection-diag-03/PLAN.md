# AR-02-LIVE-CONNECTION-DIAG-03

**状态：** `UNKNOWN_STOPPED`
**分支：** `codex/ar02-live-01`
**基线：** `8618560295460a94497bad963aea95c171278893`

## 目的

用户要求再次做独立真实调用。本次使用 Python 标准库 `urllib` 直接 POST DeepSeek Chat Completions，不经过 OpenAI SDK、LangChain 或 HTTPX；保持与上次相同的 `/v1` 路径、短文本和 64 输出 Token 上限，用于比较独立 HTTP 客户端下的结果。

## 冻结请求与边界

- URL：`https://api.deepseek.com/v1/chat/completions`
- Model：`deepseek-flash`；`thinking.type=disabled`
- 输入：`请只回复：OK`；`max_tokens=64`；`stream=false`
- 30 秒超时，禁用代理，禁用重定向，不自动重试，最多一次 POST。
- 独立授权 ID：`AR-02-LIVE-CONNECTION-DIAG-03-20261101-01`
- 独立 SQLite 账本先持久 `ATTEMPT_RESERVED` 和 USD 0.01，再将一次性计数置为 1 后才打开连接。
- 不改旧 UNKNOWN/费用账本；不重跑 S01/S02，不执行 MCP、业务写入或浏览器操作。

唯一尝试触发本机 `PermissionError [WinError 10013]`，没有 HTTP 响应，状态为 `UNKNOWN_STOPPED`。停止本探针；它只检查原始标准库客户端，不证明正式 Assistant 用户旅程。
