# M3-02 / M3-03 失败记录

所有 `runs/` 下的原始日志与 JSON 失败记录保持原样。这里区分可直接复核的原始记录与只能从本轮工具输出重建的开发尝试。

| 运行 | 原始结果 | 后续处理 |
|---|---|---|
| `runs/impl-focused-21/pytest.log` | 1 failed / 7 passed；摘要投影估算 546，超过测试界限 512 | 调整投影长度，保留核心结构字段。 |
| `runs/impl-focused-22/pytest.log` | 1 failed / 7 passed；结构摘要缺少 `unresolved_items` | 补齐显式未完成项，避免把缺失字段默认为空事实。 |
| `runs/impl-focused-23/pytest.log` | 8 passed | 上述两个定向问题转绿。 |
| `runs/red-01/pytest.log` | 3 failed；Manifest 缺 `context_budget`，迁移仍为 v9，缺少 `semantic_memories` | 此为冻结后的独立 RED；实现 Context Manifest、v9→v11 迁移和 Semantic Domain 表。 |
| `runs/strategy-comparison-03/TRACE.json` | Rolling Summary 与 Hybrid 因 `CHAT_ATTEMPTS_EXHAUSTED` 未产出最终聊天回答 | 原样保留用量、失败和摘要重试；效用仍 `NOT_PROVEN`。 |
| `runs/web-01/long-chat-pre-batch-failures.json` | 长会话压缩链出现真实失败 | 后续批处理修复前后日志和结果均保留于 `runs/web-01/`。 |
| M3-03 初始聚焦运行 | 两项失败：凭证拒绝正则未覆盖 `credential_ref`；Schema 迁移测试缺少可信 TaskBinding | 由本轮工具输出记录，最初运行没有单独落盘为原始 pytest 文件；此表是重建说明，不冒充原始日志。之后修正验证数据和检查规则。 |
| M3-03 TaskBinding 补充运行 | 1 failed / 8 passed；测试 Task 缺少 `tenant-a` binding | 由工具输出重建，未保存独立原始日志；补齐同租户 TaskBinding 后通过。 |
| M3-03 Investigator 集成运行 | 1 failed；实现读取不存在的 `source_outcome` 字段 | 由工具输出重建，未保存独立原始日志；Semantic 选择改从持久行与绑定 scope 构造。 |
| `runs/m303-final/pytest-episodic.log` | 13 passed | 包含 Semantic 生命周期、Episodic 多候选/上限/排除理由、M3-01 回归；最新完整 pytest 另见对应日志。 |
| `runs/m303-final/pytest-full-episodic.log` | 222 passed / 1 failed；`test_m301_red_s2_investigator_context_can_select_active_case_memory` 仍替换 `investigator.list_applicable_memories`，而实现已改用 `select_applicable_memories` | 保留原始失败日志；将测试替身切换到新选择 API，并兼容缺省 applicability metadata。 |
| `runs/m303-final/pytest-m301-red-compat.log` 初次尝试 | 测试替身更新后，合成旧记忆记录没有 `applicability_reason`，导致 Provenance 构造 `KeyError` | 初次完整日志未保留独立副本；从工具输出重建错误原因，修复为 `.get()` 后以同名最终日志复跑成功。重建说明不冒充原始日志。 |
| `runs/m303-final/pytest-full-final.log` | 223 passed, 0 failed | 全量复跑最终通过，退出码见 `pytest-full-final.exit-code.txt`。 |
| 原始本地 Web Task B：`task-8f2720b8-72b4-4e67-9fad-bae863de3c1d` / `run-8e65e032-5e99-4c24-96ea-867df3912a18` | 3 次 Worker 重试后 `WORKER_RETRY_EXHAUSTED`；0 Provider / 0 MCP attempt | 原 Domain 数据仍保留；generic Worker error 没有提供根因。结构化失败记录见 `runs/m303-final/FAILURE-original-web-task-b.json`，原因未推断。 |
| 第二次原数据库 Web Task B：`task-dfe71a7a-caea-4c8c-a0b4-d2dcd3d8d124` / `run-9e9834db-ca90-431c-8e6a-c5ca0948eb56` | 同样 3 次 Worker 重试后 `WORKER_RETRY_EXHAUSTED`；0 Provider / 0 MCP attempt | 作为失败保留在同一结构化记录中；没有将其改写为成功。 |
| `runs/m303-final/debug-run-clone.log` | 隔离克隆上的直接 Worker 调试调用返回 `WAITING_APPROVAL`，5 Provider / 4 MCP | 仅用于排查当前代码路径，不算 Web 验收；后续真实浏览器 Task B 使用独立 Run 并单独记录在 `TRACE-task-b.json`。 |
| 临时隔离 API 的 APPROVER 登录 | `POST /api/auth/login` 返回 401；本地克隆进程未配置 `OPSPILOT_WEB_APPROVER_PASSWORD` | 从本轮进程输出观察到 3 次 401；没有读取或保存口令。切回原 API 服务后，`approver-a` 登录和 Web 撤销成功。此项为测试环境配置失败，不是产品回归。 |
| 撤销后 support-a 登录 | 页面仍停在登录表单，显示通用 401 文案“登录状态已过期，请重新登录” | 前端将过期会话与凭证拒绝映射到同一文案；未能判断确切原因。未重复提交、读取口令或更改认证配置，后续模型调用与恢复测试待有效 support-a 会话。 |

## 本次补充尝试（原始失败仍保留）

| 运行 | 结果与处理 |
|---|---|
| `continuation-01/summary-priority-red.log` | 最初测试数据没有触发压缩，断言 compression 非空失败；这是测试设置失败，未当成目标缺陷复现。 |
| `continuation-01/summary-priority-red-02.log` | 已有有效摘要被较长近期回答挤出，`summary_refs=[]`；最小调整可选块优先级。 |
| `continuation-01/input-anchor-red.log` | 21 轮后原始任务输入丢失，正式纠错不在 Chat 查询范围；增加同范围原文锚点与来源校验。 |
| `continuation-01/input-anchor-green.log` | 11/11 专项通过；最终完整回归 `pytest-full-final.log` 为225/225。 |
| `continuation-01/process-events.jsonl` | 最初 stdin 控制器因空行 JSON 失败退出（没有独立原始 stdout 文件，此项为工具输出重建说明）；改为本地命令文件。一个崩溃监控误用不带 `::run_id` 的 thread key，未杀死进程，超时留存；该成功调查不算恢复测试。 |
| `continuation-01/crash-trigger.json` | 纠正监控关联后，真实 kill/restart，保留同 Run、实际 Checkpoint、预留数；中断 Provider 的实际 usage 未知，不能计零。 |
| `long-recovery-01/TRACE.json` Run `run-c616d2f0-83d5-4be6-9916-9bbd369187a5` | 真实崩溃发生在第一摘要提交后；下一预留尝试被标 INTERRUPTED。恢复后第三次摘要成功，但总预算3用尽，Run FAILED/CHAT_ATTEMPTS_EXHAUSTED。没有最终回答，不算恢复完成业务回答。 |
| `long-recovery-01/TRACE.json` Run `run-b7ad6557-588e-4c4f-9eef-fc388b02c6ed` | 新 Run 在原 Session 继续，真实一次摘要+一次回答成功；与上一个失败分别计数。未提升1400输入预算。 |
| `continuation-01/LONG_CHAT_CASES.json` | 另一个20轮补充计划只实际提交第1轮；浏览器工具等待输入框超时，但对应真实模型 Run 最终成功（2901 Token）。没有重发，没有把未执行19轮计入验收；长对话证明使用原26轮的真实延续。 |
| `continuation-01/login-401-red.dom.txt` / `login-401-green.dom.txt` | 测试副本故意错误口令验证401文案；正确测试口令可登录。不改用户口令，原服务继续运行。 |
| `export_continuation_trace.py` 首次导出 | 临时导出排序误用不存在的 event_sequence，报SQLite错误（仅工具输出，无独立原始文件）；改按created_at/event_id，不影响业务数据。 |

当前累计真实长会话28个Chat Run：22成功、6失败；原对照的Rolling/Hybrid失败、原库Task B失败以及本次故障注入失败均不抹除。Semantic Web撤销、新请求和恢复已补证；严格的新鲜Episodic业务案例Web整链尚未在本阶段重录，整体仍为PARTIAL，交主Agent审查。
