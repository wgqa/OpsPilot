# 512 Token 边界与预算取舍

## 可复现边界

Frozen live summary 的输出估算为 501 Token（Provider Usage 是 481 output tokens；两者是不同计量口径）。经真实 Domain 来源校验后，ID 展开的 JSON 为 1036–1075 Token，必须通过 `_compact_summary_document()` 才能落库。`MAX_COMPRESSION_OUTPUT_TOKENS` 仍为 512。

| 离线完整 Domain 重放 | 12 个映射 | 结果 |
|---|---:|---|
| 修复前，旧 `sequence` 参与计量和落库 | 10 成功 / 2 失败 | 样本 3、10 在 `unresolved_items[2]` 超预算；无 Summary 落库 |
| 修复后，`sequence` 从计量和持久 JSON 移除 | 12 成功 / 0 失败 | Summary 估算 488–512 Token；12/12 Attempt 成功，来源 ID 均可反查 |

失败样本已保存精确预算轨迹。两组在失败锚点前均选中 464 Token；原序列字段下 48 字符锚点为 528/529 Token、24 字符为 518/519 Token。删除 8 个派生 `sequence` 字段后，对应试算分别为 496/497 和 486/487 Token，512 上限本身无需放宽。

修复后按生产计量口径记录的锚点选择峰值为 469–497 Token；持久结果为 488–512 Token。Message ID 的 Token 估算在合成合法 ID 映射间变化（20–31），不再导致持久化成功/失败分化。

## 事实保真边界

内容核对只断言文本标记和其来源序列，不把它当作自然语言语义评分：

| 事实 | 持久 Summary 中可见且来源正确 |
|---|---:|
| `/callback`，来源 seq3 | 12/12 |
| seq3 早期配置 `max_attempts=3` 原文 | 10/12 完整；样本 0、8 为 **PARTIAL**，显示 `max_attempts=…` |
| 正式更正 `req-482` → `req-483`，来源 seq7 | 12/12 |
| 协议 `v1.2` → `v1.3`，来源 seq11 | 12/12 |
| `max_attempts` 3 → 5，来源 seq11 | 12/12 |
| 部署版本未知，来源 seq11 | 12/12 |
| HTTP 202 的否定标记，来源 seq1 | 12/12 |
| Receiver 完成状态仍未解决，来源 seq14/16 | 12/12 |

样本 0、8 的 seq3 文本末尾被 512 Token 压缩器明确加省略号；原始消息仍存在。旧参数值 `3` 在同一 Summary 的 seq11 协议/参数时间线中完整出现，但不能据此声称 seq3 原文完整保留。报告因此保留 `PARTIAL` 状态。完整逐样本文本、序列映射及检查结果在 `REPLAY_MATRIX.json`。

## 768 / 1024 Token 离线情景

使用修复前两个失败映射作容量试算（不是 Provider 调用）：

| 上限 | 样本 3 / 10 估算 | 选择结果（样本 3 / 10 相同） |
|---:|---:|---|
| 512 | 被拒绝 | unresolved 第三锚点无法加入 |
| 768 | 752 / 753 | constraints 3、corrections 1、unresolved 2、timeline 1、user_assertions 2 |
| 1024 | 1018 / 1015 | 额外容纳 rejected_hypotheses 1、unresolved 3、timeline 2、user_assertions 3 |

768/1024 的收益是可放入更多派生项目；当前修复已消除落库阻断，但 seq3 在 2/12 映射仍为部分文本，因此这些情景并不证明所有关键来源原文都完整。增加上限不能替代可恢复原始历史，也会扩大随后回答上下文。

仅作量级比较：冻结的前次授权价格快照为 uncached input USD 0.30 / million tokens、output USD 1.20 / million tokens。若把更高上限同时用于 Provider output，512→768 的额外输出最大 256 Token，即每次摘要至多 USD 0.0003072；512→1024 至多 512 Token，即 USD 0.0006144。若仅把增加部分作为回答输入，按 3 次回答上限及 uncached input 快照计算，分别至多 USD 0.0002304 / USD 0.0004608。此为历史价格的理论上界，不是当前报价，也不是本轮支出；本轮实际 Provider 请求与费用均为 0。

## 取舍

保留 512 Token 合同，仅去掉可从 `source_message_ids` 与 Domain 映射重建的重复 `sequence`。不删除否定、正式更正或当前来源；样本 0、8 的 seq3 部分保留如实标注。768/1024 只记录为设计备选，不在本轮放宽。
