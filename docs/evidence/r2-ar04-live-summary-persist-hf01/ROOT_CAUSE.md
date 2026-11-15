# R2-AR04-LIVE-SUMMARY-PERSIST-HF-01 根因

**状态：ACCEPTANCE_CANDIDATE（离线诊断）** | **Base：** `850dd6a61af58db77db6c46ea64360e22129da1a` | **Provider 请求：** 0；**本轮费用：** USD 0

在 Base 上实际读取的治理内容记录为：`PROJECT_NORTH_STAR.md` blob `43dabda468506717c6956e676dfad4304c4f38e6`、`AGENTS.md` blob `807b928686a4dd2cac7b15b3c354b9943c93c910`、`opspilot-slice-review` Skill blob `d405c8d413d633824b279202cc1503dab4cf0b03`。冻结复测合同 `PLAN.md` SHA-256 为 `c268a953735fc3420da33f657a0db1c0fa759aad260619121ab41291eb15729d`。

## 结论

冻结的 Q02-A 首次 DeepSeek 摘要在原实跑中的持久化失败，历史记录只保留 `TaskControlError` 类名，没有保留 `TaskControlError.code`、安全详情和当时的 `Sequence → Message ID` 映射。因此无法把离线合成重放的错误码冒充为历史实跑的精确错误码。原始失败码标记为 **`UNVERIFIED_NOT_CAPTURED`**。

在 12 个隔离 Domain 映射中用同一条冻结摘要走完整 `prepare → validate → complete` 路径，修复前有 2 个映射稳定触发 `CONTEXT_SUMMARY_FACT_RETENTION_BUDGET_EXCEEDED:unresolved_items:2`。原因是摘要 JSON 为每条来源同时序列化了 `source_message_ids` 与可由来源映射推导的 `sequence`。长 Message ID 的 Token 编码不同，重复字段使最后一个必须保留的 unresolved 锚点超过 512 Token。两次失败均没有 Summary 落库；Attempt 被置为 `FAILED`，Run 为 `INTERRUPTED_RECOVERABLE`，Answer Manifest 为空。

另有确定的 Runner 错误掩盖：压缩失败后没有 Answer Manifest，旧 Runner 仍按“必有回答记录”访问它，抛出二次 `KeyError` 并覆盖了 Domain 原因。本轮加入结构化 `STOPPED` 分支；注入 Domain 持久化失败后，Runner 保留错误码、0 次回答请求，并将之后的 Case 记为 `NOT_STARTED`。

## 冻结实跑证据与离线复现边界

冻结记录中的 `Q02-A:SUMMARY:1` Provider Response ID 为 `c3435ff4-fc27-4ffb-b053-bbfcabc600e0`，模型 `deepseek-flash`，Usage 为输入 4106、输出 481、合计 4587 Token。Provider 返回成功，未发送 Answer 请求。原实跑记录标为 `TaskControlError`，持久 Summary 数为 0，Runner 停止原因记为 `KeyError`。

12 个离线映射使用隔离临时 Domain、确定性 `message-{UUID}` ID 和同一冻结历史/问题/摘要。Message ID 的估算分别为 20–31 Token；输入摘要经来源校验后为 1036–1075 Token。该实验能复现预算边界与 Domain 状态，但**不能恢复原实跑 ID 映射或原始错误码**。

## 调用链

```text
Assistant Runtime
  _prepare_assistant_context_impl
    prepare_chat_compression_attempt
    └─ Context Manifest + source_sequence_map
    complete_chat_compression_attempt
      _validate_summary_document
      └─ Sequence → Message ID 来源绑定
      _compact_summary_document
      └─ 512 Token 锚点选择 / 投影
      Domain 事务校验当前来源并写入 Summary + Attempt
    异常处理 → fail_chat_compression_attempt + Run STOP
  ABC evaluation Runner
    get_chat_manifest
    └─ 旧路径假设 Answer Manifest 存在，失败时二次 KeyError
```

## 证据状态

| 项目 | 证据结论 |
|---|---|
| 历史真实持久化调用 | Trace 确认失败；错误码/详情及原始来源 ID 映射未记录 |
| 修复前完整 Domain 重放 | Fixture / 实际 Domain API；12 组映射中 10 成功、2 失败 |
| 失败字段 | `unresolved_items`, item index `2`；安全详情 `CONTEXT_SUMMARY_FACT_RETENTION_BUDGET_EXCEEDED:unresolved_items:2` |
| 修复后完整 Domain 重放 | Fixture / 实际 Domain API；12/12 成功，Summary 估算 488–512 Token |
| 来源保真 | 持久化仅保留 `source_message_ids`；最终投影可逆映射到 Sequence，12/12 所有 ID 可解析 |
| Runner 失败处理 | MockTransport + 注入真实 Domain `TaskControlError` 路径；结构化停止，未访问缺失 Answer Manifest |
| Provider / MCP | 0 / 0 |

逐样本的原始来源映射、Anchor 估算轨迹、Domain Attempt/Run 状态及持久化摘要见 [`REPLAY_MATRIX.json`](REPLAY_MATRIX.json)。此前根 `RESULTS.json` 的角色及真实停止文件索引见 [`LIVE_EVIDENCE_INDEX.md`](LIVE_EVIDENCE_INDEX.md)。
