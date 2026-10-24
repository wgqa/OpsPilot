# C1 最终接线收口 — 验收候选报告

**状态：** `ACCEPTANCE_CANDIDATE`（实施方未签署 PASS）
**仓库/分支：** `wgqa/OpsPilot` / `codex/m4-autonomy-c1`
**远端 main 基线：** `77ea80e87e538f0f1fae8118ef231ec622601755`
**候选基线：** `3dc761b869112900f83180ee01d50be3f5e80493`
**实现提交：** `64653bd76f94889bceee8e51d79ae5a7873adef1`。包含证据的最终候选 HEAD 以本次交付的分支引用为准。

## 改动与边界

`S3Nodes.prompt()` 已把共享 `load_investigation_context()` 装配的有界先前只读结果和排除记录接入出站消息。正常 S3 调查 Prompt、只读补查 Prompt 与解释 Prompt 都携带历史来源状态，并明确历史模型回答只用于对话衔接、旧 Run Evidence 不构成当前事实。只有来源标记为 `CURRENT_APPLICABLE` 的 Knowledge 可作为当前协议引用；当前业务状态仍要求当前 Run 的 MCP Evidence。

每次模型调用的 `summary_refs` 记录先前 Run、结果状态和摘要、结果 digest、来源引用及各来源当前性；失效 Knowledge 的原因同时进入 `excluded_sources`。原有 `model_call()` 预算估算继续对完整出站消息执行；历史上下文也有独立 Token 分项。调用前重新运行共享来源装配，摘要、来源当前性或排除原因发生变化时，沿用既有校验阻止 Provider I/O。

没有修改 `investigation_context.py`、Domain Schema、Gate、Diagnosis、TaskControl、审批、ActionIntent、回执、MCP 工具或循环预算。历史 Evidence 没有加入 `current_mcp_evidence`。新测试验证 Diagnosis、Task 状态、TaskControl revision、审批/动作/交接表与 Outbox 快照保持不变。真实外部 Provider 和新浏览器旅程不在本轮验证范围。

实现和新增测试提交：

- 冻结计划：`7b4a61c622f77da3504420fe46032caeefcd5d0a`
- 首组有效 RED 与原始日志：`f2267015bf3c74fd920eec1b692ac7cedc314d85`
- 调查/解释 Prompt 和预算 RED 补充测试：`df45502e0a3d71ec059d80b27b354efb88b6ba5f`、`d90734c219d7178829615cadb3f8c90cfcce7535`、`5dafe112108eaac7b317a8a77d42e2fdb356d00c`
- 最小源码实现：`64653bd76f94889bceee8e51d79ae5a7873adef1`
- 证据提交：由包含本报告的最终 HEAD 指定。

## 验证结果

环境为隔离候选工作树 `.venv`：Python 3.12.14、pytest 9.1.1、LangChain 1.4.1、LangGraph 1.2.16、MCP 2.3.0、tiktoken 0.14.0。目标测试使用确定性 `CapturingModel`；没有真实 Provider 请求或浏览器新旅程。

最终 S3 接线测试：5 passed。它通过真实 `S3Nodes.model_call()` 捕获模型收到的消息，并从 SQLite 读取对应 `s3_model_contexts` 和 `d5_context_provenance`。覆盖有效历史分别进入正常调查与解释调用、失效 Knowledge 仅保留历史身份且记录原因、旧 Evidence 不跨 Run 变为当前事实、空历史仍可正常调用、来源变化在 Provider 前阻断，以及历史增长超过输入预算时不预留模型尝试、不调用 Provider。真实测试观察索引见 `TRACE.jsonl`。

C1/HF-01/S3/Context 定向回归为 120 passed。最终全量结果为 **343 passed，1 deselected**（退出码 0）；排除项唯一为冻结的实现前 RED `test_explicit_protocol_followup_is_accepted_as_same_task_readonly_run_before_ttl_fix`，其基线预期是拒绝补查，REV1/HF-01 记录明确要求实现后保留而不纳入绿色回归。未筛选全量首跑原样保留：341 passed、2 failed；一个是上述旧 RED，另一个是 M2-02 子进程未获得仅用于启动的本地模型配置。后续使用确定性 no-provider 占位配置复跑，Worker 内仍由现有 `NoToolModel` 替代 Provider。全量日志和原始失败过程在 `runs/`。

本次全量运行不等于真实 Provider 或浏览器验收。MCP/HTTP 集成和浏览器功能仅由原有回归覆盖；本轮没有重新执行旧浏览器旅程。

## B：下一里程碑事实能力核验

当前没有持久、可追加的同 Event 多次 callback Transport Attempt 历史。`s3_deliveries`、`s3_receivers` 和 `s3_orders` 都是每订单一行的当前快照；投递行保留最后一个 Event/Transport Request ID、状态、计数器和最后响应 JSON。测试 Fixture 每次只生成一个 Event、最多发出一次本地 HTTP POST，把内存中的 `transport_trace` 直接作为函数返回值，再用 `INSERT OR REPLACE` 写入快照。重复准备会覆盖先前 Event 的快照。

`s3_http_observations` 是已授权订单 HTTP GET 的逐请求历史，记录 GET request id、authn event、响应、digest 和时间，不是 callback POST 历史。`d2_attempts` 与 `d2_tool_observations` 记录 Agent 调用 MCP 和观察时间/Run 关联，也不是接收方传输尝试。现有 MCP 只读工具返回订单、当前投递、当前接收状态和 Knowledge/Skill，没有历史 Transport Attempt 查询。

因此当前资料不能逐条证明同 Event 的重试请求 ID、每次 HTTP 响应、顺序、时间与来源，也不能从当前快照判明先前是同 Event 重试还是新 Event。`S3_FACT_FEASIBILITY.md` 给出同 Event 重试、不同 Event 混淆和历史不足三个样例，并建议下一业务阶段若获批，仅增加 append-only Transport Attempt 事实职责，继续以现有订单快照作当前投影；之后通过绑定当前 TaskBinding 且重新核验授权的只读 MCP 查询提供历史线索，Gate/Diagnosis/Handoff 权威不变。本轮没有实现或修改该能力。

## North Star §8 六项交付判断

1. **用户变化：** 同一个 Task 的后续调查和解释可以沿用已完成只读补查的真实结果，不必仅凭原始消息重新猜“刚才引用的协议”。
2. **Agent 决策：** 本轮不新增自主性；既有模型仍在原工具和预算范围内决定是否查询或直接解释，程序保留绑定、来源判定、Gate 与写权限。
3. **观察驱动：** 历史回答只提供线索；当前事实仍来自当前 Run Observation。Knowledge 版本失效和当前事实查询缺口都能在输入与 Provenance 中识别。
4. **新增约束及合法路径：** 未新增硬限制。负例证明过期 Knowledge 不作为当前依据、跨 Run Evidence 不作为当前事实；正例证明合法当前 Knowledge、正常空历史、解释与调查消息都能抵达模型，超预算会安全拒绝。
5. **简化结果：** 复用既有 Context assembler、`summary_refs`、`excluded_sources`、Token 预算和出站前重验证，没有新表、工具、Guard 或 Runtime。
6. **证据与停止线：** 定向及全量命令、原始日志和退出码保存在 `runs/`；B 的依据和限制在 `S3_FACT_FEASIBILITY.md`。状态仅为验收候选，交主 Agent 独立复核；不合并、不启动 C2/C3。
