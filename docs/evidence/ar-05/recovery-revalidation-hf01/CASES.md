# 原 27 项逐项复验

每一项都出现在本轮 pytest 的 JUnit 结果中。当前结果列链接到本轮原始输出，基线列链接到前次全量 pytest 的失败行。逐项用例 ID、耗时和结构化 Trace 行索引见 [RESULTS.json](RESULTS.json)。

| # | 用例 | 基线 RED | 当前结果与实际断言 |
| ---: | --- | --- | --- |
| 1 | `test_d4_repair_committed_receipt_replays_after_plan_cancel` | [复核前置拒绝](../integrated-acceptance-prep-01/logs/full-pytest.txt#L1274) | [PASS](logs/related-regression.txt#L16)，取消后回查原 REPAIR Intent、幂等键、摘要及 Ledger，版本仍为 8。 |
| 2 | `test_d4_deliver_committed_receipt_replays_after_plan_cancel` | [复核前置拒绝](../integrated-acceptance-prep-01/logs/full-pytest.txt#L1275) | [PASS](logs/related-regression.txt#L19)，取消后回查原 DELIVER Ledger、验证与报告引用，工单与交付记录各一条。 |
| 3 | `test_d4_cancelled_uncommitted_intent_cannot_become_an_action` | [复核前置拒绝](../integrated-acceptance-prep-01/logs/full-pytest.txt#L1276) | [PASS](logs/related-regression.txt#L22)，取消先发生时，旧 REPAIR Intent 拒绝执行，两项许可均 REVOKED。 |
| 4 | `test_d4_cancel_before_deliver_blocks_ticket_write_but_preserves_repair` | [复核前置拒绝](../integrated-acceptance-prep-01/logs/full-pytest.txt#L1277) | [PASS](logs/related-regression.txt#L25)，取消阻断未提交 DELIVER，原 REPAIR、验证与冻结报告可回查，DELIVER 许可 REVOKED。 |
| 5 | `test_d4_superseded_plan_blocks_old_uncommitted_intent` | [复核前置拒绝](../integrated-acceptance-prep-01/logs/full-pytest.txt#L1278) | [PASS](logs/related-regression.txt#L28)，替代后旧 Intent 不得执行或激活旧 Plan，两项旧许可均 REVOKED。 |
| 6 | `test_d4_plan_and_approval_reads_require_current_actor_scope` | [复核前置拒绝](../integrated-acceptance-prep-01/logs/full-pytest.txt#L1279) | [PASS](logs/related-regression.txt#L31)，同租户所有者可读；跨租户 Plan、Approval、恢复、Intent 与动作状态读取被拒。 |
| 7 | `test_d4_repeated_approval_does_not_restore_consumed_repair_permission` | [复核前置拒绝](../integrated-acceptance-prep-01/logs/full-pytest.txt#L1280) | [PASS](logs/related-regression.txt#L33)，重复批准复用 Approval，REPAIR 仍 CONSUMED，ACTIVE Plan 下 DELIVER 仍 AVAILABLE。 |
| 8 | `test_d4_cancel_and_repair_are_serializable` | [复核前置拒绝](../integrated-acceptance-prep-01/logs/full-pytest.txt#L1281) | [PASS](logs/related-regression.txt#L36)，两个线程竞争 REPAIR 与取消。实际 REPAIR 先提交，REPAIR CONSUMED，未消费 DELIVER REVOKED。 |
| 9 | `test_d4_cancel_and_deliver_are_serializable` | [复核前置拒绝](../integrated-acceptance-prep-01/logs/full-pytest.txt#L1282) | [PASS](logs/related-regression.txt#L39)，两个线程竞争 DELIVER 与取消。实际 DELIVER 先提交，原 Ledger 可回查，工单仅一条。 |
| 10 | `test_d4_plan_replacement_races_repair_and_historical_receipt_replays` | [复核前置拒绝](../integrated-acceptance-prep-01/logs/full-pytest.txt#L1283) | [PASS](logs/related-regression.txt#L42)，两个线程竞争替代与 REPAIR。实际 REPAIR 先提交，旧 Plan SUPERSEDED，旧 Ledger 可回查。 |
| 11 | `test_d4_concurrent_duplicate_actions_commit_once[REPAIR]` | [复核前置拒绝](../integrated-acceptance-prep-01/logs/full-pytest.txt#L1284) | [PASS](logs/related-regression.txt#L45)，两个并发执行返回同一 Ledger，动作副作用仅提交一次。 |
| 12 | `test_d4_concurrent_duplicate_actions_commit_once[DELIVER]` | [复核前置拒绝](../integrated-acceptance-prep-01/logs/full-pytest.txt#L1285) | [PASS](logs/related-regression.txt#L47)，两个并发执行返回同一 Ledger，动作副作用仅提交一次。 |
| 13 | `test_d4_os_process_crash_and_lost_action_response[REPAIR-repair_before_commit]` | [复核前置拒绝](../integrated-acceptance-prep-01/logs/full-pytest.txt#L1286) | [PASS](logs/related-regression.txt#L49)，子进程退出码 75，独立连接核对退出后的 SQLite 状态，恢复沿用同一 ActionIntent，最终只有一次提交。 |
| 14 | `test_d4_os_process_crash_and_lost_action_response[REPAIR-repair_after_commit_before_response]` | [复核前置拒绝](../integrated-acceptance-prep-01/logs/full-pytest.txt#L1287) | [PASS](logs/related-regression.txt#L54)，子进程退出码 75，独立连接核对退出后的 SQLite 状态，恢复沿用同一 ActionIntent，最终只有一次提交。 |
| 15 | `test_d4_os_process_crash_and_lost_action_response[DELIVER-deliver_before_commit]` | [复核前置拒绝](../integrated-acceptance-prep-01/logs/full-pytest.txt#L1288) | [PASS](logs/related-regression.txt#L59)，子进程退出码 75，独立连接核对退出后的 SQLite 状态，恢复沿用同一 ActionIntent，最终只有一次提交。 |
| 16 | `test_d4_os_process_crash_and_lost_action_response[DELIVER-deliver_after_commit_before_response]` | [复核前置拒绝](../integrated-acceptance-prep-01/logs/full-pytest.txt#L1289) | [PASS](logs/related-regression.txt#L64)，子进程退出码 75，独立连接核对退出后的 SQLite 状态，恢复沿用同一 ActionIntent，最终只有一次提交。 |
| 17 | `test_d4_action_intent_survives_process_exit_before_checkpoint` | [复核前置拒绝](../integrated-acceptance-prep-01/logs/full-pytest.txt#L1290) | [PASS](logs/related-regression.txt#L69)，子进程退出码 76。重查原 Action ID、幂等键、请求摘要，CAS 尚未发生。 |
| 18 | `test_d4_verification_and_frozen_report_replay_keep_original_receipts` | [复核前置拒绝](../integrated-acceptance-prep-01/logs/full-pytest.txt#L1314) | [PASS](logs/related-regression.txt#L91)，重复验证与冻结读取相同 Verification ID、Report ref 和内容摘要。 |
| 19 | `test_d4_langgraph_replays_repair_intent_after_process_exit_before_checkpoint` | [可信 Graph 上下文缺失](../integrated-acceptance-prep-01/logs/full-pytest.txt#L1315) | [PASS](logs/related-regression.txt#L105)，退出码 77，REPAIR Intent 已落库而 Ledger 未写。重启恢复同一审批 Run 和 Intent，最终 DELIVERED。 |
| 20 | `test_d4_langgraph_replays_frozen_report_after_process_exit_before_checkpoint` | [复核前置拒绝](../integrated-acceptance-prep-01/logs/full-pytest.txt#L1317) | [PASS](logs/related-regression.txt#L116)，退出码 77，报告已冻结但 Checkpoint 未推进。重启复用原报告和摘要，仅交付一次。 |
| 21 | `test_d4_langgraph_replays_delivery_intent_after_process_exit_before_checkpoint` | [复核前置拒绝](../integrated-acceptance-prep-01/logs/full-pytest.txt#L1318) | [PASS](logs/related-regression.txt#L128)，退出码 77，DELIVER Intent 已落库，工单尚未写。重启使用同一 Intent 交付一次。 |
| 22 | `test_d4_langgraph_replays_committed_repair_after_os_process_crash` | [复核前置拒绝](../integrated-acceptance-prep-01/logs/full-pytest.txt#L1319) | [PASS](logs/related-regression.txt#L140)，退出码 75，REPAIR 已提交、Graph 回执未返回。重启复用原 REPAIR Ledger 并验证、交付。 |
| 23 | `test_d4_langgraph_replays_committed_delivery_after_lost_response` | [复核前置拒绝](../integrated-acceptance-prep-01/logs/full-pytest.txt#L1320) | [PASS](logs/related-regression.txt#L152)，退出码 75，DELIVER 已提交、Graph 回执未返回。重启复用原 DELIVER Ledger，工单仍一条。 |
| 24 | `test_d4_approval_interrupt_waits_then_resumes_from_persisted_receipt` | [可信 Graph 上下文缺失](../integrated-acceptance-prep-01/logs/full-pytest.txt#L1321) | [PASS](logs/related-regression.txt#L164)，无 Approval 时持久挂起且零 Intent；独立批准产生真实恢复 Run，从同 Checkpoint 新取证、验证、交付。 |
| 25 | `test_chat_evidence_versions_exclude_pre_repair_probe_and_dependent_answer` | [复核前置拒绝](../integrated-acceptance-prep-01/logs/full-pytest.txt#L1322) | [PASS](logs/related-regression.txt#L175)，合法 CAS 后，旧 cred-v1/401 证据及依赖回答被聊天上下文排除，原证据仍存。 |
| 26 | `test_n2_01_committed_repair_event_replays_after_commit_process_death` | [复核前置拒绝](../integrated-acceptance-prep-01/logs/full-pytest.txt#L1323) | [PASS](logs/related-regression.txt#L180)，提交进程退出码 0，另一 OS 进程的 HTTP event history 只重放一个 REPAIR_COMMITTED，Intent/Ledger/事件各一。 |
| 27 | `test_pending_update_cannot_restart_a_really_delivered_s1_task` | [复核前置拒绝](../integrated-acceptance-prep-01/logs/full-pytest.txt#L1346) | [PASS](logs/related-regression.txt#L189)，真实隔离 REPAIR→VERIFY→DELIVER 后确认旧纠错，返回 409 TASK_ALREADY_TERMINAL 且写入计数不变。 |

三个并发竞争在这次复验中均观测到动作先提交。取消或替代先发生的顺序由对应的确定性反例验证。
