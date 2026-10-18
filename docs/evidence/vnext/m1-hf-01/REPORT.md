# M1-HF-01 定向稳定性修复报告

**结果：** HF-01～HF-10 冻结判据均由本轮新鲜测试覆盖并通过，提交主 Agent 独立复核。放行权属于主 Agent；M2 仍保持 BLOCKED。

**基线：** `main@8e7c48ad9a8fa0fff51c0cf69d3717eeaac62842`

**验收标准冻结提交：** `2d8da783672d831b36d8832448d589ea1bfd115b`
**工作目录/分支：** `D:\学习\agent新项目` / `main`。`开发目录/` 是用户未跟踪交接资料，未修改、未纳入提交。最终实现 SHA 在提交回报中提供。

## 本轮变更

- `opspilot/domain/task_control.py`：在 Domain 事务与 Worker owner/epoch fence 下收口失效 Run、限制失败重试；审批恢复按同 Plan 的 ActionIntent、Ledger、VerificationReceipt、Report、DeliveryRecord 和 TicketEntry 校验阶段，保留授权、版本、租户和 TaskControl 门禁。
- `opspilot/web/worker.py`：把异常限制在单 Run 调度边界；持久化受控失败码及有界重试；Worker fence 丢失仍 fail-stop。`BaseExceptionGroup` 分类保留其中的 `ACTION_OUTCOME_UNKNOWN`。
- `opspilot/web/app.py`：health 分开报告 API 存活和 Worker 当前状态；配置启用不再代表 Worker 健康。
- `opspilot/domain/chat.py`：允许持久标记 claim 前失败的队列聊天 Run。
- `opspilot/domain/investigation_context.py`、`opspilot/investigator.py`：仅在 Checkpoint 确实不存在、原始受理输入/控制版本可核对且无 Plan/动作/回执痕迹时，恢复有效的初始 `INVESTIGATE` Run。已应用纠错只读装配，不重复 apply；预算和 Attempt 沿用 Domain 数据。审批 Run 无 Checkpoint、已有业务阶段或动作结果未知时 fail closed。
- 新增 Worker 和真实子进程恢复用例，扩展 Web 审批恢复及授权负例。

未修改冻结架构或业务完成语义；未增加外部业务写入能力。Domain SQLite 仍是 Task、授权、动作资格和回执权威，Checkpoint 只表示 Graph 执行进度。

## 冻结门禁结果

| 门禁 | 结果与测试 | 证据日志 |
|---|---|---|
| HF-01 | PASS — `test_hf01_aborted_expired_recoverable_run_does_not_starve_next_task`，ABORTED 不被覆写且后续 Run 推进 | `pytest-hf01-red-venv.txt`, `pytest-hf01-green-2.txt`, `pytest-targeted-final.txt` |
| HF-02 | PASS — `test_hf02_stale_run_after_correction_is_blocked_and_new_run_progresses` | `pytest-hf02-red.txt`, `pytest-hf02-green-2.txt`, `pytest-targeted-final.txt` |
| HF-03 | PASS — `test_hf03_preclaim_failure_is_bounded_and_worker_continues` | `pytest-hf03-red.txt`, `pytest-hf03-green-1.txt`, `pytest-targeted-final.txt` |
| HF-04 | PASS — 参数化审批恢复的 REPAIR 阶段；独立进程在 REPAIR COMMIT 后退出并由新 PID 恢复同一 Run | `pytest-hf04-hf05-hf06-red-original-gate.txt`, `pytest-hf04-process-repair-green-1.txt` |
| HF-05 | PASS — 同一参数化测试覆盖 VerificationReceipt 与 Frozen Report 提交后恢复 | `pytest-hf04-hf05-hf06-green-1.txt`, `pytest-targeted-final.txt` |
| HF-06 | PASS — DELIVER 提交后回执对账；独立进程恢复后 Ledger/Ticket 各一且 Run 收敛 | `pytest-hf06-process-deliver-green-1.txt`, `pytest-targeted-final.txt` |
| HF-07 | PASS — `test_hf07_hf08_initial_investigation_recovers_before_first_checkpoint_in_new_process[hf07_claim-after_claim]`，新 PID 恢复同 Run/thread | `pytest-hf07-hf08-red-original.txt`, `pytest-hf07-hf08-green-1.txt` |
| HF-08 | PASS — 参数化的 `hf08_correction-after_correction_applied`，原纠错 digest、source、high-water 和不可信 Prompt 来源保留，未二次 apply | `pytest-hf07-hf08-green-1.txt`, `pytest-hf07-hf09-green-2.txt` |
| HF-09 | PASS — 控制变更、跨租户、Plan cancel、缺回执、审批无 Checkpoint、已有 Plan/Intent 冷启动负例 fail closed | `pytest-hf09-cold-recovery-final.txt`, `pytest-hf09-precheckpoint-control-green-1.txt`, `pytest-targeted-final.txt` |
| HF-10 | PASS — `test_hf10_health_reports_api_and_worker_liveness_separately` 覆盖 Worker 运行、退出、禁用 | `pytest-hf10-red.txt`, `pytest-hf10-green-1.txt` |

冻结判据见 [ACCEPTANCE_PLAN.md](ACCEPTANCE_PLAN.md)，机器结果见 [RESULTS.json](RESULTS.json)。

## 执行证据与限制

- 最新全量回归：**140 passed**。命令：`.venv\Scripts\python.exe -m pytest -q --basetemp .runtime/pytest-m1-hf-full-final-20261019-1`。原始输出：`logs/pytest-full-final.txt`。
- 最新定向回归：**31 passed**。命令：`.venv\Scripts\python.exe -m pytest -q tests/test_m1_hf_worker.py tests/test_m1_web_approval.py --basetemp .runtime/pytest-m1-hf-targeted-final-20261019-1`。原始输出：`logs/pytest-targeted-final.txt`。
- Python 3.14.0，依赖锁来自 `requirements.lock.txt`。关键版本：FastAPI 0.137.1、LangChain 1.4.1、langchain-openai 1.7.2、LangGraph 1.2.16、SQLite Checkpointer 3.1.2、MCP 2.3.0、Pydantic 2.14.1、pytest 9.1.1；完整清单见 `logs/runtime-versions.txt`。最终静态检查日志见 `RUNBOOK.md`。
- 跨进程用独立 Windows Python 子进程 `os._exit` 注入退出，日志记录 PID、Run、Task、Worker epoch。模型客户端用确定性替身捕获真实组装的 Investigator Prompt，**未调用外部 Provider**。启动了真实本地 MCP stdio Server 并读取 `tools/list`；本轮恢复用例没有调用 MCP `tools/call`。没有访问真实企业系统或进行新的外部写入。
- 全量测试包含已登记 M1 pytest/APR/Web 审批回归，本轮未 deselect；前端未改，未重跑 typecheck/lint/build 或浏览器演示。
- 失败与修复记录见 [FAILURES.md](FAILURES.md)。本地 SQLite 单实例证据不证明多 Worker、生产 IAM、远程数据库或外部系统 exactly-once。真实 Provider 和业务系统调用未执行。主 Agent 应复核代码、原始日志及历史审计证据后决定是否放行。`git diff --cached --check` 对源代码和说明文档执行；原始 pytest 日志保持字节内容不变，可能包含 pytest 自身输出的行尾空格。
