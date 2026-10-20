# HF-01 运行索引

除冻结检查外，所有新执行结果均保存在本目录 `runs/` 下；命令、原始 stdout、stderr 与退出码按任务卡要求保留。带有 `source-manifest.json` 的运行绑定到实际提交及锁文件摘要。

| 运行 | 用途与结果 |
|---|---|
| `freeze-check-01/` | 基线 HEAD、origin/main、main 分支和原工作区状态；起始两 SHA 与任务卡一致。 |
| `freeze-check-final-01/` | 重新校验 115 个冻结文件 SHA-256，0 个不匹配；命令及 stdout/stderr 已保存。 |
| `revoke-race-01/` | 首次 C02 pytest 在扫描 Windows 共享临时目录时遇到 WinError 5；测试尚未启动。 |
| `revoke-race-02/` | C02 原始 RED：真实 attempt reservation 后撤销，捕获到 Provider payload 仍含已撤销 Memory。 |
| `revoke-race-03/` | Investigator C02 修复后定向 GREEN，1/1。 |
| `revoke-race-04/` | Chat Worker C02 修复后定向 GREEN，1/1。 |
| `revoke-race-05/` | 修正 C02 测试计数假设后，Investigator C02 GREEN，1/1。 |
| `focused-01/` | 早期选择性记忆回归，6/6。 |
| `focused-02/` | 早期聊天和来源回归，29/29。 |
| `focused-03/` | 29 passed / 1 failed；过严的 attempt 数量断言假设 Investigator 只发两次请求，实际有界路径保留 8 次预留。失败记录已在 `FAILURES.md`。 |
| `focused-04/` | C01、C02、C05、C06 等最终定向组，30/30。 |
| `c03-investigator-01/` | C03 首次 Investigator 路径测试失败：不正确地禁止撤销后的任何后续请求；详细原因在 `FAILURES.md`。 |
| `c03-investigator-02/` | C03 经真实 `run_investigation()` 调度的 GREEN，1/1。 |
| `c03-investigator-03/` | C03 最终 GREEN，1/1；原始 stdout 带确定性 Provider 顺序、请求 payload digest、记忆包含标记和调用 ID。 |
| `restart-recovery-01/` | C04 两个真实 Worker 进程、同一 Run 跨进程恢复、MCP stdio、HTTP 401；恢复前有 Memory、撤销并重启后 Context 无 Memory，10 项检查全真。Provider 为确定性测试实现。 |
| `web-final-01/` | 初次 Web 启动前退出：所选来源 DB 缺少 Task A 的 SUPPORT-owned Session link。原始日志保留。 |
| `web-final-02/` | 最终真实 Web A→B→撤销→追问旅程 PASS；Edge/Playwright、DeepSeek、MCP、8 张截图、源/目标 Domain 快照、325 条 Outbox、326 条 Session Event（含 318 个 Chat Chunk）及 Provider/MCP/HTTP 轨迹。 |
| `mcp-stdio-01/` | 新鲜 MCP `tools/list` 与 `tools/call`，4 个只读工具、4 个调用、真实 HTTP 401 Probe、跨租户拒绝；进程退出码 0。 |
| `m3-s1-s2-focused-01/` | M3/S1/S2 重点回归，47/47。 |
| `m3-s1-s2-focused-02/` | C03 加强后的 M3/S1/S2 回归，47/47。 |
| `m3-s1-s2-focused-final-01/` | 最终提交 `e9f7dd4` 上 M3/S1/S2 新鲜回归，47/47。 |
| `frontend-build-01/` | `npm run build`，Vue 类型检查及 Vite 构建退出码 0。 |
| `frontend-lint-01/` | `npm run lint` 退出码 0；只有 npm 提示可升级版本。 |
| `full-pytest-01/` | 新鲜完整 pytest，204/204。 |
| `full-pytest-final-01/` | C03 最终行为断言后的完整 pytest，204/204。 |
| `full-pytest-final-02/` | 最终测试提交 `e9f7dd4` 上完整 pytest，204/204；本次最终权威全量日志。 |

真实 Web 主轨迹：`web-final-02/RESULTS.json`、`web-final-02/screenshots/BROWSER-TRACE.json`、`SESSION-SSE-SNAPSHOT.json`、`SOURCE-DOMAIN-SNAPSHOT.json`、`TARGET-DOMAIN-SNAPSHOT.json`。关键 C02 RED 与最终 C03 次序分别在 `revoke-race-02/RESULTS.json` 和 `c03-investigator-03/stdout.txt`。
