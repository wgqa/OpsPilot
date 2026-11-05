# AR-04B-MEMORY-JOURNEY-01 — 实现审计

## 基线与实际读取

- Gold 冻结提交：8db87e10cacbd3836ada099b38c82e38d3665035。
- 冻结时 origin/main：134df49f792dfdf8d4b9a3b846d218af5c34ec6d。
- 实施分支：codex/ar04b-memory-journey-01。
- 代码与测试提交：bdf696fb6189199123c2c87b32614d745a2f604f。
- 本轮读取的文件 Blob：
  - PROJECT_NORTH_STAR.md：e36f2f75509738551ac6d4a2de5b4f9cf44a7991
  - AGENTS.md：f174a6ab7f23f9e6d8b3ef98d455b99a75193143
  - .agents/skills/opspilot-slice-review/SKILL.md：d405c8d413d633824b279202cc1503dab4cf0b03
  - 本任务 GOLD.md：f5056cbb3344208e2e34671ea08a50963d3aea3d
  - AR-04A GOLD.md：6c8ba3867e2dad983abe6f1b85bd559fc28e36ac
  - AR-04A REPORT.md：ab409090311132166ff1a79f2cb5c031f55ab8e5
  - docs/baseline/MEMORY_LINEAGE.md：f66683083ce81b1d1eb7ae7d89b4af9e78123a2e
  - docs/learning/OPEN_SOURCE_AGENT_REFERENCES.md：5c422316164e20a922ad0596233070716225be07
  - docs/evidence/vnext/m2-01/DEFERRED_GATES.md：2e65870acb26a7c1383fdd96b5b8619748dda6b9
  - docs/evidence/vnext/m2-02/DEFERRED_GATES.md：2536030b5b942bf9e3765e0916607549fa919934

GOLD.md 保持冻结内容；本轮没有改写 Gold、历史账本或旧 Trace。隔离分支与原工作树分开。

## 调查到的调用链

Memory Domain → chat._prepare_context → Context Manifest → Assistant Run/Checkpoint → Loop.context → Loop.awrap_model_call → assistant_calls.request_json → complete_chat_attempt。

原实现的 Memory 选择、权限、适用性及预算已在 _prepare_context 中完成，Manifest 也保存 memory_refs。但 _run_assistant 构造初始消息时只保留规定的历史消息和摘要，选中的 Memory 指导块没有进入后续 LangGraph 消息。Loop.context 也没有把该块补进实际出站消息。因此“Manifest 有 Memory”不能证明模型看到 Memory。

runs/red-formal-wire.json 捕获到：Manifest 有一个已确认、跨任务 Semantic Memory 引用，而 Fixture Model 实际收到的消息只有既有系统说明与用户原文，没有该 Memory 指导块。这是正式 API/Worker 与本地 Fixture Model 的离线复现，不是真实 Provider HTTP 记录。

另一个负例是 runs/red-wire-tamper-valid.log：在测试变体中，模型调用后、答案提交前将已持久化请求中的 Memory 指导摘要篡改；旧校验仅核对引用 ID/Digest，仍成功提交答案。恢复完整指导内容核验后，runs/green-wire-tamper-valid.log 显示 Run 失败且没有提交答案。两份原始日志均保留。

## 最小修复与职责

1. Assistant.context 从现有有预算的 _prepare_context 结果提取指导块，并只在每个 Assistant Run 的模型请求中追加非权威 Memory guidance；没有改动全局 SYSTEM 提示。
2. 指导块保留 Memory ID、版本、内容 Digest、来源 Task、来源结果、摘要/经验和非权威标记。请求记录所选/排除来源及 Context 预算。
3. 每次进入模型 Handler 前复用 assert_selected_memories_current 校验；在读取 checkpoint 后、Graph 继续前检查 Manifest，并在恢复路径上复核。
4. 新增 assert_selected_memories_current_in_connection，使答案提交事务复用同一来源、租户、项目、版本、Digest、过期和源有效性规则。
5. complete_chat_attempt 在事务内核对 Manifest 与成功 MODEL wire 的 Memory 引用、版本、Digest 和完整指导块；来源在模型调用后失效时不提交答案。

没有新增 Schema、Memory 存储、预算系统、Runtime、模型调用或业务写权限。M2-01/M2-02 延期门禁保持不变：本轮未新增受控写能力、Task outcome、Approval、ActionIntent、Handoff/Receipt，也未改变 TaskControl；本任务是在 M3/D5 既有 Memory 生命周期内补统一 Assistant 的输入装配和来源复核。

## 证据界限

assistant_calls.request_json 与 Fixture Model 实际收到的消息互相核对；两者都来自正式 FastAPI/Worker/ASSISTANT_V1/MCP/Domain 路径。Fixture Model 不发网络请求。真实 Provider HTTP 为 0，因此本轮只证明离线接线与安全行为，不能证明真实 LLM 决策变化或收益。
