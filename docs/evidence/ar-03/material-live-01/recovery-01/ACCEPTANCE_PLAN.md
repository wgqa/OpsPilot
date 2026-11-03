# AR-03-MATERIAL-LIVE-01 Recovery 01 — 冻结验收计划

**基线：** `codex/ar03-material-01-public@69a1a1171b97849a6b5a77a7b8f8d03f263c95aa`  
**范围：** 新隔离数据库初始化顺序修复与一次免费预演。  
**状态：** 在实现前冻结；不授权真实 Provider 请求。

## 固定合同

- 保留 `docs/evidence/ar-03/material-01/CASES.json` 与 MAT-01～MAT-06 Gold 原样。
- 保留先前失败执行的 `EXECUTION_CLAIM.json`、数据库、日志、Trace、结果与账本原样；其 one-shot 身份仍为已消费。
- 只在确认不存在的全新隔离 DB 上调用项目 `reset_fixture(..., "S1_POS")`；必须在 Campaign ledger、Session、Task、Run 和调查状态建立前完成。若 DB 或 SQLite sidecar 已存在则拒绝初始化，不重置任何现存数据。
- 随后初始化既有 Campaign ledger，建立 `ar03-order` 及同 Event 的 `HTTP 202 / ACKNOWLEDGED`、`QUEUED` Delivery/Receiver 夹具，并通过正式 API 建立授权 Session、TaskBinding 和初始调查 Run。
- 用显式确定性 FixtureModel 驱动一个正式 Worker Run，经现有 MCP 实际读取 Delivery 与 Receiver。核验当前来源有效、观察属于本 Run、Task 额度为 16/10、活跃时间仍为 300,000ms，且没有业务写入。
- 真实 Provider HTTP 请求必须为 0；不得建立/消费新的 one-shot 执行 claim。之后的收费旅程需主 Agent/用户另行确认，并使用独立数据库、执行身份与证据目录。

## 验收标准

1. 全新 DB 的受信 Demo Bootstrap 先于 Campaign ledger；空 DB 可完成夹具与授权绑定。
2. 已存在 DB、`-wal` 或 `-shm` 时 Bootstrap fail-closed，不能触发 `reset_fixture` 清理。
3. `/assistant/order` 产生唯一 Task、Session、Message 与 `ASSISTANT_V1` Run；实际只读 MCP 调用返回同 Event 的 Delivery/Receiver 事实。
4. `/assistant-sources` 复核为 current；Observation 与 Attempt 归属当前 Task/Run；越权资源参数不由模型提供。
5. Campaign / Task 上限与剩余计数可审计；业务写表计数为零；Provider HTTP 请求为零；新的收费 claim 未创建。
6. 原始失败及历史运行证据未改写；只在 `recovery-01/` 新增结果与日志。

## 六问与停止线

1. **用户变化：** 此修复不增加产品能力；它让新的隔离演示环境能够进入原有可信调查旅程，而不是在首个 Run 前因缺少 Tenant 种子而失败。
2. **Agent 决策：** 预演使用确定性模型，只验证工具接线，不证明真实模型自主性。
3. **观察驱动：** Delivery=ACKNOWLEDGED 与 Receiver=QUEUED 都由当前同 Event MCP Observation 证明；真实模型不同事实行为留待之后获批实验。
4. **约束双向检查：** 拒绝重置已有 DB 保护历史账本和调查状态；全新 DB 的正例验证合法演示不会被误拒。
5. **职责复用：** 复用 `reset_fixture()`，删除 Runner 当前仅建 Schema 的初始化做法；不另造种子流程或预算设施。
6. **证据与停止：** 只跑一次零费用正式 API/Worker/MCP 预演和所需定向测试。完成后提交候选并停止；收费执行必须另行授权。

远端本轮不可达时，`REMOTE_UNVERIFIED`；不得推测远端变化。不得运行浏览器、真实 Provider 或业务写操作。
