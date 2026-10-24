# C1-REV1-ACCEPTANCE-FIX-01 失败记录

所有新运行均使用独立 `pytest --basetemp`，本文件只追加本修复切片的运行记录。REV1 原始失败、E2E-02/E2E-03 和 C1 冻结 RED 保留在原证据目录，未修改。

| 运行 | 命令/用例 | 结果 | 分类与说明 |
|---|---|---:|---|
| `runs/red-01.log` | 系统 `python -m pytest ... tests/test_m4_autonomy_c1_acceptance_fix_01.py` | Exit 2 | 环境准备失败：系统解释器 `D:\python\python.exe` 未安装 `langchain_core`，在收集阶段退出。不是产品 RED；后续改用仓库锁定依赖的 `.venv`。 |
| `runs/red-02.log` | `.venv\Scripts\python.exe -m pytest -q -s --basetemp (Join-Path $env:TEMP 'opspilot-c1-fix-red-02') tests/test_m4_autonomy_c1_acceptance_fix_01.py` | 1 failed, 1 passed | 有效 RED。预算耗尽用例返回普通 `report_ref` 而无只读结果；直接使用当前 Knowledge 的解释正例通过。 |
| `runs/red-03.log` | `.venv\Scripts\python.exe -m pytest -q -s --basetemp (Join-Path $env:TEMP 'opspilot-c1-fix-red-03') tests/test_m4_autonomy_c1_acceptance_fix_01.py` | 1 failed, 1 passed | 有效 RED 复跑，业务观察与 red-02 一致。Windows 捕获输出在失败 traceback 中重复匹配 Trace 前缀，导致第一次提取器把源码行当作第三条 Trace；未把这条畸形提取结果保留为正式 Trace。 |
| `runs/red-04.log` | `.venv\Scripts\python.exe -m pytest -q -s --basetemp (Join-Path $env:TEMP 'opspilot-c1-fix-red-04') tests/test_m4_autonomy_c1_acceptance_fix_01.py` | 1 failed, 1 passed | 有效 RED，作为本轮结构化 Trace 来源。原有 Diagnosis 数量由 1 变 2，Task 从 `WAITING_HANDOFF` 变成 `INCONCLUSIVE`，Domain Outbox 从 6 变 7；只读结果仍未完成。TaskControl revision 保持 0，Approval/Plan/ActionIntent/Ledger/Queue/Receipt 均未新增。既有 Diagnosis 正文/digest 保持不变。 |

## 根因确认

`S3Nodes.report()` 的当前条件将 `readonly_followup` 与剩余 MODEL 预算合并。Task 累计 MODEL attempts 为 8/8 时该条件为假，函数随后执行普通 `persist_s3_diagnosis()`。有效 RED 记录的新 Diagnosis 为 `s3-diagnosis-e43685c1-9868-421c-8ae0-82bdaca5a381`；旧 Diagnosis `s3-diagnosis-349fca50-9fd8-45a4-9f71-3434b705f601` 未改写。

预算耗尽负例不触发 Provider：测试替身在任何调用时立即失败，执行后没有触发该失败。预算充足直接解释正例使用确定性模型替身，并核验版本化 Knowledge `receiver-ack-contract-v2` 的来源。真实 MCP 合法路径沿用并新鲜复跑已存在的 `test_follow_up_investigation_uses_real_mcp_and_persists_a_readonly_result`；该回归不是本次真实 Provider 证明。

