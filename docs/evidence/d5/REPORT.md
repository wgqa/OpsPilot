# OpsPilot D5 跨任务记忆运行报告

**结果：PASS**

**执行时间：** 2026-10-17T09:26:29+00:00

**当前提交：** `b744e280d8dfdbf685f02d14908bc2d7fc372cc6`

**Python：** 3.14.0（Windows-11-10.0.26200-SP0）
**真实模型：** `deepseek-flash`（未记录密钥）

## 验收断言

- [x] `candidate_is_not_retrievable`
- [x] `candidate_text_is_absent_from_prompt`
- [x] `candidate_source_is_task_a`
- [x] `human_confirmation_activates_once`
- [x] `task_b_is_new_binding`
- [x] `task_b_retrieves_active_memory`
- [x] `task_b_real_model_call_selected_memory_and_skill`
- [x] `task_b_process_checkpointed_after_model_call`
- [x] `disabled_task_used_active_memory`
- [x] `disabled_task_real_401_and_no_action`
- [x] `revocation_changes_version_and_stops_retrieval`
- [x] `cross_process_resume_is_a_distinct_process`
- [x] `post_revocation_real_model_call_has_no_memory`
- [x] `task_b_current_evidence_still_controls_gate`
- [x] `memory_and_skill_never_enter_domain_evidence`
- [x] `insufficient_401_real_model_mcp_control`
- [x] `each_actual_model_call_has_context_provenance`
- [x] `skill_digest_was_verified_and_versioned`
- [x] `real_model_mcp_trajectories_recorded`

## 真实进程

- `task_a_d3`: return code 0.
- `task_b_first_process`: return code 0.
- `task_c_disabled_process`: return code 0.
- `task_b_restored_process`: return code 0.
- `real_insufficient_control`: return code 0.

## 依赖与回归结果

- 实现提交：`b744e280d8dfdbf685f02d14908bc2d7fc372cc6`，分支 `main`。
- 环境：CPython 3.14.0、Windows 11；真实模型 `deepseek-flash`。锁定依赖：`langchain==1.4.1`、`langchain-openai==1.7.2`、`langgraph==1.2.16`、`langgraph-checkpoint-sqlite==3.1.2`、`mcp==2.3.0`、`pydantic==2.14.1`、`pytest==9.1.1`。
- 真实 D5 smoke：**19/19 PASS**；真实 D3 Task A 来源链：**13/13 PASS**。任务 B 完成 5 次真实模型请求（均有 Provider response ID），撤销前 1 次含已确认 Memory，恢复后 4 次均无 Memory；B、C 分别完成 4 次真实 MCP Observation。
- D5 定向 pytest：**7/7 PASS**，详见 `pytest-d5-focused.txt`。D1–D5 全量回归：**62/62 PASS，61.04s**，详见 `pytest-full.txt`。
- `py_compile`：所有变更的 Python 模块通过，命令见 `py-compile.txt`。`pip check`：`No broken requirements found.`，详见 `pip-check.txt`。

复现测试命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q -s tests\test_d5_context.py --basetemp=.runtime\pytest-d5-focused
.\.venv\Scripts\python.exe -m pytest -q -s --basetemp=.runtime\pytest-d5-committed
.\.venv\Scripts\python.exe -m pip check
```

## 关键轨迹

- 任务 A 由 D3 真实模型、stdio MCP、独立审批进程完成；来源为 COMMITTED REPAIR、在线 HTTP 200/订单断言通过的 `RECOVERED` VerificationReceipt、冻结报告和同任务 Evidence。
- 候选 Memory `episodic-8d80a4af-eff8-4959-87bd-9a15544f9365` 从 `CANDIDATE v1` 经 `approver-a` 确认后变为 `ACTIVE v2`；候选阶段任务 B 的 Prompt 未包含记忆。
- 新任务 B 首个真实模型请求在出站前登记了 Memory ID/version、Skill name/version/digest、Prompt digest 与 Tool Schema digest。该请求通过本机真实模型调用并获得 Provider response ID。
- 任务 C 在 Memory 仍为 ACTIVE 时用真实模型/MCP 面对主体禁用造成的 HTTP 401，确定性 Gate 返回 `NO_ACTION`；独立真实 `INSUFFICIENT` 场景返回 `INCONCLUSIVE`。
- 撤销 `episodic-8d80a4af-eff8-4959-87bd-9a15544f9365` 后，B 从另一 OS 进程恢复旧 checkpoint。恢复后的真实模型调用均无 Memory 引用，Prompt digest 与模型轨迹相符；B 的当前 MCP Probe 仍为 HTTP 401、主体为 ENABLED，Gate 根据当前 Evidence 返回 `READY`。
- B 两个独立进程使用同一 checkpoint 文件；恢复前后文件 SHA-256 及 PID 记录在 `TRACE.json`。SQLite checkpoint 和 Demo Domain 文件留在 `.runtime`，证据目录不包含数据库文件。
- B 的 5 条逐调用 Context Provenance 均与 `d2_model_traces.prompt_digest` 对应；第一条引用 Memory `v2` 和 Skill `1.0.0`，之后 4 条仅引用当前 Skill，工具 schema digest 与模型标识也逐次记录。
- 完整脱敏逐调用 ContextProvenance、模型响应引用、MCP Observation 和当前 Evidence 见 `TRACE.json`；独立进程输出见 `process_logs.json`，任务 A 的 D3 来源包见 `d3-source/`。
- 首次失败仅由 smoke 的 Evidence 脱敏投影漏记 `status` 字段导致，已修正；复现与处理说明见 `ATTEMPT-01.md`。

## 命令

```powershell
.\.venv\Scripts\python.exe -m opspilot.cli d5-smoke --db .runtime\d5-domain.sqlite3 --checkpoint-db .runtime\d5-checkpoints.sqlite3 --evidence-dir docs\evidence\d5
```

依赖版本见本报告同目录的 `TRACE.json`。全量 pytest 日志见 `pytest-full.txt`。

## 限制与待办

- 项目作用域按冻结 D5 Demo 规则从可信 `service_id` 派生，例如 `service:orders-demo`；这不是通用项目注册中心或生产 IAM。
- Memory 固定为一条最多 30 天的 Episodic 经验，单次最多检索一条；不含向量检索、自动总结或业务根因。
- 跨层外部模型请求与 SQLite 无法构成一个分布式原子事务。ContextProvenance 在模型出站前持久化；调用开始后再发生的撤销不能撤回已发送请求，但下一次调用及 checkpoint 恢复会重新查权威 SQLite 状态。
- D5 到此停止；未扩展其他 Memory 类型、Skill、Agent、复杂审批或业务场景。
