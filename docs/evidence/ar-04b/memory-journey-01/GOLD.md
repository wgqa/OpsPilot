# AR-04B-MEMORY-JOURNEY-01 — 冻结 Gold

**状态：** FROZEN（正式实现前冻结；实施方不得自行修改）
**冻结基线：** main@134df49f792dfdf8d4b9a3b846d218af5c34ec6d
**来源：** 用户提供的 AR-04B-MEMORY-JOURNEY-01 任务卡 §5
**冻结范围：** G1–G10 及下方说明；原判据文本保持不变。

## Gold 判据

| Gold | 必须满足的判据 |
|---|---|
| G1 来源可信 | Memory 来自真实合法来源、正式候选和可信确认，不能伪造 ACTIVE |
| G2 真实可见 | ON 模式中，适用 Memory 的 ID、版本、Digest 与指导内容出现在实际 Provider 输入 |
| G3 记录一致 | Manifest、Context 来源、实际 Provider wire 与最终答案来源关系一致；不能记录未实际发送的 Memory 为已使用 |
| G4 当前事实优先 | Memory 不得代替当前 Run 的授权 MCP Evidence；历史 202 不证明下游完成 |
| G5 合法选择 | 模型可以选择合法调查工具、补查或停止，不强制固定工具顺序 |
| G6 作用域隔离 | 跨 Tenant/Project、同 Task 来源、不适用类型、CANDIDATE 或失效 Memory 不得错误注入 |
| G7 撤销不回流 | 撤销/过期/修改后，新的 Model Call 不能看到失效 Memory，旧来源关联答复及摘要不能作为有效历史回流 |
| G8 竞态安全 | Memory 在选取后、Provider 外发前被撤销时禁止外发旧内容；外发后失效不得提交依赖旧来源的有效答案 |
| G9 预算与可靠性 | Memory 计入既有 Token 预算；超限按已有 Context 策略选择或排除，不能绕过预算、产生新的无账本模型调用 |
| G10 安全不变量 | 不越权、不自动审批、不产生未经授权业务写入，不伪造 Receipt，不重复未知费用调用 |

特别要求 G8 包含双向测试：失效来源必须被拒绝，同时无关、有效的 Memory 和正常调查仍可继续。