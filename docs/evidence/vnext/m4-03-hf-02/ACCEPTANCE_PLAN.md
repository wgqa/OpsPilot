# M4-03-HF-02 冻结验收计划

基线：`main@afe3c03a756e2a60e454e0057484017448942d40`。冻结提交在 RED 执行前创建；本文件与 `tests/test_m4_03_hf_02.py` 定义本轮判定面。

## 范围和权限矩阵

| 数据/入口 | 当前授权的 SUPPORT Task owner | 撤权后的 SUPPORT Task owner | 同租户 APPROVER | 其他租户/身份 |
|---|---|---|---|---|
| 普通 Session / Message / Run 状态事件 | 按现有 owner 权限读取 | 按现有 owner 权限读取 | 按既有矩阵拒绝 | 拒绝 |
| S3 `S3_DIAGNOSIS_FROZEN` 事件 | 可读 | 历史与 SSE 均跳过，不含诊断、方向或诊断回执字段 | Session 事件端点拒绝 | 拒绝 |
| S3 `S3_HANDOFF_ACCEPTED` 事件 | 可读 | 历史与 SSE 均跳过，不含 Receipt、Queue、订单或 `HANDOFF_ACCEPTED` 字段 | Session 事件端点拒绝 | 拒绝 |
| 已提交不可变 S3 Receipt 审计摘要 | 当前授权时按现有 owner 读取 | 拒绝 | 只允许既有 `/api/tasks/{id}/s3-handoff` 只读摘要；不含诊断正文，不得提交新交接 | 拒绝 |
| Task Inspector / Run / Chat 读取 | 按现有 Task 或 Session owner 权限；当前事实复用 Domain Gate | 不得返回可绕过拒绝的 S3 Receipt 或当前事实 | 只按既有待审批权限 | 拒绝 |

权限判断复用 `_authorized_s3_scope()` 和 `get_s3_binding()`。事件筛选只针对上述两种 S3 专属事件；不删除 Outbox 或 `session_events` 历史，不改写不可变 Receipt，不改变普通事件游标。

## 冻结测试与判定

- **HF02-01a / RED**：真实 S3 Task 产生诊断与已接受 Receipt 后撤销 Scope；历史事件不得暴露 `S3_DIAGNOSIS_FROZEN`、`S3_HANDOFF_ACCEPTED`、Receipt/Queue ID、订单号或业务结果。普通事件仍可读取，`Last-Event-ID` 可从隐藏事件之后继续。撤权前 owner 仍能读取相应事件。APPROVER 事件读取保留现有 Session owner ACL 的拒绝码（403 或 404）；既有回执审计摘要仍可读。
- **HF02-01b / RED**：SSE 对同一事件流执行相同过滤；撤权后不得发送诊断或交接内容，后续普通事件仍能送达。
- **HF02-01c / audit**：Task Inspector、Task/Run 摘要、Run Context/Chunks、历史 Message 只按既有 owner/role 检查；S3 诊断和交接当前状态复用 Domain 当前性/授权检查。当前授权 owner 保持原有 Chat 读取能力；撤权后，绑定 S3 Task 的 CHAT_READONLY Run 不得通过 Context/Chunks 返回旧业务事实或回执；混合 Session 的普通用户消息保留，依赖 S3 状态的助手正文在读取响应中隐藏。Inspector 不得泄露真实 handoff Receipt/Queue ID。Approver 只能从既有 S3 handoff 端点读取提交后不可变摘要，不可读诊断正文或执行提交。
- **HF02-02 / RED**：五个版本字段（Scope Policy、Grant、Principal、Auth Policy、Integration 配置）只接受 `type(value) is int and value > 0`。REAL `1.5` 在数据库路径必须 fail-closed；Python `bool`、float、字符串、`None`、零及负数不能通过版本解析。Domain、HTTP 资源目录与 MCP 查询不得因畸形版本放行。
- **HF02-03 / RED/GREEN**：无模型的受控集成用例通过真实本地 HTTP 与 in-process MCP 完成 WAIT 诊断；推进确定性时钟到 SLA 边界，在旧 Evidence TTL 内拒绝旧诊断交接且无 Queue/Receipt/Outbox 增量；新 Run 实际调用当前绑定的 HTTP/MCP 事实，验证 Task/订单/Event/版本/观察关联，由 Gate 得到 CONTACT；owner 明确确认后只产生一份持久 Receipt，重复请求只回放。
- **HF02-04 / RED/GREEN**：`now < deadline` 为 WAIT，`now == deadline` 与 `now > deadline` 为 CONTACT；旧 WAIT 在精确截止点立即失效，证据仍在 300 秒 TTL 内，原诊断字节/digest 不变。

## 执行门禁

1. 先提交本冻结计划和 RED 测试，再运行 RED 并保留原始输出。
2. 最小实现后依次运行新增测试、HF-01/S3/M4-02、S1/S2 安全回归和完整 pytest；每次使用本轮独立 `--basetemp`。
3. 不调用付费模型、不改 Gold/旧报告/旧运行目录、不清理其他未跟踪文件。无新依赖。
4. 证据中的 Trace 只从成功测试里真实采集的 HTTP/MCP/Domain 返回值写出；不得合成调用或 ID。
5. 交付状态只能标记“验收候选”，由主 Agent 独立复核。
