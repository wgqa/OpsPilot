# M1-06 本地重跑说明

本 Runbook 仅复现冻结的 M1FIN-01…12。实验只连接 loopback Demo API，使用新建 Domain SQLite、LangGraph Checkpoint、随机本地演示口令及 Edge。不要把生产凭据或真实业务地址放入环境。

## 环境准备

仓库依赖由 `requirements.lock.txt` 和 `frontend/package-lock.json` 锁定。Windows PowerShell 新建环境：

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
npm ci --prefix frontend
```

真实 Provider smoke 从仓库根 `.env` 读取 `OPSPILOT_MODEL_API_KEY` 与 `OPSPILOT_MODEL_NAME`；自定义端点可设置 `OPSPILOT_MODEL_BASE_URL`。口令只在 smoke 子进程内随机生成，不需要写入 `.env`。不要打印或提交 `.env`。

## 每次使用新的临时目录

```powershell
$runStamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$runRoot = "docs/evidence/vnext/m1-06/replay/$runStamp"
$tempRoot = ".runtime/m1-06-temp-$runStamp"
New-Item -ItemType Directory -Force -Path $runRoot, $tempRoot | Out-Null
$env:TEMP = (Resolve-Path $tempRoot).Path
$env:TMP = $env:TEMP
```

每次真实 smoke 都另建 Domain/Checkpoint 文件，不复用上次状态：

```powershell
.\.venv\Scripts\python.exe -m opspilot.smokes.m1_04 --evidence-dir "$runRoot/m1-04"
.\.venv\Scripts\python.exe -m opspilot.smokes.m1_05 --evidence-dir "$runRoot/m1-05"
```

M1-04 通过 Microsoft Edge 实测三轮 Provider 聊天、NL-A/B 同绑定差异调查、403 Scope 安全停止、正式关键纠错、刷新、API 重启及权限边界。M1-05 通过 Edge 和真实 Provider/MCP 运行批准闭环，并在审批 COMMIT、REPAIR COMMIT 两个响应丢失窗口退出独立 API 进程。两个 smoke 会把各自新建的 SQLite 路径、Run、截图和原始日志写入结果目录。

## 回归命令

```powershell
$env:TEMP = (Resolve-Path $tempRoot).Path
$env:TMP = $env:TEMP
.\.venv\Scripts\python.exe -m pytest -q --color=no --tb=short --basetemp ".runtime/m1-06-pytest-$runStamp"
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m compileall -q opspilot tests
node --check frontend/e2e/m1-04-browser.mjs
node --check frontend/e2e/m1-05-browser.mjs
Push-Location frontend
npm run typecheck
npm run lint
npm run build
Pop-Location
```

重跑拒绝、TaskControl 原子裁决、来源撤销、Outbox 和未知动作结果定向集合：

```powershell
.\.venv\Scripts\python.exe -m pytest -vv --color=no --tb=short --basetemp ".runtime/m1-06-directed-$runStamp" `
  tests/test_m1_web_approval.py::test_apr04_rejection_resumes_original_graph_without_action_intents `
  tests/test_m1_task_control.py::test_n1_09_abort_before_old_checkpoint_resume_is_enforced_in_another_process `
  tests/test_m1_task_control.py::test_n1_10_correction_invalidates_old_run_and_new_run_binds_fresh_plan `
  tests/test_m1_task_control.py::test_n1_11_repair_commit_survives_abort_and_old_checkpoint_cannot_deliver `
  tests/test_m1_chat.py::test_chat_04_revoked_memory_source_excludes_historical_assistant_message `
  tests/test_m1_chat.py::test_chat_evidence_versions_exclude_pre_repair_probe_and_dependent_answer `
  tests/test_m1_worker_recovery.py::test_ops_01_process_death_releases_worker_lock_and_recovers_running_run `
  tests/test_m1_event_process_recovery.py::test_n2_01_committed_repair_event_replays_after_commit_process_death `
  tests/test_d4_recovery.py::test_d4_terminal_checkpoint_without_domain_receipt_blocks_unknown_outcome
```

任务卡给定的 Gold 与原始拒绝/失败记录在运行前冻结于 [`ACCEPTANCE_PLAN.md`](ACCEPTANCE_PLAN.md)。Smoke 结果中的历史 `start_sha` 字段指向其原阶段编写基线；核对本轮实际执行代码必须使用 M1-06 `RUN_MANIFEST.json` 和 Git commit，而不能把该字段当作本轮 HEAD。
