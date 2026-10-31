# AR-02-LIVE-01 P0 — 冻结验收计划

**状态：** P0 免费实现与本地验证；P1 真实 Provider 未授权。

**冻结基线：** `88e00126aaca7af0cbfd454e8f833eae90eae39c`
**冻结输入：** `docs/evidence/ar-02/hf-01/SMOKE_INPUTS.md`，Blob `ee9b1623a2296905c425449709a2f9ae6563caca`。原 S01/S02 Gold 不修改。

## 用户目标与边界

准备正式 Session/API → 单 Worker → `ASSISTANT_V1` → Provider/MCP → Domain/SQLite → 原 Session 答复的同一助手旅程。P0 不发送真实 Provider 请求、不运行浏览器、不执行业务写入，也不证明模型智能。

## 冻结判据

| 编号 | 检查 | 通过条件 |
|---|---|---|
| LIVE-P0-01 | Provider fail-closed | 默认关闭；仅凭凭据不能创建真实调用；实验 ID、固定 `deepseek-flash` 及必需配置缺失或不匹配时停止。 |
| LIVE-P0-02 | 请求协议 | 本地 `httpx.MockTransport` 仅捕获一份实际序列化 body：Chat Completions、`deepseek-flash`、`max_tokens=2048`、`thinking.type=disabled`、`tool_choice=auto`、`parallel_tool_calls=false`、工具 Schema 正确，且无 `max_completion_tokens`。测试不得触网。 |
| LIVE-P0-03 | 实验级额度 | 单一持久 ID `AR-02-LIVE-01` 跨 Session/Run 共用 Provider ≤16、MCP tools/call ≤12、USD reserve ≤10.50；每次外发前在 SQLite `BEGIN IMMEDIATE` 下原子预留。 |
| LIVE-P0-04 | 幂等/未知/恢复 | 同一 Run/kind/logical key 同 digest 不新增额度；异 digest 拒绝。已预留但 UNKNOWN 的请求/工具不释放计数或预留额，重开数据库仍不可重发。 |
| LIVE-P0-05 | 并发与原有限额 | 独立 SQLite 连接竞争不突破全局上限；现有 per-Run / Task 更小额度仍先行有效。合法零工具回答、Knowledge 与绑定范围内只读 MCP 仍可通过免费替身。 |
| LIVE-P0-06 | 正式 Worker 路径 | 确定性模型通过现有 FastAPI TestClient/Worker 执行；账本记下跨 Run 的 Provider/MCP 调度，Message/Answer 来源仍关联原 Session。该结果只证明接线，不是 Provider 或真实浏览器证据。 |
| LIVE-P0-07 | 范围红线 | 普通服务启动、Provider 工厂默认态、预算拒绝和失败恢复均不产生真实 Provider 请求、审批、Diagnosis、ActionIntent、Ledger、Handoff 或其他业务写入。 |

## 费用边界冻结

P0 实验账本固定总预算 USD 10.50。按 2026-11-01 官方峰值 cache-miss 输入价 $0.30/M、输出价 $1.20/M，以及 1M 上下文/384K 输出上限，每个 Provider dispatch 预留 USD 0.645600（输入余量 616K）；Usage 完整且合法时结算实际费用并释放差额，Usage 缺失/畸形/结果未知时保留全额预留。16 次全未知请求合计预留 USD 10.329600；第 17 次首先受冻结 Provider 次数上限 16 拦截。该预留覆盖文档化上限，不保证 Provider 违反文档边界时绝不超支。MCP 计数指 `tools/call` 尝试，不包含无业务事实的 `tools/list` 元数据发现。

## P1 停止条件

需要另行明确批准精确的模型、模式、Provider 上限、MCP 上限、USD 总额、重试/未知费用规则后才可发送真实请求。P0 代码和本测试计划不构成授权。
