# M1-06 失败与修复记录

## 本轮真实浏览器失败：M1-04 approver 页面选择器过时

- **Attempt 01：** `runs/20261018T115200Z/m1-04/runs/20261018T115410Z`，命令 exit 1，原结果保留为 `FAIL`。
- **原始记录：** `runs/20261018T115200Z/logs/m1-04-runner.txt`、失败目录中的 `logs/browser-full.attempt-01.txt`、`logs/api-server-first-process.log`、`logs/vite-server.log`、全部 screenshots、`RESULTS.json` 与 `FAILURE_DOMAIN_SNAPSHOT.json`。
- **触发事实：** API 日志显示 `approver-a` 登录 HTTP 200，`GET /api/approvals/pending` HTTP 200；Playwright helper 随后等待 `.rail-footer` 超时。当前 APPROVER 页面用 `.approval-center`，而 `.rail-footer` 位于 SUPPORT workspace。实际身份认证和待办读取均成功，失败来自 M1-04 浏览器脚本继承了旧 UI 选择器。
- **失败分母：** 本轮真实 Edge/Provider 入口共 3 次：M1-04 首次 FAIL、修正后 M1-04 PASS、M1-05 PASS。首次失败仍保留，不被成功重跑覆盖。
- **首次尝试已完成的工作：** 四个 Task，状态 `WAITING_APPROVAL`×3、`WAITING_INPUT`×1；21 个 Provider 响应均成功（16 Investigator + 5 CHAT_READONLY），12 次 MCP tools/call；实际 Provider Token 合计 49,293。四个 Task 的 Approval、ActionIntent、ActionLedger、Verification、ReportArtifact、DeliveryRecord 写入均为 0。脱敏 Domain 快照保留 Prompt digest、Evidence、Attempt、Run 和零副作用计数，不保留消息正文、Cookie 或凭据值。
- **最小处理：** 计划修订 `PLAN_AMENDMENTS.md` 在修改前单独提交推送；只修改 `frontend/e2e/m1-04-browser.mjs::login()` 的页面就绪 selector（approver 等待 `.approval-center`，support 继续等待 `.rail-footer`）。不改产品 UI/API、权限、输入、Gold 或业务逻辑。修正提交 `d74517d925cebb6e99c38dbbc01919c8064a44ed`。
- **fresh 重跑：** `runs/20261018T115200Z/m1-04-rerun-01/runs/20261018T115753Z/RESULTS.json` 为 `BROWSER_PASS_FULL_PYTEST_PENDING`；浏览器检查中 8 项为 `true`，NL-05 由独立新鲜 N1-09/10/11 pytest 覆盖。Edge 完成跨租户 404、Approver 只读 200、未列出 Origin 403、真实 Provider/MCP 调查与 API 重启。修复前失败文件未改写。

## 非产品诊断工具错误

为失败 attempt 生成只读 Domain 快照时，第一条 SQLite 查询误以为 `task_bindings` 有 `session_id` 列，返回 `OperationalError: no such column: session_id`。未修改数据库。错误输出未在发生时重定向保存；该事实在 `runs/20261018T115200Z/logs/evidence-snapshot-query-error-note.txt` 中被明确标注为事后记录，而未伪装成原始 stdout。随后 schema 检查在 `evidence-snapshot-schema-check.txt`，按真实 `task_runs.session_id` join 的成功提取摘要在 `evidence-snapshot-extraction-attempt-02.txt`，脱敏结果为 `runs/20261018T115200Z/m1-04/runs/20261018T115410Z/FAILURE_DOMAIN_SNAPSHOT.json`。这不是应用测试，不计入产品失败分母。

## 仍需保留的历史失败与局限

- D6 E10 的首次真实模型 smoke 失败仍留在 [`docs/evidence/d6/e10/ATTEMPT-01.json`](../../d6/e10/ATTEMPT-01.json) 与相邻文件；D6 整体仍为 **9 PASS + E10 PARTIAL**。后续隔离复跑不抹除它，固定通用 Memory 的内容限制也未解决。
- D7 首次干净环境 E01 失败、首次全量 pytest `61/64` 及 CRLF 准备失败仍保存在 [`docs/evidence/d7/REPORT.md`](../../d7/REPORT.md)、`preparation-attempt-01.txt`、`attempt-02/` 与首次 `e01/` 目录。D7 后续修正记录没有重写首次结果。
- M1-06 没有发现应用业务/授权阻断缺陷，因此未改 M1 产品代码。M1 仍等待主 Agent 独立验收；本报告不签发 M1 PASS，不启动 M2。
