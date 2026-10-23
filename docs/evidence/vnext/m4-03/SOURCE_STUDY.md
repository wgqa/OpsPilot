# 源码学习地图：从 S3 调查到受控交接

## 一次请求经过哪里

1. `opspilot/web/app.py` 的订单目录与 Task 创建路由要求可信登录身份。`opspilot/domain/s3.py::list_s3_order_resources` 从当前租户已登记资源返回目录；`bind_s3_order_in_transaction` 在 Task 初次创建事务中绑定用户确认的订单。URL、订单 ID、租户和角色权限不会取自模型工具参数。
2. `opspilot/investigator.py` 仍是已有调查入口；`opspilot/s3_investigation.py::S3Nodes` 定义模型提议只读行动、MCP 调用、证据处理和 Gate/报告的节点。`opspilot/domain/s3_mcp.py` 将 MCP request 再映射到可信 TaskBinding；模型仅能从有限只读 schema 选择。
3. `get_order_status_fact` 通过业务 HTTP 路由取得当前订单事实；`get_callback_delivery_fact` 和 `get_receiver_processing_fact` 以订单绑定和事件关联读取投递/接收事实。`current_s3_evidence` 与 `_gate_from_evidence` 校验当前版本、来源和必要证据，生成 `ORDER_PROCESSING`、`CALLBACK_DELIVERY_FAILED`、`RECEIVER_PROCESSING_UNCONFIRMED` 等确定结论。
4. `opspilot/domain/task_control.py` 受理正式关键纠错并控制 revision、旧 Run 失效及新 Run 创建。S3 调查完成后仍可纠错，纠错会对同一绑定重新取证，而不是用聊天回答替代业务图。
5. `opspilot/domain/s3_handoff.py::submit_s3_handoff` 在一个 SQLite 写事务中核验 Task owner、当前 Gate、版本与 idempotency identity，然后提交 S3 Queue Entry、HandoffReceipt、Command、Task 状态和 Domain Outbox。重复 operation/业务唯一键返回历史 Receipt。该协议独立于 S2 Scope Grant/Approval。
6. 前端 `frontend/src/App.vue` 和 `frontend/src/api.ts` 展示资源确认、调查进展、纠错确认、手动交接和 Receipt；刷新后通过 Domain API 回读状态。`frontend/e2e/m4-03-s3-journey.mjs` 驱动真实 Edge 并断言重启和重复提交行为。

## 知识和经验怎样进入模型而不越权

`opspilot/domain/s3_assets.py` 读取带版本、来源和服务适用范围的本地 Knowledge/Skill。知识查询做版本过滤并记录来源，比较 lexical 与 BM25-lite；Skill 按当前事实和协议适用条件选择。`opspilot/domain/episodic_memory.py::_s3_memory_relevance` 把当前线索和已经审核的案例字段比对，生成分数、匹配字段与排除原因；中文文本使用双字组减少单字符偶合。`opspilot/domain/chat.py` / Context Provenance 重新校验撤销、过期、来源版本和冲突；Memory 只能提示方法。最后的 Gate 不读取模型自述或资产文本来授予交接资格。

## 核心工程取舍

- 继续使用现有 LangGraph、TaskControl、MCP stdio、Evidence 和 SQLite；新增能力垂直落在 S3 领域。
- 将接收方排队与回调失败建模为有版本、可关联的当前事实；Gate 对事实做确定判断，减少提示词中硬编码答案。
- 交接和 S2 授权分别拥有领域状态与唯一性键。S3 回执代表本地操作队列接受，不延伸到权限获批、业务恢复或回调重发。
- R/H/A 结果显示正确规则在这个小 Gold 上已经足够；A 的高 token/延迟成本说明真实模型并非处处有收益。模型的实际产品价值主要在用户语言理解、因事实调整查询顺序与解释，而非替代确定性授权。
- 词法和 BM25-lite 本轮没有性能/质量差异；保持小型检索实现优于引入向量平台。

## 调试时建议的阅读顺序

`docs/evidence/vnext/m4-03/FROZEN_PLAN.md` → `opspilot/domain/s3.py` → `opspilot/domain/s3_mcp.py` → `opspilot/s3_investigation.py` → `opspilot/domain/s3_handoff.py` → `opspilot/domain/task_control.py` → `opspilot/domain/s3_assets.py` 与 `episodic_memory.py` → `opspilot/web/app.py` → `frontend/src/App.vue` → 对应 `runs/*/TRACE.json`。
