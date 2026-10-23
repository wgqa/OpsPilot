# M4-AUTONOMY-C1 冻结与 RED 预检报告

**阶段状态：** `FROZEN_RED_PENDING_TTL_MAIN_AGENT_ACCEPTANCE`
**C1 功能状态：** 未实施
**裁决边界：** 本报告不是 C1 功能验收，也不代表 TTL-FIX-01 已通过。

## 审查前置核验

- Repo：`wgqa/OpsPilot`
- Branch：`codex/m4-autonomy-c1`（隔离 worktree）
- Base SHA：`add47ec83f31fa76b9b6a5782e013311732bc496`
- 计划冻结提交：`c792967d271cfd63942b1e6867bf903ce769bafc`
- RED/证据提交：待提交
- Diff 范围：仅 C1 冻结验收文档、RED 测试与运行证据；不含业务源码或 Gold 变更。
- `PROJECT_NORTH_STAR.md`：已从 Base SHA 读取；blob `1f737712c7a36ceb34433ac09c3fbba3c3305542`。
- `AGENTS.md`：已从 Base SHA 读取；blob `30319000ed0054007e9b7b6b46bf98b1493c8179`。
- 已读取：C1 任务卡、`m4-03/FROZEN_PLAN.md`、`m2-02/DEFERRED_GATES.md`。以上合同保持原样。
- TTL 候选：`origin/codex/m4-ttl-fix-01@bc7fc1633cc2b9e5ed6d652fbb518ea4cd3caafe`，与 main 未合并；TTL 报告状态为 `ACCEPTANCE_CANDIDATE`，未找到主 Agent 最终 PASS/合并确认。
- 实际核验：源码与表结构、TaskControl/Worker/Chat/Investigator 入口、一个真实本地业务 HTTP Probe、确定性 Web/TestClient 路由和 SQLite 状态；没有调用真实 Provider、MCP follow-up 或真实浏览器。
- 原始日志和 Trace 是本次测试直接产生；测试准备查询错误另行保留，未作为产品缺陷。

## 用户变化

冻结目标是让用户在可信诊断后，通过同一 Task 完成有来源的协议补查。当前只冻结标准并复现旧路径失败，尚未交付这项新行为。

## Agent 决策

当前基线没有实际执行补查的 Agent 决策：分类器不接受 `READONLY_FOLLOWUP`，Worker 只会将消息作为 `CHAT_READONLY` 送入轻量聊天路径。有效 RED 的 Provider 调用为 0，不能把失败归因成模型选择。

## 观察驱动

预期的不同观察及动作已冻结：上下文含有效引用时可以直接回答；缺少协议来源时可以查版本化 Knowledge；当前事实失效时可在绑定范围内重查；缺失或歧义时应澄清/报告部分完成。RED 前初始 Diagnosis 为 `CURRENT / DIAGNOSED / RECEIVER_PROCESSING_UNCONFIRMED`，补查请求实际得到 HTTP 502 `INVALID_MODEL_CLASSIFICATION`，没有独立只读调查 Run；真实 Trace 在 `TRACE.jsonl`。

## 新增约束

冻结规范要求保留 TaskBinding、当前授权、Task 累计预算、Domain Gate 与关键纠错边界，不新增固定工具顺序。RED 观察到控制版本仍为 0、关键纠错数为 0、ActionIntent/Ledger/Queue/Receipt 均为 0；尚未运行正式双向安全回归。

## 简化结果

候选方案复用现有 Messages、TaskRuns、TaskControl、Worker、`run_investigation`、只读 MCP 工具、D2 Task 级 Attempt 与 Context Provenance。拒绝将所有聊天升级为业务调查，也拒绝把每次补查都写成正式 S3 Diagnosis。是否需要单张窄结果表待实现前基于现有结果/来源模型验证；不建设通用 Goal 平台。

## 证据与停止线

- 冻结：`FROZEN_PLAN.md` 已提交。
- 定向 RED：4 次尝试中 3 次是有效复现，1 次是测试查询错误；所有原始日志及 Trace 均保留。
- 有效 RED：当前分类入口对明确补查返回 HTTP 502 / `INVALID_MODEL_CLASSIFICATION`，不能创建与来源消息关联的只读 Investigator Run。
- 当前 Diagnosis：`CURRENT`；TaskControl revision `0`；业务动作和交接副作用为 0。
- 全量 pytest、真实 Provider、MCP、浏览器连续旅程、TTL/S3/S1/S2 回归：`NOT_RUN`。
- 停止原因：任务卡要求先以 TTL-FIX-01 合入且主 Agent 确认的新基线实现 C1。现在只推送冻结与 RED 候选，等待该门通过；不实施业务代码、不合并 TTL、不进入 C2。

## 六维预检结论

- **用户变化：** 尚未实现；目标是诊断后可完成源引文可核验的只读补查。
- **Agent 决策：** 尚未证明；Provider 未调用。
- **观察驱动：** 合法文档请求当前被拒；成对观察行为已冻结，待实现后实测。
- **新增约束：** 不改变权限或业务写语义；当前负例无业务副作用，合法请求仍无法完成，属于产品失败。
- **简化结果：** 复用既有 Runtime 和 Domain；无新业务状态实现。
- **证据与停止线：** 冻结和有效 RED 已提供；正式实现、E2E 与全量回归未运行，等待 TTL main-agent gate。

**当前裁决：** `HOLD`（C1 实现门未开放；TTL 候选尚未获得主 Agent 最终合入确认）。当前 branch 只包含可独立评审的冻结与 RED。不得据此合并至 `main` 或启动 C2。
