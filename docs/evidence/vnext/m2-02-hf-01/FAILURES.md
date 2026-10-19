# HF-01 失败与补充运行记录

原始运行均保存在 `runs/`，本页只解释其目的与后续处理，不覆盖原日志。

| 阶段 | 失败/观察 | 处理与后续结果 |
|---|---|---|
| 初次定向运行 | 系统 Python 缺项目依赖；随后某轮 pytest 临时目录扫描得到 Windows `PermissionError`，8 个测试是 collection/runtime error，不是断言通过 | 保留 `green-dev-11`、`green-dev-17-targeted-pytest.txt`；后续使用项目 venv 和独立 `.runtime` basetemp |
| 初版 HF RED | G6 同义/混合/否定目标边界未满足；stale Evidence 可继续触发无增量 Gate；H 归一化线索仅留在 Trace 未影响策略 | 原始 RED 在 `development-logs/red-*`；后续 HF 定向测试在 `green-dev-18` 达到 15 passed |
| 全量回归 | `b102454` 有 168 passed、1 failed：旧 `_s2_model_tools_for_evidence` 测试夹具用静态时间，Evidence 已超 TTL | 保留 `full-pytest-b102454.txt`；把夹具时间改为新鲜时间，不延长业务预算；`4ad7465` 全量 169 passed |
| Release Trace 提取 | 一次 Release 提前停止，SQL 读取 `d2_attempts.created_at`，而 Domain 实际列为 `reserved_at`；R 案例已跑，后续组标记未运行 | 保留 `release-4ad7465/` 的错误堆栈与 NOT_RUN；改成 `reserved_at AS created_at` 后定向测试通过，再独立运行固定 48 条 Release |
| 第一次 48 条 Release 评分 | R 与 A 的 G8 否定回答被评分器当作“已修复”肯定陈述，各有 1 个假 FAIL。原文使用“不能认定/确认”“不足以证明”等否定表达 | 原始 Release 结果与错误计分保存在 `release-ee94eac/RESULTS.json`；多次 scorer RED、修正和定向测试均留档。最终在 `20624cf` 对同一 48 条 Trace 重评，不重跑 Provider/MCP，R/A 各 16 PASS |
| H holdout | 12 条仍在正确处理评分失败、2 条 PARTIAL；H-G8 也未达到 Gold 处理要求。轨迹显示高不确定性时策略真实地澄清，安全/有界分数仍通过 | 保留所有 H 失败和完整模型/MCP Trace；没有改 Gold、分母、预算或隐藏低效用结果 |
| 浏览器验收脚本 | 多次首轮检查失败。`browser-e2e-final-6299ff2` 的断言将“尚未证明成功”的安全解释误判为未说明状态；更早 `browser-e2e-01..04` 记录真实脚本/交互失败 | 保留所有失败目录。按语义子句修复验收脚本后，Microsoft Edge 完整旅程在 `browser-e2e-final-752173a` 实际 PASS |

## 10,003 Gate 记录的解释边界

旧 G4 记录显示 10,003 次 Gate 结果都是 `NEED_MORE / S2_EVIDENCE_STALE_REQUERY_ALLOWED`，当时 MCP 与模型预算已到 6/8，Run 状态反复恢复。证据支持“stale/no-progress 没有在预算耗尽时终止，Graph 重放又可能重复插入 Gate Trace”的循环路径；也发现同 Run 新 Probe 的观察时间未进入工具策略查询，造成 fresh Probe 被误判 stale。历史材料没有最初 Worker 异常堆栈，故不能断言哪个异常触发第一次恢复。修复阻断了循环的继续条件并使 Gate ID 幂等且有 64 条上限，维持既有 8/6 预算。
