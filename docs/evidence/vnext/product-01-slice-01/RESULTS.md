# PRODUCT-01-SLICE-01 离线结果

状态：`ACCEPTANCE_CANDIDATE`（实施方自报）

Base：`67459d3928109c244cdbb4dc3c42d0ba57cdd88e`

证据等级：正式 FastAPI / Worker / Assistant / MCP / Session + 确定性 FixtureModel；不代表真实模型自主性验证。

## 用户旅程证据

第一条隔离 Session `session-f6a1eda4-5d5a-4cd4-a9ec-d60f79977794` 依次完成四轮：

1. 用户询问新版回调协议变化。无 Task/TaskBinding；FixtureModel 先调用 `list_scoped_protocol_documents(callback retry)`，再调用 `compare_scoped_protocols` 比较 `callback-retry-contract` v1.0.0 与 `callback-retry-contract-v2` v2.0.0。持久回答指出当前未绑定订单，不能确认客户状态，线上部署版本未知。
2. 用户粘贴含 `max_attempts=5`、`backoff=fixed`、`event-previous` 的 JSON。FixtureModel 零工具回答，将其标为待分析材料，不称为服务器已采用配置，并引用同 Session 的协议比较。
3. 用户要求核实“回调一直没有处理完成”的实际状态。经可信 `/assistant/order` 绑定 `product-01-order` 后建立 Task `task-fe5c7c70-a7c3-4c3d-b16b-ef0598ce931e` 和 Run `run-201ff67a-3727-41a2-bed3-d19cb3161dca`。Worker 实际通过 MCP 读取同一 `event-current`：Delivery 为 HTTP 202 / ACKNOWLEDGED，Receiver 为 PROCESSED。回答只确认这一 Event 已处理，仍说明线上部署版本未知。
4. 用户纠正为 `event-previous` 并要求客户说明。Run `run-5732b340-568f-43da-8282-15a16cf7dcea` 调用 `get_callback_transport_history(event-previous)`；返回该 Event 历史 HTTP 202、受理状态 QUEUED，并明确传输历史不是当前 Receiver 状态。回答没有借用 `event-current` 的 PROCESSED，说明当前 Receiver 状态未知，草稿未提交。

第二条隔离 Session `session-ecd0b5d5-cbf1-48e0-ac9e-6ea25f06cf69` 验证当前事实变化：同一 Event `event-042a1ec7-fdb8-48af-86bf-936bdd1d7a7d` 首轮观察为 HTTP 202 / ACKNOWLEDGED + Receiver QUEUED。测试夹具随后在隔离 SQLite 中将其改为 PROCESSED 并递增版本；新 Run 重新读取 Delivery 与 Receiver，回答改为 PROCESSED。旧答案因来源失效而显示“这条历史答复的来源已失效，不能作为当前依据。请重新查询。”新答案关联新 Run 的当前来源。

上述两条旅程的用户消息、Assistant 答案、Run、Task、MCP Observation、Evidence ID 和来源链接均已持久化并由测试断言核对。第一条旅程还核对 D3 ActionIntent/Ledger、DeliveryRecord 与 S3 HandoffReceipt 为零。状态变化仅由隔离测试夹具模拟；没有真实业务写入。

## Gold 结论

| Gold | 结论 | 证据 |
|---|---|---|
| P01-G1 材料足够 | PASS（离线） | 协议发现/比较后可零工具分析用户 JSON；普通咨询不创建 Task。 |
| P01-G2 缺少当前事实 | PASS（离线） | 无绑定时不查订单；可信绑定后通过现有 S3 只读 MCP 读取当前 Event。 |
| P01-G3 当前事实变化 | PASS（离线） | 同 Event 新观察从 QUEUED 变为 PROCESSED；旧来源被判失效，新结论关联新 Run。 |
| P01-G4 用户纠错 | PASS（离线） | 纠正为另一 Event 后读取该 Event 的传输历史；不借用另一 Event 的 Receiver 结果，明确当前处理状态未知。 |
| P01-G5 调查中止 | PASS（离线回归） | `test_terminal_model_cap_fails_closed_when_failed_run_sources_are_not_current` 验证程序限额通知不冒充模型最终答案，也不复活旧 Observation。 |

既有反例回归同时覆盖未授权协议比较、聊天文字不能授权订单读取及混合权限查询。以上均是确定性测试结论，不证明真实 LLM 会自主作出相同选择。

## 验证记录

- 新旅程定向测试：`1 passed`（最终用户输入修订后重跑）。此前两条新测试合跑：`2 passed`。
- 适用 AR-02/AR-03 回归：50 项收集，`50 passed`，退出码 0；包含 Worker/API/MCP、Context、来源撤权、OS 恢复、预算停止、越权拒绝和 Assistant 持久会话。
- 回归命令：`python -m pytest -vv -s --basetemp D:\tmp\product-01-slice-01-regression-tmp tests/test_ar02_ar03_integration_01.py tests/test_ar02_context_continuity_01.py tests/test_ar02_runtime.py tests/test_ar02_journey_p0.py`
- `git diff --check`：通过。
- 回归日志保留于本机 `D:\tmp\product-01-slice-01-regression-final.log`，SHA-256 `5fddeebd7f706821f009ece38833e14eab70a9e3c3b601a4a8770ec3a17684c0`。
- 定向旅程原始 JSONL 保留于本机 `D:\tmp\product-01-slice-01-focused-final2-trace.jsonl`，SHA-256 `c267f0f236588db4f62196245c3e347742473240169ef350d6c07099144e7954`。

本轮真实 Provider 请求 0、浏览器 0、外部业务写入 0。只改动现有集成测试与确定性 FixtureModel，不修改生产代码、预算、Gold 或执行策略。真实 DeepSeek 自主性、浏览器呈现及后续交互仍未验证。
