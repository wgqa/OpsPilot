# R2-AR04 真实摘要持久化预算回归

**候选状态** `ACCEPTANCE_CANDIDATE`。实施方离线验证，主 Agent 独立验收待完成。

## 核验范围

- 仓库 `wgqa/OpsPilot`，工作分支 `codex/r2-ar04-summary-persist-budget-hf01`。Base `24ab8bc9b4dfc910a36b2096c549a1987f739d4b` 与开工时原候选远端一致。复用既有 Worktree。
- 实际读取目标提交的 North Star、AGENTS、评审 Skill。Blob 依次为 `43dabda468506717c6956e676dfad4304c4f38e6`、`807b928686a4dd2cac7b15b3c354b9943c93c910`、`d405c8d413d633824b279202cc1503dab4cf0b03`。v1.0 安全合同 Blob 为 `30e18d7ddbade7cdf7712d035d6fd8488bcb9676`。
- 本任务采用已冻结的 1,024 Token 摘要生成上限、512 Token 持久化上限、来源失效阻断和只读回忆约束。C06 历史 RED 和 F01 已知断言失配保持原处。 [剩余复测合同](../r2-ar04-remaining-live-gate-01/PLAN.md) · [生成预算合同](../r2-ar04-summary-output-headroom-hf01/REPORT.md) · [来源门禁](../vnext/m2-02/DEFERRED_GATES.md) · [F01 差分结论](../r2-ar04-base-diff-edge-gate-hf02/BASE_VS_HEAD.md)

## 实跑失败复现

重放 `Q02-B:SUMMARY:1` 的 `RESPONSE_RECEIVED`，Response ID `0c1b0cab-cd71-43e0-a9d9-5f36aaefa989`。脚本核对 Trace、账本、运行结果、冻结历史的摘要，以及原始请求与响应的关联。Prompt 摘要与失败 Attempt 记录相同，输入估算为 6,000 Token。

首轮没有父摘要。按生产 `_summary_dependency_refs()` 的消息顺序，从 Trace 的 seq1–16 和持久 Attempt 的 16 个允许 ID 重建实际映射。逐项核对原始正文 Digest 与依赖类型。Assistant 条目另核对其 Sequence 版本。seq16 只发送了截取文本，脚本按冻结原文重建相同截取并核对原文 Digest。隔离 Domain 的准备调用随后生成了逐条相同的首轮 Prompt 和相同的来源映射。 [实跑证据](../r2-ar04-remaining-live-gate-01/live_run_02/EXECUTION_REPORT.md) · [复现数据](BASE_REPLAY.json)

直接调用 `_validate_summary_document()` 后用原 `_compact_summary_document()` 重现错误 `CONTEXT_SUMMARY_FACT_RETENTION_BUDGET_EXCEEDED:unresolved_items:2`。索引从 0 开始。该条引用 seq11，文本为“协议 v1.3 与 max_attempts=5 的部署版本未知。”。

| 累加条目 | 来源序号 | ID 格式累计 Token | 本步增加 | 同一文本换序号的累计 Token |
| --- | --- | ---: | ---: | ---: |
| `initial_goal` 与空列表 | 1 | 93 | 48（文本 25，ID 23） | 70 |
| `user_assertions[0]`，48 字符 | 3 | 140 | 47 | 91 |
| `corrections[0]`，58 字符 | 7 | 201 | 61 | 127 |
| `timeline[0]`，50 字符 | 11 | 271 | 70 | 172 |
| `constraints[0]`，23 字符 | 5 | 330 | 59 | 208 |
| `constraints[2]`，29 字符 | 13 | 396 | 66 | 245 |
| `unresolved_items[1]`，48 字符 | 14、16 | 471 | 75 | 270 |
| `unresolved_items[2]` 原 33 字符 | 11 | 525 | 54 | 299 |
| 同一条压到 24 字符 | 11 | **517** | 46 | 291 |

预算分解按同一条 system 消息做边际估算。先保留相同结构并将文本和引用置空，再加入全文，最后加入引用值。估算器为 `tiktoken cl100k_base 0.14.0`。字符串分词受序列化边界影响，各分量对应这组替换顺序。

| 结构 | JSON 骨架 | 文本 | 引用值 | 消息框架 | 合计 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 最短失败试算，长 ID | 94 | 188 | 228 | 7 | **517** |
| 必保留条目全文，长 ID | 94 | 211 | 228 | 7 | **540** |
| 必保留条目全文，序号 | 86 | 211 | 10 | 7 | **314** |
| 全部 13 条，长 ID | 134 | 329 | 637 | 7 | **1,107** |
| 全部 13 条，序号 | 121 | 329 | 37 | 7 | **494** |

模型报告 458 输出 Token。应用估算针对校验后的本地序列化结构。失败来自每条引用展开为长 Message ID 后的成本。已有的下一轮压缩投影用序号，若再走旧压缩器，估算降到 482，但会将 25 个引用裁到 19 个。全文和全部 25 个引用用序号已有 18 Token 余量。 [候选预算数据](CANDIDATE_REPLAY.json)

## 生产变更

`chat.py` 仍优先走现有 ID 结构。只有遇到必保留条目预算错误，且完整的序号结构符合条目长度与数量边界并且不超过 512 时，才写入紧凑摘要。该分支保持原模型的文本和序号列表。真实 Q02-B 的 13 条文字和 25 个引用逐项相等。超过上限时保留原错误。515 Token 反例没有落库。

现有 `source_attempt_id` 指向当次成功 Attempt。原 `source_sequence_map`、允许 ID 列表与依赖表继续作为来源记录。读取紧凑摘要时，在同一 tenant、Session 和 Task 中核对引用序号仍对应原 ID，再执行原有 Digest 与父摘要当前性检查。压缩前与写入前都复核当次映射。下一轮摘要输入复用已经合格的紧凑文档，最终回答上下文使用同一结构。说明前缀另计入完整输入预算。

未增加数据库字段或迁移。已有 ID 文档的落库、读取和回答前缀沿用原逻辑。旧版程序无法从新格式文档恢复父摘要来源集合，混合版本与回滚没有在本轮验证。生产 `chat.py` Blob 由 `f78ff94586af56b94b9585c5e7f8abeb5b006ad6` 变为 `6a57360de6f5579fa65dc008de4fcf37148c43f0`。历史 Runner 的生产 Blob 固定值和回答解析器的旧前缀保持冻结，未来真实测试需独立审查并更新绑定。 [原 Runner](../r2-ar04-remaining-live-gate-01/run_remaining_live_gate.py) · [历史回答解析](../r2-ar04-live-retention-recheck-01/retention_evidence.py)

## 离线验证与停止线

| 检查 | 证据 |
| --- | --- |
| Q02-B 初次持久化 | 原回复与原首轮 Prompt/来源映射经正常 Domain API 对照。首个 `CURRENT` 摘要为 494 Token |
| 第二轮和最终 Prompt | 下一轮输入含同一摘要和全部引用。第二个响应使用固定离线回放，新的 `CURRENT` 摘要和准备好的回答 Prompt 保留同一内容 |
| Q06-B | 既有真实回复离线回归核对 seq11 的版本和参数变化。本轮未取得新的 Q06-B 回复 |
| 不完整事实 | 合成反例中 seq3 `max_attempts=…` 原样保留，即使 seq11 有完整的版本和参数变化。历史 `PARTIAL` 记录未改 |
| 撤销及错配 | 隔离数据库中使原消息 Digest 失效或将序号绑定改到另一个已允许的 ID，摘要变为 `INVALID` 并从 Prompt 排除 |
| 预算和边界 | 515 Token 全文反例拒绝。旧的输出截断、超生成上限、C06 及来源当前性回归见测试日志 |

共 52 个不同的定向用例通过，精确重放的 6 项另行复跑通过。扩展回归的首次合跑在 C06 长历史项停滞。该隔离数据库已记录两次成功压缩和最终回答，分组复跑全部通过。合跑停滞原因未确定。 [完整测试记录](TEST_RUN.txt)

本切片验证跨轮追问可再次获得已有的历史事实和来源。没有扩大模型的决策或工具权限。观察到完整结果可放入预算时允许持久化，观察到超预算、来源无效或绑定不一致时拒绝。仍使用已有 Domain 拥有的来源映射和当前性检查，512 上限持续生效。

本轮真实 Provider 请求、授权创建、外部 MCP 调用及生产数据库写入均为 0。证据等级为冻结真实回复的离线重放、确定性 Domain 回归和本地 Mock。真实回答 L3 未运行。候选交主 Agent 独立审查。
