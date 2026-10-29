# 早期真实模型检查点：HOLD / NOT_RUN

免费最短链路已接入：同一 Session 的资料查询 → 用户确认合法订单 → 真实本地 MCP/HTTP
调查 → 原问题答复 → 结果说明。免费模型替身的原始输入、工具结果和真实接口响应单独保存。
这证明接线、权限、持久化和恢复，不证明真实 LLM 决策效果。

S01：无 Task 概念解释，允许零工具。S02：资料适用版本查询后进入已授权订单只读调查。
两条真实模型 Smoke 均尚未获得本轮付费授权，不能复用 AR-01 的次数或额度。

任务卡候选预算：16 Provider / 12 MCP / USD 0.20，不自动重试。
旧 AR-01 的 REQUEST_WIRE_P1_2048_V1 在其冻结价格假设下每次预留 USD 0.317031，
已大于此候选总额。不能直接套用、提高总额或将估算 Token 当严格计费上界。
当前价格、可审计请求边界、未知计费保留与付费 Adapter 接线仍须独立预检、审查及授权。
本轮不向收费接口发送兼容性探测。

新 ASSISTANT_V1 路径默认不创建真实 Provider 客户端，持久显示
`ASSISTANT_PROVIDER_AUTHORIZATION_REQUIRED` 程序说明。`create_app` 的
`assistant_model_factory` 是服务端代码依赖注入点，本轮仅以确定性模型用于免费验证，
不是 Web 参数、授权开关或可绕过预算的产品 API。真实模型工厂尚未获准接入。

该默认拒绝只针对本轮新入口；旧 Chat/Investigator 保留原有 Provider 构造路径，不宣称全应用禁用。
本轮免费兼容实验在明确的本地替身拦截下调用旧路径，未发送真实收费请求。
资料范围中的 configured_contract_version 是项目资料配置；deployment_version_verified=False，
不能证明线上部署或真实模型已经正确处理与 Task 配置的版本冲突。

禁止把可注入、确定性成功、Run=SUCCEEDED 或前端构建通过写成真实模型产品已通过。
Browser/B-11 继续 HOLD/NOT_RUN，未执行任何浏览器脚本。
