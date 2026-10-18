# M1-06 证据索引

所有路径相对仓库根目录。完整逐项结论请先看 [REPORT.md](REPORT.md) 与 [RESULTS.json](RESULTS.json)。运行时间、代码树 provenance、锁文件哈希、Run/Plan/Ledger/Provider ID 和真实业务回执在 [RUN_MANIFEST.json](RUN_MANIFEST.json)。最终原始文件 SHA-256 清单见 [RAW_EVIDENCE_SHA256.json](RAW_EVIDENCE_SHA256.json)。

## 冻结与变更

- `docs/evidence/vnext/m1-06/ACCEPTANCE_PLAN.md`：先于本轮测试提交的测试输入、Gold 和逐项判断标准。
- `docs/evidence/vnext/m1-06/PLAN_AMENDMENTS.md`：首次浏览器失败后、E2E 源码修改前提交的 selector 修订说明。
- `docs/evidence/vnext/m1-06/FAILURES.md`：首次失败、修正、复跑及诊断辅助错误的时间线和失败分母。
- `frontend/e2e/m1-04-browser.mjs`：本轮唯一代码改动，角色页面 ready selector。修订前后提交见 Git log。

## 全量和定向测试日志

目录：`docs/evidence/vnext/m1-06/runs/20261018T115200Z/logs/`

- `environment.txt`：最初 HEAD/origin、Python/Node/npm 和两份锁文件哈希；最终软件包版本在 RUN_MANIFEST 中。
- `pytest-full.txt`：初次新鲜回归 116/116；它早于 selector 修正。
- `pytest-directed-critical.txt`：修正后定向 APR04、N1-09/10/11、来源撤销、证据版本失效、worker 恢复、N2-01、未知动作结果，9/9。
- `pytest-full-final-d74517d.txt`：修复后、最终代码 commit 上新鲜全量 116/116。
- `frontend-typecheck-final-d74517d.txt`、`frontend-lint-final-d74517d.txt`、`frontend-build-final-d74517d.txt`：最终 commit 上 Vue 检查。
- `pip-check-final-d74517d.txt`、`compileall-final-d74517d.txt`、`node-check-m1-04-final-d74517d.txt`、`node-check-m1-05-final-d74517d.txt`：最终依赖、Python 编译与 E2E 语法检查。
- 未加 `final` 的同名文件是修复前检查日志；不得用它们替换最终日志。
- `secret-scan-final.json`：完整证据材料生成后的脱敏模式扫描汇总，不含命中原文或密钥值。
- `sse-projection-audit.json`：对本轮 M1-05 SQLite 以只读模式比较 `session_events` 与 Domain Outbox；明确记录 task event_seq 中的 846 间隙及全部 Outbox 事实均已有投影。

## M1-04：真实多轮聊天与自然语言调查

**首次失败 Attempt 01：** `docs/evidence/vnext/m1-06/runs/20261018T115200Z/m1-04/runs/20261018T115410Z/`

- `RESULTS.json` 是浏览器入口原始 `FAIL`；不要覆盖。
- `logs/browser-full.attempt-01.txt`、`browser-full.txt`、`api-server-first-process.log`、`vite-server.log`、`unlisted-origin-validation.log` 是入口及进程日志。
- `screenshots/` 保留失败前已完成的会话、聊天、NL-A/B、只读边界页面。
- `FAILURE_DOMAIN_SNAPSHOT.json` 是通过只读查询导出的脱敏四 Task Snapshot；不含正文、Cookie、凭据或 Provider key。

**修复后 Attempt 02：** `docs/evidence/vnext/m1-06/runs/20261018T115200Z/m1-04-rerun-01/runs/20261018T115753Z/`

- `RESULTS.json`：8 项浏览器检查为 true，NL-05 留给定向 pytest；含真实 Context、Task、模型、MCP、Evidence、Run、计划和权限断言。
- `logs/`：原始 API、Vite、Edge 浏览器、Origin 和恢复记录。
- `screenshots/`：真实 Edge 的聊天、NL-A/B/C、403 停止、SSE/刷新/恢复和工作台状态。
- `m1-04-rerun-01.txt`：重跑入口 stdout/exit 状态。

## M1-05：独立人工审批与真实 S1 交付

`docs/evidence/vnext/m1-06/runs/20261018T115200Z/m1-05/runs/20261018T115934Z/`

- `RESULTS.json`：完整 Edge 交互结果以及 Domain Projection；包括输入、5 个 Provider response、4 个 MCP Observation、Evidence、Gate、不可变 Plan、Approval、Run/Checkpoint Resume link、ActionLedger、实际 HTTP 验证、Frozen Report、DeliveryRecord、TicketEntry 和 Outbox 事件。
- `logs/api-investigation.log`：调查进程；`api-approval-crash.log` 和 `api-repair-crash.log`：两个 commit 后响应丢失的进程故障点；`api-recovery-process.log`：恢复进程。
- `logs/edge-approval-response-loss.txt`、`edge-delivered-outcome.txt`、`edge-investigation.txt`、`edge-readonly-chat.txt` 和各自的 `*.attempt-01.txt`：原始 Edge/API 结果，包含 502/恢复/最终投影；REPAIR 响应丢失原始进程记录在 `api-repair-crash.log`。
- `screenshots/`：双角色计划复核、审批等待、响应丢失、只读聊天和最终交付截图。
- M1-05 `APR-04` 值明确写为 `separate APR04 program test`，对应本轮定向 pytest，不是 Edge smoke。

## 历史安全与恢复回归

- 新鲜 9 项定向运行：`runs/20261018T115200Z/logs/pytest-directed-critical.txt`。
- 新鲜完整 M1-01 至 M1-05 与既有 D1–D7 回归：`runs/20261018T115200Z/logs/pytest-full-final-d74517d.txt`。
- D6 E10 的首次失败、9 PASS + E10 PARTIAL 与固定通用 Memory 局限：`docs/evidence/d6/REPORT.md` 及 `docs/evidence/d6/e10/`。
- D7 首次 E01 与 61/64：`docs/evidence/d7/REPORT.md`、`docs/evidence/d7/preparation-attempt-01.txt`、`docs/evidence/d7/attempt-02/` 和首次 `e01/`。

## 诊断快照生成记录

- `runs/20261018T115200Z/logs/evidence-snapshot-query-error-note.txt` 明确标注第一条 SQLite 查询错误未在发生时重定向保存，是事后说明。
- `evidence-snapshot-schema-check.txt` 保留 schema 输出。
- `evidence-snapshot-extraction-attempt-02.txt` 保留修正读取成功摘要。
- 成功结果为首个 M1-04 Run 目录内的 `FAILURE_DOMAIN_SNAPSHOT.json`。

## 冻结计划与可重复执行

- 冻结 Gold 和所有判定标准：[ACCEPTANCE_PLAN.md](ACCEPTANCE_PLAN.md)。
- 本地完整执行命令：[RUNBOOK.md](RUNBOOK.md)。
- 运行 SHA、执行树差异、软件版本、PID、token 与事件范围：[RUN_MANIFEST.json](RUN_MANIFEST.json)。
