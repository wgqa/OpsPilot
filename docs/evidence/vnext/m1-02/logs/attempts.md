# M1-02 失败与修复记录

本文件保留本轮发现的问题及对应的新鲜复跑结果。密钥、登录密码、Prompt 原文均未写入这些记录。

1. **真实 HTTP smoke 启动前失败。** 首次命令为 `python -X utf8 -m opspilot.smokes.m1_web --evidence-dir docs\evidence\vnext\m1-02 ...`，因脚本未先创建 `logs/` 目录而在 `Path.open(web-server.log)` 抛出 `FileNotFoundError`；没有启动服务、模型或 MCP。修复为先创建所有日志父目录后再次运行。

2. **Windows 强杀后的 byte-range lock 有短暂释放延迟。** 首次 `tests/test_m1_worker_recovery.py` 显示子进程已退出，但新 Worker 立即获得 `PermissionError(13)`。最小修复是在 Windows `msvcrt.LK_NBLCK` 获取处做最多 1 秒有界重试；仍被活动进程占用时继续 fail closed。最终 `pytest-m1-02.txt` 中 Worker recovery/lock 用例通过。

3. **第一次真实模型进程恢复停在 `INTERRUPTED_RECOVERABLE`。** 进程在已持久登记 MODEL attempt、checkpoint 已建立后被结束；重启中的恢复调用被 D3 `authorize_workflow_resume()` 拒绝。实际 Run 状态为 `INTERRUPTED_RECOVERABLE / RUN_INTERRUPTED_BEFORE_RESULT`，仅一条 `MODEL/RESERVED` attempt，没有完成的 Model trace。根因为 `expected_control_revision=0` 被 `or -1` 当成缺失版本。修复显式区分 `None` 与 `0` 并添加 revision-zero 授权回归；最终真实 HTTP 日志中同一 Run 恢复为 `WAITING_APPROVAL`。首次/最终轨迹分别见 `worker-restart.jsonl` 和 `real-model-taskrun.jsonl`；完整恢复修正由当前源代码与测试证明。

4. **M1 定向回归第一次运行 25 通过、1 失败。** `test_schema_migration_is_idempotent_and_preserves_frozen_plan_hash` 仍预期 `PRAGMA user_version=1`；M1-02 为 Web/worker/event 表将 schema 合法升至 2，TaskControl 与冻结 Plan hash 迁移仍通过。更新断言到当前 schema 2。旧日志保留在 `pytest-m1-02-attempt-1.txt`，之后定向集为 27/27、完整集 91/91 通过。

5. **D6 历史 smoke 输出 `FAIL` 仍保留。** 全量 pytest 会运行 `tests/test_d6_smoke_evidence.py`，该测试刻意确认首次 D3 smoke failure 的历史证据未被改写；pytest 断言预期该事件为 `FAIL`，不代表本轮回归失败。最终完整命令退出码为 0，`91 passed`。
