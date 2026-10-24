# C1-HF-01 验收补充：历史 Chat 回答来源失效

本补充只细化既有 HF-02 来源有效性要求，不修改原冻结 Gold、既有 RED 或业务成功定义。

## 新增边界用例

若一次 Chat 回答的 Context Manifest 实际装配了先前只读补查结果及其 `CURRENT_APPLICABLE` Knowledge 引用，之后该 Knowledge 版本、摘要或适用性发生变化，则后续 Chat Context 必须重新校验该回答的依赖，并排除失效的历史助手回答。数据库中的原回答与原 Manifest 仍保留用于审计；旧文本可以通过有明确失效标记的历史补查记录被 Agent 识别，但不得继续作为有效协议依据。

验收以同一 Task/Session 的真实消息、已完成 Chat Attempt、持久 Context Manifest、替换后的 Knowledge 版本和下一轮实际装配结果为准；应核对被排除的助手 Message ID 与原因 `PRIOR_READONLY_FOLLOWUP_SOURCE_INVALID`，并确认来源仍有效的同 Task 历史追问没有被误拒。

用例 ID：`HF-02-CHAT-LINEAGE`。该用例先于其专属实现修改提交，并在补丁暂时撤回时执行 RED；原 HF-01～06 冻结及其原始 RED 日志保持不变。
