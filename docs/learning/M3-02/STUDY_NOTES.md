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
- 浏览器长对话有成功与失败 Run；完整 PID 到跨进程恢复 Run 的持久关联证据缺失，故 CTX-07 仍为 `UNVERIFIED`。
- Context Engineering 仅决定模型看见什么；TaskControl、Domain Gate、Approval 和动作事务决定 Agent 能做什么。

## 验证记录

主回归命令：`.venv\\Scripts\\python.exe -m pytest -q`。M3-02 当轮全量记录为 `215 passed, 1 deselected`，排除的是当时尚未实现的 M3-03 语义记忆 RED 项。M3-03 合并后的新鲜全量结果以 `docs/evidence/vnext/m3-02-03/runs/m303-final/pytest-full-final.log` 为准。前端命令：`npm run build`（在 `frontend/` 目录）。
