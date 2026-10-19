# M3-01 失败与补充运行记录

所有原始输出保存在 `runs/`；本文件只解释，不删除或覆盖历史结果。初次失败与最终通过结果分别保留，不能把最终通过覆盖到早期目录。

| 运行 | 失败观察 | 后续处理 / 最终证据 |
|---|---|---|
| `focused-05` | 使用系统 Python 时缺少 `langchain_core`，退出码 2；这是运行环境选择失败。 | 改用仓库 `.venv`；`focused-06`、`focused-07`、`focused-08`、`focused-09` 使用 venv 通过。原日志保留。 |
| `full-01` | 3 项失败：两项既有 migration 断言仍把 schema 版本固定为 8（本阶段合法迁移至 v9）；M301 S2 context mock 未含 `content_digest`。 | 之后 `full-02`、`full-03` 为 195 passed。M301 上下文测试改为通过真实测试 HTTP/MCP helper 创建同 Run 403 证据，最终 `full-05` 为 197 passed。 |
| `paired-eval-01` | 结果写入器从错误模块导入 `get_task_run`，在 Provider/MCP 试次后保存结果时报 `ImportError`。 | 修正导入后运行器继续迭代；目录保存原始 stdout/stderr 与检查日志。 |
| `paired-eval-02` | 第二次结果恢复写入在恢复数据结构中遇到 `KeyError`，顶层 exit-code 记录为 1。 | 后续新鲜 8 对运行 `paired-eval-05` 完整写出 16 臂、Trace 与失败索引。 |
| `paired-eval-03` | 5 个 S2 ON Worker 在异步循环关闭后调用真实 Provider，报 `RuntimeError: Event loop is closed`。初次结果中 P03/P04 部分臂还与 Gold 不符。 | `paired-eval-04` 使用独立 Worker 重跑保留失败；最新 `paired-eval-05` 全部 Provider/MCP 调用成功。P03/P04 的 Gold mismatch 在最新运行仍存在，未隐藏。 |
| `paired-eval-04` | 隔离重跑修复了 Event Loop 错误，但 P03/P04 ON/OFF 仍都返回 `HANDOFF_READY`，不在冻结允许的 `DIAGNOSED` / `INCONCLUSIVE` 中。 | `paired-eval-05` 再次完整新鲜运行，结果相同；将 4/16 mismatch 原样作为最终发现，未改 Gold。 |
| `web-chain-02` | 浏览器流程的配置/预检未满足运行条件。 | 后续修正运行脚本并在 `web-chain-07` 完整跑通。 |
| `web-chain-03` | Web 源 Task 与候选经验界面的 session/来源关联失败。 | 在 `web-chain-07` 使用受信来源 Task 完成新鲜流程。 |
| `web-chain-04` | 浏览器中审核操作控件未按自动化预期显示。 | 保留截图与日志；后续 `web-chain-07` 真实 APPROVER 流程通过。 |
| `web-chain-05` | 浏览器自动化拿到过期 Task 查找结果，后续页面请求未使用正确绑定。 | 在 `web-chain-07` 重新建立并核验受信来源/目标 Task 关联。 |
| `web-chain-06` | 目标 B 的真实模型上下文未选入预期 S1 Memory，证明旧的按 `s2_mode` 选类型方法不能满足 Web Worker 的可信证据语义。 | `f0c56b7` 改为按当前同 Run MCP Evidence 决定 Memory 类型；`web-chain-07` 的 4 个 Context Provenance 选入 Task A Memory，撤销后新 Run 不再选入。 |
| `revoke-recovery-01` | 恢复验收的 `revoked_memory_absent_from_all_post_resume_contexts` 检查失败；原始 JSON 为 FAIL。 | 保留失败 run；后续 `revoke-recovery-02`、`revoke-recovery-03` PASS，显式比对恢复后新 Context 与撤销前审计 Provenance，确认新模型上下文为空且旧 Provenance 保留。 |
| `full-04` | 1 项旧 RED S2 上下文测试失败：mock 要求在没有当前 Run Evidence 的情况下选 403 Memory，与 M3-01 “当前证据决定适用类型”冻结规则相反；其余 196 项通过。 | 测试现在通过真实 helper 先产生同 Run 当前 403 与 Authz Evidence；定向 10/10、单项 1/1、最新全量 197/197 通过。原失败日志保留。 |

## 仍未通过冻结 Gold 的最终评测结果

`paired-eval-05` 的 P03 和 P04 ON/OFF 共 4 个臂都返回 `HANDOFF_READY`；Gold 仅允许 `DIAGNOSED` 或 `INCONCLUSIVE`。该结果是最终评测 mismatch，不是被忽略的“历史 bug”，也未用新的 Gold 或选择性分母覆盖。执行均无 Provider/MCP 错误；Domain 未写 REPAIR、DELIVER 或 Scope Grant。详见最终 `RESULTS.json` 和原始 16 臂 Trace。

## 首次 RED

冻结前写入的 RED 测试及早期失败证据位于 `runs/red/`。它们保留了实现前缺失/不兼容行为，不代表当前代码测试状态。不得重写、删除或将其与最终 PASS 混为一体。
