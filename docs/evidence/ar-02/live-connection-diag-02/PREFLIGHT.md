# 发送前预检

- 当前提交：`f4cb4ac079991a90f73ac671260c13178f7c16a8`
- 远端候选此前已推至 `origin/codex/ar02-live-01`；本轮不修改 `main`。
- DeepSeek 官方价格页：模型名 `deepseek-flash`；峰时输入 USD 0.30 / 1M tokens，输出 USD 1.20 / 1M tokens；模型别名对应当前 Flash 部署。按短输入约 10 tokens、64 输出 tokens 的峰时估算约 USD 0.00008。实际以响应 Usage 估算结算。
- USD 0.01 是本次独立应用侧预留上限，不代表供应商可被强制限制在此金额；若供应商不遵守 `max_tokens=64`，存在实际账单超过预留的风险。
- API 凭据只从主工作区本地 `.env` 读取；预检只记录凭据存在/缺失，不输出或持久化密钥。未找到唯一凭据则发送前停止。
- 目标 URL、模型、请求字段、响应结构和工具数均由离线显式 MockTransport 校验。离线预检不访问外网。
- 原 `conn-02` 授权数据库及原 `live-01` UNKNOWN dispatch 只读保留；新授权将写入本目录的独立 `runs/authorization.sqlite3`。
- 单飞、零自动重试；发送前先提交 `ATTEMPT_RESERVED`，HTTP 发送前再原子标记 `OUTBOUND_STARTED`。任何状态不明均不得再次发送。

**预检结果：** `PASS_OFFLINE_PREFLIGHT`。HTTPX MockTransport 捕获 1 个 SDK 请求，URL 与报文摘要符合冻结内容，外部请求数为 0。

**持久发送前预留：** 已在独立 `runs/authorization.sqlite3` 写入授权 `AR02-LIVE-CONNECTION-DIAG-02-20261101-01`、请求 SHA-256 `9d17d2f554ce701a3e7868936acba722fafb30a07444c42636985c5d417fa146`、`ATTEMPT_RESERVED` 与 USD 0.01。只读核验确认 request_count=0 后，唯一请求才获准出站。

**审计备注：** 复用的 legacy sender 将数据库 `scope` 标签硬编码为 `AR-02-CONN-02-ONE-COMPLETION`。虽然本次使用独立授权 ID 和独立 SQLite 文件，该标签与本次诊断名不一致；已如实保留数据库原值，不事后改写。

**最终结果：** 唯一请求的 HTTPX request Hook 触发，response Hook 未触发；SDK 返回 `OpenAIConnectionError`。发送计数已持久为 1，状态为 `UNKNOWN_STOPPED`。不重试；预留保持不结算。真实费用未知。
