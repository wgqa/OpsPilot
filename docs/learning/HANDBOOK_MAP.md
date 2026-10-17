# 《AI Agent Handbook》—OpsPilot vNext M1-01 对照地图

本地图从 M1-01 任务卡指定的第 4–6 章学习主题出发，建立“原理—源码—实验—表达”链路。章节作为学习参考，不把本项目选择冒充为白皮书的唯一实现规定。

| 学习主题 | OpsPilot 实现位置 | 可复现实验 | 表达材料 |
|---|---|---|---|
| Task 与状态的权威来源 | `opspilot/domain/task_control.py`：TaskControl/TaskRun；`opspilot/domain/d3.py`：最终业务守卫 | N1-09/10/11，`docs/evidence/vnext/m1-01/logs/n1-domain-and-process-events.jsonl` | `docs/learning/M1-01/INTERVIEW_QA.md` 第 1、3 题 |
| 对话输入与持久化 | `opspilot/domain/database.py`：sessions/messages/commands/task_runs/outbox；`admit_task_message()` | N1-01/02 原子回滚和幂等重放 | 第 2、4 题 |
| 受控 Action 与人工批准 | `opspilot/domain/d3.py` 中 Plan/Approval/Intent/REPAIR/DELIVER 的事务入口 | N1-10 stale Plan 阻断、N1-11 repair 后 abort 阻断 delivery、真实 D3 smoke | 第 1、5 题 |
| 运行恢复与事实溯源 | `opspilot/investigator.py` run-specific checkpoint；`task_run_inputs` 中的 `USER_INPUT_UNTRUSTED` | 真实 M1 TaskRun smoke 与跨进程旧 checkpoint 恢复 | 第 3、4 题 |

**贯通证据：** [M1-01 报告](../evidence/vnext/m1-01/REPORT.md)、[状态转换](../baseline/STATE_TRANSITIONS.md)、[学习笔记](M1-01/STUDY_NOTES.md)、[面试卡](M1-01/INTERVIEW_QA.md)。
