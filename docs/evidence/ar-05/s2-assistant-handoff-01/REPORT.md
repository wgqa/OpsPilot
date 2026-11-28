# AR-05-S2-ASSISTANT-HANDOFF-01 — 结果报告

**状态：`ACCEPTANCE_CANDIDATE`**

**基线：** `65612ff1cb72664c124ec5aa70cbcfa8f869eced`

**分支：** `codex/ar05-s2-assistant-handoff-01`

## 用户旅程证据

确定性模型在正式 Assistant API 收到原问题，并由正式 `ASSISTANT_V1` Worker 持久化回答。用户显式确认进入调查后，可信 Task 的 `source_message_id` 指回原 Assistant 用户消息；任务初始消息保留相同原文并记录 `investigation_origin_message_id`。

正式 S2 Worker（`PROFESSIONAL_INVESTIGATOR`）通过同一 TaskBinding 下的本地 MCP 实际调用 `probe_endpoint` 和 `get_scope_authz_facts`。Observation 显示同一请求 `/api/orders/demo-order` 返回 HTTP 403，认证成功但授权决策为 `DENY / SCOPE_INSUFFICIENT`，缺少 `orders.read`，已授予 Scope 为空。DiagnosisReceipt 与冻结草稿引用这两个同 Run Evidence。

提交前读取结果为 `HANDOFF_READY / CURRENT`，Queue、Receipt、Outbox 均为零。随后测试通过显式确认调用既有 `/handoff/submit` API；提交后为 `SCOPE_ESCALATED / PENDING_REVIEW`，Receipt 与 Queue ID 相同地从 Domain 和原 Session event history 回查。Operation 重放返回同一 Receipt，不增加队列、回执或 Outbox。

该终态只证明隔离 Demo 的本地受控审查队列接收了草稿。没有授予 Scope，没有执行修复，403 未恢复。

完整关联、来源、计数与回执在 [TRACE.json](TRACE.json)。测试断言及执行核心标记见 [test_ar05_s2_assistant_handoff_01.py](../../../../tests/test_ar05_s2_assistant_handoff_01.py)。

## 实施范围

没有发现需要改动产品 API、Domain 或 Vue 投影的缺口：现有 S2 `GET /handoff`、显式 `POST /handoff/submit`、稳定 Operation/Receipt 及前端 `HANDOFF_READY`、`SCOPE_ESCALATED`、`PENDING_REVIEW` 呈现已满足本旅程。此次只新增一条正式本地 API/Worker/MCP/SQLite 整合测试和证据文件；不声称 S2 已迁移到 `ASSISTANT_V1`。原对话由 `ASSISTANT_V1` 处理，受控诊断仍由现有专业 Investigator 处理。

## 回归与未运行项

- 新的完整本地旅程：1/1 通过。
- M2-03 Handoff、M2-02 S2 diagnosis、AR-05 S1 bridge：25/25 通过，包含 owner/租户、来源、草稿失效、关键纠错、改 payload、响应丢失重放、并发和事务回滚用例。
- M4-02/M4-03 S3：34/34 通过。
- 合计 60 项通过，来自三个独立 pytest 命令，不是一次全量套件运行。
- 全量 pytest 未运行；保留既有 TestClient shutdown 停滞为独立回归债务。AR-03 Runner 预检失败未重跑。
- 浏览器验收未运行（既有 STOP）；真实 Provider 请求为 0。
- `ruff` 未运行：当前 Python 环境未安装该包。前端源码未改，未运行 typecheck/build。
- 推送隔离分支时 GitHub 返回 HTTP 403；随后的 `ls-remote` 也返回 HTTP 403，因此候选远端 SHA 为 `UNVERIFIED`。未尝试绕过。推送前最后一次成功 fetch 的 `origin/main` 为 `60eee87bfe3cca522011316cb4cd2c0064ad291b`。

初期测试失败均来自测试断言/审计查询与真实合同不一致，而非产品行为：缺省字段 `recovered` 被误当必需、事件列写成 `event_type`、命令表误假设有 `task_id`。修正为兼容既有响应和实际 Schema 后，整合旅程通过；完整原始日志保留于本目录。

## Skill 收尾核对

已在当前目标工作树重新打开 `.agents/skills/opspilot-slice-review/SKILL.md`，按其 C 节核对实际基线、冻结合同、代码/Trace/日志与未运行项。历史 Gold、失败和其他工作树未修改。本次新增的仅是验证用例，没有引入新的生产限制或职责。

## 六问交付摘要

**用户变化：** 免费本地演示现在有一条可复查的统一 Session → S2 受控调查 → 显式本地队列接收 → Receipt 回显完整证据；未证明真实浏览器体验。

**Agent 决策：** 形式化测试中的确定性 Investigator 提议调用两个合法只读工具；它不证明真实模型的自主选择。

**观察驱动：** 本次 403 + 授权 DENY Observation 形成 `HANDOFF_READY`；提交后只形成 `SCOPE_ESCALATED`，Scope/Policy 不变，不能说明已恢复。

**新增约束：** 没有新增生产约束。显式提交、幂等和当前性由既有 M2-03 Domain/API 保障；正向旅程与既有拒绝/重放回归均通过。

**简化结果：** 没有复制 Handoff API、队列、Receipt 或写入职责；直接复用现有实现，仅新增纵向整合测试。

**证据与停止线：** 真实本地 API/Worker/MCP/SQLite 与原始 Trace 已验证；真实 Provider、浏览器和全量 pytest 未运行。等待主 Agent 独立验收，不合并 main、不进入下一阶段。
