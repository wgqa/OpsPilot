# AR-04C-REAL-JOURNEY-01 — Phase A–C 报告

**结果：** `READY_FOR_LIVE_AUTHORIZATION / ACCEPTANCE_CANDIDATE`

**真实付费调用：** 0；本报告不声称真实 LLM 自主性或 Memory 收益。

**测试源码提交：** `6951bcd7a2d791a1454c46b3b70077ebdf909cba`

**候选分支：** `codex/ar04c-real-journey-01`；最终发布 SHA 以本报告提交后 Git 记录为准。

## 用户旅程实际得到的结果

离线确定性旅程中，支持人员在同一目标 Event 上看到 Delivery `HTTP 202 / ACKNOWLEDGED`，Receiver `QUEUED`。FixtureModel 的持久答复正确表达“已受理不代表业务处理完成”，指出需按同一 Event/Delivery 版本继续观察，并提供标明未提交的同事说明草稿。J4 再次读取当前 Receiver，而没有把历史 Memory 或协议目录当成当前状态。

协议工具返回 `receiver-ack-contract-v2` v2.1.0，Digest `5fb3732339600ad1332960df08a00299358b8c4ea47c20f6fedc39b568c9850e`；`deployment_version_verified=false`。该文档说明 202 只证明接收队列已受理，不能单独证明业务处理完成。另有 `order-lifecycle-contract-v2` 与 `callback-retry-contract-v2` 返回。

**限制：** 这些工具选择和回答由 FixtureModel 脚本给定，不能证明真实模型会按此调查、会主动重查、会使用 Memory，或会更好地完成目标。

## 正式链路与配对证据

两组都经过 FastAPI → Worker → `ASSISTANT_V1` → LangGraph/LangChain → 显式 HTTPX MockTransport → 真实本地 MCP stdio → Domain → 持久 Session 答复。ON/OFF 使用独立 Session、Task、Domain/Checkpoint 数据库和预算行，订单、Event、权限、文档、Skill 暴露和业务事实等价。Memory 来源先通过既有 Candidate → Confirm 生命周期建立。

| 指标 | Memory OFF | Memory ON |
|---|---:|---:|
| Provider HTTP（MockTransport） | 6 | 6 |
| MCP 调用 | 4 | 4 |
| Context 输入估算峰值 / 12,000 | 4,402 | 5,193 |
| Provider 中 Memory 引用 | 0 | J2/J4 各每 Run 1 条 |
| Fixture Usage（每请求） | 120 in / 36 out | 120 in / 36 out |
| Fixture 账本结算估算 | $0.000480 | $0.000480 |

OFF 的 6 次 Context 估算为 `[1803, 3318, 3827, 4118, 4111, 4402]`；ON 为 `[2599, 4114, 4621, 4910, 4904, 5193]`。两者均低于冻结 12,000 Token 输入预算。Fixture Usage 与费用只证明解析和结算路径，不是实际模型 Usage 或供应商费用。

两组冻结回答和事实一致。ON 的实际输入确实多了历史 Memory Guidance，但本样本没有显示回答质量或下一步决策改善；不能把额外 Token 或 Memory 被装入消息当成收益。两组都没有实际加载升级 Skill。

## 来源、授权与副作用

- Memory `episodic-09dd7f57-4150-44a9-a766-8901457357ff`，v2，Digest `59572f43e270e72a74a792646eb32b3ac2da26e0d4f95c70b88fb8767652fbe9`，来源 Task `task-9d246ead-2bf7-4011-bfa8-99731eb3788e`、Run `run-5b6869ef-288d-4847-aa71-95483f3d659d`，Outcome `CALLBACK_DELIVERY_FAILED`，由 `approver-a` 通过既有确认 API 确认。Memory 仅作为历史方法提示。
- 目标订单 `ar04c-order`，Event `event-04872e0e-6268-4ccf-a51c-633496966da7`。MCP 返回当前同 Event Delivery 202/ACKNOWLEDGED、Receiver QUEUED。知识中的协议版本未视为线上部署版本。
- 新实验的批准记录、claim 和 one-shot token 均未创建；缺少它们时 Provider factory fail closed。
- 真实 Provider HTTP、浏览器、外部业务写入均为 0。Mock 测试按 J1 要求创建并确认了隔离 Domain Memory；这不是 S3 修复、Approval、ActionIntent、Ledger、Handoff 或回执写入。相关受保护业务表计数保持零。

## 价格与预算核对

官方 DeepSeek 价格页于 2026-11-05 核对：Flash 峰值未命中输入 `$0.30/M`、输出 `$1.20/M`；早期草稿曾把 V4 Pro 的 `$1.32/M` 输入价误读成 Flash 输出价。纠正发生在付费授权与任何 Provider 出站之前。根据完整输入/输出包络，单次最大预留 `$0.645600`；每组最多 8 次对应 `$5.164800`，总计 16 次对应 `$10.329600`，分别低于每组 `$5.25` 与合计 `$10.50`。该预留不保证供应商账单绝对不超额；超时、未知结果或无效 Usage 持久关闭 Campaign 并保留预留。

价格依据：[DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)、[Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)、[Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)。实际执行前还须重新核对当前价格、请求体、授权、HEAD、合同摘要和隔离环境。

## 验证与遗留问题

- AR-04C 定向测试：6/6 通过，16.11 秒。日志：[pytest-ar04c-final-evidence-01.log](runs/pytest-ar04c-final-evidence-01.log)。
- 当前源码适用回归：46/46 通过，157.58 秒，覆盖 AR-04A Context、AR-04B Memory、AR-02 prepaid HF01、M4 CONT-UX Stage A。日志：[pytest-ar04c-core-regressions-final.log](runs/pytest-ar04c-core-regressions-final.log)。
- `py_compile` 与 `git diff --check` 通过。完整 pytest 未完成。
- 包含 AR-03 的一次扩大回归在 `test_remainder_mocktransport_formal_worker_observes_same_event_and_serializes_live_contract` 的 Starlette `TestClient.wait_shutdown` 等待处停滞；线程/调用栈日志保留于 [pytest-ar04c-regressions-final.log](runs/pytest-ar04c-regressions-final.log)。根因未证实，未再次盲目重跑。此前不同源码快照有 61 项通过记录，不替代本轮当前源码 46 项结果。
- 全部失败尝试、早期预检问题与价格勘误历史见 [FAILURES.md](FAILURES.md) 和 `runs/`，不删除原始失败。

## 六问六维

1. **用户变化：** 离线旅程现能经正式工作路径交付“202 已受理、Receiver 仍排队、处理未确认”的有来源答复和未提交草稿；真实模型成果尚未发生。
2. **Agent 决策：** 本地 Fixture 的工具行动由脚本决定；真实模型的 Knowledge/Skill/Memory/工具选择仍待付费执行验证。
3. **观察驱动：** 同 Event 的当前 `QUEUED` Observation 与 202 组合支持“未确认处理完成”；真实模型面对其他状态的决策未验证。
4. **新增约束：** 仅 AR-04C 限定预算/Memory 模式和授权边界；新合法任务可进行多次 MCP 读取，UNKNOWN 和超额仍拒绝后续 Provider。两边正反离线测试均覆盖。
5. **简化结果：** 复用现有 LangGraph、Memory 生命周期、MCP、Experiment Ledger 与 D2 Attempt Ledger；未新增 Runtime、平台、Graph 或业务写权限。普通 Task 和旧实验限额未放宽。
6. **证据与停止线：** 定向 6 项、相关回归 46 项通过；扩大回归 shutdown 问题未决；真实 Provider、浏览器、真实 Skill 选择及 ON/OFF 收益未运行。候选提交后停止，交主 Agent 独立审查；真实执行需单独付费授权。

## 学习与面试表达

- **原理 → 业务 → 代码：** 历史 Memory 作为有来源、可撤销的调查方法提示进入 `assistant.py` / `chat.py` 装配；当前 Receiver 仍通过同 Run MCP Observation 获取，不把 Memory 升格为业务 Evidence。
- **上下文预算：** 复用 `_prepare_context` 与现有 Context 估算；ON/OFF 注入差异须在实际请求消息中验证，且不能突破 12,000。
- **账本与恢复：** 使用现有 Experiment Ledger 做 Provider 发送前预留，D2 Attempt Ledger 计 MCP；未知 Provider 结果关闭 Campaign、保留预留、不重试。
- **面试表达：** “我用离线 MockTransport 验证了正式 Assistant 的 ON/OFF 装配、当前事实边界和费用状态机。它证明工程链路可运行，但不能证明模型会自主选择 Memory，也不能证明 Memory 提高了答案质量；这些要用获得授权的真实成对运行验证。”

**最终状态：** `READY_FOR_LIVE_AUTHORIZATION / ACCEPTANCE_CANDIDATE`。实施方不签 PASS，不合并 main，不启动真实 Provider 或 AR-05。
