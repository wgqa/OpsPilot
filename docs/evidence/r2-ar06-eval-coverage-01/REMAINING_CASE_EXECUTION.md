# R2-AR06 剩余七例：执行条件与裁决点

状态：ACCEPTANCE_CANDIDATE。本文不修改正式 12 例成绩、Gold、Rubric 或旧 Trace。

## 当前结论

E03-D、E04-H、E08-H、E09-D、E10-H、E11-D、E12-H 均按本任务卡最新独立验收基线保留 NOT_RUN。已存在的 Fixture、映射测试和历史其他工作包 Trace 可证明部分技术路径，但不能代替冻结输入、正式真实模型首次运行或独立评分。

本轮所有可安全运行的相关离线回归已执行：59 passed；另有 1 项 E11 同请求 403 → DiagnosisReceipt → HANDOFF_READY Draft 的只读业务诊断 Fixture passed。没有一次新增 Provider 请求，也没有创建 Grant、浏览器自动化、交接提交、S1 动作或外部业务写入。

## 分案例执行条件

### E03-D — 协议升级 / Skill

**当前：NOT_RUN；未满足正式 Live 条件。**

- 冻结项目字段是 orders-async-demo。资料目录/协议来源使用这一 service/source 名；当前 SUPPORT Assistant 授权注册表却授权 orders-callback 项目，并以 project ID 控制资料范围。当前 Runner 不支持 E03-D。
- 本轮运行的 scoped protocol 回归确认 orders-callback 下能读取并对比受授权版本，且越权/跨租户失败关闭；它没有按 Gold 的 orders-async-demo 初态执行。
- 评测侧可选办法：主 Agent确认字段语义后，若其只是 service/source alias，可在独立 Runtime 内注入仅限该 Runtime、该 SUPPORT 身份和指定文档 digest 的测试授权。必须通过正式 Assistant API/Knowledge 路径验证，不能修改共享生产注册表，也不能静默替换项目 ID。
- 业务生产代码修改：目前无证据证明必须修改业务代码；但当前 Runner/registry 没有证明隔离授权能穿过正式路径。未经裁决不得实现或扩大共享权限。
- 下一步：由主 Agent回答“orders-async-demo 是授权项目还是服务/来源别名？”并批准隔离授权表示。通过后单独准备精确输入、新 Runtime/Session；Provider Live 还需单例费用授权。

### E04-H — 冲突文档

**当前：NOT_RUN；冻结输入不足以建忠实冲突样本。**

- Gold 只说明发布记录为 v1.4、目录有 v1/v2、两份迁移说明对 retry 字段有不同解释，没有提供两份文本、来源、版本、Digest 或授权范围。
- 构造任意两段冲突内容会人为决定模型要处理的事实，改变留出样本。不能因为 Fixture 能运行就声称符合 E04。
- 评测专用隔离 Knowledge Fixture 足够，不需生产功能；但主 Agent必须先冻结确切冲突文档、缺失版本的表现方式、来源与权限。若“文档不存在”本身就是目标，Gold 应明确允许此结果。
- 下一步：主 Agent发布 E04-H Fixture manifest 或新版本 Gold，然后跑 Fixture 路由，再决定 Live。

### E08-H — 当前 PROCESSED 与另一 Event

**当前：NOT_RUN；Gold 内有事实方向冲突。**

- 冻结题面称日志中的 PROCESSED 属于“另一个 Event”，初态却规定 target=PROCESSED、decoy=QUEUED。这会让日志中的 PROCESSED 与目标/decoy 的指代相反。
- 初态同时标记 fresh session 和 history_state=QUEUED，但未提供历史 Message ID、来源、时间、原 Run 或事件身份。当前 r2-e08-processed-decoy Profile 可准备目标 Event ...0101=PROCESSED、decoy ...0102=QUEUED；它没有可追溯的历史 Message。
- 本轮自动 Runner/源归因回归覆盖隔离目标与 decoy 的 Observation 对照，但没有执行 E08 的逐字题面与历史初态。之前 PROCESSED 探索 Run 复用了 E07-D 问题，且明确不算 E08-H。
- 不需生产代码；需要主 Agent裁决目标/decoy 与题面语义，并冻结历史记录的来源/身份。必要时发布新 Gold 版本。之后用单独 Runtime/Session 做一次 H 首次执行。

### E09-D — 长对话、材料与 Summary

**当前：NOT_RUN；逐轮评测输入未冻结。**

- CASES.json 中只有一条描述性指令，没有实际长配置/日志内容、附件 bytes/Digest、每轮输入和顺序、Summary 触发点、TaskBinding 建立轮次。
- AR04A 回归证明长会话可保留目标/材料、无效摘要不会进入模型、当前事实保持 Run scoped；测试用 GOAL_MARKER、MATERIAL_JSON 和填充文本，不是 E09 的冻结输入。
- 不需要生产代码；主 Agent需冻结材料和 Digest、逐轮消息、轮数/触发前置、绑定时序及要核查的原始用户声明。之后 Runner 复用现有正式 API 和 Summary 路径。

### E10-H — 跨 Session Memory

**当前：NOT_RUN；需要冻结记忆来源对。**

- Gold 指定一条有效方法记忆和一条冲突且被撤销或来源失效的旧记忆，但没有冻结正文、Memory ID、源 Message、Digest、版本/有效期、撤销时点或目标问题。
- 本轮 AR04B 测试覆盖已选记忆进入真实 Fixture Provider 输入、Owner/Tenant 隔离、摘要/Checkpoint 当前性和撤销时出站阻断；它没有使用 E10 的具体两条 Memory pair。
- 不需要新增 Memory 功能；主 Agent需批准并冻结双记录的正文/来源/生命周期、来源 Session、target Session 与问题。测试前要验证有效条目可读、旧条目不可读，随后一次性进行 H 执行。

### E11-D — S2 403 与显式交接

**当前：NOT_RUN；真实 Provider 路径不能用普通 Runtime Grant 约束。**

- 本轮离线测试通过：tests/test_m2_02_s2_diagnosis.py::test_m2_02_current_s2_facts_create_diagnosis_receipt_and_frozen_draft。隔离库和 localhost 合成 API 证明同请求 Probe=403 与 DENY/SCOPE_INSUFFICIENT 可创建 DiagnosisReceipt 与不可变 HANDOFF_READY 草稿；断言 Scope write=0、没有 handoff queue/receipt、未提交。它不是 Assistant/LLM Run。
- 历史 E11 Assistant Fixture 的 NotImplementedError 来源是 Fixture Model 未实现 bind_tools；历史 Fixture Investigator 的同请求 Probe/Authz 读路径另有记录。不能将这些 Fixture 记录升级为正式模型得分。
- 当前 Live Investigator 仍使用 legacy Provider；Live 启动关闭 legacy 开关。其 dispatch 没有持久 Runtime Grant/Spend Ledger 预留与结算，8 次调用/512 token 上限不是费用池。不得开启 legacy 开关或给该路径创建普通 Grant。
- 完整 Gold 要求用户显式提交后验证 Receipt/outbox。该动作本轮未授权；不能自动提交或制造回执。
- 必须新增业务代码才能 Live：需单独正式评审把 Investigator Provider 发送纳入持久 Grant/Spend 合同。还需单例 Live Provider 费用批准；交接提交需要独立明确动作授权。

### E12-H — S1 审批、REPAIR、验证与 DELIVER

**当前：NOT_RUN；需要动作授权与真实独立审批边界。**

- Gold 需要可信 TaskBinding、旧 credential_ref 401、独立 approver、重新校验、唯一 REPAIR ledger、同 binding/service/integration/principal/route HTTP 200 VerificationReceipt，再分开的 DELIVER。
- Phase A 有 AR05 S1 的本地 Fixture/Trace，但用户题面不同，不是独立 H；不能把它新登记为正式 Run。完整链会改变隔离 Domain 中的凭据引用并产生审批/REPAIR/DELIVER 记录。本轮明确不授权受控业务写入，也不伪造审批或回执，所以没有重跑。
- 业务实现可能不必改变；但需要主 Agent明确是否允许一次仅本地合成 Domain 的 action-bearing 评测、测试 approver/executor 身份、固定本地 API route、动作/回执保存目录及清理保留合同。真实 Provider 若使用 Investigator 路径，还须先审查其费用授权适配。
- 获批后每例新 Runtime、新 Session、新 Grant；原历史 DB/Trace 不得复用。审批/动作授权和 Provider 费用授权应分别给出。

## 主 Agent 必须裁决的问题

1. E03：orders-async-demo 在 Gold 中究竟是项目授权 ID，还是仅是 service/source 名？是否批准仅对隔离 Runtime 生效的测试授权映射？
2. E04：哪两份版本化迁移材料构成冲突？其真实来源、内容、Digest、授权边界是什么？“v1.4 不存在”是否为正确结果之一？
3. E08：目标应是 PROCESSED 还是 QUEUED？“另一个 Event”指目标还是 decoy？fresh session 如何同时具有历史 QUEUED？应使用哪个可信历史 Message/Run/source/time？
4. E09：具体附件内容与 Digest、每轮冻结输入/顺序、总结触发轮、TaskBinding 时点是什么？
5. E10：两条 Memory 的确切正文/IDs/source Message/Digest/version/expiry/revoke 状态及目标查询是什么？
6. E11：是否单独批准 Investigator 接入持久 Runtime Grant/Spend Ledger 的产品开发？之后是否批准一次 Live Run 的费用，以及另一次显式交接提交？
7. E12：是否允许只在隔离本地 Domain 运行审批/REPAIR/HTTP 验证/DELIVER 链？哪些可信测试身份能代表独立 approver/executor？如何保留该动作轨迹？

## 下一批候选与费用估算

当前没有一个未运行案例同时满足“忠实冻结初态、正式路径已接通、已有费用批准”三项条件。优先顺序建议如下；这不是当前授权或执行承诺。

1. **E03-D**：最接近可运行；先裁决项目/服务命名空间并形成 Runtime-local 授权，不改共享权限。每次最多 1 个首次 Run，建议单例 Grant 上限 USD 0.06。若运行期 Preflight 无法证明隔离、费率或预算足够，停止。
2. **E08-H**：在主 Agent解决目标/decoy 方向和历史消息来源后运行。每个独立 Runtime 单次建议上限 USD 0.06；不得把现有探索 Run 或 E07 的初态作正式 E08 首次结果。
3. **E09-D / E10-H**：各自先冻结输入或来源对，再安排单例运行；每个单独 Grant，预算按执行前官方费率与 Runner reserve 重新核算，建议按不高于 USD 0.06/例准备。
4. **E04-H**：等待冲突材料合同。E11/E12 暂缓 Live：E11 先需要单独安全开发评审；E12 先需要受控动作评测批准。

### 预算计算边界

- 本地 Runner 当前合同：每 Run 最多 8 次 Assistant Provider dispatch；每请求按最多 12,000 input 与 2,048 output tokens 做预算预留。源码：scripts/user-demo/runtime_admin.py 的 MAX_INPUT_TOKENS / MAX_OUTPUT_TOKENS；scripts/user-demo/run_r2_ar06_case.py 的八次 worst-case reserve 检查。
- 本轮核对的 DeepSeek 官方价格页显示 deepseek-flash Peak cache-miss input USD 0.30/百万 token、output USD 1.32/百万 token；off-peak 对应 USD 0.15 / USD 0.60。来源：[DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)（价格可能变化，Live 前需重新核对）。
- Peak 最坏单请求预留约 USD 0.006304；八次约 USD 0.050432。故历史上常见的 USD 0.05 Grant 在该价格下可能低于八次完整预留，建议每案例 USD 0.06 作为候选预算并保留 Runtime Grant 原有 8-call hard cap；最终以当时真实 Preflight 和本地费率配置为准。
- 本轮没有读取 .env、没有读取或更改任何 Runtime Grant，没有配置费率或创建预算池。USD 0.06 是给主 Agent评估的计划值，不是授权。

## 证据位置

- 冻结输入和已有历史运行：docs/evidence/r2-ar06-eval-01/CASES.json、LIVE_RESULTS.json、holdout-live-20261114/HOLDOUT_LIVE_RESULTS.json、runs/ 与 holdout-live-20261114/。
- E03/E11 既有阻断分析：docs/evidence/r2-ar06-eval-01/complex-case-ready-20261114/COMPLEX_CASE_READY.md。
- E08 初态限制：docs/evidence/r2-ar06-eval-01/HOLDOUT_READY.md。
- E11 本轮离线诊断日志：E11_READONLY_DIAGNOSIS_LOG.txt。
- 59 项受影响离线回归日志：OFFLINE_REGRESSION_LOG.txt。
