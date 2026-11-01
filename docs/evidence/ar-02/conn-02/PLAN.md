# AR-02-CONN-02 计划冻结

- Repo: wgqa/OpsPilot
- Branch: codex/ar02-live-01
- Base: 04b671551fb60a42c3d2dc857666a017e5f9a056
- main: ec8c3582f6d145eec9979c43607302731411ead8（本轮只读）
- 当前工作区开工状态：clean
- North Star Blob: 1f737712c7a36ceb34433ac09c3fbba3c3305542
- AGENTS Blob: 32c45506cceeaa8c76a5c56bf8360ff476b58856
- Skill Blob: d405c8d413d633824b279202cc1503dab4cf0b03

指定文件《OpsPilot_AR-02-CONN-02_旧成功接线单次真实调用授权任务卡_20261101.md》在开发目录、Codex 附件目录及当前仓库中未找到。执行合同采用用户本轮消息中明确给出的完整参数与停止条件；未从缺失文件推断额外权限。

## 唯一实验

使用 AR-01 已成功的 LangChain ChatOpenAI + 显式 HTTPX 客户端接线方式，完成最多一次真实 DeepSeek Chat Completion。

冻结请求：
- POST https://api.deepseek.com/chat/completions
- model=deepseek-flash
- thinking={type:disabled}
- max_tokens=64
- stream=false
- messages=[{role:user, content:请只回复：OK}]
- 不含 tools、tool_choice、parallel_tool_calls
- 零自动重试；30 秒总超时；不读取代理环境变量；不跟随重定向

真实出站前条件：
1. 显式 HTTPX MockTransport 离线预检通过，实际捕获 SDK 的 URL 和完整 JSON 请求体。
2. 凭据只从指定本地配置变量中读取且不写入日志。
3. 新的一次性授权身份 AR02-CONN02-20261101-01 不存在于既有材料。
4. 新独立 SQLite 账本以单一事务持久化授权身份、ATTEMPT_RESERVED 与 10,000 micro-USD 预留。
5. 发送前钩子再次验证 URL、方法、模型、消息、thinking、token 上限、stream、无工具和 Authorization 存在；之后将请求计数持久化为 1，才允许进入传输层。
6. 任意可能已出站或状态未知的结果立即消费一次性身份并停止，不重试。

状态只允许：PASS_CONNECTIVITY_ONLY、FAIL_STOPPED、UNKNOWN_STOPPED、BLOCKED_NOT_SENT。

## 费率与成本记录

DeepSeek 官方定价页面当前列明 deepseek-flash 峰值未缓存输入 USD 0.30/百万 Token、输出 USD 1.20/百万 Token；使用峰值费率估算，不依赖缓存或非高峰价。官方 API 说明 max_tokens 限制生成 Token，thinking.type=disabled 选择非思考模式。USD 0.01 是应用侧预留，不宣称为供应商绝对账单上限；响应丢失时费用保持未知且预留不释放。

来源：
- https://api-docs.deepseek.com/quick_start/pricing/
- https://api-docs.deepseek.com/api/create-chat-completion/

## 保留与范围

保留 CONN-01 已消耗的一次 HTTP 401 及 P1 UNKNOWN 账本原样不动；本轮不引用或重用那些授权/余额。禁止 S01/S02、浏览器、业务写入、main 合并及 AR-03。

## 停止条件

若显式离线预检、当前请求参数、唯一身份、事务预留、凭据存在、发送前校验任一不成立，则不发送并报告 BLOCKED_NOT_SENT。请求一旦进入发送边界，无论响应结果如何，不再次发送。