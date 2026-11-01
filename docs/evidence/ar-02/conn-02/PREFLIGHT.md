# AR-02-CONN-02 真实请求发送前预检

## 基线与读取记录

- Repo / branch: wgqa/OpsPilot / codex/ar02-live-01
- Base HEAD: 04b671551fb60a42c3d2dc857666a017e5f9a056
- main: ec8c3582f6d145eec9979c43607302731411ead8（本轮不修改）
- 初始工作树：clean
- North Star Blob: 1f737712c7a36ceb34433ac09c3fbba3c3305542
- AGENTS Blob: 32c45506cceeaa8c76a5c56bf8360ff476b58856
- Skill Blob: d405c8d413d633824b279202cc1503dab4cf0b03
- 指定 2026-11-01 Markdown 任务卡未在仓库、开发目录或 Codex 附件目录找到；具体参数以用户当前消息为准。

## Provider 接线复用核验

AR-01 已发布的真实 A/B Trace 来自提交 b4e130fb22491bc84e69329df2553253a239e024。其 A 组真实请求记录了：
- Endpoint: https://api.deepseek.com/chat/completions
- HTTP status: 200
- Model: deepseek-flash
- Completion ID: 836e836a-2c79-42bd-a245-3fcacd42b353
- Usage: prompt 2383, completion 89, total 2472
- Provider request_id 未返回，但 Completion ID 与 Usage 存在。

本次实验复用同一 LangChain ChatOpenAI、HTTPX AsyncClient/Client 显式注入、trust_env=False、follow_redirects=False、HTTPX retries=0、SDK max_retries=0 与发送前事件钩子；不导入或复用旧实验的预算对象、授权或数据库。当前隔离分支无 AR-01 实验模块，因此仅复用已验证的接线方式，不把旧策略配置移植为授权。

## 免费离线 SDK 预检

最终离线运行由 runs/08-final-offline-preflight.log 保存，退出码 0。真实 LangChain SDK 只经显式 HTTPX MockTransport 发出一条 mock 请求；外部 Provider 请求为 0。

- HTTPX / OpenAI / langchain-openai: 0.28.1 / 3.33.0 / 1.7.2
- Python: 3.14.0
- 请求体摘要: 9d17d2f554ce701a3e7868936acba722fafb30a07444c42636985c5d417fa146
- Sender 源码 SHA-256: ce4ec5b7be155c13a181d3c7ceecce1a59f5100461ffedb36e565d067f68cfe4
- 精确 JSON: model=deepseek-flash; messages 仅含用户原句；thinking.type=disabled; max_tokens=64; stream=false；无 tools/tool_choice/parallel_tool_calls。
- 捕获到的最终 URL 正确为 https://api.deepseek.com/chat/completions；mock 返回 HTTP 200、Completion 与 Usage。
- 请求前检查 Authorization 仅确认存在，绝不记录头值。MockTransport 与真实 HTTPX 传输是显式注入；无默认联网客户端。

## 凭据与网络配置

目标 worktree 的进程环境变量及本地 .env 均没有模型凭据。只读检查确认用户主工作区指定 .env 中存在非空 OPSPILOT_MODEL_API_KEY 项；未显示、复制到日志、保存到 SQLite 或写入 Trace。发送器只读取这一个指定键。历史连接器使用 trust_env=False，本次同样不读代理环境变量、不跟随重定向、不允许 HTTPX 或 SDK 重试。TLS 验证保持 HTTPX 默认开启。

## 当前费率与有限费用说明

查询于 2026-11-01 的 DeepSeek 官方定价页列出 deepseek-flash 峰值未缓存输入 USD 0.30/百万 Token、输出 USD 1.20/百万 Token；本次以峰值单价估算，不依赖缓存折扣。官方 Chat Completions 文档说明 max_tokens 是生成上限，1 至 384K；thinking.type=disabled 选择非思考模式。参考：
- https://api-docs.deepseek.com/quick_start/pricing/
- https://api-docs.deepseek.com/api/create-chat-completion/

本次最多一个请求。USD 0.01 预留记为 10,000 micro-USD，是应用账本的单次预留，不是供应商侧硬计费上限。如果供应商不遵守 max_tokens，或账单口径不同，不能宣称绝对不超额；响应丢失则费用未知且预留不释放。收到合法 Usage 后，按峰值单价计算应用侧估算，不代表实际账单查询。

## 预发送事务与停止门

离线证据已通过。尚未执行真实请求。真实出站前，reserve-only 命令会独占创建新的 SQLite 账本文件，并在一个 BEGIN IMMEDIATE / COMMIT 事务中插入唯一授权身份、attempt 和 ATTEMPT_RESERVED + 10,000 micro-USD；然后先将该状态提交到当前隔离分支。发包事件钩子再次核验 endpoint/body/Authorization，并以 SQLite CAS 将 attempt 从 ATTEMPT_RESERVED 改为 OUTBOUND_STARTED、request_count=1。第二个并发执行无法获得发送权。任何 OUTBOUND_STARTED 均不能重用；失去响应时落 UNKNOWN_STOPPED，不重试。

到本文件生成时真实 Provider 请求数为 0。实际请求状态将在 RESULTS.json 和 TRACE.jsonl 中补记。
