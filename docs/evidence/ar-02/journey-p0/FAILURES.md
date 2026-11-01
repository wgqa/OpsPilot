# AR-02-JOURNEY-P0 失败与补充运行记录

所有原始日志保存在本目录 `runs/`。失败不删除、不改写旧 Gold。最终候选状态仍受全量回归中的既有失败限制。

## 本轮失败尝试

| 日志 | 结果 | 归因与处理 |
|---|---|---|
| `01-provider-wire-red.log` | RED：1 failed | 真实实现缺口：`create_assistant_model()` 不接收显式离线 transport，故不能安全复用成功的 CONN-02 HTTPX 接线做 SDK 出站序列化验收。增加双 transport 注入；正式默认仍使用显式 HTTPX client。 |
| `02-journey-p0-green-attempt.log` | 收集失败 | 新测试文件遗漏 `pytest` import，属于测试准备错误；补齐后重跑。 |
| `03-journey-p0-green-attempt.log` | 11 passed / 2 failed | 一个断言尝试把 `UNKNOWN` 写入 Receiver，但冻结 SQLite CHECK 只接受 `NOT_RECEIVED / QUEUED / PROCESSED`；改为验证合法 `NOT_RECEIVED`，不扩 Schema。另一失败是该阶段的测试预算/路径断言未与真实已持久执行对齐，按现有额度改为合法有限路径。 |
| `04-journey-p0-targeted.log` | 12 passed / 1 failed | 知识答案引用正文未按测试写成预设文件名；改为核对真实 document ID、版本和 source reference，不改检索内容。 |
| `06-formal-journey-debug.log` | 失败 | 断言要求字面“未知”；实际答复准确表达“尚不能称为处理完成”。将语义断言对齐用户目标，未要求固定句式。 |
| `07-journey-p0-targeted-green.log` | 12 passed / 1 failed | 期待至少 7 个 MCP 调用，但实际合法旅程只需 5 个；降低的是错误数量断言，不减少 Gold 要求。 |
| `08-journey-p0-targeted-green.log` | 12 passed / 1 failed | Trace 查询使用不存在的 `task_runs.completed_at` 列；改用真实持久字段，业务执行本身成功。 |
| `09-journey-p0-targeted-green.log` | 未形成最终摘要 | 本地 HTTP 请求已有 200 输出，但该次 pytest 运行未保留完成摘要；不作为通过证据，后续有完整定向 GREEN。 |
| `10-not-received-case.log` | 未找到测试节点 | 手工指定了错误 node id，未执行用例；修正 node id 后运行。 |
| `13-ar02-free-targeted.log` | 收集失败：3 errors | 第一次命令误用了系统 Python，缺少 `langchain_core`。保存退出码 2；切换到仓库锁定依赖的 `.venv` 后重跑。 |
| `15-full-pytest.log` | 489 passed / 4 failed | 完整回归失败明细见下节。运行旧 C1 RED 时，测试向其历史 TRACE 文件追加了本次记录；已按本轮运行前的 HEAD Blob 精确恢复这两个文件，完整本次失败仍保留在本日志。 |
| `16-m1-n2-isolated.log` | 1 failed | 单独复跑 N2-01：REPAIR 回执历史 API HTTP 200、Event/ActionLedger/配置版本断言均通过，最终失败仍发生在 `tests/test_m1_event_process_recovery.py::_kill_tree()` 的 Windows `taskkill` 后 `Popen.wait(15)` 超时。该环境问题不能归为本轮 Provider 改动通过；测试启动的两个进程已按准确 PID 停止。服务输出另存 `16-m1-n2-server.log`。 |

## 完整 pytest 的 4 个失败

1. `tests/test_m1_event_process_recovery.py::test_n2_01_committed_repair_event_replays_after_commit_process_death`：实际回放检查返回 HTTP 200 并通过业务断言，失败是 Server teardown 的 Windows 进程回收超时。隔离重跑仍复现 teardown 超时。
2. `tests/test_m1_web_server.py::test_server_uses_configured_vue_origin_for_exact_origin_guard`：断言 `create_app` kwargs 只有 `expected_origin`。基线 `09613b2` 的正式 `opspilot/web/server.py` 已经额外传入 `assistant_model_factory`，因此该测试断言过时。
3. `tests/test_m1_web_server.py::test_server_defaults_origin_to_same_loopback_api_origin`：同一过时的精确 kwargs 断言。
4. `tests/test_m4_autonomy_c1_red.py::test_explicit_protocol_followup_is_accepted_as_same_task_readonly_run_before_ttl_fix`：历史 RED 使用旧 Intent 契约，当前接口返回 `502 INVALID_MODEL_CLASSIFICATION`。保持历史失败，不添加旧 Intent 兼容逻辑。

以上三类失败都没有通过修改冻结 Gold、扩大预算、改变业务权限或隐藏旧 RED 来处理。除目标范围内 provider/worker 和 AR-02 回归文件外，未改动生产代码。

## 远端核验与推送记录

首次 `git ls-remote` 遇到 GitHub HTTPS 443 连接失败，因此当时没有声称远端已更新。之后重新核验成功：候选分支从 `09613b2d858313a0b11ff865ee2dfeb66dd52e09` 推送至 `8006bfec41ddea391cffa32bd1600a245d790bf7`；远端 `main` 仍为 `ec8c3582f6d145eec9979c43607302731411ead8`。这属于交付网络重试记录，不改变上述测试失败分类。
