# M3-01 冻结验收计划

冻结版：m301-acceptance-v1
开发基线：main@e46d99231f5ef259754228683a1504bf18cea79f
origin/main：冻结前 fetch 后与基线相同
时间：2026-10-19（Asia/Shanghai）

本计划先于任何 M3-01 实现、RED 复现和真实评测提交。它冻结验收标准，不表示任何功能已实现或通过。主 Agent 独立复核后决定阶段结论。

## 用户旅程与范围

支持工程师在 Task A 完成可信 S1 恢复，或可信 S2 诊断/实际本地交接后，创建包含该案例具体条件、事实、方法、适用条件和局限的候选经验。候选必须引用可复核的 Domain receipt/evidence；同租户 APPROVER 明确确认后，经验才可被不同 task_id 的 Task B 作为低信任方法提示检索。Task B 使用当前真实 MCP/HTTP、可信 Domain Gate 和 TaskBinding 自行形成结论。APPROVER 撤销后，新的模型出站、Worker 恢复和新 Chat 均排除该经验及依赖它的历史助手回答。

禁止增加写工具或受控业务写能力；Memory 不授予权限、不产生 Evidence、不改变 Gate、Plan、Approval、ActionIntent、Ledger、Scope 或 Handoff 状态。S1 REPAIRED_VERIFIED、S2 DIAGNOSED 与 S2 SCOPE_ESCALATED 为不同业务 Outcome。

工作顺序固定为：独立冻结提交 → 原始 RED 提交 → 最小实现提交 → 新鲜 GREEN/真实评测证据提交 → push main → 停止等待主 Agent。直接在 main 工作，不创建分支/PR。每次仅 stage 本阶段明确管理的文件；本地既有 AGENTS.md、PROJECT_NORTH_STAR.md、开发目录、M2 历史 runs 和 pytest 目录均保持原样。

## 冻结实现卡

| 环节 | 本阶段冻结内容 |
|---|---|
| 用户输入 | Task A 的可信已完成业务经历；Task B 的自然语言描述只提供待调查线索 |
| 模型决策/工具 | Investigator 在相同 DeepSeek、Skill/Knowledge、权限、工具和预算下，Memory ON/OFF 唯一差异是可信历史经验提示；当前只读 MCP 工具决定事实 |
| 受信状态 | SQLite 中的 TaskBinding、S1/S2 receipt、Evidence、Memory 生命周期事件、Context Provenance 和 ContextManifest |
| 禁止动作 | 无 Memory 授权；无 Scope/Policy/配置/工单写入；无越租户/项目检索；不从模型输出或用户自述创建可信案例事实 |
| Gold | GOLD.json 中 8 个 Task B 场景，每项 ON/OFF 一对，16 次计划分母 |
| 真实 Trace | 真实 DeepSeek Provider 请求及 usage、MCP tools/call、Evidence/Gate、所选/排除的 Memory、Task A/B ID、浏览器截图及 Domain 状态 |

## 开工核对与基线

- 仓库：D:\学习\agent新项目；branch main；HEAD 与 origin/main 均为 e46d99231f5ef259754228683a1504bf18cea79f；origin 为 https://github.com/wgqa/OpsPilot.git。
- 已阅读根目录 PROJECT_NORTH_STAR.md、AGENTS.md、vNext v0.3 合同的 §4/M3、附录 N3/N4、M2-02 DEFERRED_GATES、M2-03 REPORT/ACCESS_MATRIX/API_CONTRACT 及本任务卡。
- 工作区存在用户未提交文件；完整路径与状态保存在本轮报告。它们不是 M3-01 的提交范围。
- M2-03 报告记载历史全量 pytest 186/186；本阶段必须重新运行全量测试，不能用历史结果充当新鲜证据。
- 当前 DeepSeek 配置已存在，model id 为 deepseek-flash；模型密钥不会写入文档、日志或 Trace。
- vNext v0.3 合同的 §4 中“长历史摘要”“≥20 轮压缩”属于完整 M3 合同；本 M3-01 明确不实施，长对话压缩仍 NOT_IMPLEMENTED。

## 冻结评测

评测细节与逐案期待见 GOLD.json、RUBRIC.json、EVAL_PROTOCOL.md。16 次试次均使用真实 DeepSeek deepseek-flash 和当前真实 MCP stdio/HTTP；采用现有动态 Investigator strategy A。每对使用等价独立 Task B DB snapshot；同一来源 A 的真实 Memory 在两份 snapshot 均存在，只通过测试级开关控制是否注入，OFF 不删除数据、不改变工具或其他 Context。

8 对由 2 个 S1 正向、2 个 S2 正向、2 个当前事实冲突、1 个主体禁用负例、1 个跨租户/无匹配负例组成。目标 task_id 与来源 task_id 必须不同。每次任务最多 8 次模型请求、6 次 MCP call attempt；预算耗尽按失败保留。记录每次 Provider usage、MCP、Latency、结果和错误；Provider 不返回价格时 cost 标记 NOT_REPORTED，不推算虚构金额。真实 Web 演示另计，不替代 16 个试次。

判定不要求 ON 胜过 OFF。只有当 ON 在至少一个冻结匹配案例中实际被模型纳入并可观察地改变合法的 MCP 调查选择/顺序，且当前事实判断与安全不退化时，才可将样本范围的效用标为 UTILITY_PROVEN；否则为 UTILITY_NOT_PROVEN。模型自述、Prompt 出现 Memory、Token 差异均不能单独证明效用。不得宣称因果或统计显著。

## M301-01～M301-14 冻结门禁

| ID | PASS 标准 | FAIL / NOT_RUN |
|---|---|---|
| M301-01 | 本冻结提交先于 RED/实现；摘要可复验；8 对 Gold 和历史证据未变 | 任一顺序错误、旧分母被改、删题 |
| M301-02 | D5 S1 Candidate/Active/Revoked 与 v8 历史行兼容；v9 迁移（若新增）保留历史 FK/事件 | 数据丢失、破坏旧 API，或以假 S1 ref 表示 S2 |
| M301-03 | 真实 S1 已提交 REPAIR、HTTP 200 VerificationReceipt、冻结 Report 和 Evidence 可生成案例特定候选 | 固定通用 MEMORY_SUMMARY 被称作案例抽取，或来源不完整 |
| M301-04 | S2 DIAGNOSED 与真实 SCOPE_ESCALATED/HandoffReceipt 严格区分 | Draft 被说成已交接，或 S2 冒用 RECOVERED/S1 receipt |
| M301-05 | Candidate 未批准前不可检索；可信 APPROVER 确认/撤销持久；错误角色拒绝 | Support/模型文本直接激活 |
| M301-06 | 同租户/项目、问题类型适配的不同 Task B 进入真实模型上下文；Provenance 含来源与内容摘要 | 同 Task 冒充跨 Task，或只有 UI 显示 |
| M301-07 | 经验与当前 MCP 冲突时当前事实与 Gate 获胜 | 经验导致错误诊断、修复或交接 |
| M301-08 | 撤销、过期、失源或版本不匹配后，后续模型与新 Chat 不含该内容及失效历史依赖 | 缓存/旧答案重注入 |
| M301-09 | Worker 进程恢复、重启及 prompt-build/reserve 竞态 fail-closed 或重新构造 | 已失效资产随恢复出站 |
| M301-10 | 跨租户/项目、错误 owner/角色、伪造来源/digest/request 被拒；Secret 零泄漏 | 越界、伪来源被激活或敏感字段泄露 |
| M301-11 | 新鲜真实浏览器完成 A→Candidate→APPROVER→不同 Task B 使用→撤销→后续 no-use；真实 Provider/MCP/Domain Trace | mock/CLI 代替或断裂用户链 |
| M301-12 | 全部 8 对/16 次纳入分母，真实 Token/时延/工具/Outcome/失败和成本可用性记录 | 选择性报告、Gold 泄漏、改 OFF 条件 |
| M301-13 | 有独立冲突反例；只有可观察策略变化才称效用已证明 | 仅模型自述或表面引用 |
| M301-14 | 新鲜完整 pytest、MCP/HTTP、S1/S2 回归、前端 build/lint 和必要安全 smoke；失败原样保留 | 无新鲜结果或安全硬门失败 |

任何越租户泄露、Domain Gate 绕过、Memory 成为写权限、来源造假、撤销后新 Provider 请求仍带失效内容，都判 M3-01 BLOCK。非阻断效用不佳如实报告并停止，不扩建平台。

## 交付与停止

最终至少提供冻结/RED/实现/证据四个提交 SHA、REPORT.md、RESULTS.json、TRACE.json、FAILURES.md、RUN_INDEX.md、真实运行原始日志与截图、源码学习笔记和面试问答。M3-01 实施 Agent 不自签 PASS；完成提交并推送 main 后立即停止，等待主 Agent 独立验收。M3-02、M4 及通用 Memory 平台均未授权。
