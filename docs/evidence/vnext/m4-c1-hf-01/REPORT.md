# M4-C1-HF-01 验收候选报告

**状态：** `ACCEPTANCE_CANDIDATE`

**仓库 / 分支：** `wgqa/OpsPilot` / `codex/m4-autonomy-c1`

**任务基线：** `b398e59dba03a25ef1e5f04aa197c4e918b0529f`

**开工时远端 main：** `77ea80e87e538f0f1fae8118ef231ec622601755`

**North Star Blob：** `1f737712c7a36ceb34433ac09c3fbba3c3305542`

**AGENTS Blob：** `30319000ed0054007e9b7b6b46bf98b1493c8179`

**实现提交：** `b26712732ef8659906d5799b7f30a95b83d447d8` (`fix: preserve C1 followup context across turns`)

**冻结提交：** `863a237`、`8135ab6`、`d7d6e58`、`f368f49`、`ab014cc`。最终候选分支 HEAD 见交接消息与 Git 分支。

本轮重读了指定基线中的 North Star、AGENTS、C1 Gold、REV1、FIX-01 与本任务合同。冻结标准、原始 RED 与本次补充 RED 分别保存在前述提交及 `ACCEPTANCE_PLAN.md`、`ACCEPTANCE_SUPPLEMENT.md`；未改写历史 Gold 或旧 E2E-02/E2E-03 失败。

实现复用 `investigation_context.py` 增加一个有界历史结果装配器，供更新分类器、Chat 与 Investigator 共用。它只读取早于当前消息、同租户/Session/Task 且 Run 已成功的只读补查结果；校验结果摘要与来源 Message，重新核验当前 S3 授权和 Knowledge 版本、摘要与适用性。原业务 Evidence 只作为历史引用，带 `HISTORICAL_RUN_ONLY`，不会加入新 Run 的当前 MCP Evidence。Chat Context Manifest 记录历史 Run、摘要、来源和当前性；历史 Chat 助手回答若依赖的来源后来失效，会在后续上下文中以 `PRIOR_READONLY_FOLLOWUP_SOURCE_INVALID` 排除。

task-bound `CHAT_READONLY` Run 在分类完成前保持不可领取。分类到 `INVESTIGATE` 时，同一消息的 Chat Run 被持久阻断，只创建 Investigator Run；`EXPLAIN` 时释放该 Chat Run 作为唯一回答流程。纠错仍走原确认协议。失败分类可由同一 Chat Run 降级；超时路由会被持久释放，迟到的分类不能再启动第二条链。分类、路由结果和 Worker 领取沿用 Domain 事务与 Outbox。

**真实浏览器旅程：** Edge/Playwright 运行记录与截图在 `runs/web-e2e-hf01-03/`，完整 Trace 在本目录 `TRACE.jsonl`。同一 S3 Task 首次确认为订单 `async-order`、协议 v2、回调已被接收并处于 `QUEUED`。首个补查被真实 DeepSeek 分类为 `INVESTIGATE`，Chat sidecar Run 为 `BLOCKED` 且 Chat Attempt 为零；Agent 实际调用 `search_callback_knowledge`，取得 `receiver-ack-contract-v2` / `2.0.0` / digest `76abb5047ae680dedc4c097b91918c438aaa8d04aca5e4600bd1296aa6bf3a70`，持久结果为 `ANSWERED`。

随后用户使用“你刚才引用的那份协议……”追问。分类为 `EXPLAIN`，Chat Provider 只执行一次。真实 Context Manifest 选中前一补查结果及其来源；协议来源标记为 `CURRENT_APPLICABLE`。真实回答正确区分 HTTP 202 入队与业务处理完成。确定性测试另外验证历史业务 Evidence 只保留为 `HISTORICAL_RUN_ONLY`，不会进入新 Run 的当前 MCP Evidence。

最后用户询问“那现在接收方完成了吗？”。分类为 `INVESTIGATE`，新 Investigator Run 实际调用 `get_receiver_processing`；新 Observation `observation-5f4bf60f-5d7b-49c3-ae68-720c51f8c00c`、Evidence `evidence-354f385e-e9e6-4260-9b4a-0028dd5aa9de` 均关联该新 Run 和绑定订单，当前接收状态仍是 `QUEUED`。该 Run 最终持久为 `PARTIAL`，原因 `FOLLOWUP_BUDGET_OR_PROVIDER_EXHAUSTED`，没有捏造最终回答。页面明确显示“本次补查尚未形成可展示的回答”及原因码。初始 S3 事实由实际本地 HTTP/MCP 路径读取；准备接收方 HTTP 202 的 fixture 操作单独标为测试准备，不计 Agent 行为。

修正后的 Trace 汇总记录真实模型 `deepseek-flash` 共 12 次 Provider 请求、输入 21,509、输出 6,917、合计 28,426 tokens：分类器 3 次 / 4,404 tokens，Investigator 8 次 / 19,652 tokens，Chat 1 次 / 4,370 tokens。两次 INVESTIGATE 消息都没有隐藏 Chat Provider 请求。与旧 E2E-04 隐藏 Chat sidecar 的 3,709 tokens 相比，本次没有产生同类隐藏调用；用户明确要求解释时产生的一次 Chat 回答是可见且有来源的流程。

浏览器旅程命令返回 `PASS`，但页面记录了两个非致命控制台资源错误：登录前 `GET /api/auth/me` 的预期 401，以及一个未捕获 URL 的非 API 404。登录后 API、SSE、消息和运行轮询正常。该 404 未定位到具体资源，保留为待主 Agent 判断的低优先级限制。

验证结果：C1-HF-01 新增与定向测试 13/13 通过；M2-HF stale no-op 恢复回归 1/1 通过（仅给确定性子进程注入占位模型配置，Worker 中的 `NoToolModel` 替代 Provider）；前端 typecheck、build、Python compileall 和 `git diff --check` 通过。全量 pytest 在隔离无网络占位配置下为 338 passed、1 deselected。被 deselect 的唯一用例是保留的旧 C1 预实现 RED `test_explicit_protocol_followup_is_accepted_as_same_task_readonly_run_before_ttl_fix`。未经筛选的全量首次执行为 336 passed、2 failed：同一旧 RED 仍按预期暴露历史缺口；M2 跨进程测试子进程因工作树没有真实 `.env` 而缺少模型配置，随后单独注入非密钥占位值的新鲜复跑通过。完整原始日志均保存在 `runs/`。

按 North Star 第 8 节的六项判断：

1. **用户变化：** 可以用指代词继续讨论已补查的协议；询问当前接收状态时会触发新 Run 取证。
2. **Agent 决策：** 真实分类器选择 Explain 或 Investigate；真实 Investigator 选择知识查询和接收状态查询。
3. **观察驱动：** 当前 Knowledge digest 可支撑协议解释，旧 Evidence 只能提示来源；当前接收状态来自新 Observation。
4. **新增限制及合法路径：** 分类前不领取 Chat Run，阻止隐藏重复调用；正常解释、调查、关键纠错和取消流程分别有通过测试或真实运行证据。
5. **简化结果：** Chat、分类器和 Investigator 共用一套历史来源装配及失效判断，没有新增 Memory、Goal 或 Runtime。
6. **证据与停止线：** 以冻结验收、13 项定向测试、完整 pytest、真实 Web/Provider/MCP/HTTP Trace 和截图为证；最后一问已真实取证但结果为 PARTIAL。此轮到此停止。

**验收裁决：** 实施方仅提交 `ACCEPTANCE_CANDIDATE`，不签署 PASS、不合并、不启动 C2。已验证范围是跨轮只读补查来源续接、来源失效和同消息 Chat 路由幂等；未验证的是最后一次新事实查询能否在预算内再产生完整自然语言答复，以及非 API 404 的确切来源。这些限制供主 Agent 独立审查。
