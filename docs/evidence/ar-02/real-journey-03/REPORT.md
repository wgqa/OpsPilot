# AR-02-REAL-JOURNEY-03 实验报告

**实施状态：** `ACCEPTANCE_CANDIDATE`
**业务旅程评估：** `PARTIAL`（五轮均完成并持久化；S02-4 未在该 Run 内重新取得 Receiver Observation）
**代码运行 SHA：** `d0e9dd2fc2f4b278fa7af6a696f6feecbb3fa77b`
**冻结基线：** `bc5484fe721bd2a54bc3a73326ff3c649fa1baa2`
**分支：** `codex/ar02-real-journey-03`
**实验：** `AR-02-REAL-JOURNEY-03`

## 用户实际完成的事情

同一个 S02 Session 中，用户提交五轮冻结问题；正式 FastAPI、单一 Worker、`ASSISTANT_V1`、真实 DeepSeek、MCP 与隔离 Domain 持久化了五轮回答。模型将 E1 日志当作待核实线索，检索授权协议；经可信 API 绑定 `ar02-order` 后，它查询该订单、投递及同一 Event 的 Receiver 状态，并生成未提交的处理说明草稿。

五个 Run 都是 `CHAT_READONLY / SUCCEEDED`，回答以 `CHAT_MODEL` 持久化。它们不代表 S1 已运行（S01 未运行），也不代表正式 Diagnosis、修复或交接已完成。**S02-4 的“当前状态核实”没有在该轮重新查询**，因此完整冻结目标仍为 PARTIAL。按停止条件没有重试或补跑。

## 五轮真实旅程

| 轮次 | 用户请求（冻结原文） | 模型选择与实际执行 | 用户获得的结果 |
|---|---|---|---|
| S02-1 | “请记住下面是待核实的示例线索，不是你已验证的业务事实：`event_id=event-e1, transport_request_id=req-e1-1, delivery_http_status=202, receiver_status=unknown`。请查适用的回调/Receiver 协议，说明 202 能证明和不能证明什么。” | 真实模型选择两次 `search_project_knowledge`，两次均由 MCP 实际执行并返回版本化文档。无订单绑定。 | 说明 HTTP 202 只表示持久入队，不证明业务处理完成；不把用户给的 E1 字段冒充真实观察；说明此时没有业务绑定与当前状态证据。两次相近查询属于效率成本。 |
| S02-2 | “我现在确认要查询资料范围中已授权的回调协议；没有特别指定旧版，请按本问题适用范围核对。说明检索到的版本、摘要和来源。” | 模型再选择两次 Knowledge 查询，MCP 均返回授权范围内结果。 | 给出适用合同版本 2、Receiver 文档 2.1.0 及来源；明示配置/绑定版本不证明线上部署版本。 |
| S02-3 | “请绑定我有权访问的订单 `ar02-order` 并核查当前状态。” | 信任绑定由可信 API 确认，不由聊天文本授予。模型选择 Knowledge、`get_order_status`、`get_callback_delivery`、`get_receiver_processing`；四次 MCP 调用均成功。 | 查到订单 `COMPLETED`；同一 Event `event-d55164b8-8a16-4430-aeaf-59fd36489c18`、delivery v1，HTTP 202 / `ACKNOWLEDGED`；Receiver 为 `QUEUED`，SLA 300 秒。结论是尚不能证明处理完成。 |
| S02-4 | “对照刚才的 E1 线索和本次真实查询，接收方现在处理完成了吗？” | 模型作一次真实 Provider 调用，没有提出或执行 MCP 工具。 | 回答“没有证据表明接收方已完成处理”，区分 E1 与真实 Event，并引用 S02-3 的 `QUEUED` 观察及时间。回答谨慎，但该状态来自前一 Run，未由 S02-4 重新核查；故未证明本轮取得当前 Receiver Observation。 |
| S02-5 | “基于目前有来源的事实整理一份处理说明草稿，并明确仍未知的部分。” | 一次真实模型调用，没有新增 MCP 调用。 | 生成标注“草稿、未提交”的说明，列出授权协议来源、订单/Event/Request ID、202/ACKNOWLEDGED、Receiver QUEUED、观测时间、线上部署版本及最终处理状态等未知；没有声称提交工单、修复或产生回执。草稿沿用前轮观察并保留其时间，不构成新的当前状态验证。 |

完整原始回答、每次出站模型消息、模型 Tool Call、实际 MCP 请求/结果和来源在 `RESULTS.json`、`TRACE.jsonl` 与 `PROVIDER_HTTP.jsonl`。模型提出调用与工具实际成功执行分别记录。

## 逐轮模型回答原文摘录

完整持久正文以 `RESULTS.json` 为准，以下摘录用于快速核验：

- **S02-1：**“HTTP 202 只证明接收方已把该投递持久地接收进自己的队列……不能证明业务处理已完成”；“仅有 202、没有同一 event 的当前接收方证据时，处理状态就是 `UNKNOWN`。”
- **S02-2：**“按问题适用范围取到的是契约版本 2”；并指出 `deployment_version_verified=false`，所以不能证明线上部署版本。
- **S02-3：**“该订单的回调事件已被 Receiver 接收入队，但尚未证明处理完成”；同一 Event 的 Receiver 是 `QUEUED`，SLA 截止前建议继续观察。
- **S02-4：**“没有证据表明接收方已完成处理。”该回答引用了前一 Run 的观察时间；这是谨慎结论，但不是本轮新取证。
- **S02-5：**“下面是一份处理说明草稿……它不是正式诊断、不是回执，也未提交任何修复或审批。”草稿明确列出 Receiver 最终处理状态与线上部署版本仍未知。

## 关联与可信事实

- Session：`session-6ba447ba-1da9-411a-adb6-0d2160a49d43`
- Task（可信绑定后）：`task-daf2b12d-f403-4729-b3f7-63e0892ce221`
- S02-1：Message `message-3e841e36-2a4d-4872-8216-022f20362bd9`；Run `run-ffb91579-9a8a-49c9-8fd2-fa7dd5d8f7b8`
- S02-2：Message `message-95dd62ab-1c90-4754-872a-1532089fce47`；Run `run-a1a17dcf-eb0f-4149-98b6-b05718ada008`
- S02-3：Message `message-978ec0ea-3088-461f-95cd-bf5be53135ff`；Run `run-da8f1ce6-fe0f-40bb-b704-6aaf3c4975e8`
- S02-4：Message `message-e31e2871-c211-42f7-b2b5-a844a66db696`；Run `run-8983141b-42b3-414a-842a-df45773052b8`
- S02-5：Message `message-604d9af0-0f5e-4162-9b66-75222aedded8`；Run `run-43f78564-df4f-4f3a-8599-98d130a3cf3d`
- S02-3 order observation `observation-f07f08e0-395e-4330-99ca-ab22bdfa0b2c` / `evidence-ec420817-9cbb-45b1-afae-955061eec5bd`；delivery observation `observation-f7d8057d-ab53-4283-b5cd-6fc361ca8329` / `evidence-e5871062-67e6-4937-bcc4-41501b0bdd77`；Receiver observation `observation-613bbcb1-deb2-4977-8b1b-9dffd8a4555d` / `evidence-7b731aff-99ff-417c-92ba-526f2dba617d`。
- 目标 Event 的真实 MCP 数据：`transport_request_id=transport-6b0ee778-a176-4993-957c-7fb4ef72185a`、HTTP 202、`ACKNOWLEDGED`、Receiver `QUEUED`、`delivery_version=1`。这些是隔离本地演示 Domain 的工具观察，不是生产服务数据。
- 运行前通过本地隔离夹具准备该订单与 Receiver QUEUED 状态；夹具准备记录与 Agent 观察分别保存在 `PREPARATION.json`、`PREFLIGHT.json` 和 `TRACE.jsonl`。不把夹具准备伪称为模型取证。

## Provider、Context 与费用

- 9 次真实 DeepSeek HTTP 请求、9 个 HTTP 200 Completion；没有超时、UNKNOWN、重试或缺失 Usage。模型标识均为 `deepseek-flash`，Fingerprint 均为 `bc19ba97cbe016479903222bb1578db6`。每个 Completion ID、请求/响应正文、finish reason 和 Usage 均保存在脱敏 HTTP Trace。
- 请求均使用冻结参数：non-thinking、`max_tokens=2048`、提供工具时 `tool_choice=auto`、`parallel_tool_calls=false`、`stream=false`、30 秒超时、零重试。端点为 `https://api.deepseek.com/v1/chat/completions`，这是当前配置的 `/v1` 路径；MockTransport 已在真实实验前验证 SDK 序列化。
- Usage：输入 51,845 tokens，输出 5,800 tokens，总计 57,645 tokens。最大实际 Prompt 9,801 tokens；冻结 Context 上限 12,000，未超限。
- 应用账本按冻结价格版本 `DEEPSEEK_FLASH_PEAK_2026-11-01` 结算估算 USD 0.022518；预留余额归零，实验累计已结算 USD 0.022518、剩余 USD 10.477482，状态 `OPEN`。这不是供应商账单保证。DeepSeek 当前公开模型映射与峰值计价参考[官方价格表](https://api-docs.deepseek.com/quick_start/pricing/)；Chat Completions 字段参考[官方 API 文档](https://api-docs.deepseek.com/api/create-chat-completion/)；`/v1/chat/completions` 也见[官方集成示例](https://api-docs.deepseek.com/quick_start/agent_integrations/workbuddy/)。
- 预算上限 16 Provider / 12 MCP / USD 10.50；实际 9 / 8 / USD 0.022518。运行结束时预算保持 OPEN。没有执行 S01 或其他探针。

## 安全、环境与已知限制

- 正式路径使用 FastAPI、一个 Worker、`ASSISTANT_V1`、ChatOpenAI/HTTPX、MCP 与 Domain；未使用独立 CLI 模型发送器。
- Domain 业务写计数：Approval、REPAIR、DELIVER、Diagnosis、ActionIntent、ActionLedger、Handoff Queue/Receipt 均为 0。没有工单提交、自动重发、审批或外部业务写入。
- Runtime Domain DB 与 Checkpoint DB 是本次独立路径，运行前确认不存在；历史 `REAL-JOURNEY-01`、`REAL-JOURNEY-02` 和其他 UNKNOWN 账本没有重置或复用。
- 授权/密钥扫描未发现 API key 或 Bearer 值；HTTP 日志 `authorization_logged=false`。日志保留 Provider 内容、业务演示 ID、来源与调用关联，便于复核。
- **产品结果限制：** S02-4 的结论与时间戳正确地避免宣称已完成，但没有当轮新取证。S02-4 的用户目标“当前状态核实”仅部分满足。由于任务冻结了不得重跑，本报告不以 S02-3 的短时间间隔替代 S02-4 的本轮 Observation。
- 运行时没有触及 12,000 Token Context 限制；因此本实验不能证明所有更长会话均不会超过该限额。
- 本地真实 HTTP/MCP 与测试 API 不等同于生产环境；本轮没有浏览器用户界面验收，也没有 S01。

## 验证记录

| 验证 | 命令/证据 | 结果 |
|---|---|---|
| 预检定向 RED（旧 runner 误拒 `/v1`） | `runs/offline-live-preflight.log` | `PROVIDER_ENDPOINT_MISMATCH`；Provider/MCP 请求为 0、隔离运行 DB 未创建 |
| 预检修正 GREEN | `runs/offline-endpoint-fix.log`、`runs/offline-live-preflight-green.log` | 5/5 通过；端点限定到正式工厂支持且文档记载的路径 |
| 聚焦离线测试 | `python -m pytest -q --basetemp=D:\学习\agent新项目\.pytest-temp\ar02-rj03-prep-20261101-01 tests/test_ar02_real_journey_03_prep.py tests/test_ar02_context_continuity_01.py` | 5 passed |
| 相关离线回归 | `python -m pytest -q --basetemp=D:\学习\agent新项目\.pytest-temp\ar02-rj03-regression-20261101-01 tests/test_ar02_real_journey_03_prep.py tests/test_ar02_real_journey_budget_scope.py tests/test_ar02_live_budget.py tests/test_ar02_context_continuity_01.py tests/test_ar02_journey_p0.py tests/test_ar02_journey_p0_hf02.py tests/test_ar02_knowledge.py tests/test_ar02_assistant.py tests/test_ar02_runtime.py` | 63 passed |
| 真实冻结旅程 | `runs/live-console.log`、`runs/live.log`、`RESULTS.json`、`TRACE.jsonl`、`PROVIDER_HTTP.jsonl` | 5 轮完成、9 Provider / 8 MCP；S02-4 新鲜观察缺口按 PARTIAL 记录 |

该 63 项是任务相关回归，不是全仓 pytest。没有在已完成的真实请求后再次执行可能触发网络的实验命令。原有历史失败和 AR-02-REAL-JOURNEY-02 的上下文预算停止证据未改写。

## Skill 收尾六问

> **用户变化：** 用户在一个 Session 内从协议解释、资料核对、可信绑定推进到真实只读订单/Event 核查及带未知事项的草稿；S02-4 新鲜复核只部分完成。
> **Agent 决策：** 模型自主选择 Knowledge 与订单/Delivery/Receiver 工具；S02-4、S02-5 选择直接回答。没有人为固定调用顺序。
> **观察驱动：** S02-3 的同 Event `202/ACKNOWLEDGED + QUEUED` 支持“未证明完成”；但 S02-4 未获得新的 Observation，不能证明用户提问时状态仍相同。
> **新增约束：** 使用独立实验身份、预算和数据库阻止旧 UNKNOWN 复用及意外写入；合法只读路径已实际成功。
> **简化结果：** 复用既有 Assistant、Worker、MCP、Domain 和预算账本；仅新增实验 allowlist/schema 和隔离 runner，没有新增 Runtime 或业务 Gate。
> **证据与停止线：** 9 个真实 Completion、8 次 MCP、原始响应/Usage/持久答案及零写入证据已保存；不补跑 S02-4，交主 Agent 独立审查。浏览器与 S01 未运行。

**候选结论：** `ACCEPTANCE_CANDIDATE`，业务旅程结果 `PARTIAL`。不自行签署 PASS，不合并 main，不启动 AR-03 或另一轮 Provider 调用。
