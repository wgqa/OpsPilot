# M1-04 面试问答：自然语言驱动的受控调查

## 1. 如何区分用户线索和可信 Evidence？

**30 秒回答：** 用户文本来自持久 Message，但来源是 `USER_INPUT_UNTRUSTED`。服务端按可信 Task/Session/Run 绑定选取初始描述和已应用更正，把其 ID、序号、摘要和控制版本写进 Prompt Provenance。它能影响调查关注点，却不能直接创建 HTTP 状态或 Evidence。真实事实仍由受限 MCP 和 Evidence Gate 提供。

**2 分钟回答：** 新建 S1 Task 时 Domain 在一个事务中写入首条 Message 与 Run 的 `source_message_id`。`investigation_context.py` 通过可信 TaskRun 查回 Message，并检查租户、所有者、来源摘要、序号及控制版本。更正 Message 只有在 `CORRECT_TASK_INPUT` 已受理、应用高水位推进后才会加入新 Run。Prompt 将它们显式标为不可信声称。模型可以据此选择合法只读 MCP 工具，但 Gate 使用当前版本兼容、同任务/资源的类型化 Evidence 计算。MCP 的 Probe 结果可以证明 401，用户说“是 401”本身不行。

**追问：** 用户说“确定被禁用”，实际 Principal 是 ENABLED 怎么办？

**回答：** 保留用户线索为猜测，查询当前 Principal 状态和 Probe；按可信结果决定 Gate，并在回复里区分用户猜测与当前证据。

**源码与证据：** `opspilot/domain/investigation_context.py`、`opspilot/investigator.py::_prompt_messages()`、`opspilot/domain/d2.py::evaluate_evidence_gate()`；NL-A/B 的 Prompt digest、Message refs、MCP 顺序见 `docs/evidence/vnext/m1-04/RESULTS.json`。

## 2. LangGraph 如何消费跨轮关键更正？

**30 秒回答：** 普通聊天仍是只读路径。正式更正走 `CORRECT_TASK_INPUT`，Domain 接受时推进控制 revision、阻断旧 Run 并取消旧 Plan 资格。新的 Run 绑定更正消息高水位，使用新的 `thread_id::run_id` Checkpoint 身份重新调查，不 resume 已失效的旧图状态。

**2 分钟回答：** TaskControl 持久化 Message 与控制变更；`claim_task_run()`、`apply_pending_critical_inputs()` 核对 expected/current revision 并确定本次可消费的更正。可信输入选择器按 `applied_critical_message_seq` 取累积更正，校验 Message 和 Run 的归属、摘要以及来源关系。运行器给每个 Run 使用独立图线程 ID，所以新 Run 不会把旧 Run 的 Evidence/Gate/Plan 作为新决策状态。模型或 MCP attempt 发出前再在 Domain 事务中检查控制上下文，挡住竞态期间变陈旧的 Run。

**追问：** 更正提交后旧 REPAIR 已经提交怎么办？

**回答：** 保留不可变 Ledger 与已发生的配置变化；新的控制状态阻止后续旧 Plan DELIVER，不声称回滚外部副作用。

**源码与证据：** `opspilot/domain/task_control.py`、`opspilot/domain/investigation_context.py`、`opspilot/investigator.py::run_investigation()`；浏览器 NL-C 的 Run/Message/revision/高水位和旧 Plan `CANCELLED` 记录见 `runs/20261018T084356Z/screenshots/browser-run.json`，N1-10/N1-11 新鲜日志见 `logs/pytest-nl-final-attempt-001.log`。

## 3. 为什么 Prompt 里的“立即修复”不能授权业务动作？

**30 秒回答：** Prompt 是模型输入，不是权限来源。普通聊天进入 `CHAT_READONLY`，不改变业务 Graph、审批、Plan 或 Intent。REPAIR/DELIVER 必须走 D3 的可信身份、分离审批、ActionPermission、先持久化 ActionIntent 和 Domain 写事务守卫。

**2 分钟回答：** 提示词和来源均可包含不可信用户数据，所以模型输出只用于调查和回答。API 端点分别区分普通消息与关键纠错；不存在浏览器审批或修复按钮。候选 Plan 也不等于授权。D3 入口以 Intent ID 为边界，在 Domain 事务内检查当前 Task 控制状态、Plan、审批消费、权限、版本和幂等身份；最终业务写入不依赖 Graph checkpoint。M1-04 真实 Edge 对同一 S1 Task 发送“我批准了/立即修复”后，Task 状态、revision、Plan hash 和动作表计数保持不变。

**追问：** 如果模型返回了结构化的“批准”工具调用呢？

**回答：** Investigator 不具有批准或写入业务配置的工具 schema；即使聊天文字出现批准，也没有可信 Approval/Permission 记录，Domain 动作入口拒绝。

**源码与证据：** `frontend/src/App.vue`、`opspilot/web/app.py`、`opspilot/web/worker.py`、`opspilot/domain/d3.py`；只读隔离浏览器证据见 `browser-run.json` 的 `readOnlyBoundary` 和 `business_state_after_browser`。

## 4. 为什么关键更正后旧 Plan 不能重新生效？

**30 秒回答：** 更正受理即是控制版本变化。TaskControl 在同一事务里登记 pending correction、增加 `control_revision` 并使旧 Plan/权限失效。后续 Run 以新 revision 重新调查，因此旧审批不能覆盖新的输入状态。

**2 分钟回答：** 关键更正影响业务目标的可信依据，因此不能按普通聊天处理。受理时 Domain 先做原子裁决：控制版本推进，旧 Run 被阻断，旧 Plan eligibility 变 `CANCELLED`，已消费的写权限失效。应用阶段把更正的 Message ID/sequence/digest 和记下的 applied revision 绑定到新 Run。新 Gate 可以再次达到 READY，但这是新的事实审查与候选 Plan，需要遵循原有独立审批，不会自动继承旧许可。

**追问：** 如何避免“检查完版本后、更正刚好提交”的竞态？

**回答：** 每次外部模型/MCP 调用的 attempt reserve 前做事务级 TaskControl 来源校验；写动作仍由 D3 事务入口最终裁决。N1-10/N1-11 回归验证更正先提交与 REPAIR 先提交两种顺序。

**源码与证据：** `opspilot/domain/task_control.py`、`opspilot/domain/database.py`、`opspilot/domain/d3.py`；NL-C 浏览器轨迹和 N1 日志见 M1-04 证据目录。

## 5. Prompt Provenance 如何控制上下文来源？

**30 秒回答：** Context Provenance 记录选中的用户 Message refs、类型、摘要、控制版本、消费高水位和 Prompt digest。每次 Run 只选择绑定内初始症状、已应用更正、当前可信 Evidence 和必要的低信任指导；不把完整聊天历史或历史助手回答当作业务事实。

**2 分钟回答：** 先从可信 Run/Task 查询源消息，而不是从浏览器参数或模型输出选择租户/资源。选择器校验消息关联、摘要与版本，建立输入清单。构建 Prompt 时把 user claims 与工具观察分层标记，并保存精确的 Prompt digest。实际模型调用注册前再次校验上下文 revision，避免未应用更正或已过期来源被发送。Evidence 查询依赖 `chat._current_evidence()` 的当前版本筛选，历史回答依赖的来源失效时也不会重新注入。前端只展示脱敏的来源摘要和 ID，不暴露系统 Prompt 或秘密。

**追问：** digest 能证明什么，不能证明什么？

**回答：** 它能核验记录的 Prompt 内容是否变化，结合来源 refs 证明哪些输入被选择；它本身不能证明用户说的内容真实，也不能证明 Gate 或权限正确。

**源码与证据：** `opspilot/domain/investigation_context.py`、`opspilot/domain/database.py`、`opspilot/domain/chat.py::_current_evidence()`、`frontend/src/App.vue`；当前版本排除测试见 `tests/test_m1_dynamic_investigation.py` 和 `tests/test_m1_chat.py`。

## 6. 为什么 403 与 Scope 请求在本阶段停止？

**30 秒回答：** M1-04 只允许既有 S1 401 业务路径。用户说 403 并要求增加 Scope 是未信任输入，不能扩展 Task 资源绑定或调用未来的 M2 逻辑。程序以 `WAITING_INPUT / S1_SCOPE_CHANGE_UNSUPPORTED` 停止。

**2 分钟回答：** 这是边界分类而非根因判定。输入不会自动改绑定、制造 403 Evidence、跳过 MCP 或构造 Scope 变更；最终 Gate 仍只认现有受信 Domain Evidence。真实浏览器运行中 NL-D 被识别为超出已验证范围，在模型调用前停止，Provider=0、MCP=0、Evidence=0。用户需创建一个服务端授权的合适 Task，后续阶段是否支持再由主线决定。

**追问：** 如果用户说的是 403，但 MCP 实测 Probe 是 401 呢？

**回答：** 明确区分用户报告与当前 Probe；是否得到 READY 由 S1 证据契约决定，绝不根据用户口述给 Scope 或以口述状态覆盖实测值。

**源码与证据：** `opspilot/investigator.py` intake 分类、`tests/test_m1_dynamic_investigation.py`、浏览器 JSON 的 `nlD`；冻结输入见 `docs/evidence/vnext/m1-04/CASES.md`。
