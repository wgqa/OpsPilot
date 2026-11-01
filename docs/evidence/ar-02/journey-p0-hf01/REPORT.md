# AR-02-JOURNEY-P0-HF01 补证报告

**状态：`ACCEPTANCE_CANDIDATE`**

**Repo / Branch：** `wgqa/OpsPilot` / `codex/ar02-live-01`

**补证基线：** `5a53815b0baea50d7b99afa2b0020e7f96f62517`

**验收冻结提交：** `afc0f0b608a3291d78fdf9bbd336235844853eb9`

**源代码改动：** 无。本补证只新增测试和证据文件。

## 用户实际看到的两种答案

HF01-01 在同一个 Session、Task、订单 `hf01-receiver-order`、Event `event-691d4a1e-6468-43c3-8a62-2a43597cc5cb` 中，对完全相同的问题发起两个独立请求。

第一次 Run 通过正式 Assistant/MCP 获取当前 Receiver `QUEUED`，答复：“同一 Event … 的 Receiver 当前观察为 QUEUED；尚不能确认处理完成。”测试核对了 `Evidence ID`、`Observation ID`、`Attempt ID` 与 Run 的持久关联。

第二次 Run 重新读取同 Event 的 Delivery，但 FixtureModel 没有选择 Receiver 工具，因此本 Run 没有当前 Receiver Observation。答复明确为：“没有可用的当前 Receiver Observation，处理完成与否为 UNKNOWN，无法确认已处理。”该测试不删除业务行、不写非法 `UNKNOWN`，而是检验 Run-scoped Observation 缺失时不能借历史 QUEUED 结论冒充当前查询。它没有模拟 MCP 网络故障，这是本证据的边界。

## 未绑定拒绝与绑定后成功

HF01-02 中，FixtureModel 对无绑定请求明确提议 `get_order_status`。正式工具列表只有 `search_project_knowledge`；Run 以 `FAILED` 结束，没有 TaskBinding、D2 Observation，也没有 `s3_http_observations` 增量（`0 → 0`）。

同一 Session 中，用户通过现有受信订单选择 API 确认订单后，以完全相同的问题文本再次运行。现在 `get_order_status` 出现在模型可用工具列表，调用经正式 MCP 与本地认证 HTTP 路径返回 `200`，订单为 `hf01-bound-order`。Trace 保存了 Task、Message、Run、HTTP Request、Evidence、Observation 与 Attempt ID。

**需主 Agent 关注的记录语义：** 无绑定 Run 中间件留下一条 `assistant_calls` 记录，工具名是 `get_order_status`，状态字段为 `OK`，但结果为 JSON `null`，没有 Evidence/Observation；Run 本身是 `FAILED`，订单 HTTP Observation 为零。测试将它保留为被拒提议的审计记录，没有误报为成功读取。当前 `status=OK` 命名可能误导读者；本卡只要求验证读权限边界，因此没有修改业务代码。

## 实施范围与安全影响

- 新增 [test_ar02_journey_p0_hf01.py](../../../../tests/test_ar02_journey_p0_hf01.py)，仅使用现有 API、Worker、`ASSISTANT_V1`、FixtureModel、MCP 和本地 HTTP/SQLite。
- 冻结计划 [ACCEPTANCE_PLAN.md](ACCEPTANCE_PLAN.md)，冻结提交为 `afc0f0b608a3291d78fdf9bbd336235844853eb9`。
- 新鲜定向回归：**40 passed / 0 failed**；命令和完整输出见 [runs/06-final-regression.log](runs/06-final-regression.log)。
- 完整 pytest 本轮 `NOT_RUN`。继承的全量 `489 passed / 4 failed` 及四项逐条记录见 [FAILURES.md](FAILURES.md)；没有改动或重写它们。
- 最终持久 Trace：[TRACE.jsonl](TRACE.jsonl)。之前每轮测试日志及部分 RED Trace 保留在 `runs/`。
- 本地 Fixture 初始化创建隔离测试事实，受信绑定用例仅执行获准订单绑定；Agent 没有进行 Approval、REPAIR、DELIVER、ActionIntent、Ledger、Handoff 或 Receipt 写入。真实 Provider 请求为 0，浏览器未运行，外部业务写入为 0。
- 原 `docs/evidence/ar-02/journey-p0/` 文件与冻结 Gold 相对基线无差异；`main` 未修改。

远端交付前核验：候选分支 `5a53815b0baea50d7b99afa2b0020e7f96f62517`，远端 `main` 为 `ec8c3582f6d145eec9979c43607302731411ead8`。本提交推送后最终 SHA 由交付消息提供；不得把本地提交当作已推送。

## 主 Agent 六问摘要

1. **用户变化：** 补足“没有当前 Receiver Observation 时仍诚实答未知”和订单读取授权边界的可核查证据；不增加产品功能。
2. **Agent 决策：** 只有确定性 FixtureModel 决策，没有真实模型自主性证据。
3. **观察驱动：** 同一 Event 的当前 QUEUED Observation 支持“排队中”；下一 Run 没有 Receiver Observation 时改答无法确认。
4. **约束双向：** 未绑定提出订单读取不得得到订单事实；可信绑定后同一请求成功取得 HTTP 200 和 Observation。
5. **简化：** 复用既有工具暴露、TaskBinding 与 HTTP 认证路径，没有新增 Guard、Runtime、Schema 或权限规则。
6. **证据与停止：** 定向回归 40/40；真实 Provider、浏览器和全量 pytest 本轮未运行。保留审计状态 caveat 及四项旧失败，停在补证候选，等待主 Agent 复核。

**交付判断：** 两项用户指定的行为补证均已由真实本地 API/Worker/MCP/HTTP/SQLite 路径验证；审计记录 `OK + null` 的含混语义已单列。仅提交验收候选，不自签 PASS，不启动付费 S01/S02。
