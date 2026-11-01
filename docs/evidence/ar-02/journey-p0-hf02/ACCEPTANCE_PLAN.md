# AR-02-JOURNEY-P0-HF02 冻结验收计划

## 开工核验

- Repo：`wgqa/OpsPilot`
- Branch / Base HEAD：`codex/ar02-live-01@990d977755854100f1718a5266499859a09dbacd`
- 本地工作区：clean；本轮仅使用 `D:/学习/agent新项目/.worktrees/ar02-live-01`。
- 本地 `origin/codex/ar02-live-01` 跟踪指针为 `990d977`。`git ls-remote` 当前因 GitHub HTTPS 443 连接失败不能刷新远端指针；GitHub API 已从目标分支读取到 HF01 报告，精确远端 HEAD 标记 `UNVERIFIED`。
- `PROJECT_NORTH_STAR.md` Blob：`1f737712c7a36ceb34433ac09c3fbba3c3305542`；本轮已实际读取 §8。
- `AGENTS.md` Blob：`32c45506cceeaa8c76a5c56bf8360ff476b58856`；本轮已实际读取全文。
- `.agents/skills/opspilot-slice-review/SKILL.md` Blob：`d405c8d413d633824b279202cc1503dab4cf0b03`；本轮已实际读取 A/B/C 及验收证据要求，并执行 A 节开工核验。
- HF01 源码/证据 Blob：`opspilot/assistant.py=85aba2e9559079ac5d033f68586b800960dece87`；`opspilot/domain/assistant.py=2987bdbee9a2e6d0007082970a6c7809824ff995`；HF01 测试=`850d6c8f9fed26112301d576893ea573b622e18c`；HF01 冻结计划=`746a8c753364210e5124009ccbc8ef675a3e5239`；报告=`98c305793680286d9edc57a81d9093dcf1f27677`；结果=`a8598d7bf25c8834f835fa4aeb5fbc43e951df38`；失败记录=`f7d9137cbfa43e4ea3cdb8ae3507dbfb95c89587`。
- 适用合同：本对话 HF02 任务卡；HF01 `ACCEPT_WITH_LIMITS` 及其原始 RED/GREEN、Trace；AR-02 P0 既有冻结 Gold 与失败记录。AR-02 的真实 Provider 与浏览器仍未获本轮授权；HF01 继承全量结果为 489 passed / 4 failed，本轮不冒充重跑。

## 本轮目标与边界

仅关闭两个验收缺口：未暴露工具提议不能以 `OK/null` 保存、缓存或作为历史有效来源；以及同一 Task/Event 的 Receiver 查询真实失败时不产生成功的当前 Receiver Evidence，答复必须保留处理状态未知。保留现有 QUEUED 正例和未查询 Receiver 正例。禁止修改 Gold/Schema、授权范围、业务写语义、旧日志或旧 Trace；Provider、浏览器和业务写入均为零。

## 冻结测试

### HF02-01 — 未暴露工具、缓存及历史来源

通过正式 API、Worker、`ASSISTANT_V1` 和 FixtureModel 在无 TaskBinding 的 Session 明确提出 `get_order_status`。工具未暴露时不能调用 ToolNode/MCP；持久审计只能明确表示失败/未执行，不能是成功的 `OK/null`，且不得创建 D2 Attempt、Observation、Evidence 或业务 HTTP 读取。以受控恢复/缓存检查证明历史 `OK/null` 记录不会被重放；历史来源检查不得将该记录装入可信当前来源。反向正例继续验证：Knowledge 返回 `documents=[]` 的真实空查询仍是合法字典结果；可信绑定后的授权 MCP 订单读取仍可成功并产生实际 Observation。

### HF02-02 — Receiver 工具已调用但查询不可用

同一 Session、Task、订单、Event 与问题先真实查询得到合法 `QUEUED`。第二个 Run 中 FixtureModel 必须再次明确调用同一 Receiver MCP 工具。仅在测试子进程通过临时 `sitecustomize` 注入受控异常，不改业务 Schema 或生产权限；保存该钩子实际被 MCP 子进程执行的标记。预期：工具调用/Attempt 为失败，不能有成功 Receiver Observation/Evidence；模型与持久答复明确为 UNKNOWN/无法确认处理完成，不能宣称 PROCESSED。保留现有“未查询 Receiver”的 HF01 用例不改。

## RED / GREEN 与回归

- 先运行两个新测试保存原始 RED；HF02-01 必须复现 `OK/null` 缺陷。HF02-02 是新补足的受控失败覆盖，即使旧代码已安全返回错误，也保留其执行证据。
- 修复只允许落在 `opspilot/assistant.py::Loop.awrap_tool_call` 及 `opspilot/domain/assistant.py` 的缓存/来源读取职责；不新增 Guard、Runtime、账本或业务权限。
- GREEN 后运行新增测试、HF01 两项既有测试、AR-02 Journey P0 与 HF02 相关定向回归。全量 pytest 不在本卡范围；489/4 作为历史记录，不算本轮结果。
- 失败日志和受控注入 Trace 原样保留。真实 Provider 请求、浏览器自动化、审批/修复/交付/工单及外部业务写入必须为零。

## 六问摘要

1. **用户变化：** 失效工具提议不再伪装成成功工具结果；Receiver 查询实际失败时，用户仍得到明确未知状态。无新增业务能力。
2. **Agent 决策：** 只观察确定性 FixtureModel 的明确工具选择，不声称真实 LLM 自主性提升。
3. **观察驱动：** 合法 QUEUED 与 Receiver 工具失败导致“排队中”与“无法确认”两种不同答复。
4. **约束双向：** 未暴露工具不产生业务读取；相同已授权 Receiver/订单工具仍可正常调用并保存合法结果。
5. **简化：** 复用既有工具列表、Assistant call ledger、来源校验与 MCP；不增加安全层或新状态表。
6. **证据与停止：** 定向 RED/GREEN、MCP 子进程 Trace 和相关回归后停止；Provider/浏览器/全量 pytest 均明确 NOT_RUN。
