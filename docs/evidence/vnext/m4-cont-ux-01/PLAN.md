# M4-CONT-UX-01 · 阶段 0 规划与冻结候选

**状态：`PLAN_FREEZE_CANDIDATE`。授权仅为 PLAN/FREEZE；阶段 A/B 实施、预算变更和付费实验均 `NOT_AUTHORIZED`。**

用户目标：在同一 Task 连续提问，Agent 接住上轮真实引用，决定解释、合法补查或澄清；新的当前事实改变回答；刷新后能够按问题、调查、答复的关联读懂过程。本阶段只冻结实现前标准，不增加产品能力。

## 前置核验与证据范围

| 项目 | 本次实际核对 |
|---|---|
| Repo / 远端 | `wgqa/OpsPilot`，`https://github.com/wgqa/OpsPilot.git` |
| 参考 / fetch 后 main / 目标 HEAD | 均为 `b70c02284a3f1f873c4fbf56b1d6768e9a0ec1c8`；参考到目标 Diff 为空，无新增 merge |
| 工作树 | 复用 `c1-approved-integration-20261025/agent新项目` detached 集成工作树；tracked/index 起始干净；7 类既有未跟踪 basetemp/cache 保留 |
| 用户主目录 | `D:/学习/agent新项目` 的本地 main 为 `add47ec83f31fa76b9b6a5782e013311732bc496`；有未跟踪实验与开发资料，未切换、清理或暂存 |
| North Star | 从目标提交对应工作树实际重读全文；Blob `1f737712c7a36ceb34433ac09c3fbba3c3305542` |
| AGENTS | 从目标提交对应工作树实际重读全文；Blob `30319000ed0054007e9b7b6b46bf98b1493c8179` |
| Skill | 目标提交不存在 `.agents/skills/opspilot-slice-review/SKILL.md`，未声称发现或执行 |
| 本次方法 | 当前源码静态核对；历史原始 JSON/JSONL 逐记录解析与 ID 关联；历史浏览器截图/可访问性文本核对；官方价格页面只读核对 |
| 本次未执行 | pytest、前端构建、真实浏览器操作、Provider、MCP、业务 HTTP、崩溃注入均 `NOT_RUN` |
| 证据等级 | 历史实施方运行原件的本次静态复核；不是主 Agent 独立复跑，也不是本阶段新鲜业务运行 |

逐文件目标 Blob、读取方法和基线检查见 `READ_MANIFEST.json`。当前任务卡来自 2026-10-26 用户消息，无 Git Blob。适用顺序：本阶段授权边界；已冻结安全不变量与阶段 Gold；North Star/AGENTS；历史报告仅作证据。历史范围文字不得否定已批准 S3。

## 现状能力与失败矩阵

`已完成` 在下表只指所列证据覆盖的具体行为，不能解读为主 Agent 新签 PASS。

| 行为 | 核验结果 | 实际依据与限制 |
|---|---|---|
| 同 Task 发起合法只读补查 | 已接入，历史真实正例 | C1-HF 原 Trace：协议补查创建 `INVESTIGATE` Run，3 MODEL/1 MCP，取得当前协议并 `ANSWERED`；独立 Chat sidecar 为 BLOCKED、0 Chat Attempt |
| 用“刚才那份协议”续接 | 已接入，历史真实正例 | C1-HF 第 2 个 follow-up 为 EXPLAIN，1 次可见 Chat，Manifest 引用前次 Run 与 `receiver-ack-contract-v2`；未要求用户重输文档名 |
| 第 3 个 follow-up 重新核实当前状态并完整答复 | 历史真实产品失败；当前三轮效果未重验 | C1-HF 新 Run 实际查询 Receiver=QUEUED，却耗尽 Task MODEL=8，持久 `PARTIAL`、正文长度 0。VS01 后来接入非空事实降级，但 b70c022 上完整三轮尚无新鲜证明 |
| Task 累计额度与恢复 | 当前源码明确；有历史失败/回归原件 | `d2.reserve_attempt()` 在写事务数同 Task 的全部 Attempt；新 Run 不清零。VS Web-02 初始与纠错各 4 MODEL/3 MCP 后，新合法补查 0 MODEL/0 MCP 直接到限制；不是新用户请求自动获得新额度 |
| 分类器、Chat、压缩的 Task 总费用边界 | 现有分项审计；总边界仅静态缺口 | 分类每 assessment 最多 2 次，Chat+compression 每 Run 合计最多 3 次；不进入 D2 Task 8/6。无限新消息可产生更多辅助调用的风险由源码推断，本阶段没有做动态无限请求实验 |
| Event 正式纠错 | 历史真实正例及失败修复记录 | VS Web-02：提议→确认→TaskControl rev=2→新 Run；E1 503 历史不能由 E2 PROCESSED 证明恢复。早期 `TASK_INPUT_HIGHWATER_STALE` 保留；当前创建补查 Run 已复制 applied high-water |
| 候选重评估与终答复用 | 当前源码与历史真实行动可核对 | S3 串行工具观察后回到正常模型决策，保留候选来源；`report()` 可复用来源仍匹配的终答复。不是自动执行全部建议，也没有逐候选 Reviewer |
| 合法部分事实进入 Chat | 最新确定性证据通过，Provider 效果未验证 | EG01-HF 的 HTTP/MCP→Chat 准备 Trace 含 200 订单、同 Event 202 投递；无 Receiver 时无当前 Receiver 事实；Gate 保持 INCONCLUSIVE。该补丁没有真实 Provider/Web 调用 |
| PROCESSED/QUEUED/UNKNOWN 语义 | 已有规则与历史真实四类 Chat；连续链仍需验证 | EG01 新规则与当前 Knowledge 明确 PROCESSED 不需等 SLA；HF01 继续核验当前事实集合。旧 VS Web-03 出现“完成还须过 SLA”的错误原文保留，不冒充现版本新失败 |
| 当前事实覆盖历史 Memory | 历史真实出站与工具证据 | EG01 Task B 早期用经验，当前事实冲突后排除。ON/OFF 同工具路径、同结果，ON 多 2,354 Token，未证明 Memory 收益 |
| 刷新后持久内容存在 | 历史真实正例 | VS Web-02/03 保留 Message、Run、答案和来源；刷新不重新发模型。不能由此推断当前整个时间线顺序正确 |
| 问题—答复时间顺序 | 历史浏览器证据确认错位；当前源码仍按类型分段 | VS Web-03 `03-refresh-persisted-journey.txt` 先列两个问题和后一个 Chat 回答，再列更早的初次调查答复。App.vue 分别循环 Messages/Follow-ups/Investigation Answers；Chat 关联用“最近前一用户消息”推断 |
| 幂等、撤权与 S1/S2/S3 安全 | 既有运行原件与当前合同，不是本轮复跑 | 最新 HF 全量原始记录 374 passed / 1 旧契约 RED；本阶段不重新执行、不把它写成当前新鲜全绿 |
| 旧 C1 `READONLY_FOLLOWUP` RED | 已废弃分类契约的历史记录 | 现行合法意图是 `FOLLOW_UP + readonly_action=INVESTIGATE`。保留该 RED，不为生产加兼容分支，也不将它重新定级为当前产品缺陷 |

可复查统计见 `TRACE_AUDIT.json`；生成器 `audit_saved_traces.py` 只读历史文件、不导入业务代码、不打开 SQLite 或模型环境文件。历史日志、Gold、留出、失败均未修改。

## 冻结用户旅程和 Gold

为避免把旧三轮失败缩小成容易的两次提问，本候选明确采用更强的边界：**同一 Task 初次调查后，再连续 3 条用户 Follow-up（总计 4 条用户请求）**。三问分别是协议查证、代词解释、当前状态复核；第三问必须得到可用答案或具体、非空的合法缺口。若主 Agent 采用“含初始问题共三轮”的解释，这组更强标准仍覆盖它，不应改写旧记录。

`GOLD.json` 冻结 20 项目标/反向用例和 4 条真实实验旅程；不固定工具序列、推理步数或唯一自然语言答案。它是独立新 Release，不修改 C1、VS01、EG01 的旧 Gold 或原留出。

## 合同冲突与待主 Agent 决策

| 编号 | 已核实边界 | 最小候选处理 / 实施前门 |
|---|---|---|
| C-01 | D2 默认 Task 8/6；现有 S3 配置仅接受 8/6、12/8、16/10，且首次 Attempt 后不可更改 | 候选新 S3 policy：Task 24 MODEL/18 MCP；初始/正式纠错 Run ≤8/6，明确新只读补查 ≤4/3。须主 Agent 明确批准数值与新任务适用范围；旧 Task 不自动升级 |
| C-02 | Chat-only 与调查预算独立；现有辅助调用只有单 Message/Run 重试上限 | 建议新 S3 Task 另设辅助 Provider 总上限 8（分类+Chat+压缩），两池不借用，总 Provider ≤32。只复用已有 Attempt 表计数；如主 Agent 不批准，必须保留“辅助调用仅分项审计、Task 成本不能全局封顶”的限制，不能宣称完整满足总成本目标 |
| C-03 | 现行 Message API 未返回 Assistant→Chat Run→源 Message 的精确链接 | 前端派生时间线为主；建议同一消息 GET 用已有 `chat_run_answers` 只读 JOIN 增补 `answer_run_id` / `answer_source_message_id`。无新表或业务状态。纯前端按最近用户猜测不能覆盖并发/晚答场景 |
| C-04 | EG01-HF 当前仓库交付是 ACCEPTANCE_CANDIDATE，本轮未见主 Agent 最终独立裁决文件 | 本阶段只做规划；正式实施前由主 Agent 确认该基线可用及剩余限制，不把远端存在当验收通过 |
| C-05 | VS01 少量预算样例含旧响应保留缺陷；旧留出不是最终响应修复版本；P1-failed 准备/Gold 不一致 | 仅用于本次成本与失败分析，不借其结果宣称新方案效果，不改旧 Gold、不重跑旧留出；新旅程使用独立 Release |
| C-06 | 历史上下文有最多 3 条、答案 1,600 字符等边界；M3 摘要能力不属于本切片扩建范围 | 新旅程在现有窗口内验收；来源缺失时允许明确澄清，不能扩大 Context 限额或新建 Memory 来掩盖；长对话泛化效果未证明 |

M2 延期门禁仍保留：新受控写能力前的 S1 再验证、operation 幂等、Handoff 唯一性/事务和本地 IAM 声明边界。本候选不新增写能力；后续实现仍必须复验 TaskControl、M1-HF 恢复和现有 S1/S2/S3 安全路径，不能用“体验优先”跳过。

## 建议阶段 A/B 范围

| 阶段 | 若主 Agent 后续批准，才允许的内容 | 阶段出口 |
|---|---|---|
| A：请求与预算语义 | 新 S3 versioned policy 与同 Run/Task Attempt 检查；新用户请求和同 Run 恢复的分界；分类/Chat 分项计账；复用当前非空事实降级/终答复用。只有 RED 证明缺陷时才最小调整既有交付逻辑 | 冻结 Gold 的后端 RED/GREEN、独立进程恢复和双连接并发；旧 Task 不变、计数不重置、合法新补查有机会、耗尽不空答或伪造完成 |
| B：时间线与真实验收 | `App.vue` 一个派生视图；必要的已有消息读取关联字段；刷新/SSE/重启的稳定显示；获独立预算批准后执行冻结 Web/Provider/MCP/HTTP 旅程 | 新鲜完整回归、前端构建、4 个独立真实旅程全部尝试/失败保留；按目标履约和事实正确性评分，交验收候选 |

A 不实现通用预算平台，B 不重写 Chat/Investigator，不增加 Domain 业务状态、工具、Memory 类型或新场景。不得由本规划提交自动进入 A，也不得 A 结束就自动进入 B；主 Agent 可在后续卡中一次明确授权 A/B。

## 六个正式自问

1. 用户变化：实施后目标是三次追问都能得到与原问题关联的可用结果，刷新仍读得懂；本阶段只提供冻结方案，没有新增可运行能力。
2. Agent 决策：保留解释/补查/澄清、合法工具与来源选择、根据观察更新答案；程序只负责可信资源、额度、恢复、来源和业务权限。
3. 观察驱动：同样问“现在完成了吗”，同 Event 当前 PROCESSED 可确认完成，QUEUED 说明排队，缺目标 Event 当前事实则 UNKNOWN；历史成功或 202 不得替代。
4. 双向限制：Run 小额度防一轮吃光 Task，Task 总上限防无限 Follow-up；同时必须用新 Run 正例证明合法重查不被旧预算或旧 Gate 误伤。直接 EXPLAIN 不强制工具。
5. 简化结果：复用 Attempt 表、TaskControl、现有 Graph、历史装配、事实降级和消息关联；时间线只做投影，删除按类型分段及最近消息猜关联的呈现职责。
6. 证据与停止：当前仅静态源码/历史原件审计与 Gold 冻结；新实验预算尚未获批。提交 PLAN/FREEZE 候选后停止，等待主 Agent 独立审查，不签 PASS、不启动 A/B 或 M5。

## 文件索引

- `GOLD.json`：三轮旅程、20 项正反判据、必要来源与禁止结果。
- `BUDGET_DESIGN.md`：A/B 比较、明确数值建议、请求/恢复/重试计账。
- `TIMELINE_DESIGN.md`：现有字段、最小派生投影及必要读取字段。
- `EXPERIMENT_PLAN.md`：付费预算申请、真实旅程、指标、失败与停止线。
- `LEARNING_AND_INTERVIEW.md`：Context / LangGraph / Budget / Evaluation 源码与学习证据。
- `TRACE_AUDIT.json`、`READ_MANIFEST.json`、`DOC_CHECKS.json`：本次只读核验及文档验证记录。
