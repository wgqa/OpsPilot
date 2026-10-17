# OpsPilot · Luna D2 任务卡（包含 D1 审查整改）

**主合同**：`docs/baseline/v1.0-implementation-baseline.md`\
**实施起点**：`main@d92d9209988d21048bd839bc5b27989b3ae476c8`（执行前核实 HEAD）\
**范围**：D2 只读动态调查与 Evidence Gate；禁止提前实施 D3/D4 的审批、修复或工单写入。\
**交付对象**：主 Agent 复核；新分支与 PR，不直接合并 main。

## 本轮唯一目标

用户提交一个订单 API 401 故障，**真实 LLM 通过真正的 MCP Client/Server 选择分步只读调查**，得到可追溯的 Observation/Evidence，由程序运行的 Evidence Gate 返回 `READY / NEED_MORE / NO_ACTION / INCONCLUSIVE`。同样的 401：凭证失配且主体有效 → READY；主体 DISABLED → NO_ACTION；证据缺失或矛盾 → 补查或安全停止。整个 D2 无受限业务写入。

## WP1 · 一并修复 D1 问题

1. D1 的 `get_demo_service_info` 一次返回客户端凭证、服务端策略和主体状态，容易让诊断变成单次答案泄露。**保留 D1 smoke 作回归，但禁止作为 D2 正式 Investigator 的工具**。将查询按真实数据源拆成最少的只读工具：`get_integration_config`（现有）、`get_principal_status`、`get_auth_policy`、`probe_endpoint`；如动态排查确实需要，再实现 `query_auth_events`。每项返回相应来源的资源/时间/版本与事实，不返回预设根因或离线 Gold。不得为了数量增加工具。
2. D1 模型 Tool Calling 与 MCP 仍是两条独立 smoke。D2 正式链路必须是：**LangGraph Investigator → LLM Function Calling → MCP Client (stdio) → MCP Server → Domain → Observation → 模型下一步**。不得用本地 LangChain Tool 绕过 MCP 冒充完成。
3. 正式任务从可信入口绑定 actor、tenant、thread、service/integration；MCP 子进程由可信 TaskBinding 绑定 scope，Domain 对每个请求做归属校验。模型不可指定 tenant/actor、Authorization、明文凭证、任意 URL、任意 thread_id。恢复前检查 thread 归属。D1 环境变量 smoke 保留即可，但不能成为正式任务身份来源。
4. `fixture_only_switch_ref` 继续仅供准备/重置测试数据使用，不暴露为 Agent/MCP 工具。

## WP2 · 最小 LangGraph 调查闭环

实现 `intake → prepare_context → investigate ↔ execute_read_tools → evidence_gate → report`，Graph 状态只保留 TaskBinding 引用、预算、诊断草案、Evidence ID、Tool Observation 关联、GateDecision、报告引用。模型负责提出假设与选择下一项只读工具；程序负责权限、Schema、预算、状态更新、事实门禁。

每个工具调用保留 `tool_call_id → call_id/attempt_id → observation → evidence_id`；Evidence 包含 tenant/task/resource/principal、来源、观测时间、资源版本、事实及原始返回引用。来自 MCP 的文本视作不可信数据。不能把根因、固定查证顺序或测试答案直接写进提示词。

## WP3 · Evidence Gate 与跨重启预算

Gate 只有四值 `READY | NEED_MORE | NO_ACTION | INCONCLUSIVE`；`WAITING_INPUT` 是任务层出口，`DENY` 是独立权限结果。

- READY：同租户/调用方/服务的真实业务 Probe=401，主体 ENABLED，客户端凭证引用与服务端当前允许版本失配，关键事实与版本相容，无重要冲突。D2 **只输出诊断与 Plan 候选，不审批、不修改配置**。
- NO_ACTION：主体 DISABLED 或明确不应自动切换凭证，报告转人工。
- NEED_MORE：当前证据缺失且预算尚可；缺必要用户输入时转任务 WAITING_INPUT。
- INCONCLUSIVE：事实冲突、过期、关键查询失败且无法解决，或预算耗尽。禁止误判 READY。

落实持久 attempt 台账：只读出站 attempt 上限默认 6（重试亦扣），模型请求上限暂为 8；每次出站前原子登记，进程重启不得重置或免费重放。超时、错误、重复无增量查询必须有终止路径。Gate 若自己读取当前事实，也必须计入工具调用、保留证据，不能把该后台查证宣传成模型自主调查。

## WP4 · 必须完成的验收

- **POS**：真实模型调用 MCP 分步获取事实，产生关联 Evidence，Gate 为 READY，且业务配置版本未改变。
- **DISABLED**：同为 401，尽管有凭证轮换线索，Gate 为 NO_ACTION，不更换凭证、不激活主体。
- **INSUFFICIENT/CONFLICT**：模型补查或安全停止，不能 READY；至少一个真实或确定性注入的负例。
- **权限与可靠性**：跨 tenant 查询失败，非法模型参数失败，恶意工具响应不能提升权限，预算达到上限后停止，任务重启预算不清零。至少验证两种场景的实际 MCP 调用轨迹不同或基于 Observation 出现可解释的不同后续分支。
- **回归**：D1 的 8 个自动化测试仍通过；新增 D2 pytest 与至少一份真实模型+MCP 调查记录。真实 LLM 偶发失败要保留日志，不能删失败样本凑成功率。

## 禁止过度投资与开发停止线

**不做**：D3/D4 审批/ActionIntent/REPAIR/DELIVER；Memory、Skills、RAG、多 Agent、向量库、S2/S3、前端、监控平台、通用 Tool Registry、框架性重构。

D1 遗留的 GitHub Actions、多 Python 版本兼容、`RELEASE.json.local_repo_synced` 文案修正均属低优先级：**不阻断 D2，不要求本轮完成**。业务 Probe 与事件的最小身份/版本/时间关联是 Evidence 契约，勿扩展成完整 Trace 平台。以 4–6 小时有效开发作为控制规模的参考而非交付保证；达到本卡验收即停手，不无限调 Prompt。

**硬停止线**：模型未通过真实 MCP 调查；禁用主体或欠证据误入 READY；越权读取；跨重启预算失效；未经授权业务写入。发生任一项 → D2 不通过，仅修这些阻断项，不扩展别的能力。

## 提交与报告格式

新分支/PR；更新 `TASKS.md` 的实际状态和 `docs/evidence/d2/REPORT.md`。提交：变更路径与 Commit SHA、依赖版本、可复现命令、pytest 分子/分母与 D1 回归、POS/DISABLED/INSUFFICIENT 的模型工具序列与 MCP 回执、Evidence IDs 和 GateDecision、预算/重启记录、当前未实现事项和已知失败。所有日志脱敏；禁止写入凭证。

**完工动作**：提交 PR 后停止在 D2，交回主 Agent 验收；达标直接进入 D3，不再发起新一轮框架评审。
