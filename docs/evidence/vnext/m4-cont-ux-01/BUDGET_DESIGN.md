# 同 Task 连续调查预算 · 待审设计

**本文件不改变任何额度。以下为主 Agent 待批准的新 S3 policy，现代码仍是默认 8 MODEL / 6 MCP。**

## 已有真实需求与成本

数据由 `audit_saved_traces.py` 对保存原件按 Run/Attempt 联表解析，不是本次新实验，也不是大量样本统计。

| 历史片段 | D2 MODEL / MCP | 实际 Token / 交付 |
|---|---:|---|
| C1-HF 初始调查 | 4 / 3 | 9,974 |
| C1-HF 协议补查 | 3 / 1 | 7,539，ANSWERED |
| C1-HF 当前 Receiver 补查 | 1 / 1 | 2,139，刚好到 Task MODEL=8；PARTIAL、正文 0 |
| C1-HF 三次分类 + 一次可见 Chat | 不在 D2 额度内 | 4,404 + 4,370 Token；整条旅程 12 Provider / 28,426 Token |
| VS Web-02 初始 + 正式 Event 纠错 | 4/3 + 4/3 | 40,647 Investigator Token；第三次合法补查因额度 8/6 已满，0 次新工具 |
| VS Web-03 初始 + 一次 EXPLAIN | 6/5 + 分类 1 + Chat 1 | 42,949 总 Token；来源续接成功，旧 SLA 解释错误保留 |
| VS budget-02 PROCESSED | 8/6 配置实际 4/3；16/10 配置实际 16/6 | 前者 MODEL ANSWERED；后者 132,322 Token、109.8 秒，事实降级 PARTIAL |

这些记录支持“正常初始常用 4–6 次模型，协议查证曾用 3 次模型/1 工具；新当前状态查询至少需要发起工具和依据结果交付”的需求。它们**不证明**每次 Follow-up 4/3 一定足够，也不证明提高 Task 上限能改善正确率。16/10 失败来自旧版本，不能当最终版本性能评测。

## A 与 B 比较

| | A：只提高 Task 总额度 | B：Task 总上限 + 每个可信新 Run 有界额度（推荐候选） |
|---|---|---|
| 比较总额度 | 新 S3 Task 24 MODEL / 18 MCP | 同为 24 MODEL / 18 MCP，便于公平理解差异 |
| 单 Run | 可能用尽全部 Task 额度 | 初始/正式纠错 Run ≤8/6；只读 Follow-up ≤4/3；实际还能用多少取两级剩余量较小值 |
| 主要收益 | 改动最少，已知 8 次饥饿窗口变晚 | 初次调查不能预先吃掉全部后续机会；新用户请求可以继续，旧 Run 恢复不能变新额度 |
| 主要风险 | 旧 16/10 例已说明一轮可消耗较多仍未履约；后续问题仍可能饥饿 | 对复杂合法补查可能过早限制；必须保留复合目标正例、非空 PARTIAL 与实际行动评测，不给每个工具固定顺序 |
| 恢复/幂等 | 沿用 Task Attempt 计数 | 同时数 Task 与原 Run Attempt；恢复/重试不改 cap，不新建 Run 领取额度 |
| 结论 | 可作简单备选，未证明足够 | 用较小 Run 窗口保护连续目标；需后续 RED/GREEN 与真实旅程验证，当前不称有效 |

推荐的 24/18 为**有界容量建议**：初始最坏 8/6 后，至少还有 16/12 可供独立用户请求消费；三个只读 Follow-up 各最多 4/3，仍有余量用于额外澄清或纠错。不是每次预扣一整份额度，也不是保证所有用户目标都完整完成。已耗尽的 Task 不自动新建 Task、提高上限或解锁业务权限。

## 辅助调用不能遗漏

建议同一新 S3 policy 另设 **8 次辅助 Provider 尝试的 Task 硬上限**，覆盖分类、可见 Chat 与 Context compression；调查与辅助额度互不借用。Task 整体 Provider 尝试至多 24+8=32，MCP 至多 18。保留每 assessment 最多 2 次、每 Chat Run 的回答+压缩合计最多 3 次的既有重试边界。

这是需要主 Agent 明确批准的新资源约束。只统计 D2 而不限制辅助调用时，只能声称“调查次数有界”，不能声称 Task 全部模型费用有界。达到辅助上限仍可持久接收合法用户消息；同一 Chat Run 以明确的持久限制原因结束，页面显示非空的“本次未执行/未完成”，不再外发分类或 Chat，也不能因为未分类而启动 Investigator。

## 新请求与恢复的权威区别

- 新机会来自可信 SUPPORT owner 的新 Command/Message，具有不同稳定 operation_id、source_message_id；合法分类/确认事务创建新的持久 Run。模型输出只是路径建议，不能自建 Run、改额度或资源绑定。
- 同 operation 重试回原 Command/Message；同 Message 重复 assessment 回原只读 Run。相同正文但两个有意操作保持两个不同 ID，不能按文本去重。
- Worker/浏览器重连、Checkpoint 重放、初次 checkpoint 前恢复仍使用同一个 run_id。它沿用原 Task policy 与 Run 类型、已消费 revision/high-water、所有已预留 Attempt；不重新分配 cap。
- 正式关键纠错沿现有确认流程生成新 Run，使用累计 Task 剩余额度；不把旧 Run 更新成最新控制版本，不清零计数。原批准、Intent/Ledger 不受预算提案扩权。

## 最小持久实现候选（尚未实施）

1. 在现有 `task_execution_budgets` 中为**新 S3 Task**固定版本化 policy 与两级总限额。优先用一个 immutable policy version 推导 Run cap：可信 `INVESTIGATE` 且无 C1 记录为 8/6；具有 `c1_readonly_followup_runs` 来源记录为 4/3。若实现期发现必须保存显式 Run cap，最多给已有 `task_runs` 增补字段，不新建通用预算平台。
2. `d2.reserve_attempt()` 的现有 `BEGIN IMMEDIATE` 在同一事务检查当前 TaskControl、Task 总计数、同 run_id 计数，再预留。额度来自可信 policy，不能信任调用方传任意更大的 limit。`attempt_counts()`/Prompt 同时展示 Task 与 Run 剩余，避免总额和本轮窗口混淆。
3. 分类/Chat/compression 沿其既有 reservation 事务，查询现有 `investigation_update_attempts`、`chat_attempts`、`context_compression_attempts` 的 Task 合计；复用一个小的既有预算职责函数。不同 Attempt ID 各记一次，ModelTrace/Provider ledger 是审计投影，不再重复扣一次。
4. 所有 `RESERVED`、FAILED、未知网络结果都占额度。若请求尚未出站但进程崩溃，也保守保留消费。真正的外发重试需要新 Attempt 并继续消耗同 Run/Task；已经持久成功的 MCP Observation 重放不重新调用网络，也不凭重放创造额度。
5. 独立 SQLite 连接的并发 admission/reservation 必须序列化：相同来源返回原 Run，两个不同新请求可排队或明确忙，Task/Run cap 不能被并发读旧计数绕过。禁止永久挂起；迟到分类不得启动第二条回答链。

旧 Task 默认保持原 8/6 或已冻结实验配置，首次 Attempt 后不迁移额度；S1/S2 policy、D3 恢复、审批与业务契约不变。新 policy 非 Web/MCP 可选参数；仅获批可信创建路径为新 S3 Task 选用。当前 `_task_attempt_limits()` 的固定合法配置集合需后续批准后最小扩展，不能在本阶段偷偷修改。

## 耗尽与正常交付

来源仍有效、已生成且满足当前目标的终答复直接复用，不强制最后再调一次模型。若模型选择继续但 Run 或 Task 上限已满，使用现有 `factual_partial()` / C1 结果存储给出本 Run 已证实事实、证据 ID、未知项和准确的限制层级。没有新事实时应说“本次未再查询”，不得把历史 Run Evidence 说成新观察。

区分 RUN_MODEL_LIMIT、RUN_MCP_LIMIT、TASK_MODEL_LIMIT、TASK_MCP_LIMIT、TASK_AUX_PROVIDER_LIMIT、ACTIVE_TIME_LIMIT 与来源/Provider 失败；沿用现有原因字段，不新增业务 Outcome。PARTIAL 正文为空或用户问“现在”却只重复历史结论，都不能计为目标完成。

保留现有 Task 300,000ms 活跃时限与单调用超时；人工等待/浏览器离线不重置或额外扣执行时长。该轮没有证据支持提高总时间阈值。请求数上限不等于固定 Token/费用；实际 Token 必须分项审计，缺失记 UNKNOWN。

## 费用估算与单独申请

本次按 2026-10-26 实际读取的 [DeepSeek 官方 Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/) 使用 Flash 峰值无缓存输入 USD 0.30/百万、输出 USD 1.20/百万估算；官方最大输出为 384K。历史 SDK `max_tokens=512` 没有形成可靠总输出上界，不可用于伪造低费用预留。

后续新切片独立申请：**4 条真实旅程，Provider 总硬上限 64 次，估算/保守预留费用硬上限 USD 1.50，最多 1 个在途付费请求**。预计 13–16 请求/旅程，仅是小样本需求估算；规划容量 400k 输入/100k 输出对应约 USD 0.24，不是保证或账单。每次外发按真实输入上界和当时官方最大输出保守预留，已完成按实际 usage 结算；未知 usage 保留预留并标 UNKNOWN。价格/模型版本变化须重新登记，触任一硬限即停止。

该申请**尚未批准，阶段 0 消费为 0**；EG01 37/40（硬上限 80）与 VS01 原 ledger 各自封存，不转借剩余额度。正式执行计划、分母和停止线见 `EXPERIMENT_PLAN.md`。
