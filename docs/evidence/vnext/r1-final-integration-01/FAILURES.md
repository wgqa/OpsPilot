# 失败与未关闭项

## 本轮确定失败

### AR-03 旧 Runner 的三项 MockTransport 目标

当前集成 SHA 上运行结果为 0/3，通过数 0，失败数 3，退出码 1。

三个测试：

1. tests/test_ar03_material_live_resume_02.py::test_resume02_formal_worker_persists_reservation_and_classifies_mock_completion
2. tests/test_ar03_material_runner_recovery_02.py::test_formal_worker_mocktransport_accepts_reserved_request_and_persists_mat01_answer
3. tests/test_ar03_material_runner_recovery_02.py::test_formal_worker_failed_mock_request_is_auditable_without_overwriting_run_reason

实际拦截点是 docs/evidence/ar-03/material-live-01/run_live.py 的 _RecordingAsyncTransport.handle_async_request → _CampaignState.begin。冻结工具校验发现当前 Assistant 正式 Schema 中的 propose_controlled_auth_investigation 和 read_session_professional_outcomes 不在实验 Runner 的 ALLOWED_TOOLS，抛出 UNAPPROVED_TOOL_SCHEMA_EXPOSED。内层 MockTransport handler 计数为零，故三个测试均在预期模型响应/错误断言前失败。

目标版本的显式 MockTransport/拒绝同步 Transport 确保没有真实网络 fallback。外部 Provider HTTP 确认 0；没有真实费用。当前临时 Domain 把 Assistant dispatch 保守记为 UNKNOWN/Usage UNKNOWN，Run 为 FAILED。这是旧记录器在进入外层 Request hook 后的状态分类，不等于外部发送结果未知。

测试最近已知通过版本 8df557dabb6f7440b371828c39974239363ee6d9：同三项 3/3，通过，6.99 秒，退出 0。较早 d4addd403ba0722d4acb4c1a33d1cd655599c97c 有前两项 2/2，通过，5.09 秒；当时第三项尚未合入。Product Bridge 对正式 Assistant 增加两个只读工具后，旧 Runner 的冻结 allowlist 未更新。它是集成后出现的历史实验 Harness 兼容失败，不是证明产品用户路径成功/失败的充分证据。

不修改旧 Runner allowlist、冻结 Gold、已消费 Claim 或预算账本。

## 保留的历史 16 项失败

此前完整 pytest 为 757 collected / 741 passed / 16 failed，退出码 1；该结果属于前次 SHA，不是本候选全量回归。

- 12 项 AR-04C 授权/Claim/冻结身份测试：依赖精确执行 HEAD 或旧 one-shot 状态；不可重放。相关负向授权合同继续有效。
- 3 项 AR-03 MockTransport 失败：本轮已定位，详见上节。
- 1 项 C1 RED：仍使用退役的 READONLY_FOLLOWUP 预期。现行 FOLLOW_UP + readonly_action=INVESTIGATE 的当前正例已通过既有报告；不恢复旧分类。

没有删改任何原始失败报告、Gold 或日志。

## 本轮环境债务

- python -m pip check：退出码 1。全局环境 opentelemetry-sdk 1.42.1 与 opentelemetry-semantic-conventions 0.63b1 期望 opentelemetry-api 1.42.1，但实际 API 为 1.45.1。本轮未安装/升级/降级包，锁文件未改。
- 上游 Bridge Closeout 曾记录 npm audit 11 个 moderate 告警；本轮未执行自动修复或改 package-lock。
- 浏览器仍 STOP，未运行。

## 无失败/无费用路径

本轮 77 项定向 Python 回归、前端 8 项、typecheck、build、相关 ESLint、Python compile、Demo reset 均通过。独立本地 API health 返回 200 且 Worker ready。Provider disabled、凭据未传给健康服务子进程。

真实 Provider HTTP=0，外部业务写入=0。隔离 CLI reset 仅创建新的临时 S1_POS Demo DB。
