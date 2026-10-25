# 真实实验发现与后续执行登记

2026-10-25，`budget-01` 六个首次预算实验全部保留，不替换结果。运行源码是 `209a3b7`（进程已载入，不受其后工作树编辑影响）。8/6、12/8、16/10 仍分组；无新增主实验、无调高默认预算。

发现一：Provider 会给出“简短前言 + 单个 fenced JSON”的合法最终回答。旧解析器没有接住这种格式，造成后续重复查询/解释和成本。已新增独立 RED（`fenced-response-red-01`），最小修正只解析唯一 JSON 块，多个块仍拒绝。未使用留出实例调优。六个首次实验不能作为修正后的统计；后续 Web/留出另记实际代码版本。

发现二：实际 Provider usage 的 output_tokens 可超过 SDK 中的 max_tokens=512（含 reasoning），首次计费预留的输出上界不成立。原始 ledger 不改。核对 [DeepSeek API](https://api-docs.deepseek.com/quick_start/pricing/) 的最大输出 384K 后，测试包装器对下一次请求改用 393216 Token 的最大在途敞口预留；已完成请求以实际 usage 的峰值估算结算，失败/usage 缺失继续保留保守敞口。开始下一组前重新计算历史敞口；仍须低于 USD 3 与 180 请求。此前实际 Token、费用全部保留，不把 SDK 参数称为 Provider 强制限制，不称估算为实扣账单。

六个首次实验只保存动作写表计数，未保存业务表完整 before/after 快照；后续实验新增该捕获，不能事后伪造前六例的快照。旧记录的这个证据限制在最终报告单列。

随后在 R/H 对照中发现本轮新增的测试 Receiver 响应不满足既有 S3 协议：缺少 `accepted_at/processing_sla_seconds`，投递投影未保留 `retry_at`，PROCESSED 测试误把接收队列确认与后续处理状态合在 HTTP 响应里。原 Gate 因而拒绝正式诊断，这是正确拒绝，不放宽 Gate。`receiver-contract-red-01` 固化复现；修正只作用于本轮新增测试发送端和投影：202 实际响应始终 QUEUED，后续 PROCESSED 是独立标记的可信测试准备状态。所有真实 HTTP 时间仍不回填。

`budget-01` 六例与 `controls-01` 四例全部保留为准备缺陷暴露组，不能当作最终公平 R/H/A 验收。新增 `budget-02` 与 `controls-02`，各例按原配置再运行一次作修复后对照；这十个补充 Task 也计入原来的全局 180 请求 / USD 3 限制，不申请追加上限。主结果与失败组分列，不能替代首次结果。`web-01` 尚未登录或发起任务/模型调用，停掉后用全新 `web-02` 测试库。
