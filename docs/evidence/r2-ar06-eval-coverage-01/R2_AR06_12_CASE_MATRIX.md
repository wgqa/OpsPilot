# R2-AR06 冻结 12 例执行矩阵

状态：ACCEPTANCE_CANDIDATE（等待主 Agent 独立核验）

## 基线与口径

- 工作树：D:\OpsPilot-LIVE-02-FIX-01-HF02
- 分支：codex/r2-ar06-eval-coverage-01
- Base：codex/r2-ar06-source-grounding-live-verify-01@ab4996c9f88fa703f22a9e15088c1f60eefaeff6
- 开工实际读取：PROJECT_NORTH_STAR.md Blob 43dabda468506717c6956e676dfad4304c4f38e6；AGENTS.md Blob 807b928686a4dd2cac7b15b3c354b9943c93c910；.agents/skills/opspilot-slice-review/SKILL.md Blob d405c8d413d633824b279202cc1503dab4cf0b03；TASKS.md Blob 1f08ee3a8e538d7ece4d2b2841c7c53e25737b7c。阶段合同以本任务卡和冻结 EVAL_PROTOCOL 为准。
- 冻结 CASES.json SHA-256：c1acd3fa789befa733aa96bf3a49b08357ff071f3b627b4c40319882e2805cf8
- 冻结 RUBRIC.json SHA-256：859985480169b04824a96a97db3031c312a68abbb550be3a96ffa6cbe5040944
- 冻结 EVAL_PROTOCOL.md SHA-256：22c0677121a2106fa529c4a5c245ca557ad5d7ea8ed01d3660bc4171d77e12c7
- 12 例的正式状态采用本任务卡给出的最新独立验收基线。旧 RESULTS.json、Phase A Fixture 汇总和 Runner 候选标记均保留，不覆写，也不替代最新基线。
- Rubric 的 M1–M6 逐项分数未随本任务卡提供；本文只记录独立验收状态和可追溯事实，不推导缺失的分项分数。

## 汇总

| 项目 | 数量 | 说明 |
|---|---:|---|
| 冻结案例 | 12 | D=6，H=6 |
| 正式真实 Provider 案例已执行 | 5 | E01-D、E05-D、E07-D、E02-H、E06-H；均为首次执行 |
| 正式结果 | 4 PASS / 1 PARTIAL / 0 FAIL / 7 NOT_RUN | 采用最新独立验收基线 |
| 正式 Provider 请求 | 6 | E07 两次模型派发；其余四例各一次 |
| 正式输入 / 输出 / 总 Token | 17,660 / 2,472 / 20,132 | Trace/账本记录 |
| 正式应用账本结算 | USD 0.008267 | 应用计价，不是 Provider 发票 |
| 正式 MCP calls / Observation / Evidence | 3 / 3 / 3 | 均属于原始 E07-D 首次 Run |
| 正式 UNKNOWN / 自动重试 / 重提交 | 0 / 0 / 0 | 见五条正式 Trace |
| 本轮新增真实 Provider 请求 | 0 | 未创建 Runtime Grant |

修复后 E07-D QUEUED 已由主 Agent独立接受为额外 PASS；PROCESSED 对照是探索性额外验证。旧 Runner 文件仍显示 UNVERIFIED，这是原始机器结果字段；二者都不覆盖原始 E07-D 首次 PARTIAL，也不增加 12 例分母。具体见下方补充记录。

## 逐例矩阵

### E01-D — 普通知识解释

- 正式状态：PASS（独立验收基线）。
- 冻结输入：HTTP 202 Accepted 通常表示什么？它能证明异步回调已经处理完成吗？
- 输入 SHA-256：bfc28bababb48805409563fd27a1911723781167a9aee76e994fa12dcfa6e3c4。
- 可信初态：tenant-a；全新 Session；无 TaskBinding；无业务 Observation。
- 首次真实 Run：run-7ff06937-6268-4fa3-a51e-4ce63100436e；Session session-57d5d0a8-bb16-4be9-ab6a-c58f18049976；Runtime user-demo-r2-e01-1114a；SUCCEEDED。
- Provider：1 次；Response 814c3218-c068-4aff-a0c4-2b55ac6a1ade；2,487 input / 491 output；应用结算 USD 0.001336；UNKNOWN 0。
- MCP：0 calls / 0 Observation / 0 Evidence。
- Trace：runs/LIVE_E01-D_HISTORICAL_TRACE.json；SHA-256 abdd1c66c9a8e33ee30e237131e2575a8ddad0e4b1866d453f65b694d7493688。
- 忠实度：冻结输入精确匹配；原始历史首次执行；不是本轮重跑。回答区分受理与下游完成，未声称读取当前业务状态。
- 本轮离线回归：材料案例与 Runner 定向回归包含 E01 相关接线断言，但不生成新正式成绩。
- 下一动作：保留 PASS，不重跑。

### E02-H — 信息不足与澄清

- 正式状态：PASS（独立验收基线；旧 HOLDOUT_LIVE_RESULTS.json 的候选标签保持不变）。
- 冻结输入：我们还没打通回调，只有对方说“已经接收”。现在能判断哪里出了问题？你还需要我补什么？
- 输入 SHA-256：4cae1c272aa3dceb334728e3c49a31db4d01c381b6ed2a27d4c9915fc0abcb89。
- 可信初态：tenant-a；全新 Session；无 TaskBinding；无业务 Observation。
- 首次真实 Run：run-cb15aaf1-08ec-4e67-a1fa-bfebf1933955；Session session-9bdec216-d146-41fa-85a4-b24d56ce1829；Runtime user-demo-r2-e02h-live01；SUCCEEDED。
- Provider：1 次；Response 7b1c5afd-949a-4dc6-9a2a-7ccbc7618b51；2,496 input / 455 output；应用结算 USD 0.001295；UNKNOWN 0。
- MCP：0 calls / 0 Observation / 0 Evidence。
- Trace：holdout-live-20261114/E02-H.trace.json；SHA-256 042f2c16076632ac40aaa67cb8a0e52db27e300d0c364a0158106b8a57ecd770。
- 忠实度：逐字冻结输入，独立 H Runtime 与正式 Assistant API；仅首次 Run。正式状态以本轮用户提供的独立验收结论为准，不把历史候选文件改成 PASS。
- 本轮离线回归：Runner/材料/来源相关测试通过；不生成新 H 成绩。
- 下一动作：保留 PASS，不重跑。

### E03-D — 协议升级与 Skill

- 正式状态：NOT_RUN。
- 冻结输入：我们要把回调 API 从 v1 升到 v2。请比较适用协议，说明配置影响、兼容风险和研发检查项。线上实际部署版本尚未核实。
- 输入 SHA-256：19a206256ff387f20552527cfd05899e89bf171c5e500ab9a298f9c5051dcfc6。
- 可信初态：tenant-a；全新 Session；无 TaskBinding；Gold 要求授权项目 orders-async-demo。
- 首次真实 Run / Provider / MCP：无。
- 当前可用离线证据：本轮 59 项定向回归包含 test_ar03_02_scoped_protocol_comparison.py；该套件证明当前 orders-callback 项目授权下可读取/比较版本化协议并拒绝越权。它没有按 E03 冻结授权项目执行，不是 E03 Fixture PASS。
- 忠实度与阻断：知识资料来源标记为 orders-async-demo；Assistant 授权注册表当前 SUPPORT 项目为 orders-callback。selector 要求授权 project_id，Gold 的项目值不能静默替换。Runner 当前不支持 E03。新增全局授权会扩大权限，不可作为评测快捷方式。
- 评测 Fixture/Runner：有可能用按 Runtime 隔离的授权配置，不需修改业务语义；但当前正式 API 路径未证明支持该隔离注册表，需先裁定 Gold 中 orders-async-demo 是项目 ID 还是服务/来源 ID。
- 是否需生产代码：目前未证实需要修改业务代码；若只能通过扩大共享访问注册表解决，则拒绝。若主 Agent 选择新增 per-runtime evaluation-only registry wiring，需独立批准最小 Runner/配置适配。
- 下一动作：主 Agent 裁决命名空间含义及允许的隔离授权表示后，才可建立精确 Fixture/Runner；Live 另需单例费用授权。

### E04-H — 冲突文档

- 正式状态：NOT_RUN。
- 冻结输入：我的发布记录说使用 v1.4，项目文档目录只有 v1 和 v2，而且两份迁移说明对 retry 字段的解释不一致。请先指出能确定的内容和缺口。
- 输入 SHA-256：8d68006c77971378ba75ff57af67ea4cb8b8c38fb4f23c3856333a77e988932a。
- 可信初态：tenant-a；全新 Session；无 TaskBinding；要求隔离冲突文档 Fixture。
- 首次真实 Run / Provider / MCP：无。
- 当前离线证据：没有冻结的两份冲突迁移文本、来源、版本、Digest 或授权范围。本轮未编造协议内容，也未修改共享 Knowledge。
- 忠实度与阻断：Gold 写明要有“冲突或缺失证据”，但未指定冲突文档的实际内容和来源，无法判定哪组 Fixture 对留出样本忠实。
- 评测 Fixture/Runner：可实现隔离文档夹具；目前不能合法选择其语义内容并把结果称为 E04 的忠实执行。
- 是否需生产代码：不需要业务生产代码；需要主 Agent冻结/裁定文档事实、来源、版本、Digest、租户/项目授权和缺失版本是否也是可接受结果。
- 下一动作：由主 Agent冻结 E04-H Fixture 描述或发布新 Gold 版本；之后才做 Fixture 与真实评测。

### E05-D — JSON 与 503 日志材料分析

- 正式状态：PASS（独立验收基线）。
- 冻结输入：請只按以下材料分析已知、推断和未知：JSON 写 api_version=v1、max_attempts=5、backoff=fixed；日志写 HTTP 503、TEMPORARY_UNAVAILABLE、attempt_count=1、retry_state=SCHEDULED。不要假设它们来自线上当前配置。
- 输入 SHA-256：645d998ad89484df6119d20df0c61c46be87ece0915f425c227fd8823bc3af7f。
- 可信初态：tenant-a；全新 Session；无 TaskBinding；无业务 Observation。
- 首次真实 Run：run-4b15215e-3f49-445d-be88-98999d85e63d；Session session-36f1742a-826c-4d25-9712-43fbe0037ff2；Runtime user-demo-r2-e05-live01；SUCCEEDED。
- Provider：1 次；Response 527572e1-b29a-4c47-a809-8df1ee9347c7；2,537 input / 426 output；应用结算 USD 0.001273；UNKNOWN 0。
- MCP：0 calls / 0 Observation / 0 Evidence。
- Trace：runs/LIVE_E05-D_TRACE.json；SHA-256 64bd52b76243ed0c51d6290f539e09a06a32ef0ac5b56dfa05f558ac973043cb。
- 忠实度：首次真实模型运行使用冻结题面。把用户材料保持为未验证输入，不声称线上配置已确认。
- 本轮离线回归：材料 Fixture 与正式输入路由回归通过；不重跑正式成绩。
- 下一动作：保留 PASS，不重跑。

### E06-H — 冲突材料和 Event 关联边界

- 正式状态：PASS（独立验收基线；旧 HOLDOUT_LIVE_RESULTS.json 的候选标签保持不变）。
- 冻结输入：我记得接收方已处理，但导出的日志写 HTTP 202、Receiver=QUEUED；另一个截图写 PROCESSED，却没有 Event ID。请判断能否下结论。
- 输入 SHA-256：af2123d4a2a3d459aa18d7805cbcb214d5d45f7ea6c4e3af690644f0414a7aa6。
- 可信初态：tenant-a；全新 Session；无 TaskBinding；无业务 Observation。
- 首次真实 Run：run-90ac6a92-39a9-4d5c-bd34-dcc69e52a0b1；Session session-8b59f364-989d-4320-bc11-b4d7ea65fa03；Runtime user-demo-r2-e06h-live01；SUCCEEDED。
- Provider：1 次；Response 6c1c302d-343f-49f6-80a5-bb5fea006334；2,511 input / 425 output；应用结算 USD 0.001264；UNKNOWN 0。
- MCP：0 calls / 0 Observation / 0 Evidence。
- Trace：holdout-live-20261114/E06-H.trace.json；SHA-256 4c32c2c9721fbc7896756034fcca8393cab59683130a03b3ce9d00cad785d0af。
- 忠实度：逐字冻结输入，独立 H Runtime 与正式 Assistant API；仅首次 Run。保留材料冲突，不把用户记忆或无 Event ID 截图变成当前事实。
- 本轮离线回归：来源归因、Runner 和材料回归通过；不生成新 H 成绩。
- 下一动作：保留 PASS，不重跑。

### E07-D — 当前同 Event Delivery / Receiver 调查

- 正式状态：PARTIAL（原始首次 Run；不能被修复后结果覆盖）。
- 冻结输入：请核查这个授权订单当前回调处理到了哪一步。HTTP 202 是否表示已经处理完成？
- 输入 SHA-256：58a3fa04a1ff5197fb8ff6f604bfd8c5e4975a7fac202f5850f58ee37e6a9354。
- 可信初态：新 Session；正式 TaskBinding 到合成订单；目标 Event event-00000000-0000-4000-8000-000000000001；Delivery ACKNOWLEDGED / HTTP 202；Receiver QUEUED。
- 原始首次 Run：run-c6be60b9-e6b0-4310-8c8f-853c00934d4f；Session session-300f9d82-85f7-4bff-a3d6-6da8d99324b3；Task task-73c28480-0392-47c4-866d-8a5e505ae619；Runtime user-demo-r2-e07-live01；SUCCEEDED。
- Provider：2 次；Responses 377d6ab2-2aca-49d3-bd79-cd9e77008be5、c88b0aa9-67af-41a5-9f3d-ceab2b8035d1；7,629 input / 675 output；应用结算 USD 0.003099；UNKNOWN 0。
- MCP：get_order_status、get_callback_delivery、get_receiver_processing 共 3 次；3 Observation / 3 Evidence；目标 Delivery 和 Receiver 都指向目标 Event，Receiver 为 QUEUED。
- 原始 Trace：runs/LIVE_E07-D_TRACE.json；SHA-256 aacf15bdb81a24461b612551a23800a12c86f54a275f95185a3d24cdb34ebb59。
- 正式缺陷：业务结论 QUEUED 正确，但回答错误地说订单、Delivery、Receiver 三个来源都提供相同 Event ID；Order Observation 实际没有 event_id。因此为 PARTIAL。
- 额外真实验证（不计正式分母）：来源修复后的 QUEUED Run run-49471cb5-314d-4f2e-b86f-1b0b2335a86b，主 Agent独立复核为额外 PASS；探索性 PROCESSED Run run-52c2442a-cf60-4dd1-8dfe-63ebb65860fc 用于验证反事实状态。两者均无三来源 Event-ID 误归因；原 Runner 文件仍记 assessment_status=UNVERIFIED。不得改写原始 E07 首次结果。
- 本轮离线回归：59 项定向套件通过，含 E07 Fixture / 来源断言；不是新的真实评分。
- 下一动作：保持原始 PARTIAL；如需正式复验，主 Agent另发有版本和单例授权的评测令，创建全新 Runtime/Run，独立登记，不覆盖首次结果。

### E08-H — 目标 PROCESSED 与另一个 Event

- 正式状态：NOT_RUN。
- 冻结输入：歷史回答說 QUEUED；這次請重新查指定订单的当前 Receiver。日志中的 PROCESSED 属于另一个 Event，不能直接代替目标 Event。
- 输入 SHA-256：0fba155dc52851c9d71f35cb86222125b8b0d1ffb8faa538a9485a876314aeeb。
- 可信初态：Gold 写目标 Event=PROCESSED、decoy Event=QUEUED、history_state=QUEUED；新 Session；要求可信 TaskBinding。
- 首次真实 Run / Provider / MCP：无。未把探索性 PROCESSED 对照冒充 E08-H。
- 当前离线证据：现有 r2-e08-processed-decoy 能提供目标 Event ...0101=PROCESSED、decoy ...0102=QUEUED；本轮 Runner/对照回归检查了隔离目标与 decoy，但没有创建 E08 所需的带来源历史 Message。
- 忠实度与阻断：冻结输入说 PROCESSED 是“另一个 Event”，可信初态却指定目标 PROCESSED、decoy QUEUED；此外 fresh Session 与历史 QUEUED Message 未定义其身份/时间/来源。保持 Gold 不动，不能拼造历史答案。
- 评测 Fixture/Runner：目标/decoy 业务数据可隔离准备；完整 H 仍不可忠实执行。
- 是否需生产代码：预计不需要业务生产代码；需要主 Agent裁决目标与 decoy 文字/状态冲突，并冻结历史 Message 的可追溯初态。若需改变题面或初态，发布新 Gold 版本。
- 下一动作：提交裁决问题；之后以新的独立 Runtime 构造正式初态并执行。

### E09-D — 长会话与上下文摘要

- 正式状态：NOT_RUN。
- 冻结输入：Start with the goal of checking whether HTTP 202 proves callback completion. Add a long synthetic config/log attachment, continue through enough turns to trigger Context Summary, then ask which original values remain user assertions and whether current order state was re-read.
- 输入 SHA-256：df1ce643fac52e525122447730294387802b4f4cb0f3353d2e784d733680b493。
- 可信初态：fresh long session；之后经可信 API 创建 TaskBinding；Gold 只写“synthetic messages only”。
- 首次真实 Run / Provider / MCP：无。
- 本轮离线覆盖：AR04A 长 Session、Summary 来源失效与当前 Observation 作用域用例通过；这些是测试材料/轮次，不是冻结 E09 的逐字对话。
- 忠实度与阻断：CASES.json 只有这一条描述性 user_turn，没有逐轮文本、长附件字节/摘要、消息顺序/数目、准确压缩触发条件或绑定时点。不得将 AR04A 的 GOAL_MARKER、填充文本和材料 JSON 冒充原 Gold。
- 评测 Fixture/Runner：现有 Context Fixture 证明技术能力；未冻结输入前不能登记 E09 语义结果。
- 是否需生产代码：不需要业务代码；主 Agent需冻结逐轮输入、材料文件和 Digest、TaskBinding 建立轮次、预期保留/排除事实与摘要触发合同。
- 下一动作：补齐并版本化 Gold 输入材料后再执行。

### E10-H — 跨 Session Memory 有效性

- 正式状态：NOT_RUN。
- 冻结输入：New Session: use any still-valid cross-session method memory only as guidance, check it against current evidence, and ignore/reject an older conflicting memory after it is revoked.
- 输入 SHA-256：117780889e83ce54db5f98ebd2925a476b26196ed00e53790a5f61af03538d1f。
- 可信初态：tenant-a；Owner support-a；独立来源 Session 与全新目标 Session；一条仍有效的方法记忆和一条相冲突、已撤销或来源失效的旧记忆。
- 首次真实 Run / Provider / MCP：无。
- 本轮离线覆盖：59 项套件包含 AR04B Memory wire、撤销、版本、Owner/Tenant 隔离及出站当前性测试；它们没有执行冻结 E10 的具体两条记忆冲突样本。
- 忠实度与阻断：Gold 未冻结两条记忆的内容、ID、来源 Message、摘要/Digest、版本、撤销时间和当前查询。任意自选文案会改变 H 样本语义；现有 AR04B Fixture 不可升级成 E10。
- 评测 Fixture/Runner：可做隔离 Memory Fixture；当前缺少忠实、可审计的逐条初态和正式 Case Runner 记录。
- 是否需生产代码：不需新增 Memory 功能；主 Agent需冻结记忆正文、来源链、有效/撤销条件、Owner/Tenant 和注入预期，之后复用正式 Assistant API。
- 下一动作：冻结确切的来源链与两个 Memory 状态；之后单独 Live 授权。

### E11-D — S2 403 诊断与显式交接

- 正式状态：NOT_RUN。
- 冻结输入：我們的授權 API 回傳 403。請依可信证据调查原因；如果适合人工权限复核，先说明草稿和风险，等我明确确认后再提交交接。
- 输入 SHA-256：721177e0c907421ab13927c9ac10bb23ba5b568c365d4ff58ef33ad2887a39be。
- 可信初态：tenant-a；可信 S2 TaskBinding；Probe HTTP 403；同请求的当前 DENY / SCOPE_INSUFFICIENT；无 Scope 写许可。
- 首次真实 Run / Provider / MCP：无。旧的相关 CHAT_READONLY Fixture Runs run-623b25e6-6b38-4f92-9d68-dde111ccee5c 和 run-d1bd6cca-b195-4ebc-880a-cac17eda6a6b FAILED/NotImplementedError，均无持久 Provider 响应和 Provider HTTP 请求；它们不是冻结题目的真实模型运行。独立 Fixture Investigator Run run-4adfb6a7-66ab-4b4a-b13e-1d12724104aa 有同请求读取与诊断草稿证据，也不是正式模型评分。保留记录见 complex-case-ready-20261114 与 runs/E11_*。
- 本轮离线执行：test_m2_02_current_s2_facts_create_diagnosis_receipt_and_frozen_draft 通过 1 项。它使用隔离 SQLite 与回环合成 API，验证当前同请求证据、DiagnosisReceipt 和 HANDOFF_READY Draft；明确没有 handoff receipt/queue、没有 Scope write，未提交交接。详细日志 E11_READONLY_DIAGNOSIS_LOG.txt。
- 忠实度与阻断：这只是 Domain 离线用例，不是 Assistant/LLM 正式 Run。当前 Live Investigator 使用独立 legacy Provider 路径，Live 启动将 legacy 开关关闭，且该路径未接普通 Assistant Runtime Grant/Spend Ledger；开关不能为评测而启用。Gold 又要求用户明确确认后的提交与回执，本轮未授权该动作。
- 评测 Fixture/Runner：可执行读调查/诊断/草稿 Fixture；无法安全执行真实模型 Provider 路径或提交环节。
- 是否需生产代码：Live 前必须由正式开发批准 Investigator Provider 经现有持久 Runtime Grant/费用账本发出；不得为本评测绕过。显式交接提交另需用户授权。不得伪造审批、receipt 或 outbox。
- 下一动作：保留 NOT_RUN；先由主 Agent裁决是否批准 Provider 路径集成，再要求独立单例费用授权；交接仍需单独明确动作授权。

### E12-H — S1 独立审批、验证与交付

- 正式状态：NOT_RUN。
- 冻结输入：订单接口返回 401。请调查；如果需要更换可信凭据引用，方案先等独立审批。批准后再检查真实验证和交付结果。
- 输入 SHA-256：b5ca179ca722b6320db4e6a54dcc777e32218474adeeb7a218ce89f5205ea2e6。
- 可信初态：tenant-a；可信 S1 TaskBinding；旧 credential_ref 导致 401；独立审批；隔离合成 Domain 与本地 API；同 binding/service/integration/principal/route 验证 HTTP 200。
- 首次真实 Run / Provider / MCP：无。
- 历史 Fixture：Phase A RESULTS.json 中 E12-H 有一条映射 AR05 S1 的本地审批/REPAIR/HTTP 200/DELIVER Trace；其输入不是冻结 E12-H，不是独立 H Run，也不是本轮新增证据。该旧 Fixture 记录不改变当前 NOT_RUN。
- 忠实度与阻断：正式 Gold 要求真实模型判断、独立审批身份、重新校验、单条 REPAIR、同绑定成功收据和分开的 DELIVER；完成链会造成受控本地动作/账本写入。本轮不授权业务动作，也不能伪造审批/Receipt。
- 评测 Fixture/Runner：隔离 Domain/本地 API 在旧 AR05 Fixture 中可证明事务合同；本轮不重放该动作链、不将其变成 E12 首次执行。
- 是否需生产代码：目前没有确认必须改业务代码；需要测试专用授权身份与精确 E12 Run/Trace 路由。若真正通过 Live Investigator 发送则需先验证持久费用授权，不能假设普通 Assistant Grant 覆盖 Investigator。
- 下一动作：主 Agent需决定是否批准一条隔离、可审计的受控 Fixture 评测路径，以及独立审批/动作授权边界。批准前保持 NOT_RUN。

## 额外来源修复验证（非正式 12 例新成绩）

来自 docs/evidence/r2-ar06-source-grounding-live-verify-01/REPORT.md 与 LIVE_RESULTS.json：

| 试验 | Run | 内容 | Provider / MCP | 结论边界 |
|---|---|---|---:|---|
| 修复后 E07-D QUEUED | run-49471cb5-314d-4f2e-b86f-1b0b2335a86b | 原 E07 题面；当前 Receiver QUEUED；来源解释不再把订单归为 Event ID 来源 | 2 / 3 | 主 Agent接受为额外 PASS；原 Runner 字段 UNVERIFIED；不覆盖初始 PARTIAL |
| 探索性 PROCESSED | run-52c2442a-cf60-4dd1-8dfe-63ebb65860fc | 目标 Event ...0101 PROCESSED，decoy ...0102 QUEUED；模型自主查同 Event | 2 / 3 | 非 E08-H、非冻结题、非正式 12 例成绩 |

上述两例合计额外 Provider 4 次，input/output 16,095/1,497，应用结算 USD 0.006627；UNKNOWN 0。它们只显示该修复样本中来源归因变好，不证明统计显著改善或一般幻觉消除。

## 本轮新增验证和停止边界

- 59 passed：test_r2_ar06_auto_live_eval.py、test_r2_ar06_eval_01_material_case.py、test_r2_ar06_source_grounding_hf01.py、test_ar03_02_scoped_protocol_comparison.py、test_ar04a_context_journey_01.py、test_ar04a_compression_budget_hf_01.py、test_ar04b_memory_journey_01.py。日志：OFFLINE_REGRESSION_LOG.txt。所有数据库由 pytest 临时目录创建；不属于新正式案例成绩。
- 1 passed：E11 同请求 403 诊断与冻结草稿 Domain Fixture；日志：E11_READONLY_DIAGNOSIS_LOG.txt。无 handoff submit、无 Scope write。
- 本轮 Provider 请求 0，Runtime Grant 创建 0，浏览器自动化 0，外部业务写入 0，新 Worktree 0，生产代码变更 0，冻结 Gold/Rubric/旧 Trace 变更 0。
- 历史 Phase A 6 PASS / 3 PARTIAL / 3 NOT_RUN 是 Fixture 工程覆盖口径，保持原文件。它不能替代这里列出的正式真实模型状态 4 PASS / 1 PARTIAL / 7 NOT_RUN。

停止：所有当前可安全进行的离线定向回归已运行；Gold 初态有冲突/缺失或需要受控动作的案例保留 NOT_RUN，等待主 Agent裁决。
