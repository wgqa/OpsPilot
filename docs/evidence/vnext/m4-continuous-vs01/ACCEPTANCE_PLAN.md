# M4 Continuous Investigation · Vertical Slice 01：冻结验收

状态：`FROZEN_BEFORE_RED`。基线：`main@85be293342529de85b40507b9c90c75bc1a77b38`。

## 用户目标、合同和开工核验

用户可在同一 Task 查询绑定订单的回调历史、更正所指 Event、追问当前处理状态，取得有来源的可用回答或具体未知事项。Agent 选择查询顺序、相关 Event、协议、澄清或结束；Domain 保持授权、事实和正式 Diagnosis/Handoff 权威，执行层负责工具、累计预算、恢复与审计。

开工远端 main、集成副本 HEAD 均为本基线。原主目录本地 main 是 `add47ec…`，有许多未跟踪测试资料及开发目录；原 C1 候选也有未提交文件，均不修改、清理或暂存。复用已集成的干净 tracked 工作树 `C:/Users/tu me manques/.codex/worktrees/c1-approved-integration-20261025/agent新项目`，不建功能分支，显式提交本任务文件并正常推送 `HEAD:main`。

已从该提交实际重读 North Star（Blob `1f737712c7a36ceb34433ac09c3fbba3c3305542`）、AGENTS（`30319000ed0054007e9b7b6b46bf98b1493c8179`）、回调业务提案、C1/HF/最终接线合同和 M2 遗留门禁。原任务卡来自附件 `47162a05-b675-4c2b-8b25-bbdcd4c73f4c/已粘贴的文本.txt`，已完整读取；最新聊天中的“主 Agent 最终实施补充”优先于其候选分支/禁止推 main 等冲突措辞。`.agents/skills/opspilot-slice-review/SKILL.md` 不在目标版本，不声称已执行。

原六对 Gold 继续有效；本轮不是完整里程碑最终 PASS。当前主 Agent C1 `ACCEPT_WITH_LIMITS`、空白 PARTIAL、历史 E2E 失败和缺失 Transport Attempt 的事实保留。旧 Gold/RED/报告/回执不可改写。

## 最小实现与不变量

1. **真实历史：** 在 S3 最小增加不可变、可追加的 Transport Attempt 观察及一个有界 TaskBinding 内只读 MCP 查询。同 Event 保留 Event ID，每次实际 HTTP 使用不同 Transport Request；记录序号、时间、请求/响应 digest、协议/订单版本和可信来源。只有显式测试发送端产生 POST；不注册发送/改 Scope/任意 URL 工具。
2. **缺失和当前性：** 没有记录不是没有发送，超时是结果未知。发送后未持久化窗口不冒称完整审计。历史响应不是当前处理状态；当前接收快照若属于 E2，不能证明用户所指 E1 已处理。新事实仍经当前授权、Run-scoped Observation、TTL 和 digest/版本核验；不复活旧 Diagnosis。
3. **正常决策闭环：** 每次串行工具观察之后，将观察与剩余未执行候选交给下一次正常模型决策。保留候选原 Call/Tool 来源和处置记录；可保留、修改、放弃，不自动执行整批候选，不增加逐候选 Planner/Reviewer 调用。无增量反馈不是立即终止，重复无意义查询仍受现有累计预算约束。
4. **结束职责：** 用 S3 自己的正常决策结果/合法继续能力替换 `after_gate()` 的 `DIAGNOSED / MCP_NO_PROGRESS / budget` 混合结束条件。Gate 只裁定业务事实；用户问题完成由 Agent 回答/澄清或明确执行限制决定。S1/S2 路由不改变。
5. **交付：** 来源仍有效且符合当前目标的已生成答案直接复用，不强制报告阶段再请求模型。答案失效、预算/Provider 失败时，从当前可信来源交付有引用的简短事实与未知事项，明确 `PARTIAL/NOT_COMPLETED` 和降级来源。空白 PARTIAL 不计成功。只读结果不得写正式 Diagnosis/Plan/Approval/Intent/Ledger/Handoff。
6. **局部简化：** 仅把本轮 S3 所需的共享小函数移到既有合适职责处或公开化，消除被触及的私有反向调用；不建设通用 Context/Goal/Runtime。

## 冻结 Gold 与双向验收

`GOLD.json` 保留 P1～P6 共 12 个正式案例描述。P2/P3 的四个独立具体实例提前生成到 `SEALED_P2_P3.json` 并记录 hash；不在开发、Prompt 调优、在线工具或模型中读取其期望标签。开发使用独立 `DEVELOPMENT_CASES.json`。留出只在实现和 Prompt 固定后运行一次，保留首次失败；若据此修复，必须标记污染，不能再声称同一留出独立成功。

| ID | 危险路径必须阻止 | 合法路径必须保留/验证 |
|---|---|---|
| VS-01 | 快照/计数冒充每次发送，伪造来源、重复请求异摘要 | 真实 HTTP 503→202 同 Event，两条独立请求与不可变历史 |
| VS-02 | E2 的 202/PROCESSED 冒充 E1 成功 | 同 Event 重试可关联；不同 Event 必须分别报告，目标未知可合理交付 |
| VS-03 | 历史缺口被猜成完整，超时当确定失败 | 有历史答时间线，无历史答具体缺口 |
| VS-04 | 旧 Run/失效 Scope/错订单证据借用 | 同 Task 新 Run 真实重查相同事实有效；撤权后读取与旧资格 fail-closed |
| VS-05 | DIAGNOSED 自动代表用户问题完成 | Gate 已形成后仍能合法查历史/协议/当前状态 |
| VS-06 | 剩余候选无声丢失或自动顺序执行 | 一次真实观察→一次正常模型决策；候选保留/修改/撤回均有来源 |
| VS-07 | 无 Tool Call 一律成功，重复查询无界循环 | 有依据直接回答、澄清、一次空结果后换方向均可用；无效循环有界停止 |
| VS-08 | 报告强制消耗额外请求，重用失效答案 | 有效终答复用且 Provider 不额外调用；出站/交付前来源改变则不当当前事实 |
| VS-09 | 预算满后空白结果、跨 Run/重启重置计数 | 当前事实的确定性部分交付，累计默认与实验预算可恢复 |
| VS-10 | 实验配置冒充默认/模型成本遗漏 | 默认 8/6 与实验 12/8、16/10 分报；分类器/Chat/Investigator 成本分别及总计 |
| VS-11 | 用户纠错直接改变绑定/授权 | 正式确认与 TaskControl 新 Run 改变调查关注点，原 Diagnosis/回执不变 |
| VS-12 | 当前状态与别的 Event 混淆 | QUEUED/PROCESSED 成对真实事实导致不同有依据回答 |
| VS-13 | 规则/Mock/CLI 冒充真实 Web 自主行为 | 真实 Provider+MCP+HTTP+Web 连续旅程和至少一组成对观察，留实际对话/来源/截图 |
| VS-14 | 旧安全契约退化或改旧 Gold 制造绿 | 完整 pytest、S1/S2、HF/TTL/C1 回归、前端检查；旧实现前 RED 单独保留 |

## 预注册实验与总成本上限

不改变工作台默认 8 MODEL / 6 MCP。只在隔离 Task 上把上限持久化为 12/8 或 16/10，首次外发后不可修改，Worker/新 Run 持续累计；非法配置不接受。独立实验重复用新的等价 Task/DB，不清零旧 Task。

主实验每例每配置 1 次：P5 开发成对事实在 8/6、12/8、16/10 上共 6 个 A Task；P2 开发成对 Web 事实再 2 个默认 A Task；实现/Prompt 固定后 P2/P3 四个留出各默认 A 一次，共 12 个 A Task。对相同 P5 两例另运行 R/H 各一次，共 4 个对照 Task。每组使用相同初态、合法资料、工具、权限、评分和预算配置；记录正常模型与确定性降级交付，不要求 A 胜出。不用失败后的选择性重跑替代首次结果。

**本切片真实 Provider 全局硬上限：180 次请求、估算/保守预留费用 USD 3.00**，包括分类器、可见 Chat、Investigator 和所有失败/调试尝试；开发 smoke 也入账。开始付费实验前用小型 smoke 包装器按实际输入与最大输出预留，持久记录请求/usage，达上限停止、不自动追加。实际 Token 缺失时记 UNKNOWN 和保守预留，不编造实付账单。开发阶段优先确定性模型。当前本机模型 `deepseek-flash`、端点 `api.deepseek.com`，密钥只在进程内读取，不入证据。

费用按 2026-10-25 实际核对的 [DeepSeek 官方价格](https://api-docs.deepseek.com/quick_start/pricing/)保守峰值估算：输入 cache miss USD 0.30/百万，输出 USD 1.20/百万，忽略缓存/非峰值优惠；这只是可核对估算，不称账户实扣。实验请求数、费用和成功结果分组，不把实验额度完成率宣传为默认体验。

## 执行与停止

本冻结独立提交 → 新定向测试 RED 原样保存 → 最小业务/循环/交付修改 → GREEN/完整回归 → 有界真实旅程和成对观察 → 一次留出 → 源码简化、失败、成本与学习材料。所有日志使用本目录独立 runs 和 basetemp，不覆盖历史证据。

最终报告先展示真实用户对话和可完成任务，再解释 Agent 决策、职责简化、测试、失败和成本；列明哪些旧混合条件被替换、重复判断被合并、是否仍需逐案例特殊分支。状态仅 `ACCEPTANCE_CANDIDATE`，直接提交推送 main 后停止，不启动新阶段或写能力。
