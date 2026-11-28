# AR-05 S1/S2 集成验收 Gold（预检冻结）

这是本轮集成预检新增的验收摘要，不替换或改写任何既有 AR-05、S1/D3、S2/M2-03 Gold。

## J-S1：401 受控修复

**冻结用户问题：**

> 我们轮换了 API 凭据以后订单接口一直返回 401。你帮我调查一下，如果需要修复，告诉我后续怎么操作。

**完整成功条件：** 同一 Assistant Session 的原始用户消息可追溯到明确确认创建的 S1 Task；专业 Investigator 取得当前 Evidence 并形成真实 READY/Plan；独立 APPROVER 批准；审批后重新核验当前事实，事实变化时重做 Plan/审批；只有授权有效后发生一次 CAS；同一 service/integration/principal/route 实际 HTTP 200；持久 VerificationReceipt 与冻结报告；独立 DELIVER 生成回执；原 Session 展示 `DELIVERED`。

**必要反例：** 普通聊天不建 Task；SUPPORT 不能审批；拒绝/过期/配置变化/主体 DISABLED/UNKNOWN 不允许 CAS；旧 Intent、重复提交或响应丢失不产生第二次 REPAIR/DELIVER；`WAITING_APPROVAL`、`REPAIR COMMITTED`、`RECOVERED_NOT_DELIVERED` 不得显示为 `DELIVERED`。

## J-S2：403 范围交接

**冻结用户问题：**

> 我们的 API 返回 403，感觉是调用权限不够。帮我查一下，如果需要人工开通权限，帮我准备交接。

**完整成功条件：** 同一 Assistant Session 的原始用户消息可追溯到明确确认的 S2 Task；同一请求的当前 HTTP 403、Authn 成功与 Authz `DENY / SCOPE_INSUFFICIENT` 形成 DiagnosisReceipt；用户看到当前 Frozen Draft；只在显式确认后写入本地 review Queue、不可变 HandoffReceipt 与 Outbox，各一；结果回显为 `SCOPE_ESCALATED / PENDING_REVIEW`。

**必要反例：** 普通聊天不建 Task、不交接；未提交/过期 Draft、跨租户/错误 owner、关键纠错、正文改变、响应丢失和重复提交不能越权或重复入队。Scope/Policy/Grant 不得因草稿或本地回执而写入；403 仍未恢复。

## 通用验收边界

- 真实 Domain Outcome 是 UI 状态的唯一权威；`Run=SUCCEEDED` 不能替代业务 Gold。
- `SCOPE_ESCALATED` 只代表本地队列已收件，不代表授权或业务恢复。
- 模拟/确定性模型、隔离 SQLite 和本地 HTTP 可以验收代码因果链；不能宣称真实模型或浏览器体验已验证。
- 浏览器 STOP、真实 Provider 付费和外部/生产业务写入均不在本轮授权中。
