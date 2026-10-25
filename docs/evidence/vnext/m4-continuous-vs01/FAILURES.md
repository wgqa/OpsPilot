# 失败与修复记录（不替换首次结果）

| 记录 | 观察 | 处理与分类 |
|---|---|---|
| `red-01` | 基线四项定向测试失败 | 有效实现前 RED：历史能力、候选回送、终答复用、有界非空交付 |
| `history-migration-failure-01` | 新 schema 16 被支持上限 15 拒绝 | 本轮实现缺陷；修正版本支持，迁移正例另测 |
| `expanded-01` / `regression-01` | 测试读取 Graph 返回值键错误、Context helper monkeypatch 位置旧 | 测试准备/兼容修正；断言语义不改 |
| `delivery-artifact-red-01` | Graph 结束却无可用用户答复 | 产品缺口；新增窄的不可变 Run 答复，未放宽 Diagnosis 正文来源 |
| `expanded-02` | 新 Run 测试先把 Task 完成；无响应 HTTP 空 JSON 抛错 | 修正测试准备；实际未知发送单独记录 OUTCOME_UNKNOWN |
| `expanded-04` | 过严历史来源过滤误拒绝更早诊断的合法引用 | 先前业务 Evidence 可作为历史来源，显式 origin_run_id 按其核对；始终不能变成本轮 current Evidence |
| `full-01` | 359 passed / 1 failed | 唯一失败是原冻结实现前 C1 RED，原样保留，不重写制造全绿 |
| `regression-final-01` | 删除旧私有解析入口使既有回归 ImportError | 恢复兼容入口；运行时共用新解析，旧合同断言保持 |
| `fenced-response-red-01` | 正常“前言 + 一个 JSON 块”终答未被复用 | 产品格式解析缺陷；只解析唯一 JSON 块，多块仍拒绝 |
| `budget-01` / `controls-01` | 新准备 Receiver 缺接收时间/SLA 等协议字段，Gate 拒绝正式诊断 | 准备缺陷暴露组全部保留；单独 Receiver RED→GREEN；不修改 Gate |
| `receiver-contract-red-01` | 真实 HTTP 事实到齐仍 NEED_MORE | 修复测试 Sender/投影，使 202 QUEUED/accepted_at/SLA 及 retry_at 关系满足原合同 |
| `budget-02` 最大配置 | 16 MODEL 后仍走事实降级，109.8s | 策略/解析与成本失败；不把加预算当收益，不替换该结果 |
| `controls-02` H | 模型 focus 导致遗漏历史目标，运行时仍 ANSWERED | 策略/结果完整性不足；评估不得直接信运行时标签 |
| `web-02/01-initial...` | 正式 Diagnosis 正文与用户答复重复展开 | 展示问题；同回执正文不重复，原截图保留 |
| `web-02/04-followup-highwater-failure.txt` | 确认更正后下一次补查被 TASK_INPUT_HIGHWATER_STALE 阻止 | 产品接线缺陷；`correction-continuity-red-01` 复现，原创建事务复制可信高水位，不删除校验 |
| `web-02/06-budget-gap-after-fix.txt` | 同 Task 累计 8 MODEL / 6 MCP 耗尽 | 受控 PARTIAL，有非空缺口；计数保持，不给旧 Task 追加或清零 |
| `response-preview-red-01` | 合法长 JSON 被 2000 字符预览截断，额外调用、最终降级 | 产品缺陷；S3 在既有 20000 字符结果边界内解析，旧 S1/S2 默认保持 2000 |
| `holdout-01` | 四例首次结果 1 ANSWERED / 3 PARTIAL，含一次事实降级 | 不重跑；版本是 e42087e，最终响应修复效果不能借这组声称独立证实 |
| `web-03/02-followup-explanation.txt` | 正确接续协议来源，却在完成证明上加入“且过了 SLA” | **未修的产品解释质量失败**。PROCESSED 不须等 SLA；Gate/权限未受影响。交主 Agent 评估，不用词表掩饰 |
| `fact-gold-01/P1-failed` | 冻结 expected QUEUED 与两次 503 准备后的 NOT_RECEIVED 不一致 | Gold 冻结不改；不计作正确性 PASS |
| `frontend-final-01/lint.log` | 历史 e2e 脚本两项 ESLint error；新模板两项 shadow warning | 新模板 warning 修正，改动文件 lint 通过；旧脚本不改，整仓 lint 仍非零 |

另外两次定向命令用了不存在的旧测试文件名，`target-final-01` / `correction-continuity-green-01` exit 4，未运行测试；随后实际正确文件组合另存日志。证据汇总脚本曾用错 chat 表/关联字段及 fastmcp 分发名，修正为实际 `chat_answer_chunks → chat_attempts` 与 `mcp` 包；属于汇总准备问题，没有写业务 DB。

安全失败与产品失败不混合计分。新增跨 Event 错误证明、错订单、撤权、TTL/Run 关联和副作用负例在最终有效回归中通过；这不抵消上述质量或证据限制。全部运行原文在 `runs/`，旧 Gold、历史 RED、回执和报告不改。
