# AR-05 集成候选差异与风险清单

**范围：** `main@60eee87bfe3cca522011316cb4cd2c0064ad291b` → 集成候选 `e011e7cbbbef3bbd28210120d4165169cf761183`。本文件只作差异与风险审查，不批准或执行 main 合并。

## 差异分类

候选包含 14 个提交、208 个变化路径（22,818 insertions / 84 deletions）。

| 类别 | 主要内容 | 判断 |
|---|---|---|
| AR-04C 实验冻结与证据 | `docs/evidence/ar-04c/{real-journey-01,prelive-hf-01,live-exec-01,f01-*}` 的案例、预算、真实 Provider Trace/Usage、失败、离线 RED/GREEN | 历史证据，必须保持不可变；`ACCEPTANCE_CANDIDATE / PARTIAL` 不能表述为通过。证据规模较大，不等同产品功能。 |
| AR-04C / 材料实验接线 | `opspilot/assistant.py` 与 `domain/assistant_experiment.py` 的实验 ID、一次性授权/Claim、模型与费用门限；`domain/d2.py` 的实验预算策略 | 这是精确实验身份的运行边界，不应被误当作普通用户通用预算或生产 Provider 授权。任何清除/迁移实验白名单的改动需单独审查；本轮未改。 |
| AR-04C 事实当前性修复 | `Loop.context()` 及 `domain.assistant.source_context_for_model()` 相关实现、`tests/test_ar04c_f01_context_currentness.py` | 代码在常规 Assistant 中也影响 Context 表达，应随来源/撤权回归审查；真实复验历史曾有 ON 条件 J4 当前性错误，不应据离线测试宣称真实模型问题已解决。 |
| AR-05 S1 接线与 D3 | `frontend/src/{App.vue,api.ts,s1-bridge.ts}`、`opspilot/{web/app.py,web/worker.py,domain/task_control.py,domain/d3.py}`、Investigator 与 D3/S1 测试 | 正式产品链路候选：同 Session 原始消息 → S1 Task/Plan → 独立 Approval → D3 Revalidation/CAS/Verification/Report/Delivery。需依赖本轮回归与后续浏览器验收；不得把任务创建、`RUN SUCCEEDED` 或计划状态说成业务恢复。 |
| AR-05 S2 接线 | `opspilot/domain/assistant.py` 等已有 Handoff Domain/API 的投影；`tests/test_ar05_s2_assistant_handoff_01.py` 与 `docs/evidence/ar-05/s2-assistant-handoff-01/*` | 纵向验证复用 M2-03 的本地队列、Receipt 和 Outbox；不授予 Scope、不恢复 403、不证明企业队列接收。 |
| 测试与历史资料 | 新增/更新的 `tests/test_ar05_*`, `test_d3_actions.py`, `test_m1_*` 及既有实验报告、日志 | 测试里有确定性模型与模拟业务数据，不是 Provider 效果证据。部分测试读取 `docs/evidence` 下的 Runner/冻结案例；执行前要检查路径假设与隔离状态。 |
| Web 前端 | `frontend/src/App.vue`、`api.ts`、`s1-bridge.ts` 与 `frontend/test/ar05-s1-bridge.test.ts` | 当前有 TS 类型检查、Vite build 与纯投影 Node 测试证据；仍需受授权的真实浏览器检查 DOM、刷新、角色切换与结果可见性。 |

## 运行态与凭据审查

- 差异文件名未发现 `.env`、SQLite、Checkpoint 或数据库运行文件。
- 对候选文档/代码/测试的本地扫描未发现常见 `sk-…`、OpenAI/DeepSeek Key 赋值模式；`Bearer` 与 `Authorization` 搜索命中的是代码路径、示例或测试数据，不能据字面匹配当作凭据泄露。
- AR-04C Trace 含真实模型的请求/响应、Completion ID、Usage 和模拟业务记录。它是公开候选中的实验原始数据；若仓库公开策略要求隐藏真实 Provider 内容/运行标识，需要主 Agent 决定是否移到私有证据归档。此轮没有改写或删除历史证据。
- 冻结 Gold、历史失败和实验 claim/ledger 不应随主线代码清理；本轮没有创建/消费任何 claim，也没有真实 Provider 请求。

## 已知发布前置

1. 完成本轮全量 pytest 与前端定向验证后，再由主 Agent 独立复核实际 SHA 和 Diff。全量结果只代表离线代码回归，不能替代 Web 体验验收。
2. 旧浏览器 STOP 仍有效：下一轮 Web 运行须由授权方另行明确解除；本轮的脚本/快照是准备材料，不是验收。
3. AR-04C `live-exec-01` 的公开报告记载 `PARTIAL`，Memory ON 的 G7 为 FAIL。只要主线包含这次实验结果，应保留失败，不要将实验授权逻辑误称已解决或获正式架构认可。
4. 不得因 `SCOPE_ESCALATED` 宣称 S2 已获授权；它表示本地队列 `PENDING_REVIEW`。S1 只有 Domain 的在线验证回执、冻结报告与独立 DELIVER 均成立才是 `DELIVERED`。

## 最终离线回归结论（2026-11-06）

- `origin/main` 仍为 `60eee87bfe3cca522011316cb4cd2c0064ad291b`；`origin/codex/ar05-s2-assistant-handoff-01` 仍为 `e011e7cbbbef3bbd28210120d4165169cf761183`，main 是候选祖先。
- 一次受控完整 pytest：741 collected，701 passed、40 failed，16m49s，exit 1。完整证据见 `logs/full-pytest.txt`。
- 失败分组：AR-04C 执行身份/共享 claim 路径 12；旧 D4 恢复夹具缺少当前 revalidation 证据 24；M1/M4 相同前置条件问题 3；废弃 `READONLY_FOLLOWUP` 历史 C1 RED 1。
- A1 shutdown 目标在单测和全量序列均通过；全量进程正常退出。没有复现停滞，也没有更改生产 Worker。
- A2 Runner 用真实临时 Git checkout 复现并修复测试夹具；生产分支/HEAD 检查未改变。
- 新 AR-05 S1/S2 正式离线旅程定向组分别 71/71 与 22/22 通过；真实 Provider、外部业务写入、浏览器均未运行。
- 前端 typecheck/build 和纯 Node 测试通过；未改动 E2E 文件仍有两项 ESLint 错误。

**最终建议：`HOLD`。** AR-04C 与 C1 的失败有清楚的隔离/历史适用性边界；但 24 项 D4 与 3 项 M1/M4 当前复核路径测试没有通过，且不能从这些 RED 判断 Crash/replay 在有效 RevalidationReceipt 下的行为。该证据缺口涉及动作与恢复边界，不应在主合并审查中略过。需由主 Agent 决定是否另行批准更新这些旧测试夹具并进行有界复核。本轮不改这些生产或测试行为，不合并 main。

浏览器继续 `NOT_RUN / EXISTING_BROWSER_STOP`。本节 supersedes 上述“等待全量 pytest”的早期结论。
