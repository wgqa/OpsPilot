# M2-02 后续门禁（冻结；本阶段不实施）

| 风险 | 后续阻断范围 | 门禁定义 | M2-02 处置 |
|---|---|---|---|
| S1 Evidence TTL / 审批后 Revalidation | 任何新增 S1 受控写能力发布 | 过期先原子阻断；重新取证、语义 digest、有效来源与持久 RevalidationReceipt 一致方可延续；`READY→NO_ACTION`、冲突及 UNKNOWN 均不得 REPAIR | S1 仅做既有回归和原 M2-01 S1 smoke；不放宽 TTL，不改 D3 写语义 |
| Web operation id / 重试幂等 | M2-03 Web 接收/提交写操作 | 一次用户意图稳定 operation id；响应丢失后同键回查；同键异 payload 拒绝；两次独立意图不同 id | 不新增写 endpoint，不声称解决 |
| S2 Handoff 唯一性与原子性 | M2-03 任何 S2 队列接收、`SCOPE_ESCALATED` | `(tenant, task, handoff_kind)` 唯一键；队列+Receipt+Outbox 单 Domain 事务；未知提交先回查 | M2-02 不建 HandoffReceipt/Queue/Outbox handoff record；Draft 为终点 |
| 项目级审批授权 | 依赖跨项目/生产资源审批的能力 | 服务端资源 Grant 与同租户异项目拒绝；现有本地角色不宣传生产 IAM | 不改角色模型，报告权限范围局限 |
| Episodic Memory、摘要及撤销传播 | M3 | 案例特有经验来源、人工确认/撤销、真实 Context 使用/排除轨迹 | 固定 `MEMORY_SUMMARY` 不称自主学习；不新增 Memory 系统 |
| 历史 S1 `CHAT_READONLY` / TaskControl 边界 | 本阶段所有新对话 | Readonly 只读，不修改业务 Graph/Approval/Plan/Intent/Task outcome；纠错必须显式类型和控制版本 | 保留原 M1-HF-01、M1-03 回归；不得绕过 TaskControl |

## 全阶段硬边界

- Runtime Scope Grant、Route Policy、credential policy 写入数必须为 0。
- M2-02 HandoffReceipt、handoff queue/record 写入数必须为 0。
- S2 `SCOPE_ESCALATED` 与 S2 `REPAIRED_VERIFIED` 必须为 0。
- 无当前匹配的可信 Authz Decision，不得生成当前 `DIAGNOSED` Receipt 或 Draft。
- 不能通过修改旧 Gold、删除历史失败、降低 148 pytest 基线或缩减 R/H/A 分母来“通过”。
