# S1/S2 业务因果 Trace 索引

本轮没有新建产品 Task；下面把候选中已经持久化的纵向本地 Trace 与本轮新鲜回归日志对应起来。新鲜运行使用独立 pytest 临时数据库；完整测试输出在 `logs/`。

## J-S1 — 401 修复

- 原始已保存完整闭环 Trace：[`s1-d3-close-01/TRACE.json`](../s1-d3-close-01/TRACE.json)
- 原始 Session 接线 Trace：[`s1-session-bridge-01/TRACE-verified.json`](../s1-session-bridge-01/TRACE-verified.json)
- 本轮新鲜纵向回归日志：[`logs/s1-offline-regression.txt`](logs/s1-offline-regression.txt)，测试 `test_formal_worker_investigates_same_session_through_real_mcp_and_http`
- 本轮测试覆盖：普通 Assistant Message → 明确 Task 创建 → 同一 Session `source_message_id` → 正式 Investigator/MCP Evidence → WAITING_APPROVAL → 独立 APPROVER → 对审批后版本变化要求 REAPPROVAL → 二次批准 → 一个 REPAIR + 一个 DELIVER → 同身份 HTTP 200 VerificationReceipt → Session 回显。
- 屏障前后事实在测试断言中包括：普通聊天阶段 Approval/ActionIntent/ActionLedger=0；等待审批阶段 REPAIR/Verification/Delivery 为空；最终 credential_ref=`cred-v2`、config_version=9、REPAIR ledger=1、DELIVER ledger=1、当前复核 VALID=1、变化时重新审批=1，Outcome=`DELIVERED`。

## J-S2 — 403 权限交接

- 原始已保存正式 API/Worker/MCP/SQLite Trace：[`s2-assistant-handoff-01/TRACE.json`](../s2-assistant-handoff-01/TRACE.json)
- 本轮新鲜纵向回归日志：[`logs/s2-offline-regression.txt`](logs/s2-offline-regression.txt)，测试 `test_ar05_same_session_assistant_to_s2_handoff_receipt`
- 本轮测试覆盖：原 Assistant 问题 → 用户确认 Task → 专业 Investigator 对同一 Request ID 调用 probe/authz → 当前 403 与 DENY 形成 DiagnosisReceipt/Frozen Draft → 显式 submit → Queue/Receipt/Outbox 一致 → Session event 回查与重放。
- 预期不变量：提交前队列/回执/Outbox=0；提交后各=1、操作命令=1；`scope_authorized=false`、Repair=0、granted scopes 不变、Outcome=`SCOPE_ESCALATED`、handoff=`PENDING_REVIEW`。

## 证据等级

这些旅程由确定性模型替身驱动正式 API、Worker、MCP、Domain 与隔离本地 HTTP，不是 DeepSeek 行为证据。此处链接的先前 JSON Trace 属候选中的历史原件，本轮不覆盖；本轮测试日志是本次新鲜重跑记录。真实浏览器、SSE/刷新 DOM、真实 Provider 与生产写入均未执行。
