# AR-02-CONN-02 真实请求预发送预检

## 基线与读取记录

- Repo / branch: wgqa/OpsPilot / codex/ar02-live-01
- Base HEAD: 04b671551fb60a42c3d2dc857666a017e5f9a056
- origin/main 基线: ec8c3582f6d145eec9979c43607302731411ead8；本轮不修改 main
- 初始工作树：clean
- PROJECT_NORTH_STAR.md Blob: 1f737712c7a36ceb34433ac09c3fbba3c3305542
- AGENTS.md Blob: 32c45506cceeaa8c76a5c56bf8360ff476b58856
- 项目 Skill Blob: d405c8d413d633824b279202cc1503dab4cf0b03
- 指定 2026-11-01 Markdown 任务卡未在仓库、开发目录或 Codex 附件目录找到；执行合同采用用户本轮消息中的完整参数，未从缺失文件推断额外权限。

## Provider 接线核验

AR-01 已发布真实 A/B Trace 的提交为 b4e130fb22491bc84e69329df2553253a239e024。A 组真实请求 Trace 记录 HTTP 200、Completion ID 836e836a-2c79-42bd-a245-3fcacd42b353、Usage prompt 2383 / completion 89 / total 2472。Provider request_id 未返回。

本次复用同一 LangChain ChatOpenAI 与显式注入 HTTPX AsyncClient/Client 的接线方式：trust_env=False、follow_redirects=False、HTTPX retries=0、SDK max_retries=0，发送前由 HTTPX request hook 检查冻结请求体。没有复用旧实验预算、授权或数据库。当前隔离分支不含 AR-01 实验模块，因此复用了已验证的客户端接线形态，不复制旧实验授权策略。

## 免费离线预检

最终离线 SDK 预检记录在 runs/08-final-offline-preflight.log，退出码 0。真实 LangChain SDK 只经显式 HTTPX MockTransport 发出本地 mock 请求；Provider 请求数为 0。

- Python 3.14.0；HTTPX 0.28.1；OpenAI SDK 3.33.0；langchain-openai 1.7.2。
- 冻结请求体 SHA-256：9d17d2f554ce701a3e7868936acba722fafb30a07444c42636985c5d417fa146。
- Sender 源码 SHA-256：ce4ec5b7be155c13a181d3c7ceecce1a59f5100461ffedb36e565d067f68cfe4。
- 最终 URL 为 https://api.deepseek.com/chat/completions；方法 POST。
- 请求体仅含 model=deepseek-flash、用户句子、thinking.type=disabled、max_tokens=64、stream=false；无 tools、tool_choice、parallel_tool_calls。
- Mock 响应通过 HTTP 200、Completion、模型输出 OK 和 Usage。
- 发送前仅核验 Authorization 头存在；头值从未写入日志。HTTPX mock 和真实网络 transport 均显式注入，无默认联网客户端。

## 凭据、网络与费用

目标 worktree 的进程环境及本地 .env 没有模型密钥。只读检查确认用户主工作区本地 .env 中存在非空 OPSPILOT_MODEL_API_KEY；实际发送器只读取该键，不输出、复制或落盘其值。HTTPX trust_env=False，不读取代理环境变量、不跟随重定向；默认 TLS 证书验证保留开启。

2026-11-01 查询的 DeepSeek 官方价格页列出 deepseek-flash 峰值未缓存输入 USD 0.30/百万 Token、输出 USD 1.20/百万 Token。官方 API 文档说明 max_tokens 是生成 Token 上限，thinking.type=disabled 选择非思考模式。依据链接：
- https://api-docs.deepseek.com/quick_start/pricing/
- https://api-docs.deepseek.com/api/create-chat-completion/

USD 0.01 是本地应用一次性预留，不代表供应商硬性账单上限。收到 Usage 后按峰值单价计算应用估算；实际供应商账单未查询。若响应丢失，费用未知且预留不释放；任何已进入 OUTBOUND_STARTED 的尝试都不重发。

## 发送前持久资格

SQLite 在单个 BEGIN IMMEDIATE / COMMIT 事务中插入授权身份、attempt 和 ATTEMPT_RESERVED + 10,000 micro-USD。该预留先提交到隔离分支；发包钩子再次核验 URL、方法、请求体与授权头，再用 SQLite CAS 将 request_count 置为 1，之后才准许进入 HTTP 传输。两个并发进程只有一个能获得该 CAS。

预发送阶段 Provider Completion 请求数为 0。唯一真实调用及后续结果已记录在 RESULTS.json、TRACE.jsonl 和 runs/12-live-single-request.log。