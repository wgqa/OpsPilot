# R1-J2-LIVE-RECHECK-01 实际运行报告

**结果：PARTIAL / ACCEPTANCE_CANDIDATE**
**实际执行源码 SHA：** 05632c71d70efe38f7cb48de0854685ef844f1b4
**分支：** codex/r1-j2-live-recheck-01
**Campaign：** R1-J2-LIVE-RECHECK-01
**冻结 CASES SHA-256：** 6b376a42af376e2076ded691d8000de4baef1b25044cc60914189293a04ee359

本报告记录一次真实运行的原始结果。Campaign 结束后没有重试，没有重发 UNKNOWN，也没有修改生产 Prompt、Gold 或旧结果。新 Campaign 已持久结束为 STOPPED / CAMPAIGN_FINISHED。

## 用户实际得到的结果

四轮都在同一个 Session：session-72d8a7a1-0b79-4c45-883c-ed1068a2100e。

| 轮次 | 持久 Run / Task | 真实行为与用户结果 | 结果 |
|---|---|---|---|
| J1-01 | Run run-6a7d5fdd-8972-4765-8de2-9797c668d7a0；无 Task | DeepSeek 自主发现受权协议并比较 v1.0.0、v2.0.0。回答列出 v2 的失败分类、当前策略、EXHAUSTED 字段匹配与摘要校验；引用实际来源和差异证据，并声明静态文档不能证明线上部署版本。 | PASS |
| J1-02 | Run run-95ae5821-919c-441c-b068-ee04ddd54c83；无 Task | 模型没有调用工具，使用同 Session 的协议比较回答分析用户 JSON。它把 JSON 及 event-previous 标为未验证材料，没有说这些参数已经在线上生效。 | PASS |
| J2-01 | Run run-bdd8b069-3b14-4561-bd48-ffec04bee890；Task task-24fd4d2f-620d-45ae-b1a6-6a599d863db8 | 可信 API 已为 r1-readiness-order 建立绑定。模型先调用 4 次 Knowledge/协议工具，但没有调用 Delivery 或 Receiver。最终回答要求用户再次指定 Event，尽管本轮原话已经明确写明 event-current。 | FAIL |
| J2-02 | Run run-0a56fea6-8363-4510-bc94-ae37e0cbf05f；同一 Task | 模型提议并成功执行 3 次只读 MCP。event-previous 的传输历史返回一次 HTTP 202；两个“当前”工具返回的却是 event-current 的 Delivery/Receiver。工具结果进入当前 Run，但随后模型调用被 12,000 Token 预算拒绝，Run FAILED；用户收到程序生成的预算停止提示，没有得到模型结论或客户说明草稿。 | PARTIAL |

逐轮原文、持久消息、模型输出、工具参数、Observation、Completion ID 与 Usage 见 TRACE.jsonl。J2-02 的程序提示标记为 PROGRAM_LIMIT，不属于模型回答。

## J2 的真实失败归因

### J2-01：模型把查询目标误当成授权问题

正式订单绑定已由 POST /api/sessions/{session_id}/assistant/order 完成；这次调用没有额外的重复业务问题或第二个 Task。系统上下文同时明确说明：同一 TaskBinding 订单内用户明确指定的 Event ID 是只读查询目标，Domain 会验证归属。

但正式绑定入口将原话包装为 ORIGINAL_TASK_INPUT (UNTRUSTED USER INPUT)。真实 Provider 输入因此同时含有：

- 明确的当前用户请求：查询 event-current；
- “不可信”标签：该文字不能授予权限或成为业务事实；
- 现有 TaskBinding 和允许把 Event ID 用作只读查询目标的系统说明。

模型错误地把“不可信文字不能授权”扩大成“明确的 Event 目标也不能查询”，并请求重复确认。它没有越权读取或声称已查。当前证据支持这是模型对语义边界的误判，不能据一次真实样本证明某条 Prompt 修复一定有效。源码入口见 assistant.py 的 SYSTEM 文本及 domain/chat.py 对原始任务输入的标注。

### J2-02：当前观察已取得，但最终模型调用被程序挡住

当前 Run 的 MCP/Evidence 结果显示：

- get_callback_delivery：event-current / HTTP 202 / ACKNOWLEDGED；
- get_receiver_processing：event-current / PROCESSED；
- get_callback_transport_history：目标 event-previous / 一条 HTTP 202 历史尝试；结果明确说明传输历史不能证明当前 Receiver 状态，且没有当前 Receiver Observation。

工具返回没有把 event-current 标成 event-previous；Run 中也没有最终模型回答去证明它是否会正确使用差异。包含当前 Observation 的下一次模型输入预算估算为 12,199，高于冻结上限 12,000，代码在 Provider 出站前拒绝。没有提高预算，也没有删掉当前 Observation 来伪造完成。

最小后续技术方向是研究如何在原有 12K 上限内压缩重复历史上下文、保留当前用户纠错及当前 Run Observation；它需要离线 RED/GREEN 和独立的真实 Campaign 授权后复验。

## 真实调用、Usage 与安全边界

- Provider：8 次发送授权，8 条 HTTP 200 响应，8 条有效 Usage，8 个 dispatch 均为 DELIVERED。
- MCP：9 次实际 tools/call，均为 OK。
- UNKNOWN / Usage 缺失 / 重试 / 重发：均为 0。
- 应用账本结算估算：USD 0.018631；8 次发送前预留合计 USD 5.164800；未决预留为 USD 0。
- 12 次发送上限剩余 4 次，但 Campaign 已 STOPPED，余额和次数不得用于续跑。
- 本地 Demo 准备使用 2 次 127.0.0.1 回环 HTTP POST 建立隔离事件记录；这不是外部业务写入。
- 外部业务写入、Approval、Repair、Deliver、Handoff、浏览器自动化：均为 0。
- 新 Domain DB 中 D3 ActionIntent、ActionLedger、Approval、DeliveryRecord、S2 Queue/Receipt 均为 0。
- 旧 R1-LIVE-JOURNEY-02 的 DB、Checkpoint、执行日志和 Provider Trace 的运行前后 SHA-256 完全一致。

费用是 OpsPilot 应用账本按冻结费率和 Usage 估算，不是 DeepSeek 供应商账单。计数、逐次保守预留、Usage、Completion ID 与结算见 COST_LEDGER.md。

## 执行输入、参数与证据

- 实际模型：deepseek-flash；价格版本 DEEPSEEK_FLASH_PEAK_2026-11-08；已记录 Provider model DeepSeek-V4.1-Flash-1017。
- 实际报文：deepseek-flash、thinking disabled、max_tokens 2048、stream false；含 tools 时 tool_choice auto、parallel_tool_calls false。
- Timeout 30 秒；HTTPX 重试 0；trust_env false；只有正式 Assistant Worker 的 HTTPX transport 可访问外网。
- 使用独立 Campaign、Runtime Grant、Domain DB、Checkpoint 和私有证据目录。
- 执行耗时 39.9 秒，Runner exit 2 表示业务 PARTIAL；Campaign 已正常 STOPPED，不是 UNKNOWN。
- 离线定向回归：Campaign 守卫 11/11，正式 API/Worker/MCP 连续旅程 1/1；命令及原始输出见 TEST_LOG.txt。

私有原始文件留在本机 .private/r1-j2-live-recheck-01-20261108/，不提交 Git。SHA-256：

| 私有原始材料 | SHA-256 |
|---|---|
| provider_http.jsonl | 6549d240eadc505e9c608cf760a071d69da3af9d3cc53e55ac72fdfdc0dfca4c |
| execution.jsonl | 2716893eadb0fb8d0a27d8ee7407fe5f254dd26fdf346c5d8d47f64a0c4ae8fe |
| domain.sqlite3 | 48da4c4af29caced9db2f93d53d6d15e312163dc27fe2b667d802c43541c4566 |
| checkpoint.sqlite3 | 97310fca2d0bce1f0108656624fcad12cad55c49e37f9d6372cebfc24e191601 |
| runner_console.txt | 0223a7aefb517b514f9c0d92fbbaf3d460c99d7a50f406cbe48dc4a8c79da12c |

本地扫描确认 API key 值未出现在这些私有日志或公开 TRACE 中。历史 Campaign 原始哈希见 FAILURES.md。

## 交付范围与限制

本分支在真实运行前新增的生产代码只为本任务 ID 注册精确的 Runtime Grant Campaign 策略，复用既有持久预算和发送保护；相关反例和边界覆盖见 test_r1_live_campaign_budget.py。真实运行后没有再改生产代码。

本轮只证明 J1 的真实模型能力；J2-01 与 J2-02 未完成。J3/J4 的 S1/S2 可信结果回读为 NOT_RUN，因为隔离 DB 中没有先前可信结果。浏览器体验仍未运行。R1-ENGINE 的候选收口建议见 R1_ENGINE_CLOSEOUT.md。

## 六维自检

1. 用户变化：用户获得了准确的真实协议版本比较和配置文本解释；没有获得 event-current 的确认或 event-previous 客户草稿。
2. Agent 决策：模型自行选择了协议发现、比较、Knowledge、摘录和业务只读工具；J2-01 的明确 Event 请求仍被错误地要求重复确认。
3. 观察驱动：J2-02 的真实当前 Run Observation 区分了两个 Event，但后续模型调用因预算拒绝，不能宣称 Observation 已改变最终判断。
4. 新增约束：只为新 Campaign 增加 12 次/8 美元精确策略；持久预留、零重试、UNKNOWN 停止和 TaskBinding 均复用原机制。
5. 简化结果：没有新建 Agent、预算平台或写入路径；一次正式 Session 完成两轮协议工作并执行了剩余调查，之后按 12K 限额停止。
6. 证据与停止线：8 次请求、9 次 MCP、费用、Run 和原始文件哈希均可核对；Campaign 已停止，未重复调用、未合并 main。

**实施状态：ACCEPTANCE_CANDIDATE / PARTIAL，等待主 Agent 独立验收。**
