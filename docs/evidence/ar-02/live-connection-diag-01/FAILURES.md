# 失败与修复记录

历史真实失败保持原样于 `docs/evidence/ar-02/real-journey/live-execution-01/attempt-03/`。本文件只记本轮免费诊断尝试。

1. 最初命令引用了 worktree 内不存在的 `.venv`，测试未启动；该命令没有独立原始日志留存，属于证据缺口。未产生 Provider/网络请求，之后改用项目 D 盘既有虚拟环境。
2. `runs/02-formal-assistant-mock-red.log`：新增正式 `run_assistant → create_agent → Loop → ChatOpenAI` MockTransport 测试在冻结断言 `tool_choice == auto` 处 RED，实际 body 缺字段。Mock handler 收到请求，未连接外网。
3. `runs/03-formal-assistant-mock-green.log` 与 `04-formal-assistant-mock-debug.log`：首次尝试把 `tool_choice` 放进 `model_settings`，LangChain 同时以 `request.tool_choice` 参数绑定，抛出 `bind_tools() got multiple values for keyword argument 'tool_choice'`。保留失败日志；将最小修正改为设置 `ModelRequest.tool_choice` 字段。
4. `runs/05-formal-assistant-mock-green.log`：同一重复参数问题的补充失败运行，未产生网络请求。
5. `runs/06-focused-regression.log`：回归发现编辑测试时误删相邻旧测试局部所需的 `TestClient` 导入；已恢复原导入，没有改变旧测试断言或产品语义。
6. `runs/07-focused-regression.log`：恢复后相关回归 **9 passed**。
7. `runs/08-formal-wire-capture.log`：正式 Assistant MockTransport 最终报文检查 **1 passed**，记录路径 `/v1/chat/completions` 和显式 `tool_choice=auto`。
8. `runs/09-historical-unknown-readonly-check.log`：只读查询隔离 SQLite，核对原 Run/Attempt/Assistant Call/Dispatch 状态和 USD 0.645600 预留；与原始结果一致，未写入或释放历史记录。

历史 `OpenAIConnectionError` 的真实底层 cause chain 未记录于此前原始日志或隔离 SQLite，归因仍是 UNKNOWN；没有新的真实请求、重试或网络探测。
