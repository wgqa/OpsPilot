# Provider 观测：覆盖范围与不能证明的部分

## 实际调用链

本轮没有更新依赖：langchain-openai 1.7.2，OpenAI SDK 3.33.0，httpx2 2.13.1。Investigator 调用 `ChatOpenAI.ainvoke`；Web Chat 调用 `astream`，压缩调用 `ainvoke`。应用的其他 HTTP 客户端不是这条传输链。

独立 `acceptance_server.py` 调用原 ChatOpenAI 构造函数后，取得原 `root_async_client._client`，在公开 `event_hooks` 添加观察函数。捕获层为 **HTTPX2_REQUEST_EVENT_HOOK_AFTER_SERIALIZATION_BEFORE_TRANSPORT_SEND**。这是原 SDK 已序列化的 HTTP 请求体，不只是应用 Prompt 或 SDK 消息。没有传入替代 Transport、修改 timeout、增加 SDK retries 或重写 Tool Schema。观察函数本身在单独验收进程；生产入口没有引入补丁。

旧 CLOSEOUT 的挂错客户端失败记录未改。新观察先用非敏感 `M3HF02_PAYLOAD_PROBE_20261021_v1` 做独立验证，之后才创建业务 Task。详情 `runs/journey-01/A2-observer-validation.json`：Run `run-7345f692-270c-482c-bb77-dfb7d7c2bcae`，Attempt `chat-attempt-f2b538cc-da35-4664-9fea-4610d6beba7b`，真实 Provider Response `0b42686e203fb08d26db1672b6ecd3c2`，378 input / 113 output / 491 total。业务开始前 Task 数为 0。

## 保留哪些内容

- 在内存检查原 bytes，保存 SHA256/长度，以及每条消息的角色、长度、正文 digest；不保存完整原始 Prompt。
- Memory 保存 ID/version/content_digest/source_task/outcome/authority、经验与说明字段 hash、限定的非敏感历史说明片段，并与 Domain 选定版本逐字段比较。
- 保存实际资产全集与预期全集、实际 Summary 结构 hash 与持久 ID/版本、当前 Evidence ID、可信任务状态/Run 块存在性。
- Manifest 排除的助手逐条比较实际请求中是否有相同 assistant 正文；Summary 排除集合与实际 Summary 集合核对。结合来源表检查，不能只搜索一个关键词。
- 压缩请求的真实 source_material 在内存与已登记依赖精确相等；输出仅序号、正文 hash、父摘要 hash，不输出源材料全文。
- body 检查前后 hash 相同。启动记录包含生产关键文件/observer hash、SDK 版本和 PID，便于区分基线与修复后的进程。
- Response hook 只记录真实 HTTP 状态和 request_ref。完整 Provider Response ID/Usage 从已有成功 Attempt/ModelTrace 联接，见 `TRACE.json.requests`。

不记录 API Key、Authorization、Cookie、CSRF、URL 查询参数、真实本地口令或原始整个请求。合成登录材料仅保留在忽略的 `.runtime/`，不入 Git。

## 本次数量与一致性

共 **49** 个真实序列化请求：23 Investigator、23 Chat、3 Compression；48 个 HTTP200 响应头，另 1 个请求在受控进程崩溃中无返回记录。49/49 关联 Attempt；资产集合、结构化内容、不可变 body 均匹配，0 OBSERVER_ERROR。所有已记录的排除助手正文都未作为相同 assistant 输入，排除摘要未在实际摘要集合出现，三次压缩源材料精确匹配。

原始 `provider-observations.jsonl` 保留每个 request_ref；`TRACE.json` 联接 Attempt/Run/Call/Response/Usage；49 表只读快照中的 `chat_message_sources`/Summary dependencies 则提供传递关系。11/11 汇总一致性检查属于运行证据核对，**不是 11 个独立模型评测样本**。

## 撤销与恢复实证

A 的 E1 v2 来源 Task A 真正完成 v7→v8 修复/同身份200/报告/交付，不同 Task B 当前 v9/401 的实际 Investigator 和 Chat 请求带入精确匹配的历史经验。E1 v3 撤销后，真实 Chat 和正式纠错后的 Investigator 请求无该资产；依赖旧经验的助手被 Manifest 排除，实际请求中无对应 assistant 正文。

Run `run-7258d97f-4f8c-458f-8163-8fb564bef838` 在 5 个 Checkpoint、当前 MCP 取证后触发杀进程；两 PID 的实际请求均排除旧经验，恢复仍同 Run/Thread，最终 WAITING_APPROVAL。Task 的 MODEL/MCP 预算到 8/6，没有重置。详细 A 技术核对 14/14；该阶段没有 Summary，因此不据此宣称 Summary 传递撤销已证明。

修复后，E1/E2 均已撤销，新的 Task E 实际 Investigator 继续排除它们而选用 E3 的正确 v2。E3 新 Chat 的历史 v11→v12/200 与当前 v13/401分开。E3 撤销后的 Chat 和重启均无 Memory/旧助手，但**当前 Evidence 已先过期**，不能把排除完全归因于撤销，也不能替代本轮两跳 P1 的确定性 RED→GREEN。

## Token、估算与未知

46 个请求取得完整 Provider Usage：125,992 input + 33,698 output = **159,690 total**，是已知下界。其余 3 个费用和 Token 均 UNKNOWN，不按 0 计算：

1. `attempt-567987b8-927f-40b6-8462-fd6c995d4d65`：实际发出后进程崩溃，未取得最终 SDK 返回。
2. `context-compression-2345279c-8da9-40a3-a32d-eda9bc4a1145`：HTTP200，但来源再验证拒绝提交，响应 ID/Usage 未写入。
3. `context-compression-4ce7f654-c0d4-4904-b4dd-4352182252b0`：同类 HTTP200/TaskControlError，元数据未写入。

46 对本地估算与实际 input 的差值范围 -960～+449，均值 -49.696；实际 input / 本地估算均值 0.9714。Investigator 与 Chat 的内容/工具 schema计算口径不同，所有逐请求数据公开，不能用总均值作计费精度保证。Provider 分词、消息开销及 reasoning/output 统计口径也不由本地估算控制。

没有抓取实际账单或冻结 Provider 单价，因此不虚构货币金额。输出预留512是原应用/请求配置，不能说所有 Provider reported output（含 reasoning）都不超过512；真实成功压缩报告 output1237，原样保留。没有为观测更改这些参数。

## 局限

hook 证明出站前实际请求内容，不证明 Provider 内部一定读了某一段、不会在远端失败，或未知请求是否最终计费。来源校验与网络 I/O 不是一个事务，存在检查后到发送前的窗口。相同 assistant 正文排除检查不等于完整语义证明，必须连同版本、DAG、角色与实际集合解读。原始请求不落盘，评审依赖脱敏结构与 digest，不能离线重现全部网络 bytes。

本轮新观察覆盖实际 Chat/Investigator/Compression 路径；没有独立计量 MCP tools/list 次数，真实 stdio tools/call 由18个持久 Attempt/Observation和工具结果证明，不杜撰 catalog 调用分母。
