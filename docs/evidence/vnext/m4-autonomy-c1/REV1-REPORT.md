# M4-AUTONOMY-C1-REV1 实施与验收候选报告

**状态：** `ACCEPTANCE_CANDIDATE`（等待主 Agent 独立验收；不代表 PASS）
**仓库 / 分支：** `wgqa/OpsPilot` / `codex/m4-autonomy-c1`
**审查基线：** `main@77ea80e87e538f0f1fae8118ef231ec622601755`
**代码提交：** `b12d387ee6cc5370b69b6809a0e306bb748c8e6b`
**验收冻结：** `e313b7a`（REV1）及 `d12fa21`（补充验收）；有效 RED 记录为 `cef50e9`。
**证据提交：** 本报告随独立证据提交；最终 SHA 由交付消息给出，避免自引用。

## 开工核验与变更范围

开发前核对了工作区、实际 HEAD 和远端 main。当前 main 经 `git fetch origin main` 复核仍为 `77ea80e87e538f0f1fae8118ef231ec622601755`，候选分支从该版本合入并继续开发。总纲、Agent 规则及 REV1 冻结验收标准在开工时已重新读取；冻结标准见 `REV1-ACCEPTANCE-ADDENDUM.md`，原 C1-01～08 Gold、报告与历史证据保持原样。

代码提交包含 21 个应用与测试文件：Vue 工作台/API/样式；聊天 Domain、TaskControl、调查上下文与更新、MCP、Investigator、S3 调查和 Web API；以及聊天、TaskControl、MCP、S1/S2/M1–M3 回归测试。改动新增同 Task 的持久只读调查结果和恢复关联，保留 TaskControl revision、当前 TaskBinding/授权、既有累计预算与 Gate；只读追问不会写正式 S3 Diagnosis、Plan、Approval、ActionIntent、Ledger、Queue 或 Receipt。页面在来源调查恢复前隐藏冲突的普通聊天回答，避免旧回答短暂冒充持久调查结果。

相对实现提交的应用 Diff 为 21 个文件、828 行新增和 39 行删除。证据提交只包含本轮报告、已明确关联的运行轨迹/日志，不包含 SQLite 数据库、Checkpoint、`.npm-cache`、Knowledge/Skill 本地文件或其他未提交工作目录内容。提交前对选定 Web Trace 与服务日志执行了凭据模式扫描，未发现 API key、Bearer 或 Token 匹配项。

## 用户变化与模型实际决策

用户现在可以在 S3 Task 调查后继续追问“按当前绑定协议核对 HTTP 202 的含义并提供可查依据”。系统将该消息作为不可信用户输入，关联到原 Task 和新只读 Investigator Run；模型可在合法工具集合内决定是否需要协议 Knowledge、业务只读证据或澄清。

真实浏览器验收中，DeepSeek 在同一 Task 选择了 `search_callback_knowledge`，取得绑定 `contract_version=2` 的 `receiver-ack-contract-v2`（版本 `2.0.0`，digest `76abb504…bf3a70`），随后查询回调投递和接收方状态。模型据此说明 HTTP 202 表示接收方已将事件持久入队，不能证明业务处理完成，并引用了同一事件的 202、`QUEUED` 和 300 秒 SLA 证据。模型没有改变 Gate、授权或业务状态。

## 真实 Web / Provider / MCP 轨迹

成功旅程位于 `runs/rev1/web-e2e-04/`，包含实际 Web 服务、隔离 SQLite Domain、Provider/MCP 结构化 Trace、服务日志、浏览器刷新观察和 Trace 导出脚本。

- Web：`http://127.0.0.1:5175/`；后端：`http://127.0.0.1:8001/`；实际操作者 `support-a`。
- Session：`session-83d92f78-9dc6-4069-9de8-d607812eab97`；Task：`task-c1dc432b-8311-4766-a407-77efeaa76749`。
- 初次调查 Run：`run-01cb289a-ffa5-4e17-a9ee-4bd98bd48377`；追问来源 Message：`message-e9d75701-6bc1-4714-a441-8a94e972777c`。
- 持久追问 Investigator Run：`run-c1-followup-d2086ae7-a00e-4614-a441-8a94e972777c`，结果 `ANSWERED`，来源回链到该 Message。
- 当前只读事实：订单 `async-order` 为 `COMPLETED`；同一回调 Event `event-856279ea-3f36-403f-98ed-51bf0886771d` 的投递 Evidence `evidence-dda45a86-84d6-4f2e-b6f0-d21b0201f221` 显示 HTTP 202 / ACKNOWLEDGED，接收方 Evidence `evidence-87697079-f3d9-4d93-be3c-6a07fd94a257` 显示 `QUEUED` 和 SLA 300 秒。
- 最终页面刷新后显示持久追问卡和来源 ID，旧的 CHAT_READONLY 回答不可见；记录见 `runs/rev1/web-e2e-04/BROWSER-REFRESH.json`。第一次刷新发现 Inspector 水合前旧回答短暂可见，已修复并另存 `BROWSER-REFRESH-INITIAL-01.json`。屏幕截图在实时 CUA 交互记录中，未作为本地 PNG 文件保存。
- 初始调查与跟进 Investigator 共消耗 Task 预算上限的 8 次模型调用和 6 次 MCP 调用；四次初始模型调用为 10,009 tokens，四次追问调查调用为 10,222 tokens。分类器真实调用为 1,047 tokens，普通聊天 sidecar 为 3,709 tokens，合计 24,987 tokens。sidecar 回答已从用户展示中隐藏，但仍会额外消耗一次模型调用，这是已知成本限制。
- 追问结果的业务 Gate 仍为 `NEED_MORE / S3_CURRENT_FACTS_REQUIRED`，不产生 Diagnosis。`WAITING_HANDOFF` 状态、TaskControl revision `0`、初次 Diagnosis 均保持不变；Approval、Plan、ActionIntent、Ledger、Queue、Receipt 计数均为 0。

两次早期真实 Web/Provider 尝试保留在 `web-e2e-02/` 与 `web-e2e-03/`。E2E-02 未取得能回答协议问题的 Knowledge；E2E-03 检索到了不适用的订单生命周期协议，且部分回答被错误归为 `ANSWERED`。这些失败促成了更聚焦的 Knowledge 查询和结果标记校验；最终 E2E-04 取得正确的接收确认协议，并明确给出可核验的 202 语义。

## 验证结果

- 定向回归：79 passed，日志 `runs/rev1/target-full-regression-03.log`。覆盖 C1 同 Task 跟进、S3、TaskControl、对话纠错、S1/S2/M1–M3 相关安全回归。
- 全量 pytest：323 passed，276.22 秒，日志 `runs/rev1/full-pytest-final-03.log`。运行时从用户本地 `.env` 仅在进程内读取模型配置，没有打印或复制密钥；排除了历史预实现 RED 文件 `tests/test_m4_autonomy_c1_red.py`，因为它冻结的断言是“基线必须拒绝 FOLLOW_UP”，在实现后本来就应失败。该原始 RED 文件及历史结果仍保留。
- 前端：`npm run typecheck` 通过；`npm run build` 通过，产物由 Vite 8.3.4 构建；`npm exec -- eslint src/App.vue` 退出码 0。
- 环境：Python 3.12.14、pytest 9.1.1、FastAPI 0.137.1、LangGraph 1.2.16、langgraph-checkpoint 4.3.0、langchain-core 1.7.0、langchain-openai 1.7.2、MCP 2.3.0、uvicorn 0.49.0；Node 24.16.0、npm 11.13.0。
- 全量测试不包含真实 Provider Web E2E；真实 E2E Trace 单独记录，避免把模型和浏览器轨迹伪装成 pytest 结果。

真实 Provider 调查体现了观察驱动的下一步：订单状态先确认已完成，随后检查投递，再检查接收方排队；用户转而询问协议语义后，模型查找匹配版本的接收确认 Knowledge 并核实相关只读事实。TaskBinding、租户、授权、工具集合、预算扣减、证据有效性、Gate 与业务状态仍由可信程序控制。

## 六项正式审查问题

1. **用户变化：** 能在同一 S3 Task 中继续完成有来源的只读协议补查，不再只收到通用聊天回答。
2. **Agent 决策：** 真实模型选择了 Knowledge 与合法的回调/接收状态工具；是否需要追问调查不由固定工具序列强制。
3. **观察驱动：** `COMPLETED`、ACKNOWLEDGED/202、QUEUED/SLA 以及匹配协议版本改变了解释路径；结果明确不等于业务恢复。
4. **约束与合法任务影响：** 新路径仍需同 Task、有效来源、当前授权和有限预算，并保持只读；正向 Web 旅程和既有越权/写入回归通过。隐藏 sidecar 不改变其仍会占用模型成本的事实。
5. **简化结果：** 复用现有 Investigator、MCP、TaskControl、Evidence 与 Context Provenance，只新增窄的持久追问结果关联，没有引入通用 Agent Runtime 或业务写能力。
6. **证据与停止线：** 冻结、RED、修复、真实 Web/Provider/MCP Trace、失败记录和测试日志已分开保留。当前只提交 C1-REV1 验收候选，停止于本阶段，不进入 C2。

## 已知限制与裁决边界

- 真实 Provider 的直接解释路径（完全不触发只读 Investigator）只由确定性测试覆盖，本轮没有独立真实 Provider 证明。
- Chat sidecar 仍运行并消耗 3,709 tokens，尽管 UI 按分类/结果隐藏其回答；可由主 Agent 决定是否列为后续优化。
- 最终 Gate 为 `NEED_MORE` 是预期的业务权威结果；C1 追问回答 `ANSWERED` 仅指 HTTP 202 协议问题得到有来源的回答，不能解读为 S3 Diagnosis 已完成。
- 浏览器运行在本地回环和隔离 SQLite Demo 环境；不证明生产级 IAM、外部接收系统或公网部署行为。
- 浏览器刷新期间的截图只留在 CUA 交互记录中；仓库保留结构化可访问性观察和来源 Trace。

**候选结论：** `ACCEPTANCE_CANDIDATE`。请主 Agent 独立检查源码、冻结合同、Trace、真实调用和失败记录后作出正式裁决。
