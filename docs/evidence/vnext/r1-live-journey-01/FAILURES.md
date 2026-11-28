# 失败、阻断与遗留事项

## 本轮真实旅程

### `BLOCKED_BEFORE_PROVIDER_SEND` — 公开容量费用界超过授权

- 当前 DeepSeek 峰值输入/输出价格及公开上下文容量计算出的单请求保守预留为 USD 0.69168。
- 16 次总界为 USD 11.06688，比当前授权多 USD 0.06688。
- 未降低预留、未减少已冻结的 16 次额度来制造 READY、未创建 Grant/Claim，未发送请求。

### Runtime Grant 预检缺口

- 现有 Grant 发送前预留只按配置的 12,000/2,048 Token 字段计算；这不等于官方最大容量的费用界。
- `store_response()` 可在 Provider 已执行并计费后发现 Usage 超预留并暂停；因此它不能替代发送前上界预留。
- 当前 Runtime Grant 路径没有可复核的持久跨 Session Campaign 发送次数上限。
- 新工作树没有 Provider 环境配置和已 provision 的 Grant；父工作区 `.env` 中的凭据值从未输出或提交，其有效性没有通过真实请求验证。模型/端点字段存在，但 model config / price version 未设。

## 旅程状态

- J1/J2：没有真实模型回答、工具选择或 Observation；只复用 Base 的离线正式路径证据，Campaign Live 状态为 BLOCKED。
- J3/J4：未调用真实模型读取受信结果，按全局发送前门禁阻断保留 NOT_RUN；已有离线 Domain 结果不冒充本次真实模型回读。
- 没有真实 Provider 失败、模型失败或工具失败可归因；不能声称修复了模型决策问题。

## 保留的既有问题和限制

- Base 既有历史 `PRODUCT-01 Slice 02` 真实 DeepSeek 四轮旅程为 `PARTIAL`，其中配置推断超证据；本轮未改写其 Trace、Gold 或结论。
- R1 `INTERACTIVE` 仍 `HOLD / NOT_RUN / BROWSER_STOP_ACTIVE`。
- Base 历史全量 pytest 757 收集、741 通过、16 失败不是本候选新鲜全量结果；12 个历史 one-shot/身份绑定测试不得在新 SHA 重放，3 个旧 AR-03 Runner Schema allowlist 失败和 1 个已废弃 C1 `READONLY_FOLLOWUP` RED 保持原归因。本轮未重跑全量 pytest。
- 当前无新的生产代码 Diff，无新的 RED/GREEN。后续执行需要先解决预算/Grant/发送计数缺口并重新核验当日价格；不能靠拿旧 Grant 或旧 Claim 重启。
