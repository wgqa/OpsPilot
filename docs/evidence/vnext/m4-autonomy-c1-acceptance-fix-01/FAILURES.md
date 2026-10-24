# C1-REV1-ACCEPTANCE-FIX-01 失败记录

所有新运行均使用独立 `pytest --basetemp`，本文件只追加本修复切片的运行记录。REV1 原始失败、E2E-02/E2E-03 和 C1 冻结 RED 保留在原证据目录，未修改。

| 运行 | 命令/用例 | 结果 | 分类与说明 |
|---|---|---:|---|
| `runs/red-01.log` | 系统 `python -m pytest ... tests/test_m4_autonomy_c1_acceptance_fix_01.py` | Exit 2 | 环境准备失败：系统解释器 `D:\python\python.exe` 未安装 `langchain_core`，在收集阶段退出。不是产品 RED；后续改用仓库锁定依赖的 `.venv`。 |
| `runs/red-02.log` | `.venv\Scripts\python.exe -m pytest -q -s --basetemp (Join-Path $env:TEMP 'opspilot-c1-fix-red-02') tests/test_m4_autonomy_c1_acceptance_fix_01.py` | 1 failed, 1 passed | 有效 RED。预算耗尽用例返回普通 `report_ref` 而无只读结果；直接使用当前 Knowledge 的解释正例通过。 |
| `runs/red-03.log` | `.venv\Scripts\python.exe -m pytest -q -s --basetemp (Join-Path $env:TEMP 'opspilot-c1-fix-red-03') tests/test_m4_autonomy_c1_acceptance_fix_01.py` | 1 failed, 1 passed | 有效 RED 复跑，业务观察与 red-02 一致。Windows 捕获输出在失败 traceback 中重复匹配 Trace 前缀，导致第一次提取器把源码行当作第三条 Trace；未把这条畸形提取结果保留为正式 Trace。 |
| `runs/red-04.log` | `.venv\Scripts\python.exe -m pytest -q -s --basetemp (Join-Path $env:TEMP 'opspilot-c1-fix-red-04') tests/test_m4_autonomy_c1_acceptance_fix_01.py` | 1 failed, 1 passed | 有效 RED，作为本轮结构化 Trace 来源。原有 Diagnosis 数量由 1 变 2，Task 从 `WAITING_HANDOFF` 变成 `INCONCLUSIVE`，Domain Outbox 从 6 变 7；只读结果仍未完成。TaskControl revision 保持 0，Approval/Plan/ActionIntent/Ledger/Queue/Receipt 均未新增。既有 Diagnosis 正文/digest 保持不变。 |
| `runs/full-pytest-01.log` | `.venv\Scripts\python.exe -m pytest -q -s --basetemp (Join-Path $env:TEMP 'opspilot-c1-fix-full-01') --ignore=tests/test_m4_autonomy_c1_red.py` | 324 passed, 1 failed | 环境配置缺失：M2-02-HF-01 恢复测试的子进程未继承主工作区模型配置，未进入故障注入阶段，返回 `Missing required model configuration`。修复运行环境后单独复跑和完整套件复跑均通过；该原始日志保留。 |

## GREEN 与回归运行

| 运行 | 用例 | 结果 | 说明 |
|---|---|---:|---|
| `runs/green-01.log` | 本文件 FIX-01/02 | 2 passed | 预算 8/8 时产出 `PARTIAL` 和 `FOLLOWUP_BUDGET_OR_PROVIDER_EXHAUSTED`，Diagnosis/Task/Outbox 不变；当前 Knowledge 足够时直接获得有来源 `ANSWERED`，只用 1 次模型替身调用且未发起 MCP。 |
| `runs/green-mcp-01.log` | 既有真实 MCP 只读跟进集成测试 | 1 passed | 实际 Investigator MCP client/server 查询 `search_callback_knowledge`，持久同 Run Observation 与 Knowledge 来源；模型为确定性 ScriptedModel，不是外部 Provider。DB 提取轨迹保存在 `TRACE.jsonl`。 |
| `runs/targeted-regression-01.log` | S3、HF-01/HF-02、TaskControl、TTL、C1 跟进 | 92 passed | 完整定向安全回归通过。 |
| `runs/targeted-env-01.log` | 首次全量环境失败的 M2-02-HF-01 用例 | 1 passed | 父测试进程只从 `D:\学习\agent新项目\.env` 读取模型配置并注入子进程环境；不打印、不保存密钥。worker 测试本身替换为 NoToolModel。 |
| `runs/full-pytest-02.log` | 全量 pytest，排除冻结历史预实现 RED | 325 passed | `.venv` 下完整回归 284.68 秒。唯一排除项仍是被冻结为“旧实现预期失败”的 `tests/test_m4_autonomy_c1_red.py`，文件与历史断言未修改。 |

## 保留的 C1 历史失败

E2E-02 和 E2E-03 的真实 Web/Provider 失败及 E2E-03 的 `ANSWERED` 产品质量样例继续保存在 `docs/evidence/vnext/m4-autonomy-c1/runs/rev1/web-e2e-02/`、`web-e2e-03/` 与 REV1 报告。当前 FOLLOWUP_PROMPT 已明确要求来源缺失、不回答目标或有实质信息缺口时使用 `PARTIAL`；结果解析器要求 `RESULT: ANSWERED|PARTIAL`，缺失标签时 fail-closed 到 `PARTIAL`，但不会以封闭关键词白名单判断语义充分性。本修复不改动这套规则或重写该历史样例。

定向回归复用了原 C1 路由 RED 测试；它会向历史 `runs/rev1/behavior-red-trace.jsonl` 追加当前运行行。三条新观察已复制到本目录 `TRACE.jsonl` 并标记为 GREEN 回归，历史文件已恢复到开工时的提交内容，最终保持无 Diff。

## 根因确认

`S3Nodes.report()` 的当前条件将 `readonly_followup` 与剩余 MODEL 预算合并。Task 累计 MODEL attempts 为 8/8 时该条件为假，函数随后执行普通 `persist_s3_diagnosis()`。有效 RED 记录的新 Diagnosis 为 `s3-diagnosis-e43685c1-9868-421c-8ae0-82bdaca5a381`；旧 Diagnosis `s3-diagnosis-349fca50-9fd8-45a4-9f71-3434b705f601` 未改写。

预算耗尽负例不触发 Provider：测试替身在任何调用时立即失败，执行后没有触发该失败。预算充足直接解释正例使用确定性模型替身，并核验版本化 Knowledge `receiver-ack-contract-v2` 的来源。真实 MCP 合法路径沿用并新鲜复跑已存在的 `test_follow_up_investigation_uses_real_mcp_and_persists_a_readonly_result`；该回归不是本次真实 Provider 证明。
