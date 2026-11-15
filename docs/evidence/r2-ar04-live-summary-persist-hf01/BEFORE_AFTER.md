# 修复前后对照

## 最小改动

1. `opspilot/domain/chat.py`：计量摘要时排除派生 `sequence`；持久化前移除 `initial_goal` / 数组条目中的 `sequence`。`source_message_ids` 保持不变，`_summary_prompt_projection()` 会使用 Domain 映射重新生成 `source_sequences`。
2. `opspilot/assistant.py`：压缩失败时安全地保留 ASCII `TaskControlError.code`，其他异常回退到异常类名。Domain Attempt 和 Run 的停止原因不再被统一的 `CHAT_CONTEXT_COMPRESSION_FAILED` 覆盖。
3. `docs/evidence/abc-live-env-unblock-01/run_abc_eval.py`：Answer Manifest 为空时直接返回结构化 `STOPPED`，读取 Domain 的失败 Attempt 原因，不再对缺失回答索引并抛 `KeyError`。
4. 新增 `tests/test_ar04_live_summary_persist_hf_01.py`；扩充边界断言，验证完整否定约束能在本样本预算内保存。

没有调整 512 Token 上限、生产策略、历史 Gold、Trace、结果或账本；没有创建授权、调用 Provider、外部 MCP 或业务工具。`run_recheck.py` 和所有冻结结果文件均保持 Base 版本。

## 可复现结果

| 验证 | 结果 | 证据等级 |
|---|---|---|
| 冻结 Q02-A 首次摘要走完整隔离 Domain 提交路径 | 修复前 10/12 成功、2/12 以 `CONTEXT_SUMMARY_FACT_RETENTION_BUDGET_EXCEEDED` 失败；修复后 12/12 成功 | Fixture + 实际 Domain API；无 Provider |
| 不同合法 Message ID | 20–31 Token 的估算跨度；修复后均成功 | Fixture |
| 来源映射和 Summary | 12/12 Summary 落库；所有 `source_message_ids` 均映射回验证来源 Sequence | 实际 Domain 数据库断言 |
| 512 上限 | 修复后 12 个持久摘要为 488–512 Token；上限保持 512 | Fixture + 生产估算器 |
| 关键文本 | Q02-A 原摘要在持久化投影中保留协议/参数变化、纠错、未知状态、否定标记和未决项；seq3 早期参数在 2/12 为 `PARTIAL` | 确定性文本/来源断言；非语义评分 |
| Runner 无回答 Manifest | 结构化停止，错误码保留；Answer 请求 0，后续 Case 未启动 | MockTransport + 注入 Domain 错误 |
| 现有事实/上下文、来源当前性、C06、Grant 回归 | 30 + 21 项通过 | 离线 pytest |
| 历史文件完整性 | Trace、Gold、RESULTS、C06 RED、账本等有 SHA-256 且 Git 状态干净 | 文件哈希 + Git |

## 保留的失败和边界

- 修复前两个 Domain 失败样本在 `REPLAY_MATRIX_BEFORE.json` 保留；失败 Attempt、未落库 Summary 和空 Answer Manifest 均被记录。
- 第一次最终核心测试遇到旧 Recheck wrapper 的冻结 Compactor blob pin，不是功能失败。测试将 pin 检查限定在本用例外，随后完整核心组通过；失败日志仍保存在 `CORE_TEST_OUTPUT_CHECKOUT_PIN_FAIL.txt`。
- Q02-A 两个较长 ID 映射中，seq3 文本明确以省略号标为部分保留；seq11 仍以自己的来源完整保留 `3→5`。不会将两个来源混为一个完整原始回忆结论。
- 历史 F01 `completed_tools` 单测失配是既有遗留，本轮未运行或修复；沿用既有记录，不扩大范围。
- C06 既有 RED Trace、结果与日志不变。相关 C06 门禁测试通过表示当前行为符合其冻结断言，不代表删除或改写了 RED。
