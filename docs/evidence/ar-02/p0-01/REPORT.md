# AR-02-P0-01：免费实现验收候选

本轮接通了专业助手入口：用户可以不建业务 Task 开始对话，在当前可信资料范围查询协议，
明确确认合法订单后使用原子只读 MCP，并将答案留在同一 Session 的原问题下。
**当前验证使用确定性模型，真实模型与浏览器未运行；不能宣布 P0 产品效果通过。**

保存的实际接口旅程（完整内容、ID 与模型输入见 runs/api-journey-persisted-trace.json）：

1. 用户：“请查协议。粘贴材料 ORION-42；202 是否代表完成？”
   免费替身调用真实 Knowledge MCP，答复“按本次检索的版本化协议，受理与处理完成不同”。
2. 用户确认授权目录里的 ar02-order，再问“现在核查本订单当前状态”。
   取得真实本地 HTTP 200、同 Event 的投递及 Receiver Observation；答复包含 QUEUED 与
   原 event_id，并区分 202 和 PROCESSED。没有生成正式 Diagnosis、审批或交接回执。
3. 用户：“根据刚才的结果整理一份说明草稿”。
   答复被持久挂回该问题，没有新 MCP 调用。**此轮固定替身只返回通用 202 解释，不能当作
   草稿质量已通过**；本实验检验原会话上下文、结果和来源接线，不以 Run=SUCCEEDED 冒充用户目标完成。

## 核验与范围

- Repo wgqa/OpsPilot；隔离 Branch codex/ar02-p0-01。
- Base `ec8c3582f6d145eec9979c43607302731411ead8`；冻结 `e2b2562`；RED `fb97658`；
  源码 `ead3ec4bcf44b1e7110fc95b8b1fde7520b1bfbf`。最终证据 SHA 以交付回报为准。
- 实际 North Star / AGENTS / Skill Blob：`1f737712c7a36ceb34433ac09c3fbba3c3305542` /
  `32c45506cceeaa8c76a5c56bf8360ff476b58856` / `d405c8d413d633824b279202cc1503dab4cf0b03`。
- 本轮用户明确批准代码与免费验证，未批准收费调用、浏览器或 main 合并。
  AR-01 仅作为参考，不整分支迁移；Stage B/B-11 HOLD 及 M2 延期门禁保留。
- 原主工作区的本地修改和未跟踪资料未触碰。当前 Diff 只含新入口、执行审计、读取接线、
  前端与必要测试/证据；无新 Goal/Planner/Memory/权限平台、无 S4、无业务写能力。
- 这是实施方亲自执行与内部审阅，主 Agent 独立核实及亲自复跑仍 PENDING。

## 实现与原职责复用

现有 Session/Message/Run、登录身份、操作幂等、Worker 锁/fence、Chat Context、Outbox/SSE、
答案唯一性和前端问题投影均复用。新增 assistant_runs 仅固定 Run 的执行核心；assistant_calls
记录外发请求与已知/未知结果，不成为第二套 Task/业务状态权威。

新入口使用 create_agent 标准循环，没有按 202/503 分类的产品 Router。工具集合由可信资源
状态决定：无 Task 只有授权 Knowledge；用户确认 TaskBinding 后可查订单、投递、Receiver、
历史和项目资料。可直接回答或停止，不强制工具顺序。新核心没有旧 `<result>` 输出解析要求。

只读事实复用原 d2 Ledger/Observation/current_s3_evidence。两处原关联检查仅给持久
ASSISTANT_V1 核心增加受限关联资格，普通 CHAT_READONLY 仍不可借用业务观察。
未改变原业务 Gate 判定、Approval、ActionIntent、Ledger 和 Handoff 语义。

Schema 17→18 只新增执行元数据及 Session 资料选择表。旧业务行、不可变回执、预算策略
不迁移；七处旧迁移测试只将“当前最新版本17”改为18，原数据/权限/幂等断言不变。
新核心实际 Provider 次数计入原 Task 辅助额度；MCP 计入既有 Task/Run 计数；失败、RESERVED、
UNKNOWN 都保留。8 MODEL / 6 MCP 的 Run 上限和原 Task 300,000ms 活跃时间均未扩大。

## 新鲜验证

| 类型 | 本次结果 | 证据 |
| --- | --- | --- |
| 有效接口 RED | 3 failed | runs/red-02.log，认证 API 的真实404 |
| 接口/资料 GREEN | 13 passed | runs/green-api-02.log |
| 连续接线、恢复、安全定向 | 24 passed，后补并发/成对事实纳入全量 | runs/final-core-02.log |
| 最终活跃全量 pytest | **433 passed** | runs/full-02.log |
| 前端新旧纯投影/接口测试 | **23 passed** | runs/frontend-node-02.log |
| TypeScript + 生产构建 / 变更 ESLint | exit0 / exit0 | frontend-build-02.log / frontend-eslint-02.log |
| 代表性 OS 崩溃恢复 | 退出86 → 新进程同 Run 成功 | full-02 的 OS case 导出及 loop-06/final-core 日志 |
| 新服务实例重开同 Session | 通过，1条最终答复；0 MCP/0 Provider | runs/reopen-01.log、reopened-session-trace.json |
| 真实 Provider / 浏览器 | **NOT_RUN / HOLD** | PREFLIGHT.md |

全量排除的是旧废弃分类 Intent RED 文件 tests/test_m4_autonomy_c1_red.py，未改它或加入兼容
分支；其余活跃测试执行。本轮第一次全量420通过、7个版本断言失败及所有接线失败均保留。
最终全量运行期间提交了源码，但代码内容未再变化，测试源码树与上述实现提交相同；不冒充
当时一直是干净 HEAD。历史 Follow-up 测试意外追加的 Trace 另存新目录，旧文件恢复原 Blob。
最终逐字节核对旧文件与 HEAD Blob 相同、git diff 为空；git status 的 EOL/stat 修改提示仍保留，
未暂存该历史文件，也未为使状态整洁而改写原始字节。测试临时目录继续保留。
源码 git diff --check 退出0；证据暂存 Diff 检查退出2，提示只来自原任务卡的 Markdown
换行空格及原始失败/运行日志的空白。为保持原始材料，不清洗这些证据来制造检查通过。

## Gold 与证据等级

- G01：无 Task / 零工具与普通答案持久化已免费验证，真实概念回答质量未评。
- G02：粘贴材料进入实际模型输入并跨轮保留；日志分析的模型质量未评。
- G03：资料范围、请求/配置/最新/适用版本及来源失效正反验证通过。多范围采用显式选择，
  未实现基于用户名称线索的自动项目选择；本地配置不等同企业 IAM。
- G04：人工确认订单、真实 MCP/HTTP 与同 Run Observation 关联验证通过。
- G05：同 Session 三次请求、答案/来源精确归属和刷新无新调用通过；自然语言体验仍待真实模型。
- G06：另在专业会话数据库的独立副本新鲜执行正式更正：可信操作者明确提交 CORRECT_TASK_INPUT，
  旧 Worker/Investigator 接管新 Run，实际查询 E1 历史和当前 Receiver，交付 E1 当前未知。
  修订0→受理1→应用2、同新 Run 两条 Observation、一条答案均核对；见 correction-04-trace.json。
  SDK 被免费替身替换，没有付费请求。旧 Graph 的原有 Domain 诊断/交付记录仍按旧协议产生，
  不代表新核心获得正式写工具。**真实浏览器的自然语言提议/确认旅程仍 NOT_RUN。**
- G07：越域拒绝后合法订单查询继续；撤权后模型和来源 API 均安全停止/拒绝，普通 Chat
  冒用 Observation 被拒。完整危险与正常路径均有免费证据。
- G08：零新取证的说明交付与来源接线验证，第三问替身未完成真实草稿目标，语义验收 NOT_RUN。
- G09：新服务实例原 Session 续问、OS Observation 后退出/恢复、相同操作不增 Run、
  未知模型结果不自动再发、最终答案唯一已验证；真实浏览器刷新仍 HOLD。
- G10：同文、真实 QUEUED/NOT_RECEIVED 的事实传递对照通过，未证明真实模型观察驱动决策效果。

## 成本、失败和剩余工作

真实 Provider 请求 **0**，没有实际 Token/费用指标。替身提供的 Usage 是合成字段，不能
作为供应商计费或智能增益。旧费用策略单次预留高于本卡拟议 USD0.20 总额；真实 Adapter、
请求预算和单独授权仍是下一检查点，新 ASSISTANT_V1 默认只给持久未授权说明；
旧 Chat/Investigator 的 Provider 构造路径保留，本轮在本地替身拦截下运行。

已有的 formal correction 仍可能进入旧 Investigator，属于本轮允许保留的过渡路径；
不做同 Run 跨核心 checkpoint 热切换。新入口未迁移 Skill/Memory 的决策和效果验证。
新核心失去来源时保守结束并提示重查，尚未证明长对话、过紧额度下的策略质量。
内部审查发现的时钟绕过、提交窗口复核、当前事实 Run 关联、Knowledge JSON 结果接线均已
定向修正；并不因此声称不存在其他缺陷。

没有把前端编译、固定模型工具序列或大量测试当作完整专业 Agent 的通过证据。
后续需主 Agent 审查免费实现与缺口，再决定收费 S01/S02、真实更正旅程和合法浏览器出口。
本轮不自动申请更多实验、合并 main 或进入下一阶段。

## Skill 六维收口

**用户变化：** 专业入口和同会话接线可免费复现，真实助手质量尚未验收。

**Agent 决策：** 产品采用标准自由工具循环；本轮替身只证明接口可执行，不证明模型自主性提升。

**观察驱动：** 本地真实事实进入后续模型输入；202/503与不同Event的智能调整仍待真实模型。

**新增约束：** 资料授权/Run身份/预算/来源复核保护明确不变量，合法读取与拒绝均有证据。

**简化结果：** 复用现有会话、执行和业务权威；不重建正式动作协议，不强制旧专用结果格式。

**证据与停止线：** 实施方源码/免费运行/Trace核验；433后端、23前端通过，旧失败保留。
Provider 和真实浏览器的完整Event更正仍未验证，停止于免费实现候选，等待主 Agent。

状态：**ACCEPTANCE_CANDIDATE（免费实现范围）**；完整 P0 产品验收尚未通过。
