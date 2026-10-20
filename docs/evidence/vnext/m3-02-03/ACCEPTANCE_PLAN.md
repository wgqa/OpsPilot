# M3-02 + M3-03 冻结验收计划

**冻结范围：** OpsPilot vNext Context Engineering 与分层 Memory 专题。任务卡授权连续执行 M3-02、M3-03；满足 M3-02 核心门禁后才进入 M3-03。完成本卡后停止，不启动 M4、S3 或其他业务阶段。

**冻结基线：** `main@5ade2b5deedbb3704b09e9d6fbbfbffa3ab8deb8`。冻结本文件和 `TEST_MATRIX.json` 的提交必须早于本轮 RED 测试、生产代码和迁移。

**已知历史事实：** M3-01-HF-01 的报告记载 204/204 pytest；M3-01 原冻结评测为 8 对 / 16 臂、12/16，`UTILITY_NOT_PROVEN`，P03/P04 不符合 Gold。历史 Gold、结果和报告保持不变。本次开工检查显示 Domain Schema 实际为 v9，任务卡中“v8”描述已过期；任何数据库变化必须从真实 v9 做向前兼容、幂等升级。

## 六段式最小实现卡

1. **用户旅程：** 用户在同一 Web Session 中围绕一个已绑定 Task 连续交流至少 20 轮，补充、否定并正式纠正一项关键线索，再通过刷新及 Worker/进程恢复继续追问；检查器能说明本轮模型实际看到了什么、为什么压缩或排除。另一段旅程从 Task A 的真实业务结果形成 Episodic Candidate，经 APPROVER 确认后供不同 Task B 参考；撤销后，新调用及恢复不能重用它。用户还可将项目别名/约定提议为 Semantic Candidate，经有权主体确认后使用、修订、撤销或到期。
2. **模型决策与工具：** Chat 与 Investigator 使用共享的预算估算、来源校验与 Context Manifest 规则，保留各自消息适配和调查语义。真实模型可生成带依赖的非权威摘要；Investigator 继续仅通过现有 TaskBinding 范围的只读 MCP 工具获取当前事实。Recent Window、Rolling Summary、Hybrid 三策略以同一冻结上下文输入作确定性比较，Hybrid 为主策略。
3. **受信状态：** TaskBinding、TaskControl、Domain/Evidence、审批、Plan、Intent、Ledger、Receipt 和业务 Outcome 继续是唯一权威。摘要保存来源 Message/Assistant/Memory/Knowledge/Skill/Evidence/Task-state 版本、digest、Tenant/Session/Task 作用域及传递依赖；Provider 实际用量与本地估算分别存储。
4. **禁止动作：** 不允许用户原话、历史模型回答、摘要、Episodic/Semantic Memory、Knowledge 或 Skill 获得权限或改写当前业务事实；不允许过期/撤销/失配依赖在出站或恢复时复活；不允许跨 Tenant/Project/Session 读取；不改 S1/S2 Gate、Approval、ActionIntent、Ledger、Handoff 或业务终点；不新增业务工具、自动 Scope 授权、M4/M5 功能或通用 Memory/向量平台。
5. **Gold 与判定：** 冻结 `TEST_MATRIX.json` 的 CTX-01..10、MEM-01..06、E2E-01..03。硬安全项任一失败即 `BLOCKED`；未真实运行的 Provider/MCP/Browser/恢复项为 `UNVERIFIED`，不能以单测替代。M3-02 核心门禁未通过则停止、不进入 M3-03。最终达成本卡只能报告 `PARTIAL` 或“等待主 Agent 独立验收”，实施 Agent 不签 PASS。
6. **真实 Trace：** 脱敏记录 `release_ref`、session/task/run/message IDs、输入版本、上下文策略和预算版本、估算 token、输出预留、安全余量、摘要及递归依赖、所选/排除来源和原因、Provider request/response ID 与实际 usage、MCP attempt/observation/evidence、撤销事件、恢复 PID/Run 关联、策略与业务 Outcome。凭据、Cookie、Authorization 和原始 Token 不入日志。

## M3-02 冻结实现与验收合同

- 每个模型请求先构建结构化块：Trusted Control、Current Facts、Current Task State、Recent Interaction、Historical Summary、External Guidance、Tool Schema。块有固定权威等级、选择优先级及版本化预算策略。
- 输入预算关联模型配置，明确最大输入、输出预留和安全余量；本地估算器名称/版本写入 Manifest。估算值和 Provider 实际 usage 分开保存。低预算测试配置必须让真实预算计算触发压缩；不允许靠标志或手工预置“已压缩”状态通过。
- Hybrid 是主策略：可信状态和当前事实作独立结构化块，较早历史摘要与来源明示，近期用户原话保留。Recent Window 与 Rolling Summary 用同一素材和估算策略参与对照。摘要是非权威、可重建派生物，不能取代 Domain/Evidence/审批/账本。
- 摘要构造有界、可重试、成本纳入已持久模型预算；失败、部分输出、重试和跨进程恢复均有状态。摘要失败或可信块超过预算时显式安全停止；不截掉安全规则、可信身份、当前 Gate/关键事实以保留聊天。
- Summary 依赖至少支持 Message ID/digest、AssistantMessage 及其有效来源、Memory/Knowledge/Skill ID/version/digest、Evidence/Task-state 版本、派生 Summary ID/version、Tenant/Session/Task。每次出站和恢复均递归重验；依赖失效时排除失效摘要并从仍有效源重建，不对文本做关键词清洗。
- 模型 attempt 预留之后、Provider I/O 之前再次校验资产及 DAG。失效 attempt 消耗原预算并关闭为明确状态；按原预算重建，禁止静默发送旧上下文或重置计数。报告构造与网络 I/O 间不可原子化的竞态边界。
- Web Context Inspector 展示本次策略/块/预算/估算和实际用量、保留原始消息、摘要范围与依赖、排除内容及原因、重建状态；不输出凭据，不泄露跨域内容。

## M3-03 冻结实现与验收合同

- Working 继续引用现有 Task/Graph/Evidence/Domain；Session 复用 Messages、纠错及 M3-02 Summary；Episodic 扩展已存在的来源、人审、撤销和检索协议；Procedural 复用版本化 Skill；Knowledge 保持独立且权威等级明确。
- Episodic Candidate 只由可信历史业务来源生成，经独立 APPROVER 确认后 Active。检索给出可核对适用理由、候选选择/排除原因、预算和与当前事实冲突处理；有限选择最多 3 项且按 Context 预算裁剪。当前 Domain/MCP Evidence 优先。保留 Task A→不同 Task B→撤销→新调用与恢复不再使用的真实链路。
- 新增最小项目级 Semantic Memory 生命周期：Candidate→Active→Revised/Revoked/Expired。自然语言仅可形成隔离的提案，不直接创建 Active；Scope 由可信身份和 TaskBinding 推导；确认者须有冻结的项目授权；修订保持可审计的旧版本/新候选关系，冲突不静默覆盖。Semantic 仅存获准项目别名、接口约定或非敏感工作约束，不能替代正式 Knowledge/实时 Domain。
- 逻辑分层共用既有 SQLite Domain，不创建新数据库或服务；迁移必须从 v9 幂等升级，并保留旧 Episodic 记录及其历史状态，不能把 D5 legacy 记录伪装成新案例。

## 发布门禁与测试纪律

- 冻结 Gold/Rubric/用例先提交；保留独立 RED 结果；实现后逐项 GREEN，并保存每次失败、修复与重跑的原始日志。
- 新鲜完整 pytest、已有 204 项回归、前端 typecheck/build/lint、真实 Provider、MCP stdio、HTTP S1/S2、真实 Web 20+ 轮、数据库迁移、Worker/Checkpoint 跨进程恢复分别报告分子/分母和退出码。
- M3-01 的 8 对 / 16 臂冻结结果只作为历史，不改写或混入本次新样本。新策略和 Memory ON/OFF 采用独立 Release、独立结果目录，保留全部尝试；可报告业务效用 `NOT_PROVEN`。
- 密钥只允许从本地环境读取；报告和 Trace 使用脱敏数据。不得把 provider 未报告的金额自行写成真实成本。
- 若必需的外部模型凭据/服务当前不可用，保留失败证据并将真实链路标 `UNVERIFIED`，不得用 Mock 代替结论。
