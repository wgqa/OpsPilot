# AR-05 S1/S2 Web 驗收准备

**状态：PREPARED / BROWSER_NOT_RUN / EXISTING_BROWSER_STOP**

本文件是下一轮 Web 验收的执行清单，不是浏览器验收结果。当前轮没有启动 Playwright、Computer Use 或浏览器，也没有创建新的业务 Task。

## 隔离启动

在 STOP 由授权方明确解除后，使用全新的本地 Demo 数据库和 Checkpoint；保留现有 `.runtime`、历史 Trace 与旧运行库。不要在已有 AR-04C/AR-03 实验 DB 上运行 Web 旅程。

API 仅绑定 loopback，并用不同的隔离文件：

```powershell
$env:OPSPILOT_DB_PATH = '.runtime/ar05-web-acceptance-<run-id>.sqlite3'
$env:OPSPILOT_CHECKPOINT_DB_PATH = '.runtime/ar05-web-acceptance-<run-id>-checkpoints.sqlite3'
$env:OPSPILOT_WEB_ORIGIN = 'http://127.0.0.1:8000'
$env:OPSPILOT_ASSISTANT_PROVIDER_ENABLED = '0'
$env:OPSPILOT_ASSISTANT_EXPERIMENT_ID = ''
$env:OPSPILOT_MODEL_API_KEY = ''
python -m opspilot.web.server --host 127.0.0.1 --port 8000 --workers 1
```

前端在第二个终端设置 `OPSPILOT_API_ORIGIN=http://127.0.0.1:8000` 并仅监听 `127.0.0.1`。登录口令只从本地 `.env` 读取，不记录到脚本、截图或报告。此次 P0 静态验证复用了本机已存在且版本与隔离 `package-lock.json` 一致的 Node 依赖；新环境需要先按锁文件安装依赖。

## J-S1：同一会话到已交付

1. 以 `support-a` 登录，创建新会话；确认 UI 角色为 SUPPORT、Demo 资源为 `orders-demo / integration-a / principal-a`。
2. 在普通聊天发送冻结的 401 报障描述。确认只创建 Chat Message/`ASSISTANT_V1` Chat Run，不创建 S1 Task、Approval、ActionIntent 或业务写入。
3. 点击“进入受控调查”；确认 `AUTH_INCIDENT`、资源身份和原始问题，然后显式点击“确认并启动调查”。记录原问题 `message_id`、Task、初始专业 Run ID；不得以 Assistant 答复或用户文字代替 Observation。
4. 检查 Inspector 的同 Task 当前 Evidence、Gate、Plan 和来源。预期初始到达 `WAITING_APPROVAL`，`REPAIR`/`DELIVER` 未发生。刷新会话后确认任务、Run 与原消息关联不变。
5. 切换至独立 `approver-a` 身份，在审批中心按 Task 和 Plan hash 审查并提交审批。SUPPORT 页面不得出现可代签行为；聊天内容不得生成 Approval。
6. 若 Plan/资源在审批后发生变化，预期 `REAPPROVAL_REQUIRED` 且 ActionIntent/REPAIR ledger 为 0；只有当前事实复核并再次独立审批后才继续。正常无变化路径允许现有 D3 复核、CAS、在线验证和 DELIVER。
7. 返回 `support-a` 原会话并刷新。只能在 Domain Outcome 显示 `DELIVERED`、验证回执显示同 service/integration/principal/route 的 HTTP 200、冻结报告及交付回执均存在时显示“已恢复并交付”。

**J-S1 预期 Domain 断言：** 普通聊天阶段：S1 Task=0、Approval=0、ActionIntent=0、ActionLedger=0；等待审批阶段：Task/初始 Run/当前 Evidence/Plan 已关联原 `source_message_id`，ActionIntent/Repair ledger/VerificationReceipt/DeliveryRecord=0；最终成功阶段：同一 Task 恰有一个 REPAIR 和一个 DELIVER ledger、一个有效 VerificationReceipt（HTTP 200 且 `recovery_verified=true`）、冻结 ReportArtifact 与 DeliveryRecord。任何拒绝、UNKNOWN、旧 Plan 重放或过期证据都不能被投影成 `DELIVERED`。

## J-S2：显式本地交接及回执恢复

1. 以 `support-a` 在另一个全新会话发送冻结的 403 范围问题。确认 Assistant 普通回答本身不产生 Handoff。
2. 用户确认进入 `AUTH_INCIDENT` 受控调查后，等待专业 Investigator 使用同 TaskBinding 的本地 MCP/HTTP 完成同请求 403 与 Authz DENY 关联。
3. 检查 `GET /api/tasks/{task_id}/handoff` 为 `HANDOFF_READY / CURRENT`，DiagnosisReceipt 与冻结 Draft 来源属于当前调查 Run；Queue、HandoffReceipt、Outbox 尚为 0，Scope/Policy/Grant 没有变化。
4. 在 UI 明确确认提交至**本地**受控审查队列。预期 `SCOPE_ESCALATED / PENDING_REVIEW`；记录 receipt、queue entry 与 operation ID。
5. 刷新和重新进入同一会话，再读 `handoff` 与 Session event history。Receipt ID 应保持相同，不新增 queue/receipt/outbox；界面必须说明未授予 Scope、403 未恢复。
6. 如果 Draft 过期、跨租户/owner、关键纠错或正文改变，提交必须拒绝且不增加副作用。

**J-S2 预期 Domain 断言：** 提交前 Queue/Receipt/`S2_HANDOFF_ACCEPTED` Outbox=0；提交后各为 1，命令为 1，重放仍为 1；Scope/Policy/Grant 写入=0，原 granted scopes 不变，Repair=0，Outcome=`SCOPE_ESCALATED`、handoff=`PENDING_REVIEW`。这仅是本地演示队列接收，不代表企业系统已接收或权限已开通。

## 验收采集

授权后应保存浏览器 DOM/可访问性文本、截图、请求/响应摘要、Session/Message/Task/Run/Plan/Receipt IDs、刷新前后 ID 对比和只读 Domain 快照。截图不得包含口令、Cookie、Token 或环境变量。浏览器结果必须独立标记，不用 TestClient/API 用例冒充。
