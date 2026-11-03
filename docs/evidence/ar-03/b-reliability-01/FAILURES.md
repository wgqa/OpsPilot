# FAILURES — 原始失败与运行记录

## RED-01 — 修复前冻结复现（有效）

- 基线源码：`332f93cca4daad308a8d57730f141e8cc5ed96b3`；执行分支：`codex/ar03-b-reliability-01`。
- 命令：
  `D:\学习\agent新项目\.venv\Scripts\python.exe -m pytest tests/test_ar02_ar03_integration_01.py::test_scoped_protocol_discovery_matches_callback_retry_topics tests/test_ar02_ar03_integration_01.py::test_callback_retry_topic_rank_prefers_retry_family_and_empty_query_stays_empty tests/test_ar02_ar03_integration_01.py::test_formal_worker_can_deliver_from_current_observations_after_mcp_cap_refusal -q --basetemp docs/evidence/ar-03/b-reliability-01/runs/pytest-red-01`
- 退出码：1；结果：13 passed/selected, 4 failed, 9 passed。
- 两个合法描述词失败：`callback retry protocol` 与 `callback retry behavior` 因为当前匹配要求每个 term 都出现在搜索串里，返回空集合。
- 相关度失败：`callback retry` 结果按 document ID 排序，callback ACK 文件排在两个 retry 文件之间，retry 家族未优先。
- 两个预算正例失败：在 `QUEUED`、`PROCESSED` 的正式 API/Worker 确定性旅程中，六个 MCP 读取后提出的第七个工具使 Run 变为 `FAILED / ASSISTANT_RUN_MCP_LIMIT`，没有给模型一次基于现有观察结束的机会。
- 本轮只新增冻结验收测试，尚未改生产代码。失败属于检索/产品交付，不是授权或写入安全失败。
- Provider 请求 0；实际 MCP 六次上限未超出；未执行的工具没有被记录成实际调用；测试 fixture 仅在独立 SQLite 中准备业务事实。
- 原始日志：`runs/red-01.log`。该日志可能受 Windows PowerShell 输出编码影响显示中文，但所有断言、调用与失败摘要完整保留；后续报告不改写此原始日志。

## 历史实验失败（只读）

AR-03-REAL-LLM-02 场景 B 的真实模型 `PARTIAL` 及其原始 `REPORT.md`、`FAILURES.md`、`TRACE.jsonl`、`RESULTS.json` 不作修改或重标。它们是本轮诊断来源，不是本轮重跑。

## 待运行

修复后测试、协议/授权回归、MCP cap 与工具拒绝回归、适用全量 pytest，以及 git 推送状态均待后续实跑。

## GREEN-01 — 未采纳的程序 PARTIAL 尝试

- 原始日志：`runs/green-01.log`，退出码 1；15 项中 13 通过、2 个 QUEUED/PROCESSED 终止额度用例失败。
- 该次实现尝试在 Run 因 MODEL 限额失败后，用工具 Observation 生成程序 PARTIAL。失败 Run 的历史来源随后被 Domain 当前性检查拒绝；将这批数据继续作为当前事实展示不符合现行 S3 权威边界。
- 该实现已撤回。没有放宽 Gate、`sources_current()` 或读取时授权复核。原始失败保留。

## GREEN-02 — 定向修复结果

- 命令：`D:\学习\agent新项目\.venv\Scripts\python.exe -m pytest tests/test_ar02_ar03_integration_01.py::test_scoped_protocol_discovery_matches_callback_retry_topics tests/test_ar02_ar03_integration_01.py::test_callback_retry_topic_rank_prefers_retry_family_and_empty_query_stays_empty tests/test_ar02_ar03_integration_01.py::test_formal_worker_can_deliver_from_current_observations_after_mcp_cap_refusal tests/test_ar02_ar03_integration_01.py::test_terminal_model_cap_fails_closed_when_failed_run_sources_are_not_current -q --basetemp docs/evidence/ar-03/b-reliability-01/runs/pytest-green-02`
- 结果：15 passed，退出码 0。QUEUED 与 PROCESSED 两条正式 API/Worker/MCP Fixture 旅程均在 6 次实际 MCP 后，把第 7 次提议标为未执行/非事实，随后交付只依据当前同 Event Observation 的模型替身回答。
- MODEL 额度终止负例仍为 FAILED；8 次 Fixture 模型 Attempt、6 次成功 MCP、0 个 `chat_run_answers`，来源当前性为 false。用户得到明确 PROGRAM_LIMIT；消息不含旧 Event/Receiver 状态。

## 适用回归

- `runs/regression-01.log`：协议比较、AR-02/AR-03 集成、AR-03-02 离线预检、旧 Assistant、安全预算共 48 passed，退出码 0。
- `runs/pytest-full-01.log`：完整 pytest 共 599 项，595 passed、4 failed，退出码 1。失败原样保留，归因如下：
  1. `tests/test_m1_event_process_recovery.py::test_n2_01_committed_repair_event_replays_after_commit_process_death`：COMMITTED 回执、重启历史事件和数据库计数断言均通过；最终测试清理阶段 `_kill_tree()` 等待子进程超时 15 秒。测试遗留的本轮 Server PID 4800 已按进程路径确认后停止。
  2. `tests/test_m1_web_server.py::test_server_uses_configured_vue_origin_for_exact_origin_guard` 与 `test_server_defaults_origin_to_same_loopback_api_origin`：旧断言不接受 `create_app` 新增的 `assistant_model_factory` 参数；与本次修改文件无交集。未在 Base 重跑，是否为基线既有失败未独立确认。
  3. `tests/test_m4_autonomy_c1_red.py::test_explicit_protocol_followup_is_accepted_as_same_task_readonly_run_before_ttl_fix`：历史 RED 使用废弃的 `READONLY_FOLLOWUP` Intent，当前响应为 `INVALID_MODEL_CLASSIFICATION` / 502；该冻结历史用例未改写，也未加生产兼容分支。
- 全量运行期间，旧 M4 C1 测试向两个历史 JSONL 追加记录。已从当前 Base 的 Git Blob 精确恢复两文件，核对 Blob 分别为 `f1fa8eb5152b8350393ee9908b54ef91ec3b13ba`、`19b9d6704228722256e8363c04a58f4f6b34660d`；历史测试副作用没有进入本次改动。
- Provider 请求 0；浏览器未运行；新测试的 fixture 只写入 `runs/pytest-*` 下独立 SQLite。没有正式业务写入。

## GREEN-03 — 命名后确认复跑

- 为避免将“终止模型额度且来源失效”的负例误称为 PARTIAL，将 Fixture 模式名改为 `cap-terminal-failed` 后，以新 basetemp 重跑同一冻结定向集合。
- 命令：`D:\学习\agent新项目\.venv\Scripts\python.exe -m pytest tests/test_ar02_ar03_integration_01.py::<frozen discovery, ranking, cap resume, fail-closed> -q --basetemp docs/evidence/ar-03/b-reliability-01/runs/pytest-green-03`。
- 15 passed，退出码 0；`TRACE.jsonl` 从这次隔离 SQLite 读取 Run/MCP/结果记录。
