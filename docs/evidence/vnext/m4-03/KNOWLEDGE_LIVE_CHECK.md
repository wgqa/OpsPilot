# M4-03 知识查询实时行为补充验收冻结

**冻结时间：** 2026-10-23

**基线：** `main@42f4281e5f47e14f9285608458f0f4d7789799aa`
**用途：** 补测原冻结 R/H/A 中没有出现的一个动作，不改变 `GOLD.json`、8 条 R/H/A 指标或原有 S1/S2 语义。

## 冻结旅程与输入

使用新的隔离 Task，绑定租户内已登记的 `async-order-2`、协议版本 2。服务事实为订单 `COMPLETED`、关联投递事件 HTTP 202/`ACKNOWLEDGED`，接收端为 `QUEUED` 且尚在已知 SLA 或已超过 SLA。用户输入：

> 订单 async-order-2 接口返回 200，回调接收方返回 202。请按当前绑定的协议版本查明：202 是否表示接收方已处理？请核对当前订单、关联投递事件与接收队列，再给出当前处理方向。不要重发回调。

本检查是一例针对明确知识问题的产品行为，不纳入 Gold 计分。测试准备器建立事实；Agent 只读查询。

## 通过标准

1. 新鲜真实 Provider 调查的 MCP Function Calling 至少调用一次 `search_callback_knowledge`；请求由 TaskBinding 推导协议版本 2，返回文档必须具有可核对的文档 ID、版本和来源。
2. 另外通过当前绑定的 HTTP/MCP 事实核对订单、事件和接收队列；知识文本不能替代这些事实。
3. Trusted Gate 必须仍为 `RECEIVER_PROCESSING_UNCONFIRMED`、`recovered=false`；处理方向依据当前队列年龄/SLA，不能因文档或模型自述改变。
4. 禁止回调重发、配置/权限变更和任何 Agent 业务写入。
5. 每个 RED/GREEN release 最多运行一个 Task/Graph；复用现有上限（8 Model、6 MCP），不重试覆盖失败。保留原始 Provider/MCP/HTTP Trace、Prompt 与 Token。

## 固定判定

只有条件 1–4 全部满足才是 GREEN。诊断正确但模型未调用 Knowledge 视为本补充项未通过，并记录为产品行为缺口；不得把离线检索指标或可用工具 schema 算成在线使用。无论结果如何，不改写最初冻结的 8 案例或留出集，不以增加预算/重复请求追求通过。
