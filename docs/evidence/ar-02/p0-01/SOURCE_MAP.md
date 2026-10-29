# 原理、业务、源码与面试

## 一条可讲清的调用链

`App.vue 专业入口 → assistant/messages → admit_task_message 同一事务 → assistant_runs 固定核心 →
Worker claim/fence → create_agent → 合法 MCP → 持久 Observation → 模型后续决策 →
complete_chat_attempt 同事务复核 → 原 Session Message / Outbox / SSE`

1. **没有 Task 也能开始**：`web/app.py` 的专业消息入口复用现有 Session/Message/Run、身份、
   Operation 幂等。`domain/task_control.py` 只为新入口持久登记核心；普通问答不创建假业务 Task。
2. **资料范围不是用户输入**：`domain/assistant_knowledge.py` 和 `knowledge/assistant-access.json`
   把当前可信 tenant/actor/role 映射到少量文档集合。唯一范围自动选，多范围由用户选。
   Semantic Memory 的 Approver grant 不被误用为 Knowledge 读取权限。
3. **LangChain 核心**：`assistant.py::Loop` 包装标准 create_agent 的模型/工具边缘。
   没有故障 Router、Planner 或 Supervisor；最终正文直接使用自然语言，避免 AR-01 的
   `<result>` 包装解释被旧专用解析器丢失。业务成功仍不由自然语言授权。
4. **原子工具**：`assistant_mcp.py` 无 Task 只提供 Knowledge；有经用户确认的 S3 TaskBinding
   后复用订单、投递、Receiver、历史工具。原有 Skill 保留在旧路径，本切片未迁移其选择与来源
   链，不能声称新入口证明了 Skill 收益。
5. **Context 的层次**：复用 `chat.py::_prepare_context` 的历史和窗口；先前工具引用由
   `domain/assistant.py::history_sources` 重建，标为历史线索。只有本 Run 的成功 Observation
   经过 `current_s3_evidence` 核验后才可支持当前业务说明。
6. **来源与预算**：`assistant_calls` 存实际模型输入、工具 Schema、逻辑键、状态、结果和 Usage。
   它是执行审计，不是业务状态。所有 RESERVED/FAILED/UNKNOWN 都占用次数；Task 内新核心的
   Provider 调用归现有辅助额度，MCP 归既有 Task/Run Ledger，不增加原 Task 上限。
7. **Checkpoint 与副作用**：固定 `assistant-v1:<run_id>` 的 SQLite Checkpoint 管执行位置；
   Domain 的调用记录判断已知结果能否重放，未知结果不能自动重发。最后答复仍由已有
   chat_run_answers 的唯一 Run 身份保证只提交一次，Checkpoint 不是授权来源。
8. **恢复证明**：测试在一次真实 HTTP Observation 持久化后 `os._exit(86)`，新进程取得同一
   Worker 锁、恢复累计时间与同 Run，再继续。计数和最终 Message 没有重置或重复。

## 已解决的真实接线失败

- 模型回调的配置应由 LangGraph `get_config()` 取得，当前 Runtime 对象没有 `.config`。
- MCP 普通 dict 结果可能在 JSON 文本内容中；只取 structured_content 会丢 Knowledge 来源。
- 旧关联校验将所有 CHAT_READONLY 排除；新核心仅通过持久的 ASSISTANT_V1 身份获得只读
  Observation 关联能力，普通 Chat 仍被拒绝。原 Gate 的业务判定谓词未改。
- 调查前的检查不足以防提交竞争；最终答案在原写事务中再次检查 TaskControl、身份与来源。
- 新核心也必须计入已有活跃时间，不能绕开 300,000ms。

## 学习分级

- 已理解/复现：标准工具循环、可信绑定、Context 来源、Checkpoint 与调用 Ledger 的职责区别。
- 已接入：隔离候选的专业入口、真实本地 MCP/HTTP、持久来源与同会话连续交付。
- 尚未证明：真实 LLM 对自由问题的质量、自主工具选择收益、正式浏览器体验、Skill/Memory 收益。

面试问：**“为什么有 Checkpoint 还需要调用和答案的持久身份？”**

答：Checkpoint 可能在工具返回前后断电，单靠执行位置不知道外部调用是否完成。
先登记有界调用，再持久化实际结果与观察；恢复时已知且仍有效的结果可重放，未知结果保守停止。
最终答案再以 Run 唯一键和 Domain 事务提交。这样进程恢复不重置预算，也不会产生两条最终答案。
这属于可靠性证明；模型是否更会调查仍需真实模型及用户目标评估，不能拿测试数量替代。
