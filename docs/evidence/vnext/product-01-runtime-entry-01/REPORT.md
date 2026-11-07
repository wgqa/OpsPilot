# PRODUCT-01-RUNTIME-ENTRY-01：入口现状与最小方案

**状态：ACCEPTANCE_CANDIDATE**（仅离线现状核查与方案，不代表正常真实 Provider 运行已实现）

## 核验基线

- Repo：`wgqa/OpsPilot`
- Branch：`codex/product-01-runtime-entry-01`
- Base / 核验 HEAD：`fa30383c1a58755e75bef7b7f393ff9ba602200c`
- 远端候选 Base：`codex/product-01-continuity-review-01@fa30383c1a58755e75bef7b7f393ff9ba602200c`
- 远端 `main`：`60eee87bfe3cca522011316cb4cd2c0064ad291b`
- 本地工作树开工时干净；未合并、未改生产代码。
- `PROJECT_NORTH_STAR.md` Blob：`43dabda468506717c6956e676dfad4304c4f38e6`
- `AGENTS.md` Blob：`807b928686a4dd2cac7b15b3c354b9943c93c910`
- Review Skill Blob：`d405c8d413d633824b279202cc1503dab4cf0b03`
- `TASKS.md` Blob：`1f08ee3a8e538d7ece4d2b2841c7c53e25737b7c`
- Agent 调用保障参考 Blob：`5c422316164e20a922ad0596233070716225be07`
- 已读当前 PRODUCT-01 Continuity Review 01 报告、M2-02 Deferred Gates，以及 North Star §0/2/3/6/8 和 AGENTS。历史报告只作定位，结论以本次源码和测试为准。

## 北极星与用户变化

本任务服务于同一 Session 的连续技术支持工作。现有正式 API/Worker/Assistant 可以执行本地 FixtureModel 路径和实验授权下的真实模型路径；但正式 `create_assistant_model` 在 Provider 开关开启而没有受支持的实验 ID 时仍拒绝构造模型。因此普通 Session 的真实 Provider 产品入口尚未成立。此次没有改变用户能力，只交付证据和一个可评审的最小方案。

## 源码结论

正常服务入口确实注入正式 Provider 工厂，Assistant Run 由正式 Worker 执行；`assistant_experiment_id` 可为空。然而生产 Provider 工厂把真实发送范围收敛到 `SUPPORTED_EXPERIMENT_IDS`。开关关闭时返回 `None`；开关打开但模型配置/授权不完整时拒绝；模型配置合法而实验 ID 为空或不受支持时仍拒绝。API Key 存在本身不能启用 Provider，这个安全属性必须保留。

### 实验专属职责

- 冻结实验 ID allowlist、执行 SHA/合同摘要绑定、一次性 Claim、实验数据库绑定、固定 Campaign 请求数/美元额度/价格版本及实验停止条件。
- `CLAIM_GUARDED_EXPERIMENT_IDS` 在传输边界消费一次性 claim；实验工具调用在 Campaign Ledger 另做持久预留。
- `PRODUCT-01-SLICE-02` 的一次性凭据、$2.00/24 请求配置和其预留参数是该历史实验合同的一部分。它们不能成为正常 Session 的永久启动条件或默认产品额度，也不能被本任务复用。

### 普通产品仍需的安全职责

- 用户/API 显式启用并绑定可信服务端 Provider Profile；仅有 Key 不构成授权。
- 服务端固定/审核模型及端点；Key 只从安全配置读取，不能由聊天或工具参数提供。
- 每个模型/MCP 调用出站前仍写入持久调用记录；Run、TaskBinding、Tenant、来源版本和撤权状态仍按现有 Domain 重验。
- 普通对话继续只获得适用的 Knowledge 与只读工具；没有合法 TaskBinding 时，业务读取工具不可调用；不开放 Approval、ActionIntent、Ledger、修复或交接权限。
- 付费运行需要跨 Session/Run 共用的显式费用池、保守发送前预留、Usage 结算、UNKNOWN 保留与禁止自动重试。

## 现有调用保证能做到什么

`assistant_calls` 对一个 Run 的 `MODEL`/`MCP` 调用使用 `BEGIN IMMEDIATE` 原子登记；唯一键为 Run/kind/logical key；同键请求摘要不同则拒绝；已成功的同请求返回已记录结果而不重新执行；失败/UNKNOWN 不能当成功缓存重放。普通 Run 默认最多 8 次模型调用和 6 次 MCP `tools/call`，计数跨同一 Run 持久化。Task 运行的模型调用还检查既有 Task 辅助预算，Task Run 有活动时间限制。

这些记录**不是**普通产品的全局费用账本：在 `experiment_id=None` 时，Assistant 会跳过 `reserve_dispatch`/`complete_dispatch`/`mark_unknown`；`assistant_calls.usage_json` 会存 Usage，但不按价格结算，也不在多个 Run/Session 间预留和累计美元成本。无 Task 的聊天也没有 Task 级时间预算。每次调用 30 秒超时、图 recursion limit 36 和单 Run 调用数只是资源边界，不能替代跨会话费用池。

## 实验账本当前承担的职责

现有 `assistant_experiment` 表及函数提供实验作用域预算配置一致性核验、模型/MCP 次数计数、发送前持久费用预留、逻辑调用幂等、成功 Usage 结算、价格版本和额度核验。UNKNOWN 保留预留并关闭该实验预算；UNKNOWN/无效 Usage/超限不会允许后续实验出站。两套职责可以复用同一账本逻辑，但其当前数据库 schema 将 scope 固定为已知实验 ID，不能直接安全地把普通产品 Profile 塞进实验 allowlist。

## 三种方案比较

| 方案 | 优点 | 风险与维护成本 | 结论 |
|---|---|---|---|
| A. 正常产品授权与实验身份分离，共用持久发送账本 | 一次性实验 Claim 与连续用户 Session 解耦；现有 `assistant_calls` 和 Campaign Ledger 的预留/结算/UNKNOWN 逻辑可复用；仍只有一个 Assistant/Worker | 需要最小持久 schema/账本 scope 适配，以及服务端 Profile 配置和 API/Worker 传递；必须保证预算池跨 Session 不重置 | **推荐** |
| B. 扩充实验 ID 承担普通运行 | 初始改动少，可复用部分 allowlist/账本 | 每类正常产品使用继续制造“实验 ID”、冻结 SHA、Claim、实验额度及回归特例；Run/Session 切换容易造成额度分池；正常用户体验被一次性实验生命周期绑住 | 不推荐 |
| C. 仅注入显式 Model Factory | 最容易做离线 API/Worker/MCP 证明，无网络兜底，现有 Fixture 测试已证明 | 不能让正式服务中的普通用户在授权下真实使用 Provider；调用者若注入真实工厂，也没有持久跨 Run 费用授权 | 只用于测试/本地演示 |

## 推荐的最小落地方案（本轮未实施）

1. 正常 Provider 运行以独立的服务端 `runtime_profile_id` 启用，不设置或伪造 `assistant_experiment_id`，不读、不写、不消费任何历史实验 Claim。
2. Profile 由明确的后续用户/主 Agent 付费授权创建，且记录授权人/来源、有效模型端点、费用池 ID、价格版本、每次最坏预留策略、总上限、有效期、状态和数据库归属；API Key 仍只保留在服务端秘密配置。
3. app 启动时仅在显式 `PROVIDER_ENABLED=1` 且 Profile 有效时把 Profile 引用传给 Worker/Model Factory；Profile 缺失、关闭、撤销、配置/价格不匹配、额度不足均在出站前 fail closed。仅存在 API Key 不变成授权。
4. 对既有实验 Ledger 做 scope 参数化的最小扩展（实验路径维持当前固定合同与行为），正常 Profile 作为另一种 scope 在同一原子预留/结算逻辑下建立一个跨 Session 的预算池；避免新增第二套账本。现有 `assistant_calls` 继续作为 Run 级幂等/来源证据，不能代替费用池。
5. 每个 Provider 请求在 Handler 前持久预留；有效 Usage 后结算；UNKNOWN 保留最大预留并停止该 Profile 费用池的后续发送，禁止自动和人工重试同一逻辑请求。明确拒绝是程序终态，不伪装成模型答案。模型仍可在现有合法只读工具和来源范围内自主选择调查、补查、回答或澄清。
6. 不制定本次新的美元上限、单次预留额、价格版本或持续时间；这些都需要下一轮单独授权。历史 `$2.00` 和 `$0.645600/$0.668468` 均不自动沿用。若无法建立可审计的每请求费用上界，普通真实 Provider 继续关闭。
7. 预计生产落点：`assistant_experiment.py`（同一 Ledger scope 化/小型迁移）、`assistant.py`（Profile 作为明确上下文、统一发送预留）、`web/app.py`、`web/worker.py`（传递 Profile 引用），以及少量正反测试。继续复用 `assistant_calls`、现有 Assistant Loop、TaskBinding 和 MCP；不改 `chat.py` 为另一套费用权威，不加通用 Provider Gateway/预算服务。维护成本是一次向后兼容的 Ledger 迁移和两个运行模式的独立测试，而不是持续扩充实验 ID。

## 六问自检

1. **用户变化：** 本轮没有新增产品能力；确定了当前产品真实 Provider 入口仍被实验范围阻断，并给出正常 Session 的最小解耦路径。
2. **Agent 决策：** 不改模型工具选择策略；未来产品 Profile 只控制能否付费运行与费用边界，不改变模型在授权只读范围内的自主性。
3. **观察驱动：** 离线测试覆盖空 Task 的普通说明、合法绑定后的只读 MCP、越域被拒后继续合法查询、撤权后停止；未运行 QUEUED/PROCESSED 新模型对照。
4. **约束双向检查：** 现有开关关闭及无效/重复实验授权拒绝；合法 Fixture API/Worker 与绑定读取成功。真实产品费用池正反行为仍需实施后测试，本轮未声称通过。
5. **责任归属和简化：** 保留单一 `assistant_calls` 与实验 Ledger 的持久发送保障作为基础；不把实验 Claim 变成普通产品权限，也不另建计费平台。本轮无生产 Diff。
6. **证据与停止线：** 18 项指定离线用例通过；Provider 真实 HTTP、浏览器、外部业务写入均为 0。没有费用授权和 Profile scope 实现，因此停止于方案审查，不启动真实调用。

## 测试与副作用统计

- `tests/test_ar02_runtime.py`、`tests/test_ar02_assistant.py`、`tests/test_ar02_ar03_integration_01.py`、`tests/test_product_01_live_scope.py`：11 项通过，包含参数化终态预算两个分支。
- `tests/test_ar02_smoke_provider_factory.py`：7 项通过。
- 合计：18/18，退出码 0；命令和原始输出见 `TEST_LOG.txt`。
- 19 个本轮 pytest 临时 SQLite/Checkpoint 文件只读聚合：`assistant_calls` 有 33 个模型 Fixture 完成记录、22 个 MCP OK 和 1 个 MCP 拒绝/失败记录。33 不是 Provider 请求数。
- Provider：真实 HTTP 0；HTTPX MockTransport 合成请求 2（不计为真实 Provider）。
- MCP：隔离本地测试共 23 次尝试（22 OK、1 越权拒绝）；无生产资源访问。
- Browser：0。
- 外部业务写入：0；11 个隔离 Domain 临时库合计 `d3_approvals=0`、`approval_resume_links=0`、`d3_action_permissions=0`、`d3_action_intents=0`、`d3_action_ledgers=0`、`s2_handoff_receipts=0`、`s3_handoff_receipts=0`。
- 未运行：全量 pytest、真实 DeepSeek、浏览器、真实用户 Provider Profile 端到端。

## 遗留限制与风险

- 真实 Provider 的普通产品入口仍未实现；此任务没有修改生产授权语义。
- 暂无经本轮授权的正常产品预算金额、发送前预留额、价格版本或 Profile 生命周期。
- 用户级 Provider 凭据/多供应商配置不在当前代码路径，本方案先指向明确授权的服务端 Profile；不得从自然语言接受任意 URL 或密钥。
- UNKNOWN 的 Profile 级停发策略需要在后续设计中明确恢复/人工核账流程；当前建议保持 fail closed，不自动释放或重试。
- 浏览器与真实模型行为未验证，当前证据只证明离线执行链、授权失败关闭、实验预留路径及来源/工具边界。

**停止线已到：** 现状、最小方案和离线证据已提交；不修改生产 Provider 授权语义，等待主 Agent 与 Astra 定向复审。
