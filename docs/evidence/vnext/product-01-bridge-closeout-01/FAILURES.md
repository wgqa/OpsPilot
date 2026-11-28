# FAILURES.md

## 本轮 RED→GREEN

1. **Outcome omitted_count**：新增覆盖 0、1、4、5、6 项的范围测试先在 `red2-20261107-034026-bf44c4f0.log` 复现旧行为缺陷；通过授权范围内窗口计数后，`green2-20261107-034423-e73dace5.log` 通过。
2. **CLI clean start**：隔离数据库执行 `python -m opspilot.cli reset --scenario S1_POS --db <private-db>` 首次报 `UnboundLocalError: cannot access local variable 'reset_fixture' where it is not associated with a value`。原因是 `main()` 内局部重复导入遮蔽模块级名称。最小删除重复局部导入后，`cli-reset-green-994ada599929466eb82958fc731313eb.log` 通过；随后健康启动检查成功。

两项原始失败日志均保存在任务私有证据目录，未删除。

## 一次完整 pytest：757 收集，741 通过，16 失败

退出码 1，耗时 1013.15 秒。测试完整走到结束，没有复现 TestClient lifespan shutdown 停滞。本轮没有依据这次结果修改 Worker 或 ASGI shutdown。

### 1. 冻结实验身份/历史执行绑定（12 项）

分类：`HISTORICAL_CONTRACT_CONFLICT` 或 `TEST_ENVIRONMENT`；不计当前产品通过，也不视作新代码回归。

- `tests/test_ar04c_f01_recheck_preflight.py`：2 项真实一次性授权正向测试在当前不同候选 SHA 下报 `AR04C_ONE_SHOT_AUTHORIZATION_INVALID`。
- `tests/test_ar04c_prelive_hf01.py`：8 项授权、claim、Provider transport 测试拒绝当前身份；并发 claim 正例的两个子进程均得到 LOST。当前测试来源绑定冻结执行 HEAD / 授权合同，不能在新的集成 SHA 上伪造旧身份后要求通过。
- `tests/test_ar04c_real_journey_01.py`：2 项期待固定路径 claim 不存在的测试发现历史路径 `.runtime/ar04c-real-journey-01/claim.json` 已存在（修改时间 2026-11-05）。它属于已消费的旧实验身份。本轮没有删除、重置或复用该 claim。

受保护的历史 claim 与账本保持原状；这组实验专属回归不适用于当前新分支的 Provider 执行资格，但相应拒绝行为仍是安全合同的一部分。

### 2. 历史 AR-03 Runner MockTransport（3 项）

分类：`UNKNOWN`，保留为未解决的实验 Runner 测试债务。

- `tests/test_ar03_material_live_resume_02.py::test_resume02_formal_worker_persists_reservation_and_classifies_mock_completion`
- `tests/test_ar03_material_runner_recovery_02.py::test_formal_worker_mocktransport_accepts_reserved_request_and_persists_mat01_answer`
- `tests/test_ar03_material_runner_recovery_02.py::test_formal_worker_failed_mock_request_is_auditable_without_overwriting_run_reason`

三项均预期 MockTransport 捕获一次出站，但实际捕获数为 0，未到达它们要验证的 Completion 成功/失败断言。没有证据把原因归到本次修改；本轮没有改 Provider Runner，也没有重跑或绕过实验授权。这是明确剩余限制，若要关闭须单独定位其冻结实验环境和 Mock 出站路径。

### 3. C1 退役合同 RED（1 项）

分类：`HISTORICAL_CONTRACT_CONFLICT`。

`tests/test_m4_autonomy_c1_red.py::test_explicit_protocol_followup_is_accepted_as_same_task_readonly_run_before_ttl_fix` 仍要求旧 `READONLY_FOLLOWUP` 分类，当前接口返回 `INVALID_MODEL_CLASSIFICATION`。不恢复废弃意图。本轮现行 `FOLLOW_UP + readonly_action=INVESTIGATE` 正例通过，包含同 Task Run、MCP 与持久只读结果检查；因此旧 RED 保留为历史证据，不表示当前追问功能不可用。

## 环境及隔离观察

- Full pytest 运行在独立 detached test worktree `D:/学习/agent新项目/.worktrees/product-01-bridge-closeout-01-fullsuite-20261107`，HEAD 与候选代码 SHA `83b886353c5252f1ec02d094259a2ca59fe699a5` 一致。
- 有两份历史 M4 C1 trace 文件被全量测试追加修改，仅在该 detached 测试 worktree 内：`docs/evidence/vnext/m4-autonomy-c1/TRACE.jsonl` 与 `docs/evidence/vnext/m4-autonomy-c1/runs/rev1/behavior-red-trace.jsonl`。未复制到候选分支，原候选文件未受污染。隔离测试 worktree 保留，未清理。
- `pip check` 失败来自全局 OpenTelemetry 包不一致：SDK 与 Semantic Conventions 1.42.1 要求 API 1.42.1，而全局安装 API 1.45.1；没有安装/升级包。
- npm audit 报告 11 项 moderate；本轮未运行自动修复。
- 第一次 npm ci 因共享缓存权限失败；使用私有 cache 重试成功，lockfile 无变化。

## 未运行

真实 DeepSeek、浏览器、main 合并、生产业务写入均为 0。以上不计入通过。\n