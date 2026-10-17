# 冻结合同 → 源码 → 测试 → 证据

运行实现 `a2517fd`；完整文件与各文件来源 SHA 在 REVIEW_INPUT/MANIFEST。下表 PASS 仅指列明的有限行为已有代码和运行证据，不是第三方验收意见。测试命令在根目录使用 `python -m pytest -q -s <文件> -k <选择器> --basetemp=.runtime/<新目录>`。D7 全量 64/64 为新鲜控制回归；D6 真实模型结果按历史 SHA/时间复用，不能混为 D7 新模型样本。

| 冻结条款 | 实现文件 / 函数 | 可跑测试 / 入口 | 真实证据路径 | 局限 / 状态 |
|---|---|---|---|---|
| §1–2 S1 单一凭证引用故障、同身份业务恢复 | `cli.main`、`investigator.run_investigation`；`domain/client.py:probe_orders`、`api.py:DemoAPIHandler`、`d3.py:verify_repair_online` | `opspilot.cli d3-smoke`；`tests/test_s1_business.py`、`test_d3_plan_repair_verify_freeze_and_independent_delivery_are_idempotent` | D7 `attempt-02/e01/TRACE.json`、`BUSINESS_STATE.json` | 本地 HTTP、合成凭证/订单；没有真实客户服务接入。**PASS** |
| §3.4 当前 Evidence Gate / 不能凭模型归因修复 | `domain/d2.py:record_tool_observation,evaluate_evidence_gate,_stable_diagnostic_fact_digest` | `tests/test_d2_investigation.py` 的 gate/probe/disabled/missing 测试 | D6 E02/E03 TRACE；D7 全量日志 | 四类结构化事实覆盖 S1；非通用根因系统。重复 Probe 回归保留。**PASS** |
| §3.3 C1 有界出站与恢复计数 | `domain/d2.py:reserve_attempt,attempt_counts`；Graph `investigate/execute_read_tools` | `test_mcp_attempt_budget_survives_process_restart`、`test_mcp_attempt_reservation_is_atomic_across_threads`；D2 budget smoke | D7 pytest-full；D6 E03 budget MODEL 8 / MCP 6 | 持久次数上限和单请求超时已做；阶段整体 wall-clock 截止检查未实现。**PARTIAL** |
| §4.1 F1 首次前 Intent / 同键异摘要拒绝 | `domain/d3.py:get_or_create_action_intent,_request_for_action,_validate_action_context,_prior_ledger,execute_repair` | D3 canonical/idempotent 测试；D4 action_intent/process_crash 测试 | D7 BUSINESS_STATE、DIGEST_CHECKS、WORKERS/RECOVERY_SUMMARY | 单库回执重放；无回执则人工核对。**PASS** |
| §4.2 F2 取消/替换与提交串行裁决 | `d3.py:cancel_plan,_activate_plan_in_transaction,execute_repair,execute_deliver` | D4 `cancel_and_repair_are_serializable`、`cancel_and_deliver_are_serializable`、`plan_replacement_races_repair_and_historical_receipt_replays` | D7 新鲜全量事件；D4 原始 pytest-full | 取消不能回滚已 COMMIT 效果；已提交历史可查，新动作受当前资格约束。**PASS** |
| §4.3 F3 两个独立授权、报告冻结及工单去重 | `d3.py:submit_plan_approval,verify_repair_online,get_or_create_report,execute_deliver` | D3 全文件；D4 `langgraph_replays_committed_delivery_after_lost_response` | D7 两条许可、两笔 Intent/Ledger、Verification、Report、DeliveryRecord、一条工单 | 一个 Plan 批准生成两条许可，非两次分别弹窗。DELIVERY_PENDING 不触发第二次 REPAIR。**PASS** |
| §4.6 可信身份与双租户边界 | `d2.py:create_task_binding,authorize_thread_resume`；`mcp_server.py:build_task_server`；`d3.py:_require_approver,_require_executor,authorize_workflow_resume` | D2 ownership/scope；D3 approval；D4 scope；D5 memory filters | D7 全量；E01 一次真实越界主体查询被拒 | CLI 身份名来自本地信任映射，无公网认证。**PASS（Demo 边界）** |
| §5 Memory / 每次调用与恢复重新检索 | `episodic_memory.py:_source_for_task,create_memory_candidate,confirm_memory,revoke_memory,list_applicable_memories`；`investigator.py:_prompt_messages` | `tests/test_d5_context.py`；D5 smoke | D6 E10 `attempt-02/REAL-TRAJECTORIES.json`；D7 新鲜控制回归 | 生命周期/跨任务注入有证据；正文为固定通用提示，未提取独特经验，收益未证实。**PARTIAL** |
| §5 单一版本化 Skill | `skill_assets.py:load_applicable_skill`；`skills/auth-incident-triage/{SKILL.md,manifest.json}`；`.gitattributes` | D5 skill lazy/digest/version 测试；D7 新鲜 E01 | D7 首轮 FAIL 与修正后 64/64；E01 provenance | 不产生工具/授权；LF 导出修正后字节摘要保持。**PASS** |
| §5 Context Provenance | `_prompt_messages`；`reserve_attempt`；`episodic_memory.py:insert_context_provenance_in_transaction,assert_task_skill_compatible` | D5 context reservation/revocation 测试 | D7 `CONTEXT_PROVENANCE.json`；D6 E10 REAL-TRAJECTORIES | 最小 SQLite 来源台账；不是复杂 Context/压缩框架。**PASS** |
| §6 E01 | D3 smoke `run_smoke`，Graph + Domain 完整链 | `python -m opspilot.cli d3-smoke ...` | D6 E01 PASS；D7 首轮 FAIL、修正后 13/13 | D7 两个 smoke 尝试分开保留，自动可信角色批准。**D6 PASS；D7 最终 PASS/初始 FAIL** |
| §6 E02 | Gate DISABLED → NO_ACTION | D2 disabled 控制；真实 D2 DISABLED smoke | D6 `e02/TRACE.json`，SHA/UTC 见 D7 REPORT | D7 只新跑确定性回归，模型轨迹历史复用；Actual Recovery=false。**PASS（历史模型+新控制）** |
| §6 E03 | Gate 缺失/冲突/预算 → INCONCLUSIVE | D2 missing/conflict/budget；真实 INSUFFICIENT smoke | D6 `e03/TRACE.json`；D7 全量 | 同上；测试注入 policy source 不可用；不计恢复。**PASS（历史模型+新控制）** |
| §6 E04 | 拒绝/未审批业务写入零 | D3 rejection/cancellation | D7 pytest-full；D6 CASES/RESULTS | 审计/审批表写入不算受限业务写入。**PASS** |
| §6 E05 | 旧 Plan/版本/CAS/竞态/重放 | D3 version/canonical；D4 cancel/replacement/duplicate | D7 全量及 D4 历史日志 | 有限测试时序，非所有并发调度的形式化证明。**PASS** |
| §6 E06 | tenant/actor/task/project 隔离 | D2/D4 scope；D5 expiry_tenant_project | D7 全量；D6 映射 | 本地注册角色和合成双租户。**PASS** |
| §6 E07 | 未信任 MCP 文本不扩权 | `test_d4_real_read_only_mcp_injection_cannot_create_action_intent`；严格 Tool Schema 测试 | D7 全量；D6 CASES 分类勘误与冻结提交 | 真实 MCP、确定性控制；没有调用模型；READY 不等于注入成功。**PASS** |
| §6 E08 | HITL 等待/跨进程恢复/重复提交 | D4 approval_interrupt；concurrent_duplicate | D7 E01 两进程；新鲜全量 | checkpoint 恢复先查身份，Domain 才是副作用权威。**PASS** |
| §6 E09 | Intent/COMMIT/丢响应/旧 checkpoint | `tests/d4_crash_worker.py`；D4 process_crash 与 langgraph_replays 测试 | D7 WORKERS、RECOVERY_SUMMARY、全量；D4 全矩阵历史 | unknown 只能安全停止并对账，不计自动恢复。**PASS** |
| §6 E10 | Memory/Skill 跨任务与撤销恢复 | D5 smoke；D5 7 项控制回归 | D6 E10 ATTEMPT-01 与 attempt-02；D7 全量 | 首次失败根因未完整还原；固定通用正文；公平 ON/OFF NOT_RUN。D7 未重跑模型。**PARTIAL（历史结论不变）** |
| §6 探索性 Memory ON/OFF | 无公平实验实现 | 无已执行入口 | D6 REPORT/RESULTS 的 NOT_RUN | 不声称准确率/效率改善，未做新评测框架。**NOT_IMPLEMENTED / NOT_RUN** |

机器逐测试映射仍以冻结 `docs/evidence/d6/CASES.json` / `RESULTS.json` 为准；它们给出准确 pytest node IDs。运行行为由源码和新鲜日志核对，文件存在本身不代表满足合同。
