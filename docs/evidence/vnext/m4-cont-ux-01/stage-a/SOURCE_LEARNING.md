# 阶段 A：预算、连续目标与恢复的源码学习

本轮沿用总纲中的 Handbook 学习方向，将原理对应到本项目的源码和失败记录；没有重新通读外部白皮书，也没有运行真实 LLM 质量实验。确定性模型替身只证明接口、来源、执行和恢复合同，不证明模型准确率提高。

| 原理 | 业务需求与源码 | 实验与取舍 |
|---|---|---|
| Task / Run / Retry 是三个不同身份 | `task_control.py::create_task_with_initial_run/create_readonly_followup_run_in_transaction`；`execution_budget.py::investigation_budget_in_transaction` | 用户新意图可产生新 Run，复用同一 Task 总额；同 operation、同 Message 重放回原身份，恢复不能变成新用户请求。A01/A03/A06/A07 核验这些关系。 |
| 预算是持久资源约束，不是 Prompt 建议 | `d2.py::reserve_attempt` 与既有 `BEGIN IMMEDIATE` | 先核验可信 policy、Task/Run 用量，再插入 Attempt；caller limit=999 不能扩大新 policy。独立连接竞争只允许合法剩余额度获胜。 |
| Attempt Ledger 优于第二套可重置计数器 | `execution_budget.py::auxiliary_attempt_counts_in_transaction`；原 D2/分类/Chat/Compression 三类 reservation | 对所有状态 COUNT，不让 FAILED/RESERVED/未知结果消失；不另建预算表族。分类/Chat/Compression 共享 8，调查独立 24 MODEL/18 MCP；32 请求上界不是固定 Token/美元上界。 |
| Checkpoint 是进度，Domain 是权威 | `investigator.py::run_investigation`；`tests/cont_ux_stage_a_worker.py` | 沿用原 Run-specific checkpoint、M1-HF 首 checkpoint 前恢复。真实子进程退出、不同 PID 恢复同 Run；已持久 MCP Observation 在 checkpoint 落后时复用，额度不清零。 |
| 调用额度不能阻止合法的现成答复交付 | `s3_investigation.py::next_step/model_call/report` | 当前来源有效的最终回答先复用，不因 MODEL 剩余为 0 就丢弃。组合补查用完本轮 4 MODEL/3 MCP 后仍交付有来源的答案；不额外调用 report 模型。 |
| 来源与历史连续性不能由预算替代 | `investigation_context.py`、S3 Prompt/current Evidence、Chat Manifest | 四次请求旅程区分协议历史引用与当前业务取证；旧 Run Evidence 只作线索。准备阶段独立提升 Receiver 版本，新 Run 实际读取同 Event PROCESSED；只读结果不修改旧 Diagnosis。 |
| 未完成也是持久用户结果 | `chat.py::record_chat_limit_in_transaction`；现有 `factual_partial` | 程序限制说明明确标记未提交模型最终答复，既有失败调用仍计数；不制造 Provider Attempt、Manifest 或业务事实。PARTIAL 非空不自动计完整目标完成。 |
| Schema 兼容不是旧任务自动升级 | `database.py::initialize` v16→v17；可信 Task 创建事务 | 只给已有预算表增加 policy/aux 两列；旧行默认 LEGACY_V1、原 limits/elapsed/Attempt 不变。新 S3 创建时显式 CONTUX；S1/S2 仍 legacy。历史预算回归显式使用 legacy fixture，原业务断言保留。 |

## 旧条件怎样被简化

- S3 的 Task-only 次数比较改为读取同一份两级剩余投影，工具 Schema、下一步和报告使用一致口径；实际权威仍是 reservation 的 SQLite 事务。
- 工具执行前的非原子 Task-only 预检查被事务预留及 `BudgetExhausted` 结果处理替代，竞争失败不外发 MCP。
- 辅助调用没有建立第四张计数账本，而是沿用三张 Attempt 表求和；没有新增 Planner、Goal Manager、Guard 平台或 Runtime。
- 没有删除 Gate、TaskControl、授权、来源重验或业务写事务守卫。旧 Task 的运行策略和原隔离实验入口保留；受信实验设置只允许首次调用前，不能由 Web/MCP/model 选择。

## 六个面试追问

**为什么不能给每条新消息重新发 8 次？** 新消息代表一个用户意图，不代表新 Task 资源。新 policy 同时检查 Task 累计额和本 Run 上限，恢复/重复 operation 不产生新身份；否则用户或崩溃重放能无限重置成本。

**为什么失败或未知请求还扣预算？** 外发可能已发生并产生费用。先持久 RESERVED，失败后更新原 Attempt，而不是删除；真正重试另预留并继续累计。未出站就被权限/额度拒绝的事务不伪造已调用记录。

**两个连接最后一格额度怎样分配？** 在同一个 `BEGIN IMMEDIATE` 中读用量并插入 Attempt。第二个连接取得写锁后必须看到第一个提交的行，不能都按旧计数通过。分类与 Chat 的混合竞争也使用这一规则。

**没有首 checkpoint 时为什么仍能恢复？** Run、控制版本、输入高水位和 Attempt 已在 Domain。沿用 M1-HF 的可信冷启动条件创建执行进度，不能重建 Task 身份、重新应用纠错或清空账本。已有 Observation 仍须同 Run、当前授权/版本/TTL 有效。

**用完最后一次模型额度后，为什么还能 ANSWERED？** 如果最后一次已形成有来源且仍有效的最终答案，保存/交付不等于再调用模型。若目标未完成，则用当前来源给具体缺口；不能靠空 PARTIAL 或 Run SUCCEEDED 宣称产品成功。

**这轮证明了多少 Agent 智能？** 已接通并验证合法调查机会、来源连续性、工具循环与受控执行；模型替身选择了两种合法顺序。真实 Provider 的自然语言理解、准确率、Token、延迟及成本收益仍未证明，留给获批后的真实实验。

## 三种完成度

- **已理解/复现：** Task 饥饿、caller limit 绕过、跨类别辅助超额和恢复补查超额有本轮原始 RED。
- **已接入业务：** CONTUX policy 进入真实 Task 创建、S3 Investigator 和辅助调用预留；确定性四请求经原 API、本地 HTTP/MCP、真实 SQLite/LangGraph 持久链路。
- **已证明效果：** 只限最终运行记录所覆盖的确定性接口与恢复合同。真实 LLM 用户体验、阶段 B 时间线、J1–J4 付费旅程及相对 R/H/A 优势均未验证；不据此宣传泛化或生产能力。

## 本轮结果核验的反例

`full-active-01` 虽然有 399 个通过用例，人工逐句读四轮真实持久答复仍发现 Chat 替身把 `receiver-ack-contract-v2@2.1.0` 错写为 `2.0.0`。源上下文和版本有效性是对的，原断言只检查文档 ID，未检查版本。增加精确版本断言得到 `fixture-version-red-01` 两个失败，再让替身读取实际 `CURRENT_APPLICABLE` 引用版本，两个变体才通过。

这说明“Run SUCCEEDED、测试通过、Context 装配成功、用户目标正确完成”是不同层次；测试替身也可能生成不可信文本。之前错误轨迹不可删除或继续统计为完整正确旅程；正式模型的引用准确率仍须真实实验另证。业务来源校验没有改为文档名/版本关键词白名单，本次仅加强测试替身与断言。
