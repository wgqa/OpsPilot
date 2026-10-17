# D5 首次真实 smoke 失败记录

- 首次命令：`.venv\Scripts\python.exe -m opspilot.cli d5-smoke --db .runtime\d5-domain.sqlite3 --checkpoint-db .runtime\d5-checkpoints.sqlite3 --evidence-dir docs\evidence\d5`
- 首次结果：`FAIL`，19 项断言中 18 项通过；仅 `disabled_task_real_401_and_no_action` 未通过。
- 复核真实 SQLite Evidence 与 Gate 后确认：主体事实为 `DISABLED`，业务 Probe 为 HTTP `401`，Evidence Gate 已正确返回 `NO_ACTION / PRINCIPAL_DISABLED`。失败发生在 smoke 的脱敏报告投影漏掉通用字段 `status`，不是 Investigator、MCP 或 Gate 行为失败。
- 修复：在证据投影允许字段中加入 `status`；没有改写 Gate、Memory 检索或授权路径。第二次完整真实 smoke 的全部断言通过，见 `REPORT.md` 与 `TRACE.json`。
