# TASKS.md — OpsPilot 相对 D1 的实施追踪

**主合同**：[`docs/baseline/v1.0-implementation-baseline.md`](docs/baseline/v1.0-implementation-baseline.md)
**设计放行**：2026-10-17 R5 · DESIGN APPROVED。**D1 实际开工：2026-10-17（北京时间）；实现已提交主 Agent 复核，D2 未开始。**

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

- [ ] Graph 只读调查循环；MCP 数据读取与类型化 ToolObservation/Evidence。
- [ ] Gate 四值 READY/NEED_MORE/INCONCLUSIVE/NO_ACTION；budget 持久 attempt 计数。
- [ ] 正例、禁用主体负例、缺/冲突证据走不同流程；真实模型 E01–E03 首版轨迹。

**停止线**：门禁漏放或跨作用域读失控，则禁止接写操作。

## D3 — 第一次真实审批 → 修复 → 业务验证 → 交付

- [ ] 不可变 Plan、Domain 权威计划资格和分项 REPAIR/DELIVER Approval。
- [ ] 两个动作首次发出前预登记唯一 ActionIntent，Domain 事务与 ActionLedger 保存可重放完整结果。
- [ ] REPAIR 事务 CAS，在线 Verifier 同调用方真实业务恢复，VerificationReceipt 持久化。
- [ ] 固定 ReportArtifact、DELIVER 意图、幂等工单交付及独立回执；拒绝分支没有未经授权业务写入。

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
| 2026-10-17 | D1（待主 Agent 复核） | `d1/implementation-2026-10-17` | WP-01–06 通过；pytest 8/8；真实模型、MCP、跨进程 checkpoint、S1 POS/DISABLED 均有日志 | D1 已停止扩展并提交复核；未开始 D2。报告见 `docs/evidence/d1/REPORT.md` |

**时间估计**：27–37 小时有效开发 + 3–5 小时排错是独立评审的初步规划；若每天只能保障 3 小时，改为约 10–14 天，不缩减恢复和安全门禁。
