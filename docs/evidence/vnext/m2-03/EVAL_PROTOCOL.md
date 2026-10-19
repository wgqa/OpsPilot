# M2-03 冻结评测协议

**协议版本：** `M2-03-EVAL-v1.0`

**基线：** `0cdc3160a2c2a6c74a89bce0a1360f2939c1ed8b`

**状态：** `FROZEN_NOT_EXECUTED`

**执行起点：** freeze commit 的父提交；任何运行记录都必须引用具体 code SHA。

## 固定原则

- 以 `GOLD.json` 中 M203-01～14 和 `RUBRIC.json` 为唯一期望，执行期间不改写标准或历史分母。若发现标准自身矛盾，暂停实现并先提交有审计轨迹的标准修订。
- 先保存 RED，再做最小实现，再跑 GREEN；每次命令、工作目录、Python/Node/SQLite/浏览器/Provider 版本、退出码、开始结束时间写入原始 run 记录。
- RED 的失败日志完整保留。失败补充运行写新文件，不覆盖原文件；报告列出全部失败、原因与是否被修复。
- Gold、Rubric、历史 Release 或 expected labels 不作为模型上下文或在线 Gate 输入。
- 全新 pytest 使用唯一 basetemp/runtime 目录，禁止清理、重置或复用用户已有的 `.pytest-m2-02-*`、`开发目录/` 与历史证据。
- 每一案例状态只允许 `PASS`、`FAIL`、`PARTIAL`、`NOT_RUN`。测试本身通过但不可观察关键业务事实时不得记 PASS。

## 固定测试层

1. **Domain/SQLite：** 真实临时 SQLite 文件；迁移从 v7 升级并重复初始化；断言 TaskBinding、TaskControl、Queue、Receipt、Command、Outbox、S2 Scope/Policy/Grant 表的事务前后数量/摘要。每个故障点记录实际事务边界。
2. **权限与幂等：** SUPPORT owner、同租户非 owner、APPROVER、跨租户、伪造/多余请求字段；同 key 同/异摘要；异 key 同业务唯一键；两个 tabs 和不同 OS 进程并发。任何跨进程测试必须共享同一个 SQLite 文件而非进程内锁。
3. **竞态与当前性：** 更正、Abort、完成 Task 与 Handoff 同时争用；记录最终提交顺序、TaskControl revision、Draft/Receipt/Queue/Outbox 事实。Policy、Grant、Principal 和 Evidence age 改变后使用原 Draft 提交。
4. **HTTP/Web：** authenticated session、Origin、CSRF、scope-protected GET/POST、真实 POST 用户动作和用户可见 GET 回查；响应丢失后相同 operation ID 重发；刷新、两个标签页和只读自然语言追问不触发新 POST。
5. **真端到端：** 真实 DeepSeek Provider、真实本地 MCP stdio、S2 HTTP Probe/Request ID、真实 Chromium/Edge UI。至少一条同 Task 旅程覆盖初始线索、正式关键纠错、新 Run、新 Request ID、当前 Draft、按钮确认、Queue/Receipt、刷新和只读追问。保存 Network、浏览器 trace/截图、Provider/MCP Trace、SSE 与 SQLite 快照。
6. **回归：** 全量 pytest（基数以实际仓库测试数报告，既有基数至少 171）、MCP stdio tools/list+tools/call、前端生产构建、S1 401→200真实 smoke。不得用阶段旧日志代替当前命令。

## 交易结果采集

每次试验至少记录：`case_id`、`run_id`、`code_sha`、命令、输入 operation ID（脱敏可保留）、Task/tenant 伪名、Draft ID/digest、控制版本、Request ID、response HTTP/error、replayed 标志、Receipt ID/digest、Queue Entry ID、handoff status、Outbox event ID、Task workflow status、business outcome、Scope/Policy/Grant 写入差值、DB row counts、关联日志/截图文件 SHA-256 和结论。

真实业务标识和凭证不得写入公开日志。测试 operation ID/receipt ID 可以保留。Token 数只按 Provider 实际响应记录；缺失填写 `null`，不得估算。

## 事务故障和竞争协议

- `after_command_before_queue`、`after_queue_before_receipt`、`after_receipt_before_outbox`：注入必须发生在同一个未提交写事务；要求异常后 Queue、Receipt、Command、Outbox、Task 业务终态均无半提交事实。
- `after_commit_before_http_response`：在真实 COMMIT 成功后让 HTTP 请求失败/断开；服务端 GET 回查后用原 operation ID 重试，要求 Receipt ID 相同且行数不增。
- 并发运行至少 2 个不同 OS 进程、两个独立 HTTP client；记录 PID、开始栅栏、退出码与 SQLite 结果。
- 更正/Abort 竞争要分别保留“控制操作先提交”与“Handoff 先提交”轨迹；不假定调度顺序，按实际 Domain COMMIT 顺序检查 Gold。

## 72 小时 SLA 协议

用可注入时钟或固定接收时间推进到 `review_due_at` 前后；读取只读状态投影。不得睡眠 72 小时。证明 overdue 查询没有写入 Scope/Grant、没有自动重新投递、没有创建新 Run/Worker job，且 Receipt 内容摘要保持不变。

## 报告要求

`RESULTS.json` 对每条 M203 case 提供冻结 expected、实际、状态、日志路径和证据 SHA。`TRACE.json` 保存真实模型/MCP/HTTP/SSE/浏览器/Domain 关联。`FAILURES.md` 逐项保存 RED 和后续修复记录。`REPORT.md` 不把接收写成授权/恢复，也不把历史 H 组结果重新包装。最后提供三个提交 SHA（标准、实现、最终证据）、远端 `origin/main` SHA 和校验结果。
