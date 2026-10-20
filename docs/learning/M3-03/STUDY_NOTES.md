# M3-03 源码学习笔记

## 先读既有 Episodic Memory

`opspilot/domain/episodic_memory.py` 复用 D5 案例记忆。`_source_for_task`（以及 S2 对应来源验证）从 Domain 收据建立候选来源；`create_memory_candidate`、`confirm_memory` 和 `revoke_memory` 管理候选生命周期；`select_applicable_memories` 会检查当前租户/项目、不同 Task、问题类型、服务、状态、到期时间、内容摘要与来源有效性，并给选中和排除项附理由。`assert_selected_memories_current` 在运行恢复时复核选中版本。

本轮保留上限：默认最多选 1 个 Episodic Memory，接口允许最多 3 个；每次最多扫描 100 条。Inspector 展示适用理由和排除原因。历史 M3-01 评测仍为 8 对、16 arms、12/16 gold match，结论 `UTILITY_NOT_PROVEN`。

## 再读新增 Semantic Memory

`opspilot/domain/semantic_memory.py` 实现最小项目约定：`create_semantic_candidate` 只从同 Task 已持久化用户消息创建候选；`confirm_semantic_memory` 检查同租户、项目授权 APPROVER、当前版本和幂等身份后生效；`revoke_semantic_memory` 写入撤销事件并使后续查询失效；`active_semantic_context` 只加载当前有效版本并返回失效/排除来源。

`opspilot/domain/database.py` 将 Schema 从 v9 前进到 v11，增加 Semantic Memory、事件、命令和项目审批授权表。迁移新增授权只按同租户既有可信 APPROVER 与已有 TaskBinding 项目回填。`chat.py` 与 `investigator.py` 将语义内容标为非权威指导，不能替代 MCP Evidence、Gate、审批或当前事实。

## Web 与审计链

`opspilot/web/schemas.py`、`opspilot/web/app.py` 暴露项目候选、审批、修订和撤销接口；`frontend/src/App.vue` 展示审核队列、有效版本、来源和 Provenance。真实 Task A 在 Web 建立，真实 DeepSeek/MCP 调查后创建项目约定，`approver-a` 确认为 ACTIVE v1。当前浏览器仍需 `support-a` 完成 Task B 的真实对话和撤销后再调用，因此 E2E-03 保持未完成。

## 安全和限制

- Semantic 内容只作为项目背景约定；即便内容写着“使用某路线”，可信 TaskBinding 与实时 MCP 决定真正可查范围。
- Task A 与 Task B 必须不同；相同 Task 的源记忆排除。
- 撤销依赖来源机制和当前 Domain 状态；checkpoint 不能重新注入已撤销内容。
- 自动化测试证明权限和状态约束，不等于真实浏览器链路完成。
- 旧 Episodic 记忆与新增 Semantic 约定是不同类型、不同审批生命周期；没有新建向量数据库或通用记忆平台。

## 验证

新增定向命令：`.venv\\Scripts\\python.exe -m pytest -q tests/test_m301_memory.py tests/test_m303_semantic_memory.py`。构建命令：`npm run build`（目录 `frontend/`）。完整新鲜全量回归以 `docs/evidence/vnext/m3-02-03/runs/m303-final/pytest-full-final.log` 和同目录 exit-code 文件为准。
