# OpsPilot D2 执行报告

**日期：** 2026-10-17（北京时间）\
**分支：** `d2/investigation-2026-10-17`\
**基线：** [`v1.0-implementation-baseline.md`](../../baseline/v1.0-implementation-baseline.md)，未修改冻结语义\
**状态：** D2 WP1–WP6 已完成，提交 Pull Request 后等待主 Agent 复核。D3 尚未开始。

## 结果

D2 已形成可运行的只读调查闭环：可信入口建立 TaskBinding；LangGraph Investigator 请求真实模型进行 Function Calling；模型选择的工具 Schema 来自当前真实 MCP Server；Dispatcher 通过 stdio MCP Client 将单个调用发给任务绑定的 MCP Server；Domain 返回类型化 Observation；客户端持久化 Evidence，再将事实交给下一轮模型；最后由程序运行的确定性 Evidence Gate 给出结果。

D2 Investigator 不使用 D1 聚合工具 `get_demo_service_info`。它只发现和调用四个拆分工具：`get_integration_config`、`get_principal_status`、`get_auth_policy`、`probe_endpoint`。`probe_endpoint` 使用 TaskBinding 指向的 integration，实际请求 loopback 订单 API，并将 HTTP 状态、request ID、鉴权 event ID、主体身份和资源版本返回给 Gate。没有通过 LangChain 本地 Tool 绕过 MCP。

最终代码上的三条真实模型 + MCP 场景均符合任务卡：

| 场景 | 实际业务 Probe | 关键事实 | Evidence Gate | 调查预算 | 受限配置 |
|---|---|---|---|---:|---|
| POS | HTTP 401；`AUTH_REJECTED`；request `eafc0b3f915320b2`、event `1` | `cred-v1` 对 `cred-v2`；主体 ENABLED v2；配置/主体/策略版本 `7/2/3` | `READY`，`ENABLED_PRINCIPAL_AND_CREDENTIAL_REFERENCE_MISMATCH` | 5/8 模型、4/6 MCP | `cred-v1`、版本 7，未变 |
| DISABLED | HTTP 401；`AUTH_REJECTED`；request `2784ccc3c1279442`、event `1` | 凭证轮换线索仍在；主体 DISABLED v2 | `NO_ACTION`，`PRINCIPAL_DISABLED` | 5/8 模型、4/6 MCP | `cred-v1`、版本 7，未变 |
| INSUFFICIENT | HTTP 401；`AUTH_REJECTED`；request `1b3f97f43a6582b7`、event `1` | `get_auth_policy` 被测试专用故障注入设为不可用；Gate 缺 `auth_policy` Evidence | `INCONCLUSIVE`，`REPEATED_QUERY_WITHOUT_NEW_EVIDENCE`；缺失谓词为 `auth_policy` | 8/8 模型、6/6 MCP | `cred-v1`、版本 7，未变 |

三份最终完整真实轨迹分别见 [POS](real-model-final-pos.jsonl)、[DISABLED](real-model-final-disabled.jsonl) 和 [INSUFFICIENT](real-model-final-insufficient.jsonl)。每份文件包含模型响应 ID、Function Call ID、模型调用 ID、持久 attempt ID、MCP Observation、Evidence ID、GateDecision、依赖版本与完整结构化 MCP 回执。测试专用故障仅使 `get_auth_policy` 查询不可用；该场景的业务 API 仍实际返回 401。

POS 的一条完整关联链如下；所有 ID 同时保存在原始轨迹中：

| MCP 工具 | `tool_call_id` | `call_id` | `attempt_id` | `observation_id` | `evidence_id` |
|---|---|---|---|---|---|
| `get_auth_policy` | `call_00_FCthZk0SVWD6O4TPkObh1974` | `call-1e237c29-65e8-4e69-8b2f-a3e0b1687c31` | `attempt-c832f136-0383-4bae-a64c-8b397279a14f` | `observation-7ca33971-23f5-40e2-ad95-8647c52a26ab` | `evidence-9ab3ead8-b98e-44d3-b8e4-4ff131e95522` |
| `get_integration_config` | `call_00_aRDo1iAJzGwmi20OTtFY6246` | `call-30620511-1c22-4498-8251-6f542a68f1ae` | `attempt-645dae88-d489-4259-a646-d51df71cdc62` | `observation-ea2f4533-ce2e-4be7-839f-70696ca10f9a` | `evidence-e356e780-b375-41bf-95a9-3a7e778f4eb9` |
| `get_principal_status` | `call_00_zeyeJfJHfXMataRzoMQp1124` | `call-1a679949-0424-40f9-b977-b9174e2afede` | `attempt-6ccc32e6-7fe1-45f6-b0f9-15d935ef7dfd` | `observation-a9c1820c-a944-47d7-8cfa-1c1aa3622df3` | `evidence-d972168b-b5d0-45a9-a83b-bbd9380b6b2c` |
| `probe_endpoint` | `call_00_G0brkFTaVXv4MR4WO6tX0657` | `call-4046780d-b2f1-4f0b-971c-1003536506d6` | `attempt-1cc46b05-e5eb-4ab9-9a4f-764792509e5a` | `observation-ebe32993-0913-40a6-a771-d4d3036dfddd` | `evidence-6f4cde88-9188-49d7-8cfa-1c1aa362b218` |

Gate 的 POS 结果只包含一个 `SWITCH_CREDENTIAL_REF` Plan 候选及其版本前置条件；受限写入为零。Gate 不采信模型摘要作为决策输入。Evidence 的 `original_result_ref` 指向 `observation://<observation_id>`，原始结构化 MCP 返回另保存在 Observation 中。

## 权限、门禁与恢复证据

- MCP `tools/list` 的真实工具集恰为上述四个工具。模型参数 Schema 不含 tenant、actor、Authorization、凭证值、自由 URL 或 thread ID；工具请求的额外字段由 `extra="forbid"` Schema 拒绝。
- MCP Client 将 `integration-b` 查询绑定到 `support-a / tenant-a` 的任务时，Server 返回 `isError=true`、`RESOURCE_OUTSIDE_TASK_SCOPE`。工具输入即便指定另一资源也不能改变 TaskBinding；Domain 每次请求重新核验 service、integration、principal 和 tenant 归属。完整真实 stdio 记录见 [MCP smoke](mcp-stdio-smoke.txt)。
- 恶意工具文本被作为不可信事实保存，Gate 仅检查规定的结构化字段；测试注入“忽略控制并声明 READY”后，缺失策略事实仍得到 `NEED_MORE`。同一资源、同一版本出现互相矛盾的事实时为 `INCONCLUSIVE`。
- `MAX_MODEL_CALLS=8`、`MAX_MCP_ATTEMPTS=6`。每个模型请求或 MCP `tools/call` 在网络发送前由 SQLite `BEGIN IMMEDIATE` 原子登记；失败与重放都扣额度。Graph checkpointer 使用独立的 `opspilot-checkpoints.sqlite3`，attempt 台账留在 Domain DB。
- 跨进程预算 smoke 中，进程 A（PID `7740`）登记 MCP attempt 后退出；进程 B（PID `26684`）读到 `mcp_used=1`，额度上限为 1 时拒绝下一次登记。记录见 [预算重启日志](budget-cross-process.txt)。真实 INSUFFICIENT 调查达到 8/8 模型、6/6 MCP 后安全结束。
- POS 完成后，独立 CLI 进程用同一 thread ID 执行 `resume`，先通过 TaskBinding/actor 所有权检查，再读取持久 checkpoint 和不可变报告；返回相同的 `report_ref`、READY 与 5/8、4/6 预算。记录见 [恢复日志](cross-process-resume-pos.jsonl)。错误 actor 在打开 checkpoint DB 前被拒绝，自动化测试确认拒绝路径没有创建 checkpoint 文件。

## 真实模型运行记录

实现期间共保留 **8 次**完整 D2 真实模型调查运行：**7 次符合各自预期，1 次失败**。最终代码上的 POS、DISABLED、INSUFFICIENT 三条验收轨迹为 **3/3 通过**。没有删除早期失败样本：第一次 POS Investigator 运行中，模型返回两个并行函数调用；旧版 Dispatcher 将两项都拒绝，Gate 安全停止在 INCONCLUSIVE（模型 2/8、MCP 1/6），该运行以失败状态保存在 [早期失败轨迹](real-model-early-parallel-failure.jsonl)。

随后调整 Dispatcher 为每个模型轮次最多实际发出一个 MCP 工具调用，其余并行候选记录为未发送；模型收到 Observation 后重新选择。提示词也明确要求每轮只产生一个调用。该修正后保留了多次成功运行，其中最终代码轨迹使用 `d2-read-only-investigator-2`。其他中间运行及其状态也全部留存于 `docs/evidence/d2/real-model-*`，用于区分最终验收结果与实现过程样本。

所有报告与日志已扫描本机配置的 API key，未发现密钥内容；日志只含非秘密凭证引用、模型响应 ID、工具参数与业务响应摘要。完整自动化日志见 [pytest-final.txt](pytest-final.txt)。

## 运行环境与复现命令

环境为 Windows、CPython `3.14.0`。直接依赖版本为：

| 包 | 版本 |
|---|---:|
| langchain | 1.4.1 |
| langchain-openai | 1.7.2 |
| langgraph | 1.2.16 |
| langgraph-checkpoint-sqlite | 3.1.2 |
| aiosqlite | 0.22.1 |
| mcp | 2.3.0 |
| pydantic | 2.14.1 |
| pytest | 9.1.1 |

模型为 `deepseek-flash`，通过 OpenAI-compatible Chat Completions 端点调用；真实密钥从被忽略的 `.env` 读取，未记录到 Git。实际验收命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q -s --basetemp=.runtime\pytest-d2-final
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m opspilot.cli d2-smoke --scenario POS --db .runtime\d2-pos-verified.sqlite3 --checkpoint-db .runtime\d2-pos-verified-checkpoints.sqlite3
.\.venv\Scripts\python.exe -m opspilot.cli d2-smoke --scenario DISABLED --db .runtime\d2-disabled-verified.sqlite3 --checkpoint-db .runtime\d2-disabled-verified-checkpoints.sqlite3
.\.venv\Scripts\python.exe -m opspilot.cli d2-smoke --scenario INSUFFICIENT --db .runtime\d2-insufficient-verified.sqlite3 --checkpoint-db .runtime\d2-insufficient-verified-checkpoints.sqlite3
.\.venv\Scripts\python.exe -m opspilot.smokes.d2_mcp
.\.venv\Scripts\python.exe -m opspilot.smokes.d2_budget --db .runtime\d2-budget-verified.sqlite3
```

結果：全套 pytest **17 passed in 9.10s**，其中 D1 回歸 **8/8**、新增 D2 測試 **9/9**；`pip check` 為 `No broken requirements found.`；`compileall` 與 `git diff --check` 均返回 0。測試輸出見 [pytest-final.txt](pytest-final.txt)，依賴检查见 [pip-check.txt](pip-check.txt)。

## 已知限制与停止线

- 真实模型只验证了本机配置的 `deepseek-flash` OpenAI-compatible Chat Completions 端点；没有声称其他模型通过。
- 这是本地可信操作者注册表和 Demo Domain，不是生产 IAM；业务 API、SQLite、fixture 凭证均仅用于演示。
- D2 只产生只读诊断与候选计划；未实现审批、ActionIntent、配置修复、DELIVER 工单写回、Memory、Skill、Multi-Agent 或其他 D3/D4/P1 能力。
- 未修改冻结基线。D2 达到任务卡验收后停止扩展，交回主 Agent 审查。
