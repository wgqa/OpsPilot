# AR-02-LIVE-CONNECTION-DIAG-01

**状态：** `ACCEPTANCE_CANDIDATE`（只读诊断已完成；无真实 Provider 请求）
**仓库/分支：** `wgqa/OpsPilot` / `codex/ar02-live-01`
**Base：** `85ec4e89387229b581c8be19ec7dfd28d893b64e`
**准则文件 Blob：** North Star `1f737712c7a36ceb34433ac09c3fbba3c3305542`；AGENTS `32c45506cceeaa8c76a5c56bf8360ff476b58856`；Skill `d405c8d413d633824b279202cc1503dab4cf0b03`。任务合同为本轮用户指令；前次真实运行报告与原始证据保持只读。

北极星问题是正式助手首次 Provider 调用为何 UNKNOWN。本轮只读对照原记录，并以显式 `httpx.MockTransport` 经过真实 `run_assistant → create_agent → Loop → create_assistant_model` 检查线上线形；不连接 DeepSeek，也不做网络探测。

## 已证实差异

| 项目 | CONN-02 已成功调用 | REAL-JOURNEY S01 正式助手 | 核验结论 |
|---|---|---|---|
| SDK 与模型 | `ChatOpenAI`；DeepSeek Flash；HTTPX 0.28.1、OpenAI SDK 3.33.0、`langchain-openai` 1.7.2 | 同一组版本；真实请求 User-Agent 为 `AsyncOpenAI/Python 3.33.0`，PREFLIGHT 记有相同 HTTPX / LangChain 版本 | 未发现 SDK/HTTPX 版本分叉。CONN-02 使用短纯文本，S01 使用较长系统上下文和 Knowledge 工具，负载不等价。 |
| Base URL 与路径 | Base URL `https://api.deepseek.com`；实际 `POST https://api.deepseek.com/chat/completions`，HTTP 200 | 配置 Base URL 带 `/v1`；原始 HTTPX 请求为 `POST https://api.deepseek.com/v1/chat/completions`，之后无响应 | 路径不同是已证实差异，但单凭差异不能归因。DeepSeek 官方集成页也示例 `/v1/chat/completions`；官方 Chat Completions 规范列出 `/chat/completions`。[`/v1` 官方示例](https://api-docs.deepseek.com/quick_start/agent_integrations/workbuddy/)；[Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/) |
| HTTPX、代理与重试 | 显式 sync/async HTTPX Client；`trust_env=False`、不跟随重定向、HTTPX retries=0、SDK `max_retries=0`、30 秒超时 | 相同设置；正式运行 PREFLIGHT 记录无代理环境变量；原始请求 Hook 已触发 | 没有证据支持环境代理导致差异；两边都不读取 HTTPX 环境代理。Hook 触发说明请求已交给 HTTPX 请求流程，但不能证明连接进入了哪一层网络。 |
| 连接与响应 Hook | CONN-02 `WireCapture` 在发送前校验端点/请求体并核对持久单次授权；有响应 Hook | 运行器在正式模型工厂创建后附加被动请求/响应记录 Hook；持久预算在 Assistant Domain dispatch 层预留；此次只记录到 request Hook、没有 response Hook | 钩子职责不同。已保存代码和日志中没有 Hook 抛错证据；不能将钩子差异认定为连接根因。 |
| 请求体与工具 | `max_tokens=64`、`thinking=disabled`、`stream=false`、无工具；不含 `tool_choice` | `max_tokens=2048`、`thinking=disabled`、`stream=false`、`temperature=0.0`、一个 Knowledge 工具、`parallel_tool_calls=false`；工具存在但实际体漏了 `tool_choice` | 实际请求体违反本地冻结报文对显式 `auto` 的要求。DeepSeek 官方协议说明带工具时省略该字段默认就是 `auto`，故这不是供应商协议违规，也没有证据显示它能造成连接失败。[默认规则](https://api-docs.deepseek.com/api/create-chat-completion/) |
| 原始错误记录 | 完整响应：HTTP 200、Completion ID、Usage 均已保留 | HTTPX 请求记录 1 条、响应记录 0 条；Run `FAILED`，外层错误 `OpenAIConnectionError: Connection error.`；SQLite 仅有相同的外层类型/消息 | 已检查报告、JSONL、运行日志与隔离 SQLite。底层异常类型及 `__cause__` / `__context__` 链未持久化，无法从现有材料恢复。 |
| 预算与历史 UNKNOWN | CONN-02 独立的一次性 $0.01 账本 | REAL-JOURNEY 原记录仍为 dispatch `UNKNOWN`、Usage `UNKNOWN`，预留 645600 micro-USD，结算 0 | 使用只读 SQLite 核验与原 `RESULTS.json` 一致；本轮未修改或释放该记录。 |

## 根因判断

| 分类 | 判断与证据 |
|---|---|
| 已证实 | CONN-02 与正式助手使用相同的核心 LangChain/OpenAI/HTTPX 版本、显式 HTTPX 客户端、不读环境代理、30 秒超时和零重试。两者实际 URL 路径和请求体不同。正式 Assistant 的工具请求漏掉本地冻结要求的显式 `tool_choice=auto`。 |
| 可能相关 | `/v1` 与根路径的路由不同、S01 更大的上下文/工具 Schema、`temperature=0.0`、正式运行被动 Hook 与 CONN-02 发送前校验钩子不同，都是运行条件差异；没有 HTTP 错误响应或底层异常链，无法判定其中任何一项引发了 `OpenAIConnectionError`。 |
| 已排除 | `/v1/chat/completions` 不是已知的 DeepSeek API 协议违规：官方 WorkBuddy/CodeBuddy 集成文档明确给出该 URL。省略 `tool_choice` 也不是协议违规：有工具时官方默认 `auto`。两种差异均不能解释为已证实的连接故障根因。 |
| 证据不足 | 原始 Hook 仅留有外层 `OpenAIConnectionError` 和通用 `Connection error.`；Run、Chat Attempt、dispatch SQLite 行也没有下层 cause。无 HTTP response，所以无法区分连接建立、TLS、代理/网络、中途断连或其他原因；没有依据声称 DeepSeek 服务故障或 DNS/TCP/TLS 问题。 |
| 恢复建议与授权 | 已把唯一可证实的本地报文偏差最小修正为：正式 Assistant 有工具时经 `ModelRequest.tool_choice` 显式传 `auto`，没有工具时保持原设置。离线正式 Assistant 测试通过；该修正不解释原连接失败。不要把 `/v1` 改回根路径来做未经证明的修复。若要恢复付费实验，需主 Agent 复核本补丁后，用户另行批准一个明确的一次性新尝试、独立身份和费用预留；本任务本身没有授予真实请求授权，不能复用或改动旧 UNKNOWN dispatch。 |

## 免费验证

运行环境：Python 3.14.0、HTTPX 0.28.1、OpenAI SDK 3.33.0、`langchain-openai` 1.7.2。正式 Assistant 的新 RED 为 `tool_choice` 缺失；GREEN 使用显式 MockTransport 实际捕获最终请求。已执行测试的日志和退出码在 `runs/`；最初指向缺失 `.venv` 的命令未启动测试，未留下独立原始日志（见 `FAILURES.md`）。最终相关回归为 **9 passed**；另一次对其中 wire 测试的独立运行为 **1 passed**。全量 pytest 未运行。诊断期间真实 Provider 请求、MCP 请求和外部网络探测均为 **0**。

本次修改仅涉及 `opspilot/assistant.py` 的工具选择字段及 `tests/test_ar02_live_hf02.py` 的一条正式 Assistant MockTransport 回归。`main`、冻结 Gold、历史失败与既有 UNKNOWN 预留未改。
