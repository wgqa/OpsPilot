# SOURCE_MAP 与本地演示说明

## 实际调用链

1. **Assistant 消息入口**：`opspilot/web/app.py::post_assistant_message` 接收同 Session 消息并持久创建只读 Chat Run；专业 Task 入口由同文件 `post_task` 处理。
2. **可信 Task 创建**：`opspilot/domain/task_control.py::create_task_with_initial_run` 在用户确认后建立 Task、初始 Run 与命令幂等关联；自然语言本身不授予资源权限。
3. **执行核心选择**：`opspilot/web/worker.py::_dispatch_run` 按 Run 类型把普通对话送到 ASSISTANT_V1，把专业调查送到现有 Investigator。
4. **Assistant Loop**：`opspilot/assistant.py::run_assistant` 装配 LangChain `create_agent`、当前 Context、受限 MCP tools 和持久答复。
5. **Bridge 工具**：`opspilot/assistant_mcp.py::run` 暴露 `propose_controlled_auth_investigation` 与 `read_session_professional_outcomes`。前者只提议；后者从服务端当前 Session 推导可读结果，不接受模型指定任意 Task ID。
6. **Domain 约束**：`opspilot/domain/assistant.py::propose_controlled_auth_investigation`、`read_session_professional_outcomes` 和 `sources_current` 处理来源与结果；Outcome 列表只读取同 Session、授权且来源当前的结果。
7. **专业 S1 调查**：`opspilot/investigator.py` 通过 TaskBinding 下的工具得到 Evidence；`opspilot/domain/d2.py::evaluate_evidence_gate` 决定是否 READY、继续读取或停止。
8. **S1/D3 与 S2**：S1 Plan/Approval/Repair/Verification/Delivery 复用 `opspilot/domain/d3.py`；S2 交接读取复用 `opspilot/domain/s2_handoff.py::get_s2_handoff_outcome` 和现有 `POST /handoff/submit` 接口。
9. **结果回到会话**：用户通过已有 Task API 确认调查或提交交接；随后 Assistant 可在普通会话 Run 中读取持久 Outcome 并形成用户可读解释。HandoffReceipt 表示队列接收，不表示授权或业务恢复；VerificationReceipt 只证明它记录的时间点。

## 关键技术取舍

- **保留专业 Investigator**：旧 S1/S2 Graph 已承载 Gate、审批、幂等副作用与恢复合同。统一入口由 Assistant 决策和解释，不需要把这套受控执行语义复制进新 Loop。
- **调查建议不直接创建 Task**：模型输出不是可信资源授权。用户确认后走既有 TaskControl API，按可信租户、角色与资源创建。
- **Outcome 工具不接受任意 Task ID**：当前会话身份、Session/Task 关联和来源版本由服务端核验，避免提示注入或伪造 ID 越权。
- **交接不等于恢复**：`SCOPE_ESCALATED` 只说明交接范围；没有新的授权事实。S2 `PENDING_REVIEW` 仍等待人工处理。
- **历史验证不是持续健康**：旧 VerificationReceipt 有形成时间；需要当前状态时必须新取证。
- **一个 Assistant + 一个专业执行组件**：Assistant 提供连续对话和自主合法选择；Investigator/D3/S2 继续承担业务专属、可信的诊断与副作用事务，避免双状态权威。

## 本地离线启动检查

本轮通过了当前 Python 环境中的命令帮助、隔离 Demo reset、单 Worker 本地 Web Server 健康检查。以下为核验过的入口形式，不含密钥，也不会自动启用真实 Provider：

```powershell
python -m opspilot.cli reset --scenario S1_POS --db <private-demo-db>
python -m opspilot.web.server --host 127.0.0.1 --port <local-port> --workers 1
```

用本地客户端检查 `/api/health` 的 worker 状态。环境中应保持 `OPSPILOT_ASSISTANT_PROVIDER_ENABLED=0` 做离线演示；不要把 TestClient 结果称为浏览器验收。真实浏览器仍受 STOP 限制。\n