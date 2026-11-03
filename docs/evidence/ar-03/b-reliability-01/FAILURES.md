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
