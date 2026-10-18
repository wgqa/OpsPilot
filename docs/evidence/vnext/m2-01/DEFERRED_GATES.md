# M2-01 后续阶段门禁（本轮冻结，不实施）

本文件冻结 M2-01 卡指定的跨阶段风险和阻断关系。它不是这些缺陷已修复的声明；M2-01 不修改 D3 Plan/Action/approval 行为，不增加 Scope 写入，也不实现队列、Receipt 或前端重试。

| 风险/级别 | 后续阻断范围 | 必须单独通过的拟定测试 | 本轮处置 |
|---|---|---|---|
| S1 Evidence TTL 与审批后 Revalidation / P1 安全门禁 | M2-02 开始前需由主 Agent 明确是否先单独修补；任何新增受控业务写能力发布前必须修复并复验 | 到 TTL 后旧证据不可执行；重取证前先原子写阻断；语义 digest 相同才用 RevalidationReceipt 延续原 Plan；事实版本/Principal/Policy/Probe 实质改变则同事务取消 Plan、撤销未消费许可；`READY→NO_ACTION` 断言新增 Repair Ledger=0；未知来源/冲突/动作 UNKNOWN fail closed | 冻结合同与 RED/Gold 设计；不改 D3 |
| Web operation_id / Idempotency-Key 稳定性 / P1 | 阻断 M2-03 接收队列写操作交付；M2-01 不改 Vue/Web Command | 首次请求响应丢失后以原 operation_id 重试；同正文的两个独立用户操作须有不同 ID；同键异 payload 冲突；消息、Command、Run、control revision 不重复增加 | 登记风险；不实现 |
| S2 Handoff 唯一性、Receipt 与 Outbox 原子提交 / P1 | 阻断任何 S2 队列接收/`SCOPE_ESCALATED` 实现，包括 M2-03 | 后端业务唯一键 `UNIQUE(tenant_id, task_id, handoff_kind)`；不同幂等 Key 同一业务键不重复入队；同键异草稿 digest 拒绝；队列、HandoffReceipt、Outbox 一个 Domain `BEGIN IMMEDIATE` 事务；Run 结束与队列处理分离；三日排队不占 Worker 活跃预算 | 只冻结；本轮没有 HandoffReceipt/queue/Outcome |
| Approver 仅租户级而非项目级授权 / P1 声明边界 | 阻断声称已实现项目级、企业级 IAM 或依赖此授权的生产范围 | 若引入 Project：服务端资源 Grant；同租户异项目拒绝；Plan/Approval 重新验证资源归属与版本 | 保持本地 Demo 说明，不升级权限模型 |

## 安全关系

- HTTP 403 和 Authz Decision 事实不授权 Scope 写入，也不等同于批准或 Handoff。
- Knowledge、模型文本、MCP JSON 和 Gold 不能提供当前权限真相。
- `DIAGNOSED`、`HANDOFF_READY`、`SCOPE_ESCALATED` 后续需分别有自己的证据/冻结草稿/真实回执；M2-01 所有 Agent/交接业务结果均保持 NOT_IMPLEMENTED。
- 若未来实施需要改变 M1-HF-01 的审批、Evidence Gate、ActionIntent 或事务合同，必须先另提主 Agent 审核，不能在 M2-01 作为“必要兼容”顺手放宽。
