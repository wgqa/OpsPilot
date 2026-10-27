# RED、失败与修复记录

按发生顺序保留原始日志。历史 Stage B/Supplement 日志与冻结 Gold 未改动。

| 运行 | 原始结果 | 归因 | 后续处理 |
|---|---|---|---|
| `runs/red-frontend-01/node-test.log` | 冻结 4 项中 0 通过、4 失败 | 正式纠错后的 Answer/Diagnosis/Follow-up/stream 未统一挂回原问题；正常授权 Inspector 完成时错误淘汰并行消息结果 | 作为预实现 RED 原样保留；最终 15 项通过 |
| `runs/red-api-01/pytest.log` 与 `runs/red-api-01/responses/` | 3 失败 | 真实 Inspector Run JSON 没有 `task_id`；初始 Answer、Follow-up 和纠错最终结果在生产投影里均未关联 | Inspector 从数据库 Runs 查询返回受信 `r.task_id`，最终 4 项 API 集成通过 |
| `runs/green-api-01/pytest.log` | 1 通过、2 失败 | 修复来源映射后，API 的 `trusted_state.s3_outcome` 仍缺少与不变 Receipt 对应的 Run 身份，真实 Diagnosis 无法安全加入 Answer | 在已有受信 Inspector 事务内、当前 S3 Scope 有效时以 tenant/task/receipt 查不可变诊断 `run_id`；撤权响应仍不含该 ID；最终 API 测试通过 |
| `runs/green-frontend-02/node-test.log` | 14 通过、1 失败 | 测试把“Answer Task 与 Run Task 不同”的负例仍预期在原问题下存在 Answer；实现正确拒绝了它，失败的是测试期望 | 将负例改为断言 Answer 不投影；新的 `green-frontend-03/04` 均为 15 通过 |
| `runs/frontend-checks-01/typecheck.log` | TypeScript 退出码 2 | 新诊断投影分支未显式排除 `s3Outcome === null` | 增加空值收窄；最终 typecheck/build/ESLint 均退出码 0 |
| `runs/green-api-04/pytest.log` | 1 失败、3 通过 | 新增 Chat API 用例在 Worker claim 前未调用正式提议分类端点，Run 仍可信地处于 `UPDATE_CLASSIFICATION_PENDING`；这不是产品路径缺陷 | 测试改为经 API 提交确定性的 `FOLLOW_UP/EXPLAIN` 后由 `next_worker_run()` 受理；`green-api-05` 4 项通过 |

所有以上失败都被保留，不以覆盖日志或修改 Gold 消除。`green-api-02/03`、`green-frontend-01/03/04`、`frontend-checks-02/03` 与 `backend-regression-01` 是对应的后续成功运行。

