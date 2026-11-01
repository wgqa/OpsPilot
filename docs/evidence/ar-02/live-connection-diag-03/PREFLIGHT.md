# 发送前预检

- 当前 HEAD / 规则文件：`8618560295460a94497bad963aea95c171278893`；North Star Blob `1f737712c7a36ceb34433ac09c3fbba3c3305542`；AGENTS Blob `32c45506cceeaa8c76a5c56bf8360ff476b58856`；Skill Blob `d405c8d413d633824b279202cc1503dab4cf0b03`。
- 分支：`codex/ar02-live-01`；工作区在开始时干净，远端跟踪引用与 HEAD 一致。此后只新增本证据目录。
- 本地配置中存在唯一 `OPSPILOT_MODEL_API_KEY`；密钥仅由脚本读取，不打印、不记录、不提交。
- SDK 与 HTTPX 均不参与本次发送。使用 `urllib` opener，显式空 `ProxyHandler`，禁用重定向，30 秒 timeout。
- Offline preflight 只构造并校验请求，不联网：POST 到 `/v1/chat/completions`，请求摘要 `9d17d2f554ce701a3e7868936acba722fafb30a07444c42636985c5d417fa146`，max_requests=1、retries=0。
- DeepSeek 当前 `deepseek-flash` 官方峰时单价：输入 USD 0.30/M，输出 USD 1.20/M。64 输出 Token 加短输入约 USD 0.00008；应用侧独立预留 USD 0.01。响应 Usage 缺失时账单金额保持 UNKNOWN。该预留不是供应商强制账单上限。
- 新授权 ID 为 `AR-02-LIVE-CONNECTION-DIAG-03-20261101-01`，新账本路径 `runs/authorization.sqlite3`，scope `AR-02-LIVE-CONNECTION-DIAG-03-ONE-URLLIB-POST`。旧账本不读取、不修改。

**预检结果：** `PASS_OFFLINE_PREFLIGHT`；请求构造与 source digest 通过，外部请求为 0。新账本已独立持久化并只读核对。

**发送结果：** 唯一一次标准库 urllib 请求尝试触发 `URLError`，原因链含 `PermissionError [WinError 10013]`。没有 HTTP 响应，账本状态 `UNKNOWN_STOPPED`，发送计数为 1。实际计费未知，USD 0.01 预留未结算；不重试。
