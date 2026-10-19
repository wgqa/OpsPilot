# M3-01 原始运行索引

运行均在 `docs/evidence/vnext/m3-01/runs/` 下 append-only 保存。没有用后续成功覆盖此前失败；本轮冻结用例仍固定在 `GOLD.json` / `RUBRIC.json`。

| 目录 | 用途 / 结果 |
|---|---|
| `red/` | 冻结后、实现前的 RED 测试与输出。 |
| `focused-02/` | 早期 M3 定向验证；原始日志保留。 |
| `focused-05/` | 系统 Python 缺依赖，失败环境尝试。 |
| `focused-06/`, `focused-07/` | `.venv` 下的定向记忆/来源回归通过。 |
| `focused-08/` | 10 项 M301 memory/red 定向组通过。 |
| `focused-09/` | 最后调整后的 S2 当前 Evidence 上下文单测通过。 |
| `full-01/` | 初次完整回归，3 项失败，详见 `FAILURES.md`。 |
| `full-02/`, `full-03/` | 195/195 回归通过。 |
| `full-04/` | 196/197；一个缺可信 Evidence 的旧测试夹具失败，保留。 |
| `full-05/` | 最终 `.venv` 新鲜全量：197/197 通过。 |
| `frontend-01/` | 新鲜 `npm run build` 和 `npm run lint`，均通过。 |
| `source-s1/` | Task A 真实 S1 401→人工审批→REPAIR→HTTP 200→冻结报告→DELIVER 运行报告、Trace 和脱敏进程记录。 |
| `web-chain-02/`–`web-chain-06/` | 早期浏览器尝试；配置、session/source、控件、Task 关联、Memory 注入等失败，逐个保留。 |
| `web-chain-07/` | 最终真实 Edge、DeepSeek、MCP、APPROVER Web 旅程；8 张截图与脱敏浏览器 Trace。 |
| `paired-eval-01/`–`paired-eval-04/` | 配对评测结果写入器/事件循环错误和早期 Gold mismatch。 |
| `paired-eval-05/` | 最终全 8 对 / 16 臂真实评测；含 Results、Failures、Trace 与逐臂 Worker 日志。 |
| `paired-eval-02.exit-code.txt` | 第二次恢复写入失败的独立退出状态记录。 |
| `revoke-recovery-01/` | 首次撤销恢复断言失败。 |
| `revoke-recovery-02/`, `revoke-recovery-03/` | 新 Worker 跨进程恢复后不再加载撤销 Memory；`-03` 为最终 Smoke。 |

最终入口：[`REPORT.md`](REPORT.md)、[`RESULTS.json`](RESULTS.json)、[`TRACE.json`](TRACE.json)、[`FAILURES.md`](FAILURES.md)。浏览器图像位于 `web-chain-07/screenshots/`。
