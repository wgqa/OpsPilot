# E03-D 离线执行报告

## 结果状态

**Fixture 链路已执行；真实模型语义仍未评定。** 这不是 E03-D 的真实模型 PASS，也不改变冻结 Gold、Rubric 或 12 例评测分母。

- Branch：`codex/r2-ar06-e03-eval-exec-01`
- Base：`0852c2d4896cd49f036a1751a62b6082ed768faa`
- Runtime：`user-demo-r2-e03-fixture-20261115-01`
- Session：`session-e1c940f4-e999-4e2d-934f-eec43c78dbae`
- Run：`run-79fb648f-9de5-4f55-ae18-e73fd34f529f`
- Run 状态：`SUCCEEDED`；Runner 评定：`UNVERIFIED`
- 无 TaskBinding。Session 关联 Run、冻结用户消息、Assistant 回答及三条 MCP Tool Call。

冻结题面由 Runner 从 Gold 原样读取：

> 我们要把回调 API 从 v1 升到 v2。请比较适用协议，说明配置影响、兼容风险和研发检查项。线上实际部署版本尚未核实。

冻结 `CASES.json` SHA256：`c1acd3fa789befa733aa96bf3a49b08357ff071f3b627b4c40319882e2805cf8`。本次题面 SHA256：`19a206256ff387f20552527cfd05899e89bf171c5e500ab9a298f9c5051dcfc6`。

## 隔离授权与来源

没有修改共享 `knowledge/assistant-access.json`。新建 Runtime 时，Runner 从现有 `knowledge/async-callback/manifest.json` 验证文件 Digest，再在该 Runtime 内生成最小注册表：仅 `tenant-a / support-a / SUPPORT` 可选 `orders-async-demo`，只列入以下两份材料：

| Document ID | Version | Source | Manifest content digest |
| --- | --- | --- | --- |
| `callback-retry-contract` | `1.0.0` | `local:orders-async-demo/contract-v1` | `a5974f46bf50e2bfcd63ed1e6528d473560854204d12a50dfb3f82b9e61bc0c3` |
| `callback-retry-contract-v2` | `2.0.0` | `local:orders-async-demo/contract-v2` | `9ad3f5a67a5f40da986769c66a78317027d3e57803371a0674d3b14fe412e238` |

Runner 验证实际文档内容 SHA 与 manifest 相同。此授权由可信的初始化/服务启动配置选取；Web 请求和模型工具 Schema 均不接受注册表路径或授权内容。`create_app` 只接受与被选 Runtime Domain DB 同目录的普通文件，MCP 子进程再次校验该路径。

## 本次链路

真实 FastAPI TestClient + 正式 Assistant Session/Message API + 单 Worker + LangGraph Assistant + 独立 MCP stdio 子进程 + 现有 Knowledge/Comparison Domain。Fixture Model 只根据已返回的工具结果选择下一步；两种合法调用次序均通过：

1. 发现 → 比较 → 原文摘录。
2. 发现 → 原文摘录 → 比较。

Runner 实际离线执行采用第一种顺序。工具返回的 `project_id`、文档 ID/版本/source/Digest、比较差异和原文行引用均保存在 [E03_FIXTURE_TRACE.json](E03_FIXTURE_TRACE.json) 的实际 MCP 调用结果中。最终 Fixture 回答说明 v1/v2 重试语义差异、核查项目和兼容风险，并明确材料不能证明线上实际部署版本。

本案例没有业务 Task，因此没有 S3 Observation 或业务 Evidence 行；协议来源由 MCP Tool Call 结果中的带来源 `protocol_documents`、`comparison` 与 `source_refs` 证明。这是正常的文档分析路径，不代表业务 Observation 已发生。

## 正反验证

- **授权正例：** 新建 SUPPORT Session，只能看到 `orders-async-demo`；通过正式 API 显式选择后，合法文档发现、比较和摘录均成功，来源当前性为 `true`。
- **工具顺序：** 两种合法顺序分别由 Fixture Model 选择，Runner 未固定要求模型必须先比较或先读摘录。
- **跨租户：** `tenant-b / support-b` 的隔离 Scope 返回空授权集与 `KNOWLEDGE_SCOPE_DENIED`。
- **未授权文档：** 对允许的 callback 文档与 `api-scope-current` 发起比较，Domain 返回 `DocumentNotAuthorizedError`。
- **其他 Runtime：** 单独初始化的普通 Runtime 仍只看到既有 `orders-callback` 项目，不会继承 `orders-async-demo`。
- **撤权：** 将隔离注册表中的授权停用后，正式 Assistant Sources API 返回 `current=false`，工具结果被隐藏，历史回答投影不再展示为有效依据。
- **Digest 失配：** 篡改隔离测试 DB 中摘录结果的 Digest 后，正式 Assistant Sources API 拒绝所有来源结果。
- **线上版本边界：** 工具输出 `deployment_version_verified=false`；Fixture 答案没有把资料版本说成线上部署事实。
- **注册表路径边界：** 把 Runtime 外的共享注册表传给 App 初始化会以 `ASSISTANT_KNOWLEDGE_REGISTRY_PATH_INVALID` 拒绝。
- **业务写入：** 未创建 TaskBinding、Approval、ActionIntent 或业务回执。

## 运行与费用

本次真实 Provider 请求：**0**。Runtime Grant：**未配置**。发送许可：`0`；收到 Provider 响应：`0`；UNKNOWN：`0`。三个 MCP 文档工具调用均为本地只读；Fixture Model 派发 4 次，Fixture Token 元数据为输入 110、输出 77、合计 187。这些数字不是真实 Provider Usage，也不产生费用。

完整 Runner 结果见 [E03_FIXTURE_RESULT.json](E03_FIXTURE_RESULT.json)，测试和运行日志见 [E03_TEST_LOG.txt](E03_TEST_LOG.txt)。

## 限制与下一步

本次证明隔离授权确实进入正式 Assistant/MCP 链路、来源能追溯且失效能阻断。Fixture 输出由确定性测试模型生成，**没有证明 DeepSeek 能自主选择这些工具、理解语义或产出合格迁移建议**。下一步如需真实测评，先由主 Agent 独立验收本候选；再由用户另行批准一次 E03-D Live、单独 Runtime Grant 和不超过 USD 0.06 的应用预算。步骤见 [E03_LIVE_RUNBOOK.md](E03_LIVE_RUNBOOK.md)。
