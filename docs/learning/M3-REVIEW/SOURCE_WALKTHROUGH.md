# 从 Web 到模型、摘要、撤销和恢复的源码阅读路线

本轮唯一生产改动在 `opspilot/domain/chat.py::_message_source_valid`；其余阅读对象都是已有实现。文件名相对仓库根目录。下列行号对应修复 `00d054a`，函数名是更稳定的定位方式。

## 1. 先看可信输入受理，不从 Prompt 开始

1. `opspilot/web/app.py` 的 `/api/sessions/{session_id}/tasks`、`/messages` 路由验证会话、CSRF、Idempotency-Key。
2. `domain/task_control.py:908 create_task_with_initial_run()` 在 Domain 创建绑定、Message、Run 和 Outbox。
3. `task_control.py:1029 admit_task_message()` 区分 CHAT_READONLY 和 CORRECT_TASK_INPUT。前者不取得修复权限；后者提升控制版本，使旧调查/Plan 不再支撑新动作。
4. `task_control.py:1271 claim_task_run()` / `:1330 resume_task_run()` 校验运行资格，revision 0 是合法整数，不能当缺失值。

请沿着任务卡的 tenant/session/task/run/message/control_revision 逐项查库。浏览器标题会截断 UUID；不要据此手补身份。本轮曾发生测试监视器使用错误 Task UUID，原失败保留，之后改为从只读 Domain 取完整 ID。

## 2. 分流到 Chat 或原业务 Graph

`web/worker.py:519 run_worker()` 使用单实例 Lease/Fence；`:509 _dispatch_run()` 按 Run kind 分流。

```text
CHAT_READONLY → _process_chat_run() → Chat Domain → Provider
INVESTIGATE / APPROVAL_RESUME → _process_run_inner() → run_investigation()
```

不要因为两条路径都使用模型而把它们合并成同一种“Agent 状态”。Chat 不能替业务 Graph 写 Plan、Approval、Intent 或修复配置；真正审批恢复仍使用原 Graph/Checkpoint。

## 3. Chat 发送前的 Context

- `domain/chat.py:121 _current_evidence()`：TaskBinding 范围、TTL、Config/Principal/AuthPolicy 当前版本；Probe before/after 稳定且匹配，S2 决策/Grant/Policy/请求关联亦需有效。
- `chat.py:289 _current_memories()`：重新检索当前 Episodic/Semantic，并把不适用/失效理由交给 Manifest。
- `chat.py:358 _message_source_valid()`：历史助手检查 MESSAGE、EVIDENCE、MEMORY、TASK_STATE、MODEL_ATTEMPT 及 Summary refs。本轮在 MODEL_ATTEMPT 分支加入租户/会话/任务范围内的祖先回答递归，含 cycle guard 和局部 cache。
- `chat.py:475 _summary_is_current()`：递归检查 Summary 来源，不能把一个“ACTIVE Summary”当作无条件可信缓存。
- `chat.py:890 _prepare_context()`：组装必选与可选块、正式输入锚点、版本化资产与排除理由。
- `domain/context_engineering.py:114 allocate_context_blocks()`：先保留 required，再按优先级裁剪 optional，返回选用集合和排除集合。
- `chat.py:1708 prepare_chat_attempt()`：持久 Attempt、Manifest、Context Provenance，再出站。
- `chat.py:1684 assert_chat_context_current()`：临发送前再验证来源。这个检查与网络发送不是原子事务，存在很短的外部 I/O 竞态窗口；不把它说成分布式事务保证。

## 4. 压缩不是直接往 Summary 表写 JSON

```text
prepare_chat_compression_attempt()
  → _prepare_context() 产生 compression_work
  → _compression_prompt() 仅使用有效源材料
  → assert_chat_compression_sources_current()
  → worker 的 model.ainvoke()
  → complete_chat_compression_attempt()
      → _current_compression_work() 再验证
      → _validate_summary_document()
      → Summary / dependencies 持久化
  → 新 prepare_chat_attempt() 选用当前 Summary
```

源材料包含原消息引用/正文、可追溯依赖和上一 Summary。实验导出只保存正文 digest、序号、依赖身份及真实摘要结果，**不保存完整原始 Prompt**。压缩失败可能不产生任何 Summary；提交后的摘要才有资格成为后续输入。

本轮首个 B 实验就是模型压缩响应返回时 Probe 已过 TTL，重新准备发现原压缩不再需要。日志只存 TaskControlError 类，不能装作已经拿到了某个确切错误码，也不能把这个 HTTP200 计成已持久化的摘要或已知 Token。

## 5. 真实 Provider 路径

- `web/worker.py:340 ChatOpenAI(...)`：原 timeout 和 max_retries；`:376 model.ainvoke()` 处理压缩；`:447 model.astream()` 处理 Chat。
- `investigator.py:2457 ChatOpenAI(...)`；`:1328 / :1560 ainvoke()` 发出理解/调查请求。
- 本轮安装的 langchain-openai 1.7.2 → OpenAI SDK 3.33.0 → **httpx2 2.13.1** → Transport。不能在另一个 `httpx.AsyncClient` 上加 hook 就宣称抓到了这些请求。
- 独立验收入口 `docs/evidence/vnext/m3-hf-02/acceptance_server.py` 创建原客户端后，在其原 httpx2 客户端注册 request/response event hooks；`observe_provider.py` 在序列化后、Transport send 前检查原 body。
- 原 body 不修改；输出仅 digest、角色/长度、资产结构投影和精确比较结果。真实 Provider Response ID/Usage 从 Domain 已完成 Attempt 联接。压缩提交失败或进程中断则可能 UNKNOWN。

## 6. 经验来源与撤销

`domain/episodic_memory.py:125 _source_for_s1_task()` 校验真实 REPAIR Ledger、同身份验证、冻结报告等；`:350 _source_for_s2_task()` 使用 S2 的可信诊断/交接来源，绝不伪造 S1 修复字段。

`:810 create_memory_candidate()` → `:901 confirm_memory()` → `:955 revoke_memory()`；`:1043 select_applicable_memories()` 用当前状态筛选；`:1314 assert_selected_memories_current()` 在出站前复核。Semantic 对应 `semantic_memory.py` 的 candidate/confirm/revoke/active_semantic_context，并维护作用域。

撤销不删除历史审计。旧 Assistant/旧 Summary 需要通过递归来源排除；文本里找不到 Memory ID 不能证明未使用派生经验。本轮 RED 两跳复现和实际 HTTP 投影分别验证程序与真实请求。

## 7. Investigator 与 Checkpoint 恢复

`domain/investigation_context.py:164 load_investigation_context()` 从 Message/Run/控制版本加载正式输入；`:170 load_initial_checkpoint_recovery_context()` 处理首 Checkpoint 前窗口；`:241 validate_task_run_context_in_transaction()` 检查当前有效性。

`investigator.py:742 _prompt_messages()` 每次读取可信 Task 输入、当前 MCP Evidence、适用 Memory/Skill；**不直接把 Chat 的 Summary 当业务事实**。`:1133 build_investigation_graph()` 包含有界模型/MCP、Gate、Plan/审批/动作链。`:2376 run_investigation()` 验证所有者、原 Checkpoint 与 Domain，按持久进度恢复。

审批恢复不是重新调查另造 Plan。业务 REPAIR/DELIVER 均先持久 Intent，再在 Domain 写事务校验 Plan/Approval/控制版本、提交 Ledger；同一动作历史回执可回查。Checkpoint 是进度引用，不能代替 Ledger。M1-HF-01 的恢复协议本轮没有改动，全部旧回归在新鲜 227 项中保留。

## 8. Worker 异常边界

`web/worker.py:216 _worker_error_class()` → `:231 _process_run()` → `task_control.py:1781 record_worker_run_failure()`。未知运行错误有界重试；确定性失效阻断；Lease/Fence 和 Outbox 写入仍由 Domain 负责。`:1905 next_worker_run()` 选择可运行任务。

历史两次 WORKER_RETRY_EXHAUSTED 缺少原异常类型/堆栈。注入 RuntimeError 能复现相同终态，不代表历史根因就是这个注入。`_prompt_messages()` 在预算 Attempt 前也可能失败，MCP 初始化/tools/list 也不等于 tools/call，因此“计数 0”不能证明与 M3 无关。

## 9. 建议的 30 分钟实读顺序

先看本轮 REPORT 与 SUMMARY_LINEAGE，选一个真实 Run，查 HTTP request_ref/Attempt/Provider response/Usage；再读 `_prepare_context` 的 selected/excluded；接着读 `_message_source_valid` 和新增两项 RED；最后看 Worker 恢复与真实业务 Ledger。沿一个身份贯穿，不靠总 PASS 数替代业务因果证据。
