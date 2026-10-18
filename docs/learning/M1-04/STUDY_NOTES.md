# M1-04 学习笔记：自然语言进入受控调查的边界

本笔记围绕白皮书第 4、5、6 章对照本仓库实现。白皮书用于理解任务、上下文和受控行动的通用概念；实际行为仍以 `docs/handoff/vnext/OpsPilot-vNext-v0.3-product-architecture-contract.md`、API/状态/访问合同和已验收的 TaskControl、D2、D3 代码为准。

## 1. Task 输入、Run 与 LangGraph 是三种不同的状态

用户在工作台创建调查时，初始自由文本已经以 Message 保存。M1-04 从可信 `source_message_id` 回查 Task、Session、租户、操作者、消息摘要和 Run 控制版本，得到 `INITIAL_SYMPTOM` 来源。它是 `USER_INPUT_UNTRUSTED`，只解释用户看到了什么，不是 HTTP 状态或 MCP Evidence。更正通过独立 `CORRECT_TASK_INPUT` 接口受理；Domain 提交控制版本并阻断旧 Run/Plan 后，新的 TaskRun 才能消费它。

新 Run 以 `thread_id::run_id` 区分持久 Checkpoint。因而更正不会把旧 Graph 中已算出的状态当成新事实。每次注册模型或 MCP attempt 前还会在 Domain 事务中核对 TaskControl、消息高水位和来源清单，避免陈旧 Run 外发调用。

**新鲜证据：** NL-C 浏览器轨迹中的 Task `task-7ba29c16-2efb-4dd4-8dea-ad43d9ac9707`，初始 Message `message-7578e3df-a652-41d5-b0bc-fd188447ccc9`（seq 8），更正 Message `message-ba929417-b5dc-4f0f-84de-e6555d34d8f4`（seq 9）。更正 Run `run-4163b62f-242c-406a-ba73-ac14d6d6ae83` 的 expected/current revision 均为 2，consumed/applied highwater 均为 9。旧 Plan eligibility 为 `CANCELLED`。见 [真实浏览器结果](../../evidence/vnext/m1-04/runs/20261018T084356Z/screenshots/browser-run.json) 与 [机器结果](../../evidence/vnext/m1-04/RESULTS.json)。

## 2. Prompt Provenance 证明模型看到的输入，不授予权限

`investigator._prompt_messages()` 把初始描述、已应用更正、当前工具观察和 Gate 以不同来源组织。Prompt 中的用户语句始终标记为未信任输入；Context Provenance 保存所选 Message ID、sequence、digest、控制版本、消费高水位及 Prompt digest。只读聊天记录、未应用更正和整段历史不会被悄悄提升成调查事实。

同一受信资源下，NL-A 和 NL-B 的实际 Prompt digest 不同，模型也实际选择了不同的 MCP 查询次序。两者最终都由当前 MCP Evidence 证明主体 ENABLED、配置 v7 引用 `cred-v1`、策略 v3 接受 `cred-v2`，Probe 为 HTTP 401 / `AUTH_REJECTED`，Gate 才给出 `READY`。模型输入不同改变的是调查线索和实际检索顺序；READY 只能由类型化、同作用域、版本兼容的真实 Evidence 决定。

**新鲜证据：** NL-A 首个模型请求 digest `9ce923f05abffaa4d66786c0df687fc500c875ee02351726d41102e482cd455b`，Provider response `2ddf425d-c6a2-4e7a-ba2c-dc20b4c402a4`；MCP 次序为 `get_integration_config → get_auth_policy → get_principal_status → probe_endpoint`。NL-B 首请求 digest `b033d96b4c07f6712b0e245355936c0b3fb1dc0d731b3a30e566ed8a885b354e`，Provider response `d460005e-9ac2-4526-a37c-8cafe8f034a3`；MCP 次序为 `probe_endpoint → get_principal_status → get_auth_policy → get_integration_config`。具体所有 Provider IDs、工具 trace、Evidence IDs 和 Token 见机器结果及浏览器日志。

## 3. Gate 和业务动作保持确定性、独立授权

自然语言分类只负责一个保守的范围识别：NL-D 明确提出“403 并自动增加 Scope”时，系统在图 intake 阶段转为 `WAITING_INPUT / S1_SCOPE_CHANGE_UNSUPPORTED`，没有模型调用、MCP 调用或 Evidence。用户说“我批准了”或“现在修复”只作为 `CHAT_READONLY` 文本进入普通聊天，不能生成 Approval、ActionPermission、ActionIntent、Ledger、验证、冻结报告或工单。

Scope 识别结果不是 Gate 结果，也不改变 Task 的绑定资源。其他模糊描述仍由模型提出受限只读调查，再由 `evaluate_evidence_gate()` 根据 Domain Evidence 决定 `READY` 或其他状态。审批前允许展示候选 Plan/`WAITING_APPROVAL`；执行仍需 D3 的真人审批、持久 Intent 与 Domain 事务守卫。

**新鲜证据：** NL-D Task `task-c075caeb-a8b8-4bb0-be0e-84f64b2808b5` 的真实 Edge Run `run-837fe3e2-caf1-4661-9fe6-a616658e8e31` 进入 `WAITING_INPUT`，0 Provider calls、0 MCP attempts、0 Evidence。四个冻结案例合计无 Approval、ActionPermission、ActionIntent、ActionLedger、VerificationReceipt、ReportArtifact、DeliveryRecord 或 ticket-resolution 写入。见 [失败与修复台账](../../evidence/vnext/m1-04/FAILURES.md)，其中保留了第一次 NL-D 缺少 Graph 状态字段导致意外到达 `WAITING_APPROVAL` 的失败记录。

## 4. 当前证据和历史来源必须按版本区分

调查只复用当前受信 TaskBinding 下 MCP Server 返回的 Evidence。配置、主体和策略版本在 Evidence 中明确记录；Endpoint Probe 同时记录 Probe 前后版本。M1-03 的 `_current_evidence()` 与来源失效规则继续负责将旧版本事实及依赖其回答的来源排除。M1-04 测试重新覆盖配置版本变化后的旧 401 Probe 排除，保证新调查不会从用户历史描述或聊天回答复活过期业务事实。

**复现实验：** `tests/test_m1_dynamic_investigation.py` 中的 `test_followup_run_reuses_only_live_version_compatible_task_evidence`；M1-03 来源版本回归 `tests/test_m1_chat.py::test_chat_evidence_versions_exclude_pre_repair_probe_and_dependent_answer`。全量 pytest 新鲜运行结果为 109/109。

## 学习与复现入口

- 架构合同：`docs/handoff/vnext/OpsPilot-vNext-v0.3-product-architecture-contract.md`、`docs/baseline/API_CONTRACT.md`、`STATE_TRANSITIONS.md`、`ACCESS_MATRIX.md`、`EVENT_RECOVERY.md`。
- 核心实现：`opspilot/domain/investigation_context.py`、`opspilot/investigator.py`、`opspilot/domain/task_control.py`、`opspilot/domain/d2.py`、`opspilot/domain/chat.py`、`opspilot/domain/d3.py`。
- 测试：`tests/test_m1_dynamic_investigation.py`、`tests/test_m1_task_control.py`、`tests/test_m1_chat.py`。
- 真实运行：`docs/evidence/vnext/m1-04/REPORT.md`、`RESULTS.json`、`CASES.md`、`FAILURES.md`、`runs/20261018T084356Z/`。
- 白皮书对照：白皮书第 4 章（任务与长程编排）、第 5 章（上下文与复用资产）、第 6 章（受控行动与验证）；可从 `docs/learning/HANDBOOK_MAP.md` 的 M1-03/M1-04 部分打开原章链接。
