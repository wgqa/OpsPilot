# HF-02 RED 与失败记录

本文件保留本轮从冻结、RED、测试夹具校正到 GREEN 的失败过程。对应原始日志均在本目录 `runs/`。

## 冻结后 RED

- `red-01-pytest.log`：第一轮 RED 包含 in-process MCP 直接调用缺少 `CallToolRequestParams` 的测试夹具问题；此失败不能作为业务缺陷结论。
- `red-02-mcp-context-pytest.log`：复核了上述 MCP 调用上下文缺失。
- `red-03-harness-verification.log`：为直接 `call_tool` 传入 MCP Context 后，真实本地 HTTP 请求经 MCP Server 的工具测试通过，确认此前失败为 harness 问题。
- `red-04-final-baseline.log`：修正 harness 后的基线 RED 为 `18 failed, 4 passed`，复现历史事件/SSE 泄露及授权版本小数被 `int()` 接受。
- `red-05-read-surface-audit.log`：首次额外 MCP 路径检查误用不可达的服务 URL；该尝试只证明调用失败，不能证明授权拒绝。
- `red-06-real-mcp-version.log`：改为真实本地 HTTP 服务后，基线 MCP 对异常版本仍未拒绝，保留了有效失败证据。
- `red-07-chat-read-leak.log`：直接复现撤权后 Chat Chunks 返回真实 handoff Receipt ID。
- `red-08-chat-all-surfaces.log`：同一测试数据证实撤权后 Chunks、Context Manifest、历史助手 Message 分别暴露回执/队列/业务状态或订单号。此日志记录的是受控 RED 测试观察，补足了 `red-04` 未覆盖的聊天读取边界。

## 修复后的补充失败

- `green-focused-01/pytest.log`：使用全局 `D:\python\python.exe` 运行时环境缺少项目锁定的 `mcp` 包，导致 MCP 相关导入失败；另有一项测试将既有 APPROVER Session owner 拒绝状态写死为 403，而 API 按既有 ACL 返回 404。之后改用项目 `.venv`，并将冻结要求明确为拒绝（保留 403/404 既有差异）。
- `green-focused-02/pytest.log`：`23 passed, 1 failed`。事件测试在同一 TestClient 内登录 APPROVER 后，客户端 Cookie 已切换，随后原 SUPPORT Header 配合的是 APPROVER Cookie，Inspector 因而正确返回 404。测试已在独立测试提交中重新登录 SUPPORT 后再验证；产品 ACL 未改动。

## 最终复验

- `green-focused-03/pytest.log`：24 项冻结定向测试通过。
- `green-trace-01/pytest.log`：24 项通过并写出真实 `TRACE.jsonl`。
- `regression-s3-01/pytest.log`：HF-01、M4-03 S3、M4-02 S3 共 50 项通过。
- `regression-security-01/pytest.log`：既有 S1/S2 安全回归 104 项通过。
- `full-01/pytest.log`：全量 pytest 316 项通过。

上述失败没有被隐藏或改写。测试 harness 的两处误报与业务 RED 缺陷分别说明；所有正式安全断言在项目运行环境中重新执行并通过。
