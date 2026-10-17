# vNext M1-01 验收用例映射

| ID | 新鲜验证 | 权威事实 | 结果/证据 |
|---|---|---|---|
| N1-01 | Trigger 在同一受理事务的 Run 插入处注入 SQL abort | 失败后 Message/Command/Run/outbox 全为 0；重试整套受理成功 | PASS，`logs/n1-domain-and-process-events.jsonl` |
| N1-02 | 同 key/digest 重放及同 key 不同正文 | 重放原三 ID；revision 只增一次；改正文返回 `IDEMPOTENCY_CONFLICT` | PASS，同上 |
| N1-05 | 两个线程/独立 Domain 连接同时 claim 同一 Run | 至多一个 RUNNING claim；另一方得到 `TASK_RUN_NOT_QUEUED` | PASS，同上 |
| N1-06/07 | cross-tenant/role/owner 校验、审批撤销后回放、migration/history | 越界 command 拒绝；历史 approval 只读且 permission 不复活；历史 Plan hash 不变 | PASS，测试日志与 `test_m1_task_control.py` |
| N1-09 | 有 READY Evidence、无 Plan，abort 后独立 OS process 恢复旧 checkpoint | child PID 不同且返回 `TASK_ABORTED`；Plan/Approval/Intent/Ledger 均 0 | PASS，同上 |
| N1-10 | 已审批旧 Plan/Intent 后 correction 先提交；新 Run 消费并重新取证 | 旧提交先 `TASK_INPUT_PENDING`、后 `TASK_CONTROL_STALE`；新 Plan 绑定 rev 2/high-water；只有新 approval 后 REPAIR 一次 | PASS，同上 |
| N1-11 | REPAIR/真实 200/报告/DELIVER Intent 后 abort，再在独立 OS process 恢复旧 checkpoint | REPAIR Ledger 与 config v8 保留；恢复在 checkpoint access 前拒绝；DELIVER ledger/receipt/ticket entry 0 | PASS，同上 |
| Compatibility | D1–D7 全量既有 pytest | 本轮全量 pytest 真实结果 73/73 | PASS，`logs/pytest-full.txt` |
| Real model + MCP | D1 M1 TaskRun smoke | 5 个真实模型 request、4 个 MCP tools/call；Run/Plan revision 2 关联，审批前无写入 | PASS，`logs/real-model-task-run.jsonl` |
| S1 closure | 既有 D3 真模型/MCP/D3 smoke 重跑 | 401 → 同身份真实 200；REPAIR/DELIVER 各一 Ledger；工单 1 条 | PASS，`s1-d3-smoke/` |

pytest 内 `test_d3_smoke_preserves_failed_start_process_without_crashing` 会故意注入 provider timeout 并保存预期 `FAIL` 的 smoke 结果；该用例本身 PASS，属于失败证据保留回归，不是本轮 D3 实际 smoke 的失败。完整输出中首轮此项按旧 D6/D7 历史保留。
