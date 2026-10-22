# M4-02 原理、业务接入与源码学习

## 从用户的一个问题开始

用户看到订单查询 HTTP 200、下游却没有回调，实际上混合了三个阶段：订单生命周期、投递传输、接收方处理。Web 选择“订单 200 但下游未收到回调”后，服务端只允许注册好的 S3 资源映射；自然语言不能改 tenant、principal、order 或 URL。

先读 `frontend/src/App.vue::createDemoTask`、`opspilot/web/app.py::post_task`，再跟入原有 `create_task_with_initial_run → Worker → run_investigation`。TaskControl、Session、Message、Run 仍是既有实现，S3 没有另造任务权威。

## 原理到取舍

**动态行动与固定工作流。** 固定工作流由代码选路径，Agent 可以根据反馈决定工具使用；这也是 R/H/A 分组要区分的部分。[Anthropic 原文](https://www.anthropic.com/research/building-effective-agents)。本轮 R 的顺序由规则决定，H 的真实模型 focus 影响合法首个查询，A 每轮都收到五个合法工具及当前事实，由真实 Function Calling 选择行动。`opspilot/s3_investigation.py::investigate` 的 R/H 分支不是 A 的派发器；A 的实际路径见原始 Trace。小型三状态实验中规则已足够，模型自主行动不能自动等价为更高准确率。

**工具协议不是权限。** MCP 定义了发现、调用、结构化结果等协议能力；注解本身不能实现资源授权。[MCP Tools 规范](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)。读 `opspilot/domain/s3_mcp.py`：工具没有资源 ID/URL/凭证参数，严格拒绝多余字段，并重新核验持久 TaskBinding。只读注解帮助理解工具；真正的隔离来自 SQL 归属、Schema、TaskControl 和只暴露查询函数。真实 MCP 负例在定向测试和原始日志中。

**短期执行状态与跨任务经验。** Checkpointer 保存线程执行进度，跨线程信息需要独立持久化；二者作用不同。[LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)。本轮继续使用原 `AsyncSqliteSaver` 和 D5 SQLite Memory。Checkpoint 只保留资产引用；每次模型请求重新读取 Knowledge/Memory 并记录 Provenance。不是从 Checkpoint 直接复活过期正文，也没有增加向量平台。

## 核心源码阅读顺序

| 位置 | 需要解释的决定 | 对应证据 |
|---|---|---|
| `opspilot/domain/s3.py::prepare_s3_fixture` | 单独准备最小业务状态，并真实 POST 本地接收端；Agent 不可调用 | 每个运行的 PREPARATION.json 与 transport request/event |
| `opspilot/domain/api.py::do_GET`、`s3.py::order_http_payload` | S3 独立路由、真实认证/授权 HTTP、持久 Request ID；原 S1 路由不变 | TRACE 中 HTTP observation 与 Authn 关联 |
| `s3.py::get_s3_binding`、`current_s3_evidence` | 从实际 Domain 反查版本/归属/原始 HTTP；不能信任一个自称 typed 的 JSON | 伪造、版本变化、跨租户负例 |
| `s3.py::_gate_from_evidence` | 验证事实是否足够；它不替 A 选择下个工具 | 三种 Outcome、缺事实和冲突测试 |
| `opspilot/domain/s3_assets.py` | 两个文档用有界词法检索；版本、来源、时间、digest 逐次重验；Skill body 按需打开 | 真 MCP 查询、选用理由、后续实际 Provider Context |
| `opspilot/domain/episodic_memory.py` 的 S3 扩展 | 从真实只读诊断抽取案例事实，复用原候选/审核/撤销；不伪造修复/验证回执 | SOURCE_A_TRACE、Memory ID、B 第一轮 Context |
| `opspilot/s3_investigation.py::model_call` | 出站前登记预算/Provenance/实际 Prompt，检查当前资产；多提议只派发首个并留存其他请求 | Provider ID、usage、pending 状态和原始失败 |
| `s3_investigation.py::report`、`s3.py::persist_s3_diagnosis` | A 在读到最终事实后生成说明，Gate 事务仍独立核验；说明不授予权限 | 最后一个真实 Provider 请求、不可变诊断、Outbox |
| `opspilot/domain/chat.py` | 追问读取当前 S3 事实与来源；失效事实使旧回答的依赖不再有效 | Web 真实追问、版本失效回归 |

## 用失败学习

- 初次 pytest 默认临时目录权限失败，随后指定项目 `.runtime/m4-02` 的唯一目录；环境失败和真正功能 RED 分开留存。
- 初次 S3 Probe 得到 403，原因是新服务尚未准备实际 Scope Policy/Grant。最小修复是测试准备注册独立 S3 principal/grant/policy，未扩大 S1 权限，也未给 Agent Scope 写能力。
- MCP 无具体返回类型的知识字典曾缺少结构化结果，导致安全 INCONCLUSIVE。补充返回 Schema 与标准 JSON 文本兼容读取后，用真实 stdio 重跑。
- 模型曾违反“每轮一个工具”，一次返回两个调用；控制器现在保留完整提议，只派发首个，后续必须根据新的观察重新决定。不能把 `parallel_tool_calls=False` 当作安全保证。
- 缺失 Knowledge 曾导致模型反复检索空结果。后续 Context 明示空检索状态和禁止无增量重复的规则；由模型选择其他合法行动，不在 A 中硬编码接下来必须查哪个工具。原失败不删除。
- 最终说明缓存曾缺少资产来源依赖：撤销 Memory 后，事实诊断仍正确，但旧说明可能再次进入聊天。`runs/narrative-red.log` 保存真实定向 RED；说明现在绑定原模型调用的既有 Context Provenance，来源失效则隐藏说明、改变当前 State digest 并记录排除原因。已冻结事实诊断与历史审计仍保留。真实 Provider 后续追问补测见资产收尾运行中的 `POST_COMPLETION_INVALIDATION.json`。
- Windows 检出会改变文本换行。新增有 digest 合同的 Skill/Knowledge 正文固定 LF，原始证据固定字节；这关系到复现，不是业务根因。

## 已接入与未证明的部分

Knowledge、按需 Skill、经审核跨 Task Memory 已进入真实 Provider Context，并有实际工具选择记录；过期/撤销后的请求重新加载，恢复进程也排除无效资产。固定 Gold 中 R/H/A 都可正确处理三个事实状态。没有证明 A 必然优于规则、Memory ON 必然省 Token、词法检索适合大规模语料，也没有验证外部企业回调基础设施。完整量化与历史失败以 REPORT/RESULTS/FAILURES 为准。
