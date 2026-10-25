# M4-EG01-HF-01 修复报告

状态：`ACCEPTANCE_CANDIDATE`（实施方交付候选，等待主 Agent 独立验收）

## 基线与范围

- Repo：`wgqa/OpsPilot`；任务基线、远端 `origin/main`：`3db7fa80aebd4a92dea7205656d47a26500ee295`。
- 本轮冻结提交：`d52fb62`；RED 提交：`cf81641`、`e8758fe`。原 Gold、冻结记录与旧失败未改。
- 源码与回归提交：`97673c3`（Chat 上下文修复、RED-03 原始失败和最终 GREEN-05 Trace）。
- 实际工作树：Codex 隔离工作树；用户主工作区 `D:\学习\agent新项目` 未修改。任务期间远端 main 仍为基线 SHA。
- 正式读取：`PROJECT_NORTH_STAR.md` Blob `1f737712c7a36ceb34433ac09c3fbba3c3305542`；`AGENTS.md` Blob `30319000ed0054007e9b7b6b46bf98b1493c8179`。
- 冻结合同：M4-EG-01 Plan Blob `949938a3c269cf8069f0fb526930a9947e80e786`，Gold Blob `9ef662173c3bcbdae05a20d24fe3673cd2dd8cbf`，原 Report Blob `44265410c740ed9f005f2150f0dc8ef868f4f442`；M2-01/02 延期门禁及访问、状态、恢复和 vNext 架构合同的 Blob/SHA 见 `ACCEPTANCE_PLAN.md`。
- 当前目标提交中没有 `.agents/skills/opspilot-slice-review/SKILL.md`，因此未声称执行该 Skill。
- 唯一业务源码变更：`opspilot/domain/chat.py::_current_evidence()`。新增回归：`tests/test_m4_eg01_hf01.py`。其余为本任务隔离证据。

## 用户现在能完成什么

当同一 S3 Task/Run 通过本地 HTTP 与 MCP 取得订单 HTTP 200 和同 Event 投递 HTTP 202，但没有当前 Receiver Observation 时，Chat 的真实出站消息现在会带上经 Domain 重新核验的订单与投递事实，并明确把处理状态留为 UNKNOWN。此前 Gate 仅使用订单事实得出 `INCONCLUSIVE`，Chat 又把 Gate 的 `checked_fact_ids` 误当成全部可解释事实，导致已验证的 HTTP 202 投递事实被丢弃。

最终出站事实仍不授权业务动作：Gate 不变、Task Outcome 不变，TaskControl revision 不变，Approval/ActionIntent/Ledger/Handoff Queue/Receipt 不新增。

## 最小实现

`_current_evidence()` 不再将 Gate 的 `checked_fact_ids` 当成 Chat 的完整事实集，也不信任 Diagnosis body 中复制的事实或 Observation Pin。它从可信表中取该 Diagnosis Run 下已成功的 MCP Attempt/Observation，限制到已登记 S3 工具与类型，再复用 `current_s3_evidence()` 重验 Task、Run、Observation、TaskBinding、授权、版本、Event 关联和 TTL。失效候选按 Domain 返回的原因进入 exclusion provenance。

HTTP 202 的不可变原始响应有时含受理时的 `receiver_state=QUEUED`。这不是独立的当前 Receiver 查询。本轮在 Chat 事实投影中仅移除此嵌套原始响应字段，保留 202、ACKNOWLEDGED、同 Event、Transport Request、Observation、Evidence digest、版本和时间；原始 Evidence、Observation 和 Gate 均未修改。Chat 当前状态只来自经当前性核验的独立 `s3_receiver` Observation，因此不会把旧响应快照冒充当前排队状态。

没有增加 Gate、Guard、Runtime、Memory、工具或预算分支。

## 实际业务 Trace

完整测试 Trace 与准确出站 `provider_input_messages` 位于 `TRACE.jsonl`，逐条来自最终 `green-05/TRACE.jsonl` 中测试对真实 `prepare_chat_attempt()` 输出的捕获。此为真实本地 HTTP + in-process MCP 取证及确定性出站上下文证据，不是 Provider 实际生成的回答，也不代表生产服务。

无 Receiver 案例示例：

- Task `task-bb65f515-0ecf-418e-a445-76aa2e670cd4`；调查 Run `run-de0dc06e-3172-42ee-bd30-cb1a9ede170b`；Chat Run `run-0e0106ba-2574-44de-abe0-9b3dd97d7b09`。
- 订单 Attempt `attempt-7a23018e-6de6-4863-9aa2-68b51550ab8a`、Observation `observation-39fe8df5-cee3-4dfb-96ce-6c86b211effe` 持久化为 Evidence `evidence-e9c28edc-5aab-47be-9a14-ef1ee6bb9f3f`，HTTP 200。
- 投递 Attempt `attempt-d275c2cb-a208-4d63-82e6-876f321fc81e`、Observation `observation-670b893d-92c3-4ad1-a965-c561b869dd6d` 持久化为 Evidence `evidence-719fe88b-4c00-4dbb-8a9f-93b1eb556d39`，同 Event `event-30bbf765-d2a9-455c-bc2b-789aeb0af67b`，独立 Transport Request `transport-d8bd0b6d-4da6-49a7-a772-3db5b55928de`，HTTP 202。
- 冻结 Gate 仍为 `INCONCLUSIVE`，仅将订单列入 `checked_fact_ids`；Chat 出站当前事实含 `s3_order` 与 `s3_delivery`，不含 `s3_receiver`。不同 Event 的候选 Evidence 被排除为 `S3_CURRENT_FACT_MISMATCH`。
- 测试前后 Diagnosis receipt/digest/body、Task Outcome、TaskControl revision、审批、动作和交接写表均相同。

三种状态的合法上下文：A. 202 且无 Receiver Observation → 已受理、完成未知；B. 同 Event 当前 `PROCESSED` → 可以说明已处理，无需等待 SLA；C. 同 Event 当前 `QUEUED` → 可以说明排队，处理方向由 SLA 决定。D2/D3 Gate 对这些情况的裁决保持原样。

## 验证结果

执行环境：Windows；Python `3.12.14`，pytest `9.1.1`，MCP `2.3.0`，Pydantic `2.14.1`，HTTPX `0.28.1`，LangGraph `1.2.16`。完整命令与退出码见 `RESULTS.json`，原始日志在 `runs/`。

- RED-01：`1 failed, 2 passed`，复现 HTTP 200/202 同 Run 但 Chat 只包含 `s3_order`。
- RED-02：`3 failed`，复现没有沿完整同 Run 候选集合生成 wrong-Event 排除 provenance。
- RED-03：`1 failed`，复现 Chat 会携带 HTTP 202 原始响应中的受理时 `QUEUED` 快照。
- 最终 HF-01：`4 passed`（最终源码与测试运行见 `green-05/pytest.log`）。包含无 Receiver、同 Event `PROCESSED`、同 Event `QUEUED` 与跨 Task 隔离。
- 当前性、撤权、畸形版本、SLA 到期、历史 Run 隔离：`11 passed`。
- 合法 C1 `FOLLOW_UP + readonly_action=INVESTIGATE` 及补查：`15 passed`。
- M1/M2 安全回归：`107 passed`。
- 最终完整 pytest：`374 passed, 1 failed`，退出码 1。唯一失败是原有 `tests/test_m4_autonomy_c1_red.py::test_explicit_protocol_followup_is_accepted_as_same_task_readonly_run_before_ttl_fix`，该历史预实现用例提交 `READONLY_FOLLOWUP`；现行合法分类为 `FOLLOW_UP + readonly_action=INVESTIGATE`，对应合法路径回归 15 项通过。未加旧 Intent 兼容分支，未改写该 RED。两次全量执行都出现同一旧失败；日志均保留。
- 实际 Provider：`NOT_RUN`。本轮通过 Chat 的真实出站消息装配、ContextManifest、HTTP/MCP Trace 验证载荷；没有消耗 Provider 请求或 Token，也没有宣称模型已经给出正确最终回答。未重置或提高 EG-01 的模型预算。
- 浏览器：未运行，本任务按冻结合同不要求重演旧 Web 功能。

完整 pytest 中两个旧 C1 测试会向已有历史 Trace 追加运行记录。每次运行都把新增行原样复制到对应 `full-pytest-*/legacy-test-generated-traces.jsonl`，随后恢复历史文件到基线状态；旧文件没有进入本轮 Diff。

## 安全影响与限制

- Gate 的 `_gate_from_evidence()`、诊断 outcome、TaskControl、审批、动作事务和历史 Receipt 未修改。
- 修复允许有效的部分当前事实进入 Chat，同时继续 fail-closed 排除跨 Task/Event、旧 Run、过期、版本不匹配或撤权来源。
- Chat 只读事实内容可解释，不构成当前 Gate、审批、写权限或成功恢复的证据。
- 没有调用 Provider，因此“实际生成的自然语言答案”未在本轮复验；可信提示与 A/B/C 当前证据分离已由确定性载荷测试覆盖。模型遵循提示的概率性仍需上层验收判断。
- 测试服务使用本地 Demo Schema/HTTP；不宣称具备生产 IAM 或生产 Receiver 覆盖。

## Context Engineering 学习记录

这次修复采用“上下文事实集合”和“决策所用事实集合”分离的做法：Gate 的最小证明集用于业务裁决，Chat 的事实集则从同 Run 的成功工具观察重建，并在装配前按当前权限、版本、Event 与 TTL 重验。否则把 `checked_fact_ids` 当成完整上下文会造成遗漏；把整个历史 Diagnosis JSON 当成上下文又会误用过期或未经当前校验的数据。源码位置、原理笔记和面试答案见 `STUDY_NOTES.md`、`INTERVIEW_QA.md`。

## 六问与停止线

1. 用户变化：可以从同一调查中获知“订单正常、投递已被受理、完成状态未知”，不会因 Gate 缺 Receiver 而看不到投递事实。
2. Agent 决策：本轮没有运行 Provider；代码没有替模型作业务判断。Agent 可用的决策输入现在含合法部分事实和明确 UNKNOWN 约束。
3. 观察驱动：新增同 Event 当前 `PROCESSED` 或 `QUEUED` Observation 会改变出站事实；跨 Event Observation 被拒绝。
4. 新约束与合法影响：按 Run 的真实成功 MCP Observation 和当前 Domain Gate 校验防止陈旧/越域事实，同时允许同 Run 有效部分事实。合法 A/B/C 路径均有测试。
5. 简化结果：只在 Chat `_current_evidence()` 修正事实集合边界；Gate/Domain 状态机无新分支。
6. 证据与停止线：RED/GREEN、HTTP/MCP、ContextManifest、授权/版本/SLA/Run 回归和完整 pytest 均保留。Provider 未运行；旧契约 RED 是全量唯一失败。修复范围已止于 Chat 上下文装配。

本交付仅为 `ACCEPTANCE_CANDIDATE`；等待主 Agent 独立审查，不自行宣布 PASS。
