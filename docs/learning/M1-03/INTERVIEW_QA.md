# M1-03 面试问答卡

## 1. 如何让普通聊天复用业务 Task，又不让聊天篡改业务状态？

Session 可以同时承载没有 Task 的普通对话和关联 Task 的只读追问。每条聊天是独立 `CHAT_READONLY` Run；[`worker.py`](../../opspilot/web/worker.py) 对它走 `_process_chat_run()`，不进入原 Investigator Graph。`TaskControl` 仍是业务 Run 的状态入口，Plan、审批和动作由 Domain SQLite 控制。真实 Edge 对 WAITING_APPROVAL Task 发出业务追问和“我已批准，请改凭证”文本后，Task 仍处于 WAITING_APPROVAL，动作表保持 0；单测还对关键业务表做了前后快照比较。证据在 `docs/evidence/vnext/m1-03/RESULTS.json` 和 `tests/test_m1_chat.py`。

## 2. 为什么 Worker 会把聊天受理与模型调用拆开？

HTTP 受理只负责验证可信身份、Origin/CSRF、幂等键并持久化 User Message/Run/Outbox；后台单实例 Worker 再调用真实 Provider。断开浏览器不会取消或重复提交业务 Run。[`task_control.py`](../../opspilot/domain/task_control.py) 管受理、Claim 和重试边界；[`worker.py`](../../opspilot/web/worker.py) 管异步处理。E2E 在真实回答还处于 RUNNING、已经看到增量 Chunk 时刷新浏览器，然后等待同一个 Run 完成并验证历史消息恢复；API 重启测试再登录读取原 Session。真实请求序列与结果见 `logs/browser-full.attempt-*.txt`、`logs/api-server-after-restart.log` 与机器报告。

## 3. Context 中的 MCP Evidence 和历史助手回答如何避免过期？

[`chat.py`](../../opspilot/domain/chat.py) 在每次模型请求前从 SQLite 重新读取 TaskBinding、Task 状态、新鲜 Evidence、有效 Memory 与消息来源，写入 ContextManifest。不能只相信上一次 Prompt 或 checkpoint 中的文本。历史 Assistant Message 会回查其来源；被撤销或失效 Memory 的回答会从后续上下文排除，并在 Manifest 中记原因。定向回归见 `test_chat_04_revoked_memory_source_excludes_historical_assistant_message`，真实 Task 的有效 Evidence 追问见 `RESULTS.json`。

## 4. 真实模型遇到聊天中的“我批准了”为什么不能改配置？

模型只能产生日常语言回答。浏览器消息使用 `CHAT_READONLY`，服务端身份从受信 Cookie 获取，写入 API 检查 CSRF 与配置的精确 Web Origin，Task/Session 读取按 Tenant/owner/role 检查。REPAIR/DELIVER 仍要求各自持久化的 Intent 和获批权限；聊天路径不导入动作入口。真实聊天的恶意请求与状态核对见 `RESULTS.json`；HTTP 跨租户与错误 Origin 用例在 `tests/test_m1_chat.py` 和 Playwright 日志中。

## 5. 为什么同时保存流式 Chunk 与最终 Assistant Message？

Chunk 让 UI 在 Provider 生成时显示进度，允许刷新后按 `chunk_seq` 继续读取。Chunk 不是最终回答，也不能在重试时当作新的历史 Message。完成时 `complete_chat_attempt()` 在一个事务中检查唯一 `chat_run_answers.run_id`，创建单一 Assistant Message、来源回执并将 Run 标为 SUCCEEDED。进程恢复回归覆盖有部分 Chunk 的未完成调用；真实 Edge 在第三轮流式回答中途刷新，确认用户看到的最终 Message 与持久读取一致。

## 6. M1-03 的 S1 演示到底证明了什么？

真实浏览器登录后可以创建固定 `orders-demo / integration-a` Task，原 D2 调查通过真实模型和 MCP 收集四类 Evidence 并到达 WAITING_APPROVAL。聊天可解释真实 credential ref、主体状态、Policy 与 HTTP 401 Probe；审批、配置变更与工单写入保持未执行。页面明确提示该首轮 S1 调查仍是固定场景；自由文本驱动业务调查与动态工具决策属于 M1-04，Web 审批属于 M1-05。详见 `RESULTS.json` 的 Task、Provider/MCP 轨迹与零动作记录，以及 `REPORT.md` 的限制。
