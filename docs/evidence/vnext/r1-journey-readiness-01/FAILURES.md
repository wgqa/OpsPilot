# 失败与环境记录

保留本轮所有可见失败，失败不会从报告或原始日志中删除。以下均未产生真实 Provider 请求或外部业务写入。

## 本轮可复现/修复

1. 直接运行 `pytest` 首次在 collection 前因导入路径报 `ModuleNotFoundError: opspilot`。用 `python -m pytest` 并显式设置 `PYTHONPATH` 后消除。
2. 使用默认 Windows 临时目录时遇到 pytest `WinError 5 Access Denied`。将每次 `--basetemp` 指向当前 D 盘隔离 worktree 下全新路径后通过；没有改全局权限。
3. 新的 J1/J2 离线 Runtime Grant 夹具在早期迭代中分别出现：FixtureModel 分支匹配过窄、Mock 读取了错误工具结果键、断言了旧工具返回字段、审计查询假设不存在的 `execution_core` 列。每次均只发生于隔离 Mock 测试；完整原始失败保存在 `RUNTIME_JOURNEY_*_LOG.txt`，最终修正仅涉及测试夹具/断言。
4. 第一版对照夹具按 `version` 建索引导致两个 v1 文档被覆盖，测试虽执行成功但比较基准错误。该证据不采用为最终证据；现夹具按明确 `document_id` 选中 `callback-retry-contract` v1.0.0 与 `callback-retry-contract-v2` v2.0.0，最终重新通过。
5. 首次组合回归中，既有 S2 本地测试缺少独立 Legacy Provider opt-in，正式 Worker 正确阻断并返回 `NO_S2_DIAGNOSIS`；单独复现确认 Run=`BLOCKED`, `blocked_reason=LEGACY_PROVIDER_AUTHORIZATION_REQUIRED`，没有模型请求。测试已通过 `monkeypatch` 显式设置两个 Legacy 测试 opt-in；`ChatOpenAI` 在同一测试内仍被替换成确定性 `_S2InvestigatorFixture`，因此没有真实 Provider。修改仅为测试夹具，最终隔离及组合回归均通过。

## 当前仍未关闭

- 本轮完整 `pytest` 未运行；全量结果不声明通过。
- 真实 Provider 行为/费用未运行，需新的独立授权。
- 浏览器验收 `NOT_RUN`，Browser STOP 未解除。
- 历史全量报告中的 16 项失败来自旧 SHA：12 项绑定 AR-04C 一次性授权/执行身份；3 项旧 AR-03 MockTransport 工具 Schema 白名单问题；1 项 C1 已废弃 `READONLY_FOLLOWUP`。本轮没有重跑或修改这些历史合同。

## 原始日志索引

- `BASELINE_TEST_LOG.txt`
- `BASELINE_TEST_LOG_PYTHONPATH.txt`
- `BASELINE_TEST_LOG_LOCAL_TMP.txt`
- `RUNTIME_JOURNEY_TEST_LOG.txt`
- `RUNTIME_JOURNEY_GREEN_LOG.txt` 与 `_02` 至 `_04`
- `RUNTIME_JOURNEY_FINAL_LOG.txt`
- `S2_READBACK_ISOLATED_LOG.txt`（授权负例）
- `S2_READBACK_GREEN_LOG.txt`
- `TEST_LOG_FINAL.txt`
- `SOURCE_REVALIDATION_LOG.txt`
