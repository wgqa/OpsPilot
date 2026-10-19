# M3-01 源码学习笔记

## 数据从哪里来

- [`opspilot/domain/episodic_memory.py`](../../../../opspilot/domain/episodic_memory.py)：沿用 D5 的 Candidate、审批状态、过期/撤销、来源完整性和 Context Provenance。新案例 schema 为 `opspilot-case-memory-v1`；候选由来源 Task 的持久事实抽取，不从对话文字生成任意业务断言。
- [`opspilot/domain/database.py`](../../../../opspilot/domain/database.py)：从用户提供的 v8 数据库演进到 v9，增加案例来源/Outcome/摘要相关字段，并兼容迁移历史行。旧行以 `d5-legacy-v1` 表示，不假装拥有新案例来源。
- [`opspilot/domain/d3.py`](../../../../opspilot/domain/d3.py)：S1 来源资格依赖已提交 REPAIR、在线恢复验证、报告与 Evidence；仅有模型回复不能成为成功案例。
- [`opspilot/domain/s2_diagnosis.py`](../../../../opspilot/domain/s2_diagnosis.py)：S2 DiagnosisReceipt 建立于当前可信 Probe 与授权事实；它与真正业务 HandoffReceipt 是不同证据。Memory 不会创建权限 Grant。

## 如何进入真实模型上下文

- [`opspilot/investigator.py`](../../../../opspilot/investigator.py) 的 `_prompt_messages()` 在每次出站前重新查 Domain。`_current_evidence_memory_problem_type()` 用当前 Run 的可信 Probe、绑定作用域、版本稳定性和认证事件关联来决定可查询的案例类型；S2 还要求同一个请求关联的当前 Domain Authz Decision。用户描述或 S2 UI 标记不会选择历史结论。
- `historical_memory_guidance` 以 `HISTORICAL_METHOD_HINT_ONLY` 标记，和 `authoritative_task_binding`、当前 Evidence、确定性 Gate 分开。Provenance 保存 prompt digest、memory ID/version/digest、源 Task/outcome/refs 及调用状态。
- `memory_enabled=False` 只关闭历史提示，不删 DB 记录，也不改变 Task、Skill、Knowledge、工具、预算和权限，保证 OFF 臂对照公平。

## 谁能确认或撤销

- [`opspilot/web/app.py`](../../../../opspilot/web/app.py) 暴露受信登录的候选、审批、查看和撤销端点；浏览器只发 Memory 操作身份与幂等键，不提交模型答案作为授权。
- Vue 工作台在 `frontend/src/` 提供来源 Task 候选、APPROVER review、确认/撤销和目标 Task 当前 Provenance。服务端重新检查 actor、租户/项目、候选来源与状态。
- 撤销不会删除审计记录。下一次模型调用重新查询状态，因此旧 Provenance 保留而当前上下文为空。Checkpointer 保存运行进度，不缓存仍可注入的 Memory 正文。

## 建议的阅读 / 调试顺序

1. `docs/evidence/vnext/m3-01/DATA_CONTRACT.md` 与 `ACCESS_MATRIX.md`：先看来源与授权边界。
2. `opspilot/domain/episodic_memory.py`、`database.py`：看候选/激活/撤销和迁移。
3. `investigator.py::_current_evidence_memory_problem_type()` → `_prompt_messages()`：看查询类型选择和 ContextManifest。
4. `web/app.py` 与 `frontend/src/`：看用户审批流程和结果显示。
5. [`tests/test_m301_memory.py`](../../../../tests/test_m301_memory.py)、[`tests/test_m301_red.py`](../../../../tests/test_m301_red.py)：看来源区分、跨 Task、隔离和当前证据测试。
6. [`opspilot/smokes/m301_eval.py`](../../../../opspilot/smokes/m301_eval.py)、[`m301_web_chain.py`](../../../../opspilot/smokes/m301_web_chain.py)、[`m301_revoke_recovery.py`](../../../../opspilot/smokes/m301_revoke_recovery.py)：看真实评测、浏览器和进程恢复如何留证。

## 本轮观察到的限制

真实 ON/OFF 运行证明了历史经验能进入独立 Task 的真实 Provider 上下文，也证明撤销后后续调用不再载入；它们没有证明经验提升了正确性或减少了调查成本。P03/P04 两臂均偏离冻结 Gold，效用报告为 `UTILITY_NOT_PROVEN`。因此把 Memory 理解为可撤销、可追溯的调查提示，而不是可靠事实源或自动化业务能力。
