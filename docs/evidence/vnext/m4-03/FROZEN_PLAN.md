# M4-03 S3 用户旅程、设计与验收冻结

基线：`main@f7c739f4e3d02988fc125b377dfa85a902bc2a0d`  
状态：实现前冻结；Gold、Rubric 与本文件必须先独立提交。  
范围：仅深化现有 ASYNC_CALLBACK / S3，不新增 S4；M4-02 的 Gold 与历史结果保持原样。

## 用户得到的业务进展

用户描述订单回调问题后，系统先展示当前租户预注册并授权的订单目录。用户选中并明确确认一个订单，服务端在创建 Task、首条 Message、首个 Run 的事务中验证该订单仍属于固定 S3 服务/集成，并保存不可变的 Task→订单资源绑定。模型只看到已绑定订单的事实与工具，不接收 `order_id`、租户、URL 或凭证参数。换订单必须创建新的 Task。

同一 Task 的正式关键纠错继续走现有提议、确认、`CORRECT_TASK_INPUT` 和 TaskControl revision。纠错只增加不可信线索；旧 Run/旧诊断不能支撑新判断，新 Run 对同一已确认订单重新调用 MCP/HTTP。订单身份变化不能由纠错修改。

当前证据可形成三种诊断：订单仍在处理；订单完成但回调传输失败；服务端已接受回调但接收方仍排队。失败原因通过真实本地回调传输响应、重试状态与次数核实；接收排队方向通过匹配 Event 的接收状态、接收时间及 SLA 核实。确定性 Domain Gate 将这些证据映射为“等待已排定重试”“联系回调运维”“等待接收方处理”或“联系接收方”。原因或版本证据缺失/矛盾时停止为证据不足。

只有可信 Task owner 对当前不可变诊断和人工处理方向点击确认，Domain 在一个 SQLite `BEGIN IMMEDIATE` 事务中重验 TaskBinding、TaskControl revision、诊断回执和来源 Evidence，并原子写入独立 S3 Queue Entry、不可变 S3 HandoffReceipt、Task 状态、命令结果和 Outbox。重复提交回查原 Receipt；不同 operation id 也受 `(tenant_id, task_id)` 唯一约束。唯一业务结果是 `HANDOFF_ACCEPTED`。队列状态仅表示待人工处理；不得写配置、重发回调、授予 Scope、创建 S2 审批，或宣称订单/回调已恢复。

## 源码扩展审查与最小实现

- S3 事实、现有只读 MCP 与 Gate 位于 `opspilot/domain/s3.py`、`s3_mcp.py` 和 `s3_investigation.py`；只加订单资源绑定及少量投递/接收原因字段，继续复用既有 Graph、Worker、Checkpointer、8 次 Model / 6 次 MCP 预算和 Evidence 重验。
- Task 创建继续走 `create_task_with_initial_run`。新增可选的 S3 资源引用，只在 `ASYNC_CALLBACK` 路径校验并与 TaskBinding 同事务落库；普通 S1 创建、S2 Gate 和 M4-02 历史 Gold 不变。S3 诊断 Run 结束后进入可纠错的 `WAITING_HANDOFF` 状态；已有 TaskControl 负责纠错版本和重启，Receipt 提交后才结束 Task。
- Knowledge 保持小型版本化目录与实际按需 MCP 检索；补充协议/确认/错误处理版本和来源。比较已有词法排序与一个固定实现的 BM25-lite（含文档长度归一化和冻结查询集），报告 Recall@1、MRR、手工相关性及本地耗时；不引入向量库或外部 RAG 服务。
- Skill 仍为有限、版本化、按需加载目录，按 S3 协议和中间证据标注适用范围。每轮重新验证 digest；适用性只影响模型提示，不控制 Gate。
- Episodic Memory 沿用 D5 来源、审批、撤销和出站校验。S3 相关性由当前未信任描述线索与已核验的订单协议/传输状态字段和来源案例字段计算；每个候选记录匹配字段、分数、阈值和排除原因。无关/冲突方法只能被标为提示或排除，当前 Evidence/Gate 不受影响。ACTIVE、来源当前、未过期、异 Task 与同租户仍是前置条件。
- 新 S3 handoff 独立表、接口、业务唯一键和 Outcome；复用 Domain 命令、事务、TaskControl 与 Outbox 原语，不复用 S2 `SCOPE_REVIEW`、Scope Policy/Grant、`SCOPE_ESCALATED` 或审批语义。
- Vue 先完成目录澄清与订单确认，再建立 Task；同一 Task 显示调查、纠错、新 Run、当前方向、确认交接、Receipt 和队列状态。刷新和 API 重启后由 Domain 回读。

## 冻结实验

### R / H / A

- **R**：合理的确定性调查政策，依次读取最小当前事实；按 Gate 的缺失事实请求后续只读查询；达到证据条件即停止。它不是无条件扫描全部工具。
- **H**：真实 LLM 归一化用户描述/补充，产生受限调查焦点；规则按同一合法目录决定查询。模型归一化必须实际改变首个合法查询或澄清。
- **A**：真实 LLM Function Calling 在每轮看到的新鲜可信事实、版本化知识候选、适用 Skill/Memory 和完整受限工具目录后，自主提出下一只读行动或停止。程序只接受目录内工具并按预算登记；Gate 独立裁决。
- 三组使用 GOLD 中相同租户、订单、服务端初态、Binding 规则、资产版本和用户答案。每个冻结行各运行一次 R/H/A；每格只允许一个新鲜 attempt，失败不重试覆盖。Holdout 行在冻结后不用于 Prompt 调整，仍完整运行并报告。
- 分别报告：正确诊断/处理方向、可证明的 Task 推进、Binding 与控制安全、首次正确工具率/工具数/无效与重复调用、Agent 追加澄清数、绑定选择负担、Provider Token、端到端延迟与失败。R 的模型 Token 为 0；不做显著性或普遍优势声明。资产选择/曝光不等于业务收益。

### 资产实验

- 至少 2 个协议/接收确认版本、2 个因果不同的经审批历史案例、2 个适用条件不同 Skill；用冻结查询逐条评估词法与 BM25-lite 的排序。
- 对真实任务比较正确案例、无关案例、与当前事实冲突的案例，以及撤销/到期案例的下一工具、Evidence、Gate 和交接方向。撤销/到期后继续同一 Run 或新 Run时，实际 Provider Context 不得重新包含其内容。
- 知识缺失、过期、旧版本冲突时当前 Evidence 仍决定事实和 Gate；事实不足则明确停为 INCONCLUSIVE。

### M3 Summary 来源链有界实验

仅复用现有 Context Compression/Source DAG。最多 2 个隔离用户旅程、4 次实际 Provider 请求、每个旅程不超过 25 分钟；不得提高模型/聊天/摘要预算、放宽 Evidence TTL、直接插入摘要或改写历史 PARTIAL。至少记录 Summary 的真实来源版本与当前 Evidence/Memory 依赖；撤销或来源版本变化后的后续 Provider Context 必须排除旧 Summary 和依赖回答。首次失败完整保留。任一窗口未完成即标 `PARTIAL/NOT_PROVEN` 并按预算停止。

## 安全与停止条件

越租户/越订单读取、客户端任意订单/URL/凭证绑定、用户聊天文字改写绑定、模型决定授权或写操作、无当前 Gate 的 handoff、TaskControl 版本绕过、跨事务的 Queue/Receipt/Outbox、重复或无法核对的回执、无证据声称恢复、S1/S2 历史安全回归退化，均为硬失败；不以正确率抵消。禁止新增自动重发、Scope 修改、S2 审批、通用队列/平台、多 Agent、向量 DB。遇到需要重写 Runtime、TaskControl 或 S2/S1 合同的情况停止并提交变更说明。

## 冻结验收编号

- **M403-01**：受信订单目录按租户/支持者角色过滤；不存在、跨租户、伪造资源与任意 URL 均拒绝。
- **M403-02**：资源选择由用户确认；订单资源与 TaskBinding/首条输入/首 Run 同事务、幂等；Task 绑定不可变。
- **M403-03**：不同订单正确分流；真实同描述不同事实、不同描述同事实对照保持 Gold。
- **M403-04**：处理中的订单最小查询即可停；不得归因回调故障或创建人工交接。
- **M403-05**：真实关联投递失败原因、次数、重试状态支撑对应方向；状态缺失/矛盾安全停止。
- **M403-06**：真实 202 接收确认、Event 关联、receiver queue、时间与 SLA 区分等待和联系人工；不得称已处理。
- **M403-07**：关键纠错经确认使用现有 TaskControl 提升 revision、失效旧诊断并创建新 Run；重新获取绑定订单的真实 HTTP/MCP Evidence；绑定不变。
- **M403-08**：Knowledge 版本/来源/适用协议检索；冻结查询集比较 lexical 和 BM25-lite；缺失/过期/冲突不覆盖当前事实。
- **M403-09**：Skill 按条件加载且每次 Provider 前重验；正确、无关、冲突、撤销/过期 Episodic Memory 按相关性、安全和来源合同处理。
- **M403-10**：人工方向只由 Domain Gate 与充分当前 Evidence 给出；无模型文本或知识/记忆文本可直接形成方向、授权或 Gate。
- **M403-11**：可信 owner 确认后 S3 Queue Entry、`HANDOFF_ACCEPTED` Receipt、Task 状态、命令与 Outbox 原子提交；S2 Scope 写账本不变。
- **M403-12**：重复点击、不同 operation id、响应丢失、并发、事务 failpoint、进程/API 重启均回查一个 Receipt/Queue Entry，无重复副作用。
- **M403-13**：真实浏览器完成目录澄清、订单确认、调查、正式纠错、新 Run/取证、用户确认交接、Receipt 追问；刷新和重启后状态一致。
- **M403-14**：8 个冻结 Gold 各自按 R/H/A 完成，至少 2 个 holdout；完整报告推进、正确、澄清、工具、Token、延迟、失败与安全矩阵。
- **M403-15**：真实 Provider/MCP stdio/HTTP/Web Trace 跨 ID 可关联；资产和模型作用如实分析。
- **M403-16**：M3 Summary 来源链按上述预算运行；未完成保留 PARTIAL；旧 M4-02 与 S1/S2 历史结果不改写。
- **M403-17**：新鲜完整 pytest、前端构建、M4-02/S1/S2 回归、真实 MCP 和 S1 401→200 smoke 通过；所有原始失败保留。

