# M3-03 面试问答

## 1. Semantic Memory 和 Episodic Memory 有什么区别？

**30 秒回答：** Episodic Memory 是从已验证业务结果抽出的案例方法；Semantic Memory 是人工确认的项目约定。两者都只给模型提供指导，不是当前事实或授权。

**2 分钟展开：** Episodic 来源要能追溯到同一业务 Task 的修复、在线验证、冻结报告和证据，检索时核对问题类型、服务和来源状态。Semantic 候选来源于同 Task 持久化用户消息，且创建后不立即进模型；有项目授权的同租户 APPROVER 确认后才在项目范围内加载。它还支持明确修订和撤销。两种记忆都必须服从当前 TaskBinding、MCP Evidence、Gate 和审批。

**可能追问：** 为什么不全部做成一种？来源可信度与审批方式不同，混成一种会模糊案例事实和项目偏好。

**证据：** `episodic_memory.py`、`semantic_memory.py`、`tests/test_m303_semantic_memory.py`。

## 2. 如何保证候选不会未经审批影响模型？

**30 秒回答：** 候选写入时状态是 CANDIDATE，Context 查询只读取活动版本；确认要由拥有项目授权的 APPROVER 完成，Domain 检查操作者、租户、项目、版本和幂等键。

**2 分钟展开：** 候选只从同 Task 已持久化用户消息创建，正文经过敏感信息过滤并记录来源引用。Candidate 创建事件本身不会让它进入 `active_semantic_context`。确认事务再检查现有可信操作者和项目授权，之后状态转为 ACTIVE 并写审计事件。修订明确引用被 supersede 的版本，避免静默覆盖。

**可能追问：** 前端隐藏 Approve 按钮够不够？不够。Web 只是入口，Domain 每次对请求的 actor、scope、版本做最终核验。

**证据：** `tests/test_m303_semantic_memory.py` 的候选隔离、授权、版本和幂等测试；数据库事件记录。

## 3. 撤销后如何防止恢复时重新加载旧记忆？

**30 秒回答：** 每次构造调用上下文都从 Domain 查询当前状态和版本；撤销会改变权威记忆状态并产生事件，旧 checkpoint 只保存执行引用，不能把旧内容当来源重新注入。

**2 分钟展开：** Domain 的 active 查询排除 REVOKED 或过期版本，并给 Provenance 记录排除原因。恢复时所选来源需要再次检查是否仍有效。历史消息若依赖已失效来源，也通过来源有效性判定被排除。测试覆盖撤销后的 Context 查询和引用检查。仍需浏览器完成真实 Task B、撤销和进程恢复链路才能满足 E2E-03。

**可能追问：** 如果旧文本已经保存到聊天记录怎么办？保留审计历史，但不把它重新作为有效来源装载进新模型调用。

**证据：** `active_semantic_context`、`assert_chat_context_current`、M3-03 测试与 `RESULTS.json`。

## 4. 当前能否宣称跨 Task 经验复用已完成？

**30 秒回答：** 代码和自动化测试已覆盖读取、审批、跨 Task Provider 上下文与撤销边界；真实浏览器只完成 Task A 创建和审批，Task B、撤销后的新请求及恢复还未完成，因此整体仍是 `PARTIAL`。

**2 分钟展开：** 当前已核实 Task A 的 DeepSeek 和 MCP Trace，以及 `approver-a` 写入的确认事件；Semantic Memory 是 ACTIVE v1。真实跨 Task 证据还需要 support 身份在不同 Task B 上运行 Provider/MCP，并在撤销后再次调用和跨进程恢复。当前浏览器仍处于 approver-a，因此真实 Web E2E-03 尚未闭环。机器结果和报告明确列出此阻断。

**可能追问：** 为什么不把测试通过当成完成？因为自动化测试不证明浏览器登录与真实 Provider/MCP 的端到端交互发生。

**证据：** `docs/evidence/vnext/m3-02-03/RESULTS.json`、`TRACE-task-a.json`、当前 Web 状态。
