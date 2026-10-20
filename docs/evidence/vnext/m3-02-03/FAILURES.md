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

本轮仍有产品层失败：26 轮真实 Web 会话中 5 个 Run 失败；真实 DeepSeek 对照中的 Rolling Summary / Hybrid 均未完成最终回答。真实跨进程浏览器恢复、Task B 跨任务使用和撤销后重放尚未形成新证据，因此保持 `PARTIAL`。
