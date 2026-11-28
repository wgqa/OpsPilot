# 失败记录与剩余事项

## 基线 RED

前次全量运行记录 701 通过、40 失败。其中 27 项与本卡相关，具体失败保存在[原全量日志](../integrated-acceptance-prep-01/logs/full-pytest.txt)。本轮开工复跑 6 项代表用例，全部到达相同的失败点。Domain 路径缺合法复核回执，审批后的 Graph 路径缺有效 Run。两者均早于目标崩溃或重放断言。[本轮原始 RED](logs/red-baseline.txt)

## 实施中的夹具失败

首次共享夹具运行得到 3 通过、3 失败。新任务通过 TaskControl 建立后，夹具只返回 `get_task_binding()` 的投影，其中没有原调用者使用的 `session_id`。M1 聊天、M1 子进程和 M4 纠错用例因此在夹具阶段报 `KeyError`。夹具改为从真实任务创建结果返回对应 Session ID 后，三项在定向 GREEN 和最终相关回归均通过。[中间失败](logs/fixture-direct.txt) · [定向 GREEN](logs/fixture-focus.txt)

## 当前复验边界

- 原 27 项当前合同通过 27 项。未到目标断言的用例 0，复现的生产缺陷 0。[逐项结果](CASES.md)
- 三个并发样本实际是动作先提交。反序由确定性取消及替代用例验证。进程证据适用于本地 SQLite、真实 loopback HTTP 和固定 Demo 角色。
- 最终 129 项相关回归退出码 0。该组之外的整仓测试本轮未运行。[完整相关回归](logs/related-regression.txt)

## 原清单剩余的 13 项

| 原失败组 | 数量 | 本轮状态 |
| --- | ---: | --- |
| AR-04C 冻结执行身份和 Claim | 12 | `NOT_RUN_OUT_OF_SCOPE`，原执行身份与 Claim 约束继续保留 |
| C1 历史 `READONLY_FOLLOWUP` | 1 | `NOT_RUN_OUT_OF_SCOPE`，原始 RED 保留，当前合同使用 `FOLLOW_UP + readonly_action=INVESTIGATE` |

13 个原用例 ID 和日志行号均保存在 [RESULTS.json](RESULTS.json)。它们是上次全量的未复验项，本轮没有据此推定新的整仓失败数。真实 Provider、外部业务写入及浏览器均没有执行，隔离 Demo 中的预期 CAS 和工单已在 Trace 中逐项记录。
