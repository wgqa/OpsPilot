# AR-02-JOURNEY-P0-HF01 失败与遗留问题

## 本轮补证尝试

| 日志 | 结果 | 记录 |
|---|---:|---|
| `runs/01-first-targeted.log` | 1 passed / 1 failed | 第二项测试最初断言未绑定时不能留下任何 `assistant_calls` MCP 行。实际运行留下了一个同名预分发记录，但没有结果、Evidence、Observation 或 HTTP 订单读取；断言把审计/预留行当成已执行业务读取，过严。未改生产代码，后续测试分别断言工具未暴露、Run 失败、无事实结果/Observation/HTTP 读取。原失败日志保留。 |
| `runs/02-targeted-green.log` | 1 passed / 1 failed | 同一预分发记录的 `result_json` 是 JSON 文本 `null`，不是 SQL NULL；测试按真实持久表示解码后判断为空。该测试准备错误原样保留。 |
| `runs/03-green-attempt.log` | 2 passed | 两项新用例首次通过；后续补强 Trace 中的 Observation / Attempt / HTTP 关联字段。 |
| `runs/04-ar02-regression.log` | 40 passed | P0/HF-02 适用回归通过；后续又补充了精确 Observation 关联断言。 |
| `runs/05-final-targeted-regression.log` | 40 passed | 当时的最终定向回归通过；后续仅增强实际 Trace 字段后，再执行最后一遍。 |
| `runs/06-final-regression.log` | 40 passed | 最终代码与 Trace 版本；包含两项 HF01 用例和既有 38 项适用回归。 |

## 需主 Agent 看到的审计限制

无 TaskBinding 时，模型替身提出了未暴露的 `get_order_status`。运行时留下一个 `assistant_calls` 预分发记录，当前状态字段为 `OK`，但 `result_json` 解码为 `null`，且 `evidence_id`、`observation_id` 均为空；对应 Run 为 `FAILED`。同一 Run 没有 D2 Observation，`s3_http_observations` 数量保持 0。受信绑定后相同问题文本才获得 `get_order_status`，并产生 HTTP 200、D2 Observation 和 HTTP Observation。

因此本轮证明了未绑定提议没有产生业务事实读取；**没有把这条 `assistant_calls.status=OK` 空结果记录解释成成功工具执行。** 该审计状态名称可能造成误读，本轮按任务范围只记录，不改业务代码或新增 Guard。底层 MCP stdio 的逐帧工具调用没有单独抓包，本轮以工具列表、Run、结果/Observation 与真实 HTTP 记录交叉核验。

## 继承的四项全量 pytest 遗留失败

上一轮 AR-02-JOURNEY-P0 全量 pytest 为 `489 passed / 4 failed`。本轮没有重跑全量测试，也没有修改这些失败或相应 Gold；本轮 40 项是定向回归，不能替代全量结果。

1. `tests/test_m1_event_process_recovery.py::test_n2_01_committed_repair_event_replays_after_commit_process_death`：业务回执、Event 与配置断言通过；Windows `taskkill` 后 `Popen.wait(15)` 清理超时。前轮隔离复跑仍复现。
2. `tests/test_m1_web_server.py::test_server_uses_configured_vue_origin_for_exact_origin_guard`：旧测试的精确 kwargs 期望没有包含基线已有的 `assistant_model_factory` 注入。
3. `tests/test_m1_web_server.py::test_server_defaults_origin_to_same_loopback_api_origin`：同一旧精确 kwargs 期望问题。
4. `tests/test_m4_autonomy_c1_red.py::test_explicit_protocol_followup_is_accepted_as_same_task_readonly_run_before_ttl_fix`：历史用例使用废弃 Intent，现行接口返回 `502 INVALID_MODEL_CLASSIFICATION`；未添加旧 Intent 兼容。

更早的 AR-02-JOURNEY-P0 RED、四项全量失败和隔离复跑原件仍保留在 `docs/evidence/ar-02/journey-p0/`，未覆盖或移动。
