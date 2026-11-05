# AR-04C-REAL-JOURNEY-01 — 后续真实执行合同（待授权）

**当前状态：** `PAID_EXECUTION_NOT_AUTHORIZED`。本合同仅定义审查范围，不是 Provider 调用授权；真实用户授权及主 Agent 核验缺一不可。

## 实验身份与隔离

- 实验 ID：`AR-04C-REAL-JOURNEY-01`
- 分支：`codex/ar04c-real-journey-01`
- 代码基线：`main@60eee87bfe3cca522011316cb4cd2c0064ad291b`
- 本候选中经测试的源码提交：`6951bcd7a2d791a1454c46b3b70077ebdf909cba`
- OFF 与 ON 使用不同 Domain SQLite、Checkpoint、Session、Task、预算行和运行 Trace；订单、Event、文档、授权与 Memory 初态相同。
- 旧实验数据库、UNKNOWN dispatch、费用预留和 claim 不读取、不迁移、不修改。
- 两个 SQLite 各分配总上限的一半，所以总额不会因独立数据库而翻倍。

## 冻结用户输入与执行顺序

完全沿用 `CASES.json` 的 J1–J4。OFF 先于 ON，双方使用完全相同的 J2/J4 原句、同一个 `ar04c-order`、同一 Event、`202/ACKNOWLEDGED` 和 `QUEUED`。不同结果不重跑、不修 Prompt；UNKNOWN、无效 Usage、越权、超时或预算停止后不重试。

正式入口仍为 FastAPI → Worker → `ASSISTANT_V1` → LangChain/LangGraph → 受限 MCP → Domain。模型自由选择 Knowledge、可选 Skill、只读工具、直接回答、澄清、继续或停止；不硬编码工具顺序。Memory 只能作历史方法提示，当前 Receiver 必须重新查询。

## Provider 与费用

- Provider：DeepSeek；模型名 `deepseek-flash`（官方模型版本标识 `DeepSeek-V4.1-Flash-1017`）。
- OpenAI 格式 Base URL：`https://api.deepseek.com`；最终 Chat Completions 路径由显式预检确认。
- `thinking={"type":"disabled"}`；`max_tokens=2048`；有工具时 `tool_choice="auto"`；`parallel_tool_calls=false`；`stream=false`。
- Context 输入估算上限 12,000 tokens；每请求超时 30 秒；并发 1；自动/人工重试 0。
- 每条件 Provider 上限 8、应用预算 `$5.25`；合计最多 16、`$10.50`。
- 官方价格页面（2026-11-05 核对）：Flash 峰值未命中输入 `$0.30/M`、峰值输出 `$1.20/M`，模型上下文 1M、最大输出 384K。费率与模式协议另见 DeepSeek [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/) 和 [Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)。
- 不依赖缓存命中或非峰值折扣。单请求按完整模型上下文包络预留：`(616,000 × $0.30 + 384,000 × $1.20) / 1,000,000 = $0.645600`。16 次最大预留 `$10.329600`；每条件 8 次最大预留 `$5.164800`。有效 Usage 到达后按该价格版本向上取整结算并释放剩余预留。
- MCP 无固定低次数上限；每次仍持久记录。执行受到既有权限/TaskBinding、单 MCP 12 秒、单 Run 60 秒、Task 活跃 300 秒、Campaign 3600 秒及 Graph recursion limit 36 约束。不能以相同工具名拒绝合法补查。

## 授权、claim 和凭据

- 当前 `PAID_AUTHORIZATION.json`、`.runtime/ar04c-real-journey-01/claim.json` 与 one-shot token 均不存在，本候选未创建或消费 claim。
- 只有获得本合同范围的明确用户付费授权后，才可在私有运行目录写入精确授权记录，原子创建唯一 claim，绑定实验 ID、授权记录哈希、分支、基线、执行 HEAD、冻结合同摘要、预算、价格版本和 token SHA-256。
- claim 必须在任何 Provider 外发之前持久消费；同一实验再次启动、响应丢失或结果 UNKNOWN 均立即拒绝，不能创建第二个 claim。
- `create_assistant_model()` 对新实验要求授权记录、claim、token、实验 ID、启用标记、分支、当前 HEAD、冻结文件摘要、模型/费率/参数/预算均精确匹配。只有环境中存在 API Key 不能通过授权。
- API Key 只从 Provider 客户端环境读取；不能写日志、Trace、报告或 Git。记录请求/响应须脱敏；不记录 Authorization/Cookie/密钥头。

## 超时、UNKNOWN 与恢复

Provider 预留在发出之前写入既有 `ar02_live_dispatches`；MCP 尝试在工具执行前写入 D2 Attempt Ledger。超时、取消、响应丢失或 Usage 缺失/无效：停止整个成对 Campaign，保留该 Provider 预留，关闭对应预算，不释放或重试。不因 Worker 重启、新 Run、新 Session 或改换工具顺序重置计数。仅有效 Usage 且在预算内时才结算并允许下一合法请求。

## 当前未完成

本 Phase A–C 没有授权或运行真实模型；也没有生成 claim、执行真实登录旅程或浏览器检查。MockTransport 验证了正式 API/Worker/Assistant 序列化和预留先于 HTTP 传输，不证明 DeepSeek 真实行为、费用账单或 ON/OFF 收益。未来执行前应再次核对官方价格、当前分支/HEAD、冻结合同 Digest、服务端凭据与新 claim；若其中任一条件不一致则阻止 Provider 出站。
