# OpsPilot vNext M1-06 整体独立验收报告

**结论：** `PASS_PENDING_MAIN_AGENT_REVIEW`。本报告只表示 M1-06 冻结验收项均有本轮新鲜证据；不自行签发完整 M1 PASS，等待主 Agent 独立复核。M2 尚未启动。

**开发基线：** `main@4aca4b5d3cbae511d36f65df3f9f0adc2849c723`。**最终提交：** `main@d74517d925cebb6e99c38dbbc01919c8064a44ed`。最终验证时 `origin/main` 与 HEAD 一致。冻结判据在本轮任何测试及真实 Provider/MCP 调用前提交，文件为 [ACCEPTANCE_PLAN.md](ACCEPTANCE_PLAN.md)。

## 结果

M1FIN-01 至 M1FIN-12 按冻结判据均为 PASS，逐项机器结果见 [RESULTS.json](RESULTS.json)，完整源码、日志、轨迹和截图路径见 [EVIDENCE_INDEX.md](EVIDENCE_INDEX.md)。拒绝路径由计划中明确指定的新鲜 APR-04 确定性集成测试证明；它不被描述成浏览器或真实 Provider smoke。批准路径由新鲜 Edge、真实 Provider、MCP、HTTP、Domain Ledger 与进程重启恢复共同证明。

| 项目 | 新鲜结果 |
|---|---|
| 全量 pytest | 116 passed / 0 failed，71.81 秒，commit `d74517d` |
| 定向关键回归 | 9 passed / 0 failed，14.41 秒 |
| 前端 | `npm run typecheck`、`npm run lint`、`npm run build` 均 exit 0 |
| Python 环境 | `pip check`、`compileall` 均 exit 0 |
| 真实浏览器入口 | 3 次：M1-04 第一次 FAIL，修正后 M1-04 PASS，M1-05 PASS。第一次失败保留在失败分母中 |
| 三次浏览器/Provider smoke 累计 | Provider 成功响应 47 次、MCP tools/call 28 次、模型返回 Token 110,799；包括失败的 M1-04 浏览器入口已成功完成的真实模型调用，不是性能指标 |

最终测试日志列于 `runs/20261018T115200Z/logs/`。环境为 Windows、本地 loopback Demo、Microsoft Edge 155.0.4283.45；锁文件、依赖版本与哈希见 [RUN_MANIFEST.json](RUN_MANIFEST.json)。没有使用生产凭据或真实业务服务。

## Edge + Provider + MCP 的调查与多轮对话

修正后的新鲜 M1-04 Edge Run 位于 `runs/20261018T115200Z/m1-04-rerun-01/runs/20261018T115753Z/`。它在一个持久 Session 中执行 5 个真实聊天 Provider 响应，真实 Investigator 共 16 个 Provider 调用、12 次 MCP tools/call；模型及 MCP 轨迹和实际 Token 记录在 `RESULTS.json` 与相邻原始日志中。浏览器重启前 PID 31276，重启后 PID 27380；服务恢复后重新读到 10 条用户消息和 5 条助手消息，并找回 `BLUE-ORBIT`。

NL-A 与 NL-B 使用同一可信 `orders-demo / integration-a / principal-a / /api/orders/demo-order` 绑定，真实 Prompt digest 分别为 `3207d029…c60fa` 和 `22bd8bd9…f0809`。NL-B 对主体停用的怀疑没有升级为事实；MCP 返回当前主体为 ENABLED、配置为 v7/`cred-v1`，真实 Probe 为 HTTP 401。用户初始消息 ID、摘要、Run 和 Context Provenance 均在持久结果里。模型工具顺序存在差异但不是通过条件，Gate 仍由 Domain Evidence 决定。

正式纠错 Run 将控制版本推进到 2，使旧 Plan `80aa17dd…db913` 变为 `CANCELLED`，新 Plan `45082c02…11293` 依据新 Run 生成并等待审批。403/Scope 越权请求到达 `WAITING_INPUT`，该 Task 的模型调用、MCP 调用与 Evidence 数均为 0。整个 M1-04 Run 对所有业务任务的审批、Intent、Ledger、修复、验证、报告与交付计数均为 0。`CHAT_READONLY` 保持只读。

浏览器检查值为 8 个 true；冻结矩阵中的 NL-05 由同一轮新鲜的 N1-09/10/11 定向回归覆盖，所以 M1-04 结果 JSON 中该浏览器子项保留为 `null`，没有把未运行的浏览器断言填成 true。完整列表与原始 HTTP/截图见该 Run 的结果、logs 和 screenshots。

## Edge 双角色批准与业务闭环

新鲜 M1-05 Edge Run 位于 `runs/20261018T115200Z/m1-05/runs/20261018T115934Z/`。SUPPORT `support-a` 提交同一不可变 Plan，独立 `approver-a` 审批；来源 Run `run-47da6233-ae63-4f7f-80a9-bc0b4554b124` 保持 `WAITING_APPROVAL`。唯一 `APPROVAL_RESUME` Run `run-c4f81a6e-3a01-47e7-9eb2-7b1cfbc36d3e` 通过原 checkpoint thread `opspilot-b3459a89-2aaf-4ef7-935c-d6e609c88056::run-47da6233-ae63-4f7f-80a9-bc0b4554b124` 恢复，最终 `SUCCEEDED`。Plan hash 为 `43de79c0ec15b573bd5621a8b73d2a583392802503e7310ebbd3c1eb170b6aa2`，Approval ID 为 `approval-79835a87-6aa6-44ab-9e83-32b6b8502827`。

真实 Investigator 调用 `deepseek-flash` 5 次，全部返回 OK，Provider response ID 和实际 Token 数在 `RESULTS.json`；MCP Client/Server 成功调用 `get_integration_config`、`get_auth_policy`、`get_principal_status`、`probe_endpoint`，各自 Evidence ID 也在 [机器轨迹](RUN_MANIFEST.json)。初始 Probe 为 `cred-v1`、配置 v7、固定业务 route HTTP 401；获批 REPAIR 将 Config 从 v7 CAS 到 v8/`cred-v2`。同一 service、integration、principal 与业务 route 的真实验证返回 HTTP 200，响应字段 `order_id=demo-order`、`status=CONFIRMED`，最终业务结果为 `DELIVERED`。

Domain 最终计数为 2 ActionIntent、2 ActionLedger、2 独立 ActionPermission、1 VerificationReceipt、1 Frozen Report、1 DeliveryRecord、1 TicketEntry。REPAIR Ledger 为 `ledger-dfbcb7d7-1e37-45f8-8a1e-3087af2e12b2`，DELIVER Ledger 为 `ledger-577b7964-43c0-4133-8f96-25f9e4806d4c`；验证、报告、投递与 Ticket ID 见 RUN_MANIFEST。浏览器截图保留审批复核、等待审批、丢失响应和最终 DELIVERED 状态。

## 拒绝、控制、权限与崩溃恢复

冻结方案要求 APR-04 用确定性新鲜集成测试证明拒绝路径，不要求消费模型 Token。定向测试 `test_apr04_rejection_resumes_original_graph_without_action_intents` 本轮通过：独立 approver 的 REJECTED 决定由新 resume Run 恢复原 Graph，保留拒绝结果；ActionIntent、REPAIR/DELIVER Ledger、DeliveryRecord、TicketEntry 均为 0，Config 保持 v7。`test_n1_09...` 与 `test_apr05_abort_after_approval_blocks_resume_before_checkpoint_access` 通过，旧 checkpoint 不越过 Task abort。此处没有宣称发生了拒绝浏览器 smoke。

N1-09/10/11 定向测试均通过：跨进程终止与旧 Run 续跑被 TaskControl 阻止；关键纠错提升 revision 并使旧 Plan 失效；已提交 REPAIR 不回滚，未提交 DELIVER 被阻断。安全 HTTP 轨迹另证明跨租户读为 404、未列出的 Origin 为 403、Approver 只读 API 为 200；全量既有权限回归通过。

M1-05 实际响应丢失故障窗：审批事务提交后，API PID 32416 以退出码 86 终止，Edge 收到 502；随后新 API PID 接续。REPAIR Ledger COMMIT 后、HTTP 响应前 PID 14648 以退出码 87 终止；新 API PID 17240 恢复并完成验证/交付。最终审批、REPAIR、DELIVER 及 TicketEntry 各只有一个。该 Session 有 850 个已持久化事件（含 `SESSION_CREATED`），Task 事件投影有 849 条、序号唯一且递增，范围为 2–851；原始审计观察到 846 处序号间隙。只读对账确认 850 条匹配的 Domain Outbox 记录全部已有投影，反向也无脱离 Outbox 的投影行；因此没有把游标序号描述为无间隙。事件恢复和 N2-01 故障测试通过。D4 `ACTION_OUTCOME_UNKNOWN` 回归仍要求没有 Domain 回执时保持未知，不能由 checkpoint 或聊天猜测成功。

审批等待期间，M1-05 的活跃预算在只读聊天前后均为 7,877 ms，deadline 为 600,000 ms，说明等待/CHAT_READONLY 未扣除活跃执行预算。Provider 实际 Token 只汇报供应商回传值，未从失败或无 usage 的请求合成用量。M1-04/M1-05 各 Provider、MCP、ContextManifest 和事件轨迹保留在新鲜结果文件。

## 失败、修复、历史局限与范围

本轮唯一真实浏览器入口 FAIL 是 M1-04 首次运行等待了旧 approver selector `.rail-footer`。认证与待办 API 已分别返回 200，当前 Approver workspace 使用 `.approval-center`。失败原始日志、截图和失败时 Domain 脱敏快照均原样保留；先提交 `PLAN_AMENDMENTS.md` 后，仅将 E2E ready selector 改为角色对应页面，未改产品代码、权限、Gold 或业务逻辑。修复后在全新 Domain/Checkpoint DB 中重跑通过，随后在最终 commit 上完成 116/116 pytest 和全部前端/依赖检查。详细逐次记录见 [FAILURES.md](FAILURES.md)。

为生成失败 Run 的只读快照，诊断查询最初误把 `task_bindings.session_id` 当作列，SQLite 返回 `no such column: session_id`；未写数据库。这个非产品诊断错误没有在发生时重定向保存，故报告用明确标为事后说明的 note 记录，没有伪装成原始 stdout。后续 schema 检查和成功提取、脱敏快照均已保留。D6/D7 历史文件未改动：D6 仍是 9 PASS、E10 PARTIAL，固定通用 Memory 局限仍存在；D7 首次 E01 失败和 61/64 初次测试记录仍在原位。M1-06 未解决长期 Memory 压缩/效用评测，未增加产品架构能力；不宣称生产 IAM、生产业务集成、分布式 exactly-once 或多模型 Gateway。

本轮仅新增 M1-06 验收、运行证据及学习材料，唯一代码更改是 M1-04 Playwright 的 approver-ready selector。所有准备材料和原始任务卡在仓库 `开发目录/` 中均未更改。主 Agent 复核前停止开发，M2/M3/M4 均未启动。

## 报告与复核入口

- 冻结判据：[ACCEPTANCE_PLAN.md](ACCEPTANCE_PLAN.md)
- 单独变更说明：[PLAN_AMENDMENTS.md](PLAN_AMENDMENTS.md)
- 失败与修复：[FAILURES.md](FAILURES.md)
- 逐项机器矩阵：[RESULTS.json](RESULTS.json)
- 运行与版本：[RUN_MANIFEST.json](RUN_MANIFEST.json)、[RUNBOOK.md](RUNBOOK.md)
- 原始日志、Provider/MCP/HTTP/Domain/Checkpoint 和截图：[EVIDENCE_INDEX.md](EVIDENCE_INDEX.md)
- 白皮书源码地图、学习笔记和面试材料：`docs/learning/M1-06/`
