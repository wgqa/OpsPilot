# AR-02-REAL-JOURNEY Provider 与费用预检

**状态：** 免费预检完成；付费请求未授权，真实调用未执行。

## 请求配置候选

- DeepSeek Chat Completions，模型 `deepseek-flash`，非思考模式。
- `max_tokens=2048`，有工具时 `tool_choice=auto`、`parallel_tool_calls=false`。
- 超时 30 秒，零自动重试；不兼容时停止，不静默删参数或换模型。
- 正式执行入口是 FastAPI → 单 Worker → `ASSISTANT_V1` → MCP/Domain；不能用 CLI 直接生成答案替代。
- 现有 `create_assistant_model()` 构造本身不发网络请求；只有显式 Provider 开关、精确实验 ID、固定模型、API Key 与官方 HTTPS 端点同时成立才创建客户端。免费测试必须用显式 `httpx.MockTransport`。

## 额度复核

新身份：`AR-02-REAL-JOURNEY-01`，新建独立 Domain 与 Checkpoint SQLite 文件；不使用旧 P1、CONN-02 或默认用户数据库。实验级限制与既有 P1 相同：最多 16 个 Provider dispatch、12 次 MCP `tools/call`、账本上限 USD 10.50。一次 Provider dispatch 的保守预留 USD 0.645600；16 次预留 USD 10.329600。MCP 只计 `tools/call`。

实际用户动作最多六轮，不代表最多六次 Provider 请求；模型 Agent 每轮可有多次调用，但实验全局硬限额仍为 16/12，另有每 Run/Task 现有额度。单次模型请求超时/取消/结果未知均保留预留、消耗一次额度并停止，不重试。一个完整连续旅程可能因额度不足而明确部分完成；不得以 PARTIAL 宣称目标完成。

该金额是本地应用账本预算，不是 DeepSeek 账户级绝对封顶。若历史 P1 UNKNOWN 最终收费，则有最多 USD 0.645600 的额外未知历史支出，不纳入新预算或新身份。不能声称新旧总账本限制账户支出。

DeepSeek 官方公开价格（核验日期 2026-11-01）：`deepseek-flash` 峰时 cache-miss 输入 USD 0.30/M、输出 USD 1.20/M；公开 1M 上下文/384K 最大输出。费用上界按未缓存计算：`616K * .30/M + 384K * 1.20/M = USD 0.645600`。调用前须重新核对[价目表](https://api-docs.deepseek.com/quick_start/pricing/)和[Chat Completions 参数](https://api-docs.deepseek.com/api/create-chat-completion/)。

## 运行隔离与授权

- 本轮 Provider 请求数：0；MCP/HTTP 本地离线请求可按后续 GREEN 测试记录；真实 DeepSeek 旅程仍 `NOT_RUN`。
- 当前工作树没有 `.env`，检查时没有 Provider 环境配置；只核对变量是否存在，没有显示或记录密钥值。代码默认 Provider disabled。
- 未来执行需要独立 Run ID、正式 API/Worker、全新空 DB 和 Checkpoint DB、单 Worker、仅本实验流量。当前任务没有付费授权，不能设置开关或启动真实请求。
- 浏览器自动化仍受 STOP 约束；本任务不触碰。

## 硬停止

付费授权缺失；任何请求参数、模型、响应、Usage 或账本不一致；未知结果；预算/请求限额达到；跨租户/跨绑定读取；模型提议未授权工具；业务写入风险；不能证明本地服务仅使用本实验 DB/Worker。发生后立即停止，不进行自动/手动重试或网络切换。
