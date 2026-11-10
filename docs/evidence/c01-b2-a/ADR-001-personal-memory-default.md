# ADR-001: 普通 Assistant 的个人长期记忆

**状态：** C01-B2-A 候选决策

**基线：** `codex/c01-b-memory-continuity@1c48f365c93fcef1b7e97cfe4941f6bb83a0a9de`

## 决策

- 继续复用 `personal_memories`、`personal_memory_events` 与 `semantic_memory.py`。普通 `CHAT_READONLY` Assistant 增加本地 `memory_remember` 工具；租户、所有者和来源消息由当前持久 Run 派生，模型只能提交记忆类型、模式、Key、内容和可选版本引用。
- 用户消息必须明确表达长期保存意图，且不得只是一次性要求、引述内容或日志/文档材料。程序校验可信来源、个人作用域、长度、敏感内容、版本、幂等和来源当前性。明确保存直接成为 `USER_EXPLICIT` 活跃版本；旧 C01-B 候选仍须用户在面板确认，记为 `USER_CONFIRMED`。
- `PINNED` 仅用于个人偏好/工作习惯，召回时不要求关键词匹配，最多 3 条、约 250 Tokens；`PROJECT_BACKGROUND` 不允许标为全局固定。`RELEVANT` 保留现有词项检索并最多选择 3 条。两种模式仍使用同一 Store 和 Context Builder。
- 用户的显式修订回合不注入旧个人记忆。若当前可信用户消息明确要求更正同一 Key，Store 在 `BEGIN IMMEDIATE` 事务中读取并校验该 Key 的当前版本，再创建新版本；普通保存不能静默覆盖冲突。撤销/过期记录可由后续新的明确保存建立新版本。
- 新增最小 `personal_memory_settings` 表，作用域为 `(tenant_id, owner_actor_id)`，默认开启且惰性持久化。关闭只排除后续请求的个人记忆，不删除 Session、原始消息、Memory 或 Checkpoint。
- 继续沿用当前 180 天有效期，并在管理面板显式展示；不使用远期时间戳假装永久。无固定到期时间留给 B2-B 裁决。
- `AUTO_LEARNED` 只作为来源枚举预留；本阶段没有自动 Consolidator、自动提升或自动学习开关。个人记忆不能成为业务事实、Evidence、审批或授权。项目 Semantic 与 Episodic Memory 合同不变。

## 生命周期与持久化

Memory 内容和来源只保存在个人 Memory 记录与既有请求审计数据中，不写入 Session Assistant Message。`memory_remember` 的工具结果只返回不含内容的收据。活动 Run 的 LangGraph Checkpoint 保留执行恢复能力；若任一模型请求实际包含个人记忆，或 Run 调用了 `memory_remember`，则先持久化最终回答，再删除成功 Run 的整个 Checkpoint thread，避免长期保留召回文本或工具参数。工具调用与结果 ID 必须配对；源消息及 Memory 来源记录仍保留。

Schema 22 为现有个人 Memory 增加 `memory_mode`、`creation_source`，为设置增加一行一用户的存储，并扩展个人 Memory 事件类型。迁移将旧已确认记录映射为 `USER_CONFIRMED`，未确认候选保持空来源；原记录、状态、事件和外键关系均保留。

## 影响与未实施事项

本决策改变普通 Assistant 的个人记忆保存和召回入口，不放宽项目/租户共享记忆审批，不改变业务 Domain、Runtime Grant、MCP 权限或 LangGraph Agent Loop。B2-B 的自动整理、无固定到期时间、冲突合并和更智能检索均未实施。
