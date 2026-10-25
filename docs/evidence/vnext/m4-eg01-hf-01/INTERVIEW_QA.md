# 面试问答

**问：如何让 Agent 在 Gate 尚不能给出完整诊断时仍回答已确认的部分事实，又不削弱安全边界？**

**答：** 我把 Gate 的 `checked_fact_ids` 视为正式裁决使用的最小证明集，而不是用户解释上下文的全集。Chat 只从该诊断 Run 的成功 MCP Attempt/Observation 建候选，再调用 Domain 的当前性检查验证 TaskBinding、授权、版本、同 Event 关系和 TTL。这样有效的 HTTP 200 订单及同 Event HTTP 202 投递能进入 Context，即使 Receiver 尚未重新取证仍要回答“处理状态未知”。历史 Diagnosis JSON、其他 Run 或不同 Event 都不能因为“看起来相关”而成为当前事实。Gate 继续返回 `INCONCLUSIVE`，Chat 也不产生任何业务写权限。
