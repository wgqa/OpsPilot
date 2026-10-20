# M3-01-HF-01 补充验收报告

本轮补齐了 M3-01 的撤销竞态和最终版本证据。执行侧结果已整理为可核对证据，阶段裁决仍交由主 Agent；本报告不签署 M3-01 PASS，也不启动 M3-02。

起始 HEAD 和 `origin/main` 均为 `22823acc519789c14e2cefe8e0f4c16a05fb4b72`。冻结标准先于实现提交：冻结 `811508cf844b2d10590f44a42883d29c54e61572`，C02 原始 RED `887bf58787d09aea38cb6fbb9762000202aee9a7`，最小修复 `f6025880133c7132bd703fcbaa83b99191b7c21e`。随后仅为提高 C03 竞态证据质量提交了测试和轨迹输出：`cab76ff4996d94260072c9c260b72521ee947080`、`e9f7dd4630bda91b3691bd2973a47028a3480382`。生产实现没有在 `f602588` 后变化。

## 实现与安全门禁

C02 RED 证明真实 Investigator 在模型 attempt 已持久预留、Memory 已提交撤销后，仍把旧 Memory 放进 Provider 消息。修复在 Investigator 的每次请求预留后、Provider 调用前重新核对 Memory 当前状态、版本、摘要、来源、租户、项目、过期时间和来源回执；若不匹配，则关闭该 attempt 与 Context Provenance 为 `CONTEXT_ASSET_INVALIDATED`，并按原预算重建一次。只读 Chat Worker 在开始流式 Provider 请求前执行同一 Domain 校验。失效 attempt 保留在账本并消耗既有模型预算，未提高预算或跳过审批。

HF-C01～C06 的新鲜定向验证通过：构造后预留前撤销被拒绝；预留后 Provider I/O 前撤销会阻止旧 Context 出站；Provider 已接收请求后才撤销时保留先后顺序；Checkpoint 跨进程恢复不复活旧引用；过期、版本/状态变化和来源失效均被排除；来源于 ACTIVE Memory 的历史回答保留审计记录，但后续 Chat Provider payload 不再包含该回答或记忆 ID。C03 最终 trace 记录首个请求含 ACTIVE 记忆、撤销随后提交，后续七个有界请求均不含该记忆，见 `runs/c03-investigator-03/stdout.txt`。

## 最终源码下的真实 Web 旅程

使用最终生产实现提交 `f602588` 启动 FastAPI、Vue/Vite、SQLite Domain、LangGraph、任务绑定的 MCP stdio Server 和 Microsoft Edge / Playwright。来源 Task A `task-798b6841-82db-4976-8f41-860d0a33df0c` 的 Domain 回执证明 REPAIR 为 `COMMITTED`，配置从 v7 到 v8；同一 service、integration、principal 和 `/api/orders/demo-order` 的在线验证为 HTTP 200，订单字段 `demo-order / CONFIRMED`；随后冻结报告并完成 DELIVER。完整快照在 `runs/web-final-02/SOURCE-DOMAIN-SNAPSHOT.json`。

真实 SUPPORT Web 会话从 Task A 建立 Candidate；独立 `approver-a` Web 身份将其确认成 ACTIVE v2。浏览器创建不同的 Task B `task-f5ba2a2f-bdca-4b57-90d4-74f7ef9f8ddc`。DeepSeek `deepseek-flash` 共完成 5 次 Investigator 请求，其中 4 次 Context Provenance 明确选择 Task A 的 Memory；本轮调查累计报告 19,575 输入、1,195 输出、20,770 总 token。真实 MCP 工具调用依次读取 Policy、Integration、Principal 并 Probe，业务路由返回 401，版本为 config 7 / policy 3 / principal 2。Gate 将其保留为 S1 `AUTHENTICATION_FAILURE_REMAINS_S1`，Run 停在 `WAITING_APPROVAL`；Task B 没有 REPAIR 或 DELIVER Ledger，Scope Grant 与运行前相同。

随后 `approver-a` 在 Web 撤销 Memory，状态变成 REVOKED、版本递增到 v3。用户在 Task B Web 对话中追问后续核查方向，产生真实 `CHAT_READONLY` DeepSeek Run 并成功；该调用有 898 输入、1,320 输出、2,218 总 token，ContextManifest 的 Memory refs 为空，当前适用 Memory 列表也为空。八张本次真实浏览器截图、294 条浏览器 API 响应记录及 Domain Outbox/SSE 快照均已保存：本 Session 有 325 条 Outbox、326 条持久 Session Event，其中追问 Run 写入 318 个持久 Chat Chunk 并提交最终答案；9 条浏览器 API 请求命中 `/events` 路径。明细见 `runs/web-final-02/screenshots/BROWSER-TRACE.json` 和 `runs/web-final-02/SESSION-SSE-SNAPSHOT.json`。UI 另记了 10 条控制台 401/404 噪声，来自登录前身份查询及尚未选中 Task 的空选择请求；完整业务旅程 API 返回成功，未掩盖这些日志。

## 全量和定向验证

最终测试代码提交 `e9f7dd4` 上新鲜运行完整 pytest：204/204 通过；M3/S1/S2 定向组：47/47 通过。前端生产构建和 ESLint 均退出码 0。独立真实 MCP stdio smoke 列出 4 个只读工具并完成 4 个绑定范围内调用，Probe 实际 HTTP 401；跨租户资源调用被拒绝为 `RESOURCE_OUTSIDE_TASK_SCOPE`。跨进程恢复 smoke 使用两个不同 Python Worker PID、真实 MCP stdio 和实际 HTTP 401；确定性测试 Provider 在恢复后的模型 Context 中没有旧 Memory。命令、完整 stdout/stderr、退出码及源码 manifest 见各 `runs/` 子目录。

运行依赖：Python 3.14.0、pytest 9.1.1、LangChain 1.4.1、langchain-openai 1.7.2、LangGraph 1.2.16、langgraph-checkpoint-sqlite 3.1.2、MCP 2.3.0、FastAPI 0.137.1、Pydantic 2.14.1、Node v24.16.0、npm 11.13.0；锁文件为 `requirements.lock.txt` 与 `frontend/package-lock.json`。模型 ID 为 `deepseek-flash`，密钥只在本地环境中使用，未写入证据；对新证据文本执行了密钥泄漏扫描，0 个命中。

## 原评测结论与范围

M3-01 冻结评测保持原样，未重跑、未修改 Gold：8 对 / 16 臂，12/16 Outcome 符合 Gold；P03/P04 的 ON/OFF 均为 `HANDOFF_READY`，仍与允许结论不符；效用保持 `UTILITY_NOT_PROVEN`，Provider 费用保持 `NOT_REPORTED`。本轮没有据此宣称 Memory 提升了诊断效用。

所有 115 个被冻结文件 SHA-256 与 `FROZEN_SHA256SUMS.txt` 一致，原 M3-01 证据未改动。既有用户 `AGENTS.md`、`PROJECT_NORTH_STAR.md`、`开发目录/` 和早先未提交文件没有被暂存或覆盖；最终 Git 状态见交付时的终端记录。实现仍是单机本地 SQLite Demo，跨进程恢复和双角色审批证据不代表生产级 IAM 或分布式部署。

本轮有真实 C02 违例并已按 RED → 最小修复 → GREEN 处理；另有测试运行器临时目录权限、错误选择源 DB 缺少 SUPPORT Session link，以及两项测试断言过严，均原样记录在 `FAILURES.md` 并有独立后续运行。没有未解决的本轮安全硬失败。执行侧建议主 Agent按门禁复核本报告、机器结果和原始轨迹，再独立签署裁决。
