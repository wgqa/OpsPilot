# AR-02-REAL-JOURNEY — 免费准备与真实实验冻结计划

**状态：** `FREE_PREPARATION_ONLY / PAID_PROVIDER_NOT_AUTHORIZED`
**仓库/分支：** `wgqa/OpsPilot` / `codex/ar02-live-01`
**冻结基线：** `d576bb9dbad8ee96500de14bd215fcf26e1fb527`
**远端 main：** `UNVERIFIED`（本次 `git ls-remote` 连接 GitHub HTTPS 443 失败）

## 开工快照

目标 worktree 为 `D:\学习\agent新项目\.worktrees\ar02-live-01`，分支跟踪 `origin/codex/ar02-live-01`；开始时工作树干净，HEAD 与远端候选均为冻结基线。根工作区 `D:\学习\agent新项目` 有另一分支和未跟踪资料，不在本任务修改范围内。

本次实际重读的文件版本：

| 文件 | 基线 Blob / SHA |
|---|---|
| `PROJECT_NORTH_STAR.md` | `1f737712c7a36ceb34433ac09c3fbba3c3305542` |
| `AGENTS.md` | `32c45506cceeaa8c76a5c56bf8360ff476b58856` |
| `.agents/skills/opspilot-slice-review/SKILL.md` | `d405c8d413d633824b279202cc1503dab4cf0b03` |
| Frozen S01/S02: `docs/evidence/ar-02/hf-01/SMOKE_INPUTS.md` | `ee9b1623a2296905c425449709a2f9ae6563caca` |
| `docs/evidence/ar-02/live-01/ACCEPTANCE_PLAN.md` | `6ea52b2ee584a405d69d71861e48515b69b76d03` |
| `docs/evidence/ar-02/live-01/PREFLIGHT.md` | `5aa555530adeec356933baaacf12139e6017a048` |
| `docs/evidence/ar-02/live-01/p1/PLAN.md` | `91689a269768a15005dd205fb089875456041c8f` |
| `docs/evidence/ar-02/live-01/p1/RESULTS.json` | `a9f5159c3b852eecd40260046130d94a7611d7e0` |
| `docs/evidence/ar-02/live-01/p1/FAILURES.md` | `010de638a2efb5d3d0b3808bef751b5af82d09d4` |
| `docs/evidence/ar-02/conn-02/REPORT.md` | `ab22885137e7a73f0520e4fa915d68488dc1a571` |
| `docs/evidence/ar-02/journey-p0-hf02/REPORT.md` | `412c0ae38e69792bac1711863eb1accef64440e0` |
| `docs/evidence/ar-02/live-01-hf-02/REPORT.md` | `9b462627f790087b26b77d59cd0cefb9d6a63942` |

此轮适用约束：HF02 的 `PASS_HF02_SCOPE`；历史 Stage B `HOLD` 和浏览器 STOP 不在本轮解除；M1–M4 安全合同继续有效。历史 P1 的一次 `OpenAIConnectionError` dispatch 保持 `UNKNOWN`，旧账本中的 USD 0.645600 预留不释放、不重用、不改写；CONN-02 仅为独立连通性样本，不是 S01/S02 业务旅程证据。

## 产品 Gold

逐字复用 `SMOKE_INPUTS.md` 中的 S01 和同 Session S02 五轮输入，详见 `CASES.json`。不得调换、润色或根据模型行为改题。S01 没有绑定订单或当前业务 Observation，验收的是对 HTTP 202 的协议解释以及明确承认当前订单/Receiver 状态未知；S02 在同一 Session 中从不可信示例线索开始，在第 3 轮由可信操作确认 `ar02-order` 绑定，然后允许只读查询。

## 对照与记录

本轮真实实验计划最多 6 个用户轮次：独立 Session 的 S01 一次，以及同一 Session 的 S02 五轮。每轮经正式 FastAPI → 单一 Worker → `ASSISTANT_V1` → 当前 MCP/Domain → 持久 Session 答案。模型自主决定直接回答、查 Knowledge/MCP、澄清、继续或停止；不得规定唯一工具顺序。分别记录模型请求/工具提议、实际 MCP 调用与 Observation、最终持久答复，不能把程序 fallback 算成模型成功。

免费准备可以使用确定性替身、显式 MockTransport、隔离 SQLite 和本地只读 MCP/HTTP；不调用任何真实 Provider，不用浏览器自动化。

## 费用与停止合同

新实验身份拟定为 `AR-02-REAL-JOURNEY-01`，使用全新的隔离 Domain DB 与 Checkpoint DB，复用 `assistant_experiment` 的 SQLite 预留/结算机制。预算沿用先前已审 P1 数值：Provider dispatch ≤16，MCP `tools/call` ≤12，应用侧预算 USD 10.50；单次模型出站预留 USD 0.645600，未知、超时、取消或响应丢失保留完整预留、计入次数且不重试。16 次全额预留合计 USD 10.329600，余量 USD 0.170400。每个 Run/Task 既有限额仍同时生效，取更严额度。`tools/list` 不计入 MCP `tools/call`。

价格上界引用 DeepSeek 截至本次预检的公开峰时 cache-miss 价格：输入 USD 0.30/M、输出 USD 1.20/M，模型上下文 1M、公开最大输出 384K。计算为 `(1,000,000-384,000)*0.30/1M + 384,000*1.20/1M = 0.645600`。此为应用侧预留，不是供应商账户硬上限；Provider 超出公开 Usage/上下文边界时仍可能产生额外费用。真实调用前必须复核官方价格和冻结请求参数。

旧 P1 有一个金额未知、最多占用原 USD 0.645600 预留的 dispatch。新预算不包含、不抵扣、不释放该历史记录。若旧 UNKNOWN 最终计费，则在最坏的新实验预算外还可能发生最多 USD 0.645600 的历史费用；新旧账本并非账号级总支出封顶。

**停止条件：** 付费授权未签发前一律不发送真实 Provider 请求。未来获批后，预算预留失败、配置/模型/协议偏移、Usage 缺失或畸形、UNKNOWN 结果、自动重试、越域/授权异常、意外业务写入、证据关联失败或任何冻结硬限触达时立即停止，不修参数、不切网络、不重跑样本。无审批、REPAIR、DELIVER、工单或外部业务写入。

## 六问（Skill B）

1. **用户变化：** 可得到一轮可信的 202 语义解释，以及随后同 Session 的协议、绑定订单和当前事件状态连续调查与有来源说明草稿。
2. **Agent 决策：** 真实模型本可自主选知识/只读 MCP、澄清、按 Observation 改变后续行动或停止；当前阶段未做真实调用，尚无行为结论。
3. **观察驱动：** 订单、目标 Event Delivery 与同 Event Receiver 的真实本轮 Observation 决定可说事实；示例日志仅是线索。
4. **新增约束与合法任务影响：** 仅保留租户、TaskBinding、只读工具、持久预算和“不写业务”的已冻结边界；合法同范围查询必须有正例，缺失当前事实可明确报告未知。
5. **简化结果：** 复用现有 formal Assistant、Worker、MCP、SQLite dispatch ledger；新增一个精确 allowlist 的实验身份，不建设预算/Provider 平台。
6. **证据与停止线：** 本轮只可得免费协议/隔离测试证据；没有实际付费授权前，真实 S01/S02 一律 `NOT_RUN`。免费准备结束即停止。
