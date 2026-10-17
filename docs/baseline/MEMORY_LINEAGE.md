# vNext M1-01 Memory 与来源链

M1-01 不新增、迁移或重建 Memory。v1.0 D5 的 Episodic Memory、`auth-incident-triage` Skill 与 Context Provenance 按其原有事实和边界保持不变。

`CORRECT_TASK_INPUT` 作为用户消息持久保存，并在当前持久 Run 消费时写入 `task_run_inputs`，provenance 固定为 `USER_INPUT_UNTRUSTED`。它只给 Investigation Prompt 提供用户观察/调查方向，不是 MCP Evidence、Auth Policy、Plan、Approval、permission 或授权依据。被消费的 input digest 可以追溯到 Message/Run，但不能替代本轮 Evidence Gate。

现阶段 Prompt 只在真实 TaskRun 新执行时把本 Run 消费的纠错内容放在标注为 `untrusted_user_corrections` 的字段中；Run checkpoint 隔离避免旧用户输入被别的 Run 隐式继承。记忆撤销传播和更广的 context lineage 仍遵循 v1.0/D5 已记录范围，M1-01 不扩大它们。
