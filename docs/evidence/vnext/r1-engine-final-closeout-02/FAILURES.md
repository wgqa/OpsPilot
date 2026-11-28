# R1-ENGINE 收口保留的失败与限制

此文件汇总历史结果，不改变原始 Gold、Trace、Run、Claim、失败日志或状态。

## 当前最重要的产品缺陷

`R1-J2-LIVE-RECHECK-02` 的 J2-02 为 `PARTIAL`。模型正确指出 `event-previous` 当前 Receiver 状态未知，也没有把 `event-current` 的 `PROCESSED` 套用到另一个事件；但草稿称后续团队会按流程核查并同步，未找到工单、交接或行动回执。用户发送该草稿可能误以为后续工作已安排。原结果见 [LIVE_FAILURES.md](../r1-j2-live-recheck-02/LIVE_FAILURES.md) 和 [LIVE_REPORT.md](../r1-j2-live-recheck-02/LIVE_REPORT.md)。

## J2-02 可复现性

- 唯一原样重放审查为 `BLOCKED_RAW_REQUEST_UNAVAILABLE`；旧 Provider 记录有冻结的 HTTP body digest，但没有原始请求体字节。不能用 `assistant_calls.request_json`、消息、Checkpoint 或重新序列化请求代替线上的原始字节。
- 独立 J2-02-only 重复实验也未运行：没有可验证的 J2-02 开始前 Domain/Checkpoint 配对快照，且建议费用本身不是授权。重复性结论为 `UNDETERMINED`。
- 原 J2-02 的 PARTIAL 保留；没有第二个有效样本，无法判断无回执承诺是否会稳定复现。

材料：[Wire replay REPORT](../r1-j2-02-wire-replay-01/REPORT.md)、[请求体字节核验](../r1-j2-02-wire-replay-01/REQUEST_BODY_CHECK.md)、[Repeatability REPORT](../r1-j2-02-repeat-01/REPORT.md)。

## 历史 59/60 回归差异

F2 Headroom 修复候选 `1be7739...` 上，相关回归为 59 passed / 1 failed。唯一失败：`tests/test_ar04c_f01_context_currentness.py::test_zero_tool_followup_can_explain_valid_historical_snapshot`，旧测试读取 `current_run.completed_tools`，但当时的 `source_context_for_model()` 投影不含该字段，运行报 `KeyError: completed_tools`。历史报告把它记录为断言/投影合同不一致，并保留失败；本收口不把它计为通过，也没有在最新候选上重新运行该组。原始报告：[F2 Headroom REPORT](../r1-j2-f2-headroom-hf01/REPORT.md)、[失败说明](../r1-j2-f2-headroom-hf01/FAILURES.md)、[原测试日志](../r1-j2-f2-headroom-hf01/TEST_LOG_RETRY.txt)。

## AR-03 冻结 Runner 兼容债务

旧 R1 集成候选 `7e9fd...` 的 AR-03 MockTransport Runner 目标测试为 0/3。报告定位为实验 Runner 固定工具 Schema allowlist 没有包含 Product Bridge 新增的 `propose_controlled_auth_investigation` 与 `read_session_professional_outcomes`。这是历史 Runner/Harness 对新增产品 Schema 的兼容债务，不证明普通 Assistant 业务路径失败；不应通过修改已消费实验 Claim/合同伪造可复用授权。详见 [R1 集成失败说明](../r1-final-integration-01/FAILURES.md)。

## 其他回归与未运行范围

- 更早 SHA 的全量 pytest 记录为 741/757、16 失败：12 项绑定 AR-04C 的冻结身份/Claim，3 项旧 Runner allowlist，1 项废弃的 `READONLY_FOLLOWUP` 合同断言。该记录非当前 SHA 的全量结果；现行 `FOLLOW_UP + readonly_action=INVESTIGATE` 有独立正例。原报告：[R1 Integration](../r1-final-integration-01/INTEGRATION_REPORT.md)。
- `7e9fd...` 集成候选上的 77/77 是定向回归，不是当前最新代码 SHA 的全量 pytest；不可冒充新鲜全套通过。
- R1 新统一 Bridge 的真实模型 S1/S2 调查和结果回读没有运行。已有真实 DeepSeek J1/J2 不等于真实模型 S1/S2。
- Browser STOP 仍有效；无浏览器端到端验收。没有生产企业系统接入或生产 IAM 证明。
- 公开账本为应用 Usage 估算；DeepSeek 供应商发票未独立核实。

## 本轮执行

本收口没有发 Provider 请求、MCP 调用、浏览器动作或外部业务写入。没有运行 pytest；当前候选只新增证据整理 Markdown/JSON。旧失败保留，不做新代码修复。
