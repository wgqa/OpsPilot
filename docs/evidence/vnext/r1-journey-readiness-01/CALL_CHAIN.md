# 正常 Assistant 调用链

J1/J2 离线证据实际经过正式 API/Worker 和 Runtime Grant；本文件按源码边界说明每一跳。

1. **用户提交和可信作用域**：`opspilot/web/app.py:create_app` 注册 `/api/sessions/{session_id}/assistant/messages`（约 L692）、`/assistant/order`（约 L718）及 Run Sources API（约 L728）。普通问题建立 Session Run；订单查询必须经可信 order API 绑定 Task，聊天文字本身不授予资源读取权限。
2. **Worker 分派**：`opspilot/web/worker.py::_process_chat_run` / `_dispatch_run`（L314/L524）识别 ASSISTANT_V1。Runtime 模式开启时由 Domain 加载并校验当前持久 Grant，再将 run-specific binding 交给模型工厂；无 Grant/禁用时拒绝，不回退 Legacy Provider。
3. **模型构造**：`opspilot/assistant.py:create_assistant_model`（L907）基于当前 Grant 构建 `ChatOpenAI` 和异步 HTTPX 客户端。正式同步/异步出站包在 `opspilot/runtime_provider.py:RuntimeAsyncTransport` / `RuntimeSyncTransport`（L52/L102）。
4. **Context 与每次发送保护**：`assistant.py:Loop.context`（L1220）装配当前用户输入、当前 TaskBinding、有效历史来源和当前 Run Observation；`Loop.awrap_model_call`（L1310）在模型发送前登记 Assistant Call。`domain/assistant_runtime_grant.py:reserve_dispatch`（L848）持久预留费用；Runtime HTTPX transport 在调用内层网络前执行 `claim_send`（L955）。本轮 MockTransport 在收到请求时断言预留已存在。
5. **响应/UNKNOWN**：收到有效响应后使用 Runtime Grant 完成 Usage 结算；传输未知会在 `runtime_provider.py` 调用 `mark_unknown`，保持占用且禁止同 logical request 再发。Usage 无效/未知或 Grant 失效时停止该模型循环。
6. **模型工具选择与 MCP Observation**：LangGraph Agent 由模型响应决定回答或使用已暴露工具。工具来自 `opspilot/assistant_mcp.py`，MCP/Domain 根据当前 Session、TaskBinding、授权文档集合及资源权限重新核验；S3 Tool 调用和 Evidence/Observation 由 Domain 写入。结果进入下一次模型 Context，不能由 Fixture 直接绕过 MCP。
7. **回答和来源回显**：Agent 最终答案写回原 Session 并关联用户 Message/Run；Sources API 按本次 Run 读取并重新校验来源。`assistant_mcp.py` 里的 `read_session_professional_outcomes` 通过 `domain/assistant.py:read_session_professional_outcomes`（L519）回读同 Session 已存在的可信 S1/S2 Outcome，携带历史/当前性语义，不创建专业业务状态。

## 路径边界

`assistant_experiment.py:reserve_dispatch/complete_dispatch`（L270/L410）是冻结实验专用 Campaign 账本；普通产品测试使用独立 Runtime Grant，不消费历史实验 Claim。两条机制职责不同，但都使用正式出站保护，不允许从 Grant 失败回退到实验或 Legacy Provider。

J3/J4 的专业 Investigator 仍由旧执行核心运行；J3 的 Legacy 测试启用只在测试进程里明确存在，模型构造被 Fixture 替代。J4 的 D3 修复和 DELIVER 是现有隔离 Demo 的专业闭环，不是 Assistant 普通聊天产生的副作用。
