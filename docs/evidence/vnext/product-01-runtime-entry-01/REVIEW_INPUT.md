# Astra 定向复审输入：PRODUCT-01-RUNTIME-ENTRY-01

## 要复核的设计问题

基线源码：`fa30383c1a58755e75bef7b7f393ff9ba602200c`。实现方未改生产代码。普通正式 Session 在 `OPSPILOT_ASSISTANT_PROVIDER_ENABLED=1` 且 `OPSPILOT_ASSISTANT_EXPERIMENT_ID` 为空时，`create_assistant_model` 最终以实验 Scope 错误拒绝；若关闭开关则返回 `None`，Worker 记录程序级未运行/预算提示。此前 PRODUCT-01 Slice02 的真实 Provider 运行使用实验 ID、冻结合同和一次性 Claim，因此正常产品路径尚未证明。

## 推荐方向

把正常产品授权表达为持久服务端 `runtime_profile_id`，与实验 ID 和 one-shot Claim 分开。Profile 由单独的用户/主 Agent 费用授权建立；显式 Provider 开关、Profile 状态、模型端点、费用池、价格版本与预算必须匹配后，Worker 才能创建 Provider 客户端。每次请求在发送前通过现有持久 Ledger 预留，Usage 结算；UNKNOWN 保留预留、停止该预算池且不重试。Run 级调用记录继续复用 `assistant_calls`。实验 scope 仍按现行冻结路径运行，普通用户不获得额外工具或写入权限。

这一做法会要求把现有实验 Ledger 的 scope 从固定实验 ID 最小参数化；不建议用新的“普通产品实验 ID”或另建一般计费服务。无需现在确定金额或价格合同；在获批金额/可审计预留缺失时，真实普通 Provider 仍应关闭。

## 请 Astra 只评估

1. 与“继续加实验 ID”相比，`runtime_profile_id` 是否确实切断了普通 Session 对实验 SHA/Claim/one-shot 生命周期的依赖？
2. 使用同一持久 Ledger 的 scope 参数化是否比复制一份产品预算表更简单且可安全迁移？历史实验的固定参数和记录如何保持不可变？
3. 由 `assistant_calls` 提供 Run 级记录、共享 Ledger 提供跨 Run 费用预留，职责是否清楚；是否有更小的等价现有机制？
4. 关闭开关、无效/撤销 Profile、Usage UNKNOWN、额度耗尽、同逻辑请求重放时，推荐的拒绝/停止语义是否足够 fail closed，是否造成不必要地锁死其他合法使用？
5. 是否存在从环境变量/用户输入、Session 或 Run 切换绕过费用池、重放历史 Claim 或让未绑定用户调用业务工具的风险？
6. 是否有比 schema scope 迁移更简单、同等安全且不会把正常产品重新绑回实验合同的实现？

## 不在复审范围

不评价整个 OpsPilot 架构，不提出新的 Planner/Graph/Provider Gateway，不改工具选择逻辑，不设预算金额，不授权真实 Provider、浏览器或业务写入，不批准 main 合并。
