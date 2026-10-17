# TASKS.md — OpsPilot 相对 D1 的实施追踪

**主合同**：[`docs/baseline/v1.0-implementation-baseline.md`](docs/baseline/v1.0-implementation-baseline.md)
**设计放行**：2026-10-17 R5 · DESIGN APPROVED。**D1、D2 已通过主 Agent 验收；D2 PR #2 合入 `main@171f028`。D3 WP-01–05 与运行验收已完成，提交主 Agent 复核。**

> 本表只勾选已执行且有证据的项目。D1–D7 代表实际开发的相对顺序，**不是**把 2026-10-17—23 自动当作已经执行。评审阶段累计的时间不当作有效编码时间。

## D1 — 环境实证 + S1 无模型真实因果链

- [x] 锁定 Python、LangChain、LangGraph、MCP SDK、模型适配器和测试依赖；记录 lockfile 与不包含密钥的 `.env.example`。干净 CPython 3.14.0 环境安装与 `pip check` 通过。
- [x] 真实模型 Tool Call smoke：`deepseek-flash` 返回结构化调用参数，实际执行一次受控只读工具；记录 `tool_call_id`、Schema、Observation 和失败尝试。
- [x] 真 MCP stdio smoke：客户端 tools/list 发现服务器工具，tools/call 返回真实 Domain 数据；证据含 Schema、structured result、scope 错误处理。
- [x] LangGraph 持久 interrupt smoke：进程 A 退出后，进程 B 用原 thread_id 恢复；前置状态保留，越权 actor 在读取前被拒绝。
- [x] Demo Domain 和两种 fixture：S1-POS 真实 HTTP 401→fixture-only 配置切换→同主体、同路由 200/订单字段；S1-DISABLED 切换凭证后仍为 401。
- [x] 独立干净环境完整运行测试；提交 D1 报告、脱敏日志、失败尝试与 D2 建议。

**停止线**：三个技术 smoke 有任何一个失败，优先修复兼容/部署；S1 无模型真实因果链不通过，不叠加 Agent 执行逻辑。Fixture 修改必须限制为离线测试驱动专属，不暴露为无审批的 Agent 写工具。

## D2 — 只读动态调查与证据门禁

- [x] WP1：保留 `get_demo_service_info` 仅作 D1 回归；D2 MCP 只暴露按来源拆分的 `get_integration_config`、`get_principal_status`、`get_auth_policy`、`probe_endpoint`。持久 TaskBinding 绑定 actor/tenant/thread/service/integration，Domain 每次请求重验资源归属。
- [x] WP2：LangGraph `intake → prepare_context → investigate ↔ execute_read_tools → evidence_gate → report`；真实模型 Function Calling 只提出 MCP 工具调用，真实 stdio Client/Server 执行。记录 `tool_call_id → call_id/attempt_id → Observation → Evidence ID`。
- [x] WP3：Gate 的四值为 READY/NEED_MORE/NO_ACTION/INCONCLUSIVE；模型请求上限 8、MCP `tools/call` attempt 上限 6，预登记台账持久化在 Domain SQLite；跨进程预算重启测试通过。READY 只产生候选诊断，不执行写入。
- [x] WP4：真实模型 + MCP 的 POS 得 READY、DISABLED 得 NO_ACTION、策略证据源缺失时 401 得 INCONCLUSIVE；三种路径均保持 config_version=7。另验证跨租户调用拒绝、严格模型参数、恶意事实不能提升 Gate、重复无增量停止。
- [x] WP5：D1 回归 8/8 通过；D2 新增 pytest 9/9 通过；真实模型 POS/DISABLED/INSUFFICIENT 轨迹及一次保留的并行调用失败样本见 `docs/evidence/d2/`。
- [x] WP6：更新 README/TASKS/AGENTS，提供锁定依赖、实际命令、脱敏轨迹、已知问题与 `docs/evidence/d2/REPORT.md`；未实现 D3/D4、Memory、Skills 或 Multi-Agent。

**停止线**：门禁漏放或跨作用域读失控，则禁止接写操作。

## D3 — 第一次真实审批 → 修复 → 业务验证 → 交付

- [x] WP-01：不可变 Plan、Domain 权威计划资格和分项 REPAIR/DELIVER Approval；LangGraph interrupt 由独立进程审批并恢复，checkpoint 只存业务对象引用。
- [x] WP-02：两个动作首次发出前预登记唯一 ActionIntent；各自授权、幂等身份、ActionLedger 分别持久化，事务入口只接受 Intent ID。
- [x] WP-03：REPAIR 事务 CAS；同一 TaskBinding 的真实业务路由在线验证 HTTP 200 和订单字段；VerificationReceipt 持久化。
- [x] WP-04：固定 ReportArtifact；DELIVER 使用独立 Intent、许可、ledger 和 receipt，工单处置条目只追加一次。
- [x] WP-05：拒绝、DISABLED、过期版本和失败在线验证均阻断受限写入；重复 Probe 新 request/auth-event ID 不再误判冲突，稳定事实变化仍触发 INCONCLUSIVE。
- [x] 真实 D3 smoke、D1/D2 回归、全套 pytest 及 `docs/evidence/d3/REPORT.md` 已执行并记录；未扩展 D4、Memory、Skills 或 Multi-Agent。

**停止线**：无法显示真实 401→200 或受限操作不安全，停留 D3 修复，不添加 Memory/Skill。

## D4 — 丢响应/恢复/旧计划/越界安全门禁

- [ ] E04 拒绝/未审批：配置及工单受限写入均为零。
- [ ] E05：同资源版本下先取消/替换再执行会阻断；动作先执行后取消历史可读；重复批准不能重置已消费授权；旧 activate 不能复活旧计划。
- [ ] E06/E07：跨租户的任务、Evidence、Memory、工具、审批和注入安全。
- [ ] E08：持久中断恢复；重复/并发恢复不重复 REPAIR/DELIVER。
- [ ] E09：Intent 返回丢失、REPAIR COMMIT 后丢响应、Checkpoint 落后、报告冻结后退出、DELIVER 丢响应，均可恢复原身份/报告/回执；配置版本只递增一次，工单仅一条；交付不重跑修复。

**停止线**：任一已承诺的安全红线失败，不进入 D5；失败不能被平均成功率掩盖。

## D5 — Memory / Skill / Context

- [ ] 一种经来源核验、人工批准后 ACTIVE 的 Episodic Memory；过期/撤销/恢复后重新检索过滤。
- [ ] 一个版本化 `auth-incident-triage` Skill，按需加载、不新增工具执行权限。
- [ ] 实际 Context Provenance 记录来源 ID/版本/Prompt/Tool/Skill 信息。

## D6 — 离线评测与故障归因

- [ ] E01–E10 按合同分别运行；控制断言和真实模型表现单独统计。
- [ ] 保存错误类别、动作台账、证据关联、Token 与工具次数（若可获得）。
- [ ] 有条件时 Memory ON/OFF 探索性对照；不声称统计显著性。

## D7 — 独立复现、材料与面试准备

- [ ] 干净环境单命令重现主要业务和 checkpoint 中断。
- [ ] README 完成可运行命令、版本与边界；报告真实通过数/失败数；演示脚本和 STAR 条目。
- [ ] 提交给主 Agent 做完整实现审查；P0 未通过时诚实注明，优先修缺陷。

## 实际进度登记

| 日期（实际） | 阶段 | Commit / 版本 | 结果（测试分子/分母） | 阻断与下一步 |
|---|---|---|---|---|
| 2026-10-17 | D1（已验收） | `1a038be` / PR #1 merged | WP-01–06 通过；pytest 8/8；真实模型、MCP、跨进程 checkpoint、S1 POS/DISABLED 均有日志 | 主 Agent 已通过审查。报告见 `docs/evidence/d1/REPORT.md` |
| 2026-10-17 | D2（已验收并合入 main） | PR #2 / `171f028` | WP1–WP6 通过；D1 回归 8/8、D2 新增测试 9/9；真实模型/MCP 三场景有轨迹 | 主 Agent 已验收。报告见 `docs/evidence/d2/REPORT.md` |
| 2026-10-17 | D3（完成，待主 Agent 复核） | `main` / SHA 见交接 | 全量 pytest 29/29；D3 真实跨进程模型/MCP/HITL smoke 13 项检查通过；D2 POS/DISABLED/INSUFFICIENT 三场景回归通过 | 真实 401→200、订单字段、固定报告与单条工单交付见 `docs/evidence/d3/REPORT.md` |

**时间估计**：27–37 小时有效开发 + 3–5 小时排错是独立评审的初步规划；若每天只能保障 3 小时，改为约 10–14 天，不缩减恢复和安全门禁。
