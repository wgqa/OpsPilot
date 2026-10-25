# M4-EG01-HF-01 失败记录

所有运行原始日志保留在 `runs/`。历史 Gold、原 C1 Trace 和旧报告不作为本轮可修改文件。

| 运行 | 阶段 | 结果 | 归因 |
|---|---|---:|---|
| `red-01/pytest.log` | 原始遗漏事实 RED | 1 failed, 2 passed | 有 HTTP 200 订单与同 Run HTTP 202 投递 Observation，但 Chat 当前 Evidence 只有 `s3_order`。确认主缺陷。 |
| `red-02/pytest.log` | 跨 Event 来源 RED | 3 failed | 旧实现未把完整同 Run 观察候选交给当前性校验，因此不能为被排除的错误 Event 候选记录预期 exclusion provenance；无 Receiver 路径仍遗漏投递事实。 |
| `red-03/pytest.log` | 受理快照语义 RED | 1 failed | Chat 输入带有 POST 202 原始 `transport_response_json`，其中受理时 `receiver_state=QUEUED`，但没有当前 Receiver Observation。 |
| `green-04/pytest.log` | 最终定向 GREEN | 4 passed | A/B/C 状态、跨 Task/Event、事实来源及 202 原始快照剔除均通过。 |
| `full-pytest-01/pytest.log` | 源码最终投影前全量 | 374 passed, 1 failed | 唯一失败为旧 `READONLY_FOLLOWUP` 预实现 C1 RED。 |
| `full-pytest-02/pytest.log` | 最终源码全量 | 374 passed, 1 failed | 同一既有旧 C1 RED。没有删除或适配其旧意图；现行合法 `FOLLOW_UP + readonly_action=INVESTIGATE` 路径 15 项通过。 |

## 保留的旧 C1 RED 详细说明

失败测试：`tests/test_m4_autonomy_c1_red.py::test_explicit_protocol_followup_is_accepted_as_same_task_readonly_run_before_ttl_fix`

该测试使用测试替身返回 `{"intent":"READONLY_FOLLOWUP"}` 并要求 API 接受该意图。现行分类合同要求 `intent=FOLLOW_UP` 且 `readonly_action=INVESTIGATE`。全量测试仍执行并失败为 `502 INVALID_MODEL_CLASSIFICATION`，符合“保留旧 RED、不加生产兼容分支”的要求。合法分类测试文件 `tests/test_m4_autonomy_c1_acceptance_fix_01.py` 与 `tests/test_m4_c1_hf_01.py` 全部通过。

## 测试附带写入的历史 Trace

全量运行会由既有旧 C1 测试向 `docs/evidence/vnext/m4-autonomy-c1/TRACE.jsonl` 与 `runs/rev1/behavior-red-trace.jsonl` 追加临时测试记录。为避免覆盖历史证据，本轮将每次新增行原样保存到对应的 `full-pytest-*/legacy-test-generated-traces.jsonl`，然后恢复上述两个历史文件。它们没有被提交为本轮变更。
