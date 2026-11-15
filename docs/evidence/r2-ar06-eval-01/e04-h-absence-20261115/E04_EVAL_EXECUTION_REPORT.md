# E04-H 离线执行与首次 Live 准入记录

## 结果边界

本轮完成的是 **Fixture 离线接线验证**，不是 E04-H 真实模型成绩。冻结题面和原始 Gold 未修改；新增数据条件是后补的隔离缺失分支，状态为 `POST_FREEZE_FIXTURE_SPECIFIED`。因此本结果不属于完全未接触的预冻结留出实验，也不计为 E04-H PASS。

- Base：`9dd9bb1366bdeaf601f0023f66a443c9f8b6f38a`
- 冻结 CASES SHA256：`c1acd3fa789befa733aa96bf3a49b08357ff071f3b627b4c40319882e2805cf8`
- 冻结题面 SHA256：`8d68006c77971378ba75ff57af67ea4cb8b8c38fb4f23c3856333a77e988932a`
- 后补 Fixture Manifest SHA256：`5ea356cc2928d335aa5030bae083ffd899aa121843454a028532fb53b124b83f`
- 真实 Provider 请求：`0`；Grant：未创建；外部业务写入：`0`

原始 CASES、RUBRIC、EVAL_PROTOCOL 与 FROZEN_HASHES 保持不变。Manifest 明确记录了生成时间、Base、冻结文件摘要、原始文档摘要、逐字节内容、评测范围和限制。它没有声称在 Gold 冻结时已经存在。

## 隔离范围与实际材料

Runner 从冻结 CASES 逐字读取原题，通过 SUPPORT 正式 Assistant API 创建一个新 Session，不创建 TaskBinding。只向当前隔离 Runtime 写入运行时 `assistant-access.json`；没有改共享 `knowledge/assistant-access.json`。

- Tenant / Actor / Role：`tenant-a / support-a / SUPPORT`
- 运行时项目：`orders-e04-absence`
- 授权文档：仅 `callback-retry-contract`、`callback-retry-contract-v2`
- 检索 Schema 的 `configured_contract_version=2` 是已有 Registry 的合成检索默认值，不是部署版本或真实项目配置断言。
- v1 文档：版本 `1.0.0`；来源 `local:orders-async-demo/contract-v1`；SHA256 `a5974f46bf50e2bfcd63ed1e6528d473560854204d12a50dfb3f82b9e61bc0c3`
- v2 文档：版本 `2.0.0`；来源 `local:orders-async-demo/contract-v2`；SHA256 `9ad3f5a67a5f40da986769c66a78317027d3e57803371a0674d3b14fe412e238`
- v1.4 文档及用户提及的两份迁移说明：本隔离授权目录中没有注册/提供；缺失只适用于本 Fixture 的授权范围。用户对“两份说明冲突”的陈述保持未验证。

实际查询返回上述两个版本。比较工具报告 v1/v2 存在结构差异；原文工具返回 v2 的行 1 摘录及当前摘要。没有把资料版本说成线上版本。完整脱敏 API/Assistant/MCP Trace 见 [E04_FIXTURE_TRACE.json](E04_FIXTURE_TRACE.json)，Runner 结构化记录见 [E04_FIXTURE_RESULT.json](E04_FIXTURE_RESULT.json)。

## 执行记录

- Runtime：`user-demo-r2-e04-h-absence-20261115-01`（新建并保留）
- Session：`session-3d71a55b-bfa3-4f1b-83a1-6e23dc03baae`
- Run：`run-fd6ee466-1176-4d42-a6ab-0e05e79766fe`
- Run 状态：`SUCCEEDED`；Fixture Runner 的独立语义评分：`UNVERIFIED`
- 调用：3 个 MCP 工具（文档列表、v1/v2 比较、v2 原文摘录），Fixture Model 共 4 次派发
- Observation / Domain Evidence / TaskBinding：均为 0
- Provider Spend / Send Grant / UNKNOWN：均为 0
- Fixture Token 元数据：输入 118、输出 81、合计 199；不是 Provider Usage 或真实费用
- 运行时间：约 2.1 秒
- Trace SHA256：`7354e0ba526e18515c829f31a659640a064584f98689a4d57602f8366b23c432`
- 脱敏器标记 API Key、Cookie、Authorization、配置密码和 Bearer 类秘密均已移除。

Fixture Model 的 `compare_available` 路径完成列表、比较、原文；独立测试中的 `request_missing_materials` 路径只查目录后结束，未强制比较或穷尽工具。两条路径用于检查合法接线选择和停机边界，均不证明真实模型具备相同判断能力，也不作为评分样本。

## 定向反向验证

同一回归运行包含 E03 与 E04，共 **14 项通过**：

- E03 原有正式 API / Knowledge / 比较 / 撤权 / 摘要失配 / 路径边界回归：6 项通过。
- E04 正式 API 两条工具决策路径、冻结输入、Manifest 篡改拒绝、租户及 Runtime 隔离、未授权文档（含 v1.4 ID）拒绝、撤权和 Digest 失效：8 项通过。
- 测试日志及失败重试说明见 [E04_TEST_LOG.txt](E04_TEST_LOG.txt)。

测试证明：未授权文档比较会失败关闭；不同 Tenant 的 Scope 为空；其他 Runtime 不获得 E04 项目授权；项目撤权或持久 MCP 来源 Digest 被篡改后，旧来源无法继续作为当前来源展示；用户输入没有创建 TaskBinding、Observation 或 Evidence。

## 首次 Live 准入判断

评测隔离、冻结输入读取、来源校验和离线正式 Assistant 链路已具备候选证据，可交由主 Agent 独立验收。只有独立验收通过并获得新的单例费用授权后，才可以使用一个新的空 Runtime 进行首次 DeepSeek Live。建议上限 USD 0.06 仅为预算建议，不是本轮授权。执行时仍须按官方当前费率核验本地配置、每请求 Token 上限和八次派发的最坏预留；Preflight 不通过时停止，不降低费率。

E04-H 真实模型首次成绩仍是 `NOT_RUN`；本轮的 Fixture 结果不能替代它。
