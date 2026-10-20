# M3-02 源码学习笔记

## 阅读顺序

1. `opspilot/domain/context_engineering.py`：从 `_encoding`、`estimate_text_tokens` 和 `estimate_messages_tokens` 看预算估算；`context_budget_for_model` 建立模型预算；`allocate_context_blocks` 在优先级与预算间取舍；`bounded_recent_window` 限定最近交互。
2. `opspilot/domain/chat.py`：`_prepare_context` 负责构建调用输入；`_summary_is_current`、`_latest_current_summary`、`_summary_dependency_refs` 和 `_validate_summary_document` 判断摘要是否仍依赖有效来源；压缩尝试先记录来源，再执行压缩；`assert_chat_compression_sources_current` 和 `assert_chat_context_current` 在使用前复核。
3. `opspilot/investigator.py`：`_prompt_messages()` 将可信绑定、用户未验证输入、当前 MCP Evidence、Gate 反馈与外部指导分区后交给真实 Provider；`context_metadata` 记录 Context Manifest。`_rule_s2_tool_decision()` 是策略对照入口，不替代真实模型轨迹。
4. `frontend/src/App.vue` 与 Web API：Inspector 展示摘要、上下文来源、预算与阻断原因，帮助复核用户会话中的实际调用。

## 关键边界

- Token 估算是可复现的预算工具，不代表 Provider 账单成本；报告优先采用 Provider 返回的实际 token usage。
- 摘要是可重建的派生材料。它必须记录来源引用，并在压缩或模型调用前重新验证，不能成为当前 Evidence。
- `recent_window`、`rolling_summary` 和 `hybrid` 的比较必须保留失败样本。当前真实比较中 Recent Window 完成回答，另两种策略触发 `CHAT_ATTEMPTS_EXHAUSTED`，因此效用没有被证明。
- 浏览器长会话原26轮保留21成功/5失败；此次同一持久会话续至28轮，22成功/6失败。跨进程尝试保留同Run和调用数，预算耗尽安全停止；新Run真实一次摘要+一次回答成功。原始记录在`runs/long-recovery-01/`，不能将安全停止说成有回答。
- Context Engineering 仅决定模型看见什么；TaskControl、Domain Gate、Approval 和动作事务决定 Agent 能做什么。

## 验证记录

主回归命令：`.venv\\Scripts\\python.exe -m pytest -q`。M3-02 当轮全量记录为 `215 passed, 1 deselected`，排除的是当时尚未实现的 M3-03 语义记忆 RED 项。M3-03 合并后的新鲜全量结果以 `docs/evidence/vnext/m3-02-03/runs/m303-final/pytest-full-final.log` 为准。前端命令：`npm run build`（在 `frontend/` 目录）。

## 真实失败后的两个最小修复

`_prepare_context`曾把有效摘要置于近期长回答之后，导致预算1400时生成了摘要却没给模型。补充RED先复现，再调整可选块顺序。另一个缺口是正式`CORRECT_TASK_INPUT`不在旧Chat历史查询中；现在同Tenant/Session/Task的最初任务与最近正式纠错作为原文锚点，依然是未验证用户输入。摘要不可靠时保住目标原文，比让摘要成为权威更容易审计；代价是锚点过大时必须显式失败。

最终专项11/11、全量225/225。真实第28轮Inspector选入Summary v24及两条原文锚点，估算1374/1400；模型准确复述最初目标、禁止事项和正式更正。原对照的失败没有改写，收益仍NOT_PROVEN。索引见`docs/evidence/vnext/m3-02-03/REPORT.md`。
