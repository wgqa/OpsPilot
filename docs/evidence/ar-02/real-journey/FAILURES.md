# 失败与历史问题

## 保留的历史失败

- AR-02-LIVE-01 P1 的 S01 曾在第一次 Provider dispatch 后收到 `OpenAIConnectionError`。本地 API 记录 Run `FAILED`，Chat Attempt 曾为 `STREAMING`，实验 dispatch 为 `UNKNOWN`，USD 0.645600 预留保留；没有抓到 Provider HTTP 请求/响应，实际传输和计费均未知。该次不重试、不结算、不从本账本抵扣；S02 未运行。
- AR-02-CONN-01 的一次 401 与 AR-02-CONN-02 独立连通性 HTTP 200 均保留为各自实验，不能替代本次真实 S01/S02。
- HF02 前全量 pytest 的历史 489/4 仍如实保留；其四个失败不是本任务新测试通过率的一部分。

## 本轮新增运行

### 冻结 RED — 2026-11-01

- 命令：`python -m pytest -q tests/test_ar02_real_journey_budget_scope.py --basetemp=.pytest-tmp/ar02-real-journey-red-01`
- 原始日志：`runs/frozen-red.zip`；退出码：`1`。
- 结果：`4 failed`。新预算身份被 `_validate_experiment_id` 拒绝；真实 Provider 工厂拒绝新实验 ID；正式 `create_app()` 拒绝该 ID；旧 SQLite schema 上预期的 schema-specific fail-closed 被更早的旧 ID allowlist 拒绝。
- 归因：现有 SQLite 实验额度与 Provider/App 接线只允许 `AR-02-LIVE-01`。当前测试明确冻结了最小必要补差，并未发送 Provider 请求。
- 警告：仅 FastAPI TestClient 对 `httpx` 的既有弃用警告，与本缺口无关。
