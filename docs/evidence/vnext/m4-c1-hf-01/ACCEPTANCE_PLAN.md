# M4-C1-HF-01 验收冻结

**状态：** 冻结后进入 RED；实现门仅在 RED 材料提交后开放
**仓库 / 分支：** `wgqa/OpsPilot` / `codex/m4-autonomy-c1`
**本轮基线：** `b398e59dba03a25ef1e5f04aa197c4e918b0529f`
**远端 main：** `77ea80e87e538f0f1fae8118ef231ec622601755`
**目标：** 跨轮只读补查能够续接真实答案与来源；分类完成前不重复运行 Chat sidecar。

## 开工核验

- 本地 HEAD、候选远端均为 `b398e59dba03a25ef1e5f04aa197c4e918b0529f`；工作分支为 `codex/m4-autonomy-c1`。
- `PROJECT_NORTH_STAR.md` 从本轮基线读取，Blob `1f737712c7a36ceb34433ac09c3fbba3c3305542`；第 8 节完整读取。
- `AGENTS.md` 从本轮基线读取，Blob `30319000ed0054007e9b7b6b46bf98b1493c8179`。
- `.agents/skills/opspilot-slice-review/SKILL.md` 在基线中不存在；不声称已读取。
- 适用冻结合同：`docs/evidence/vnext/m4-autonomy-c1/FROZEN_PLAN.md`、`REV1-ACCEPTANCE-ADDENDUM.md`、`REV1-REPORT.md`、`docs/evidence/vnext/m4-autonomy-c1-acceptance-fix-01/ACCEPTANCE_PLAN.md` 与 `REPORT.md`。原 C1 Gold、RED、E2E-02/E2E-03 失败、真实 E2E/Provider/MCP 记录保持不变。
- 基线至 HEAD 无本轮新增合并；分支历史中已有先前 C1 集成提交。已有未提交 Knowledge/Skill 修改和 REV1 临时产物不属于本切片，保持未暂存。
- 当前实现已证实的缺口：分类器只接收先前用户消息；普通 Chat 的 Prompt 只接收普通助手消息，未装配 `c1_readonly_followup_runs` 的持久回答；消息受理后 Chat Run 已可被 Worker 领取，分类器尚未完成时会触发被 UI 隐藏的 Provider 调用。

## 冻结行为与权限矩阵

| 输入/条件 | 模型可见上下文 | 允许执行 | 必须禁止 |
|---|---|---|---|
| 同租户、同 Session、同 Task、较早且成功的只读补查 | 持久答案、来源 Message/Run、结果摘要、来源类型与重新校验状态 | Agent 可解释有效协议来源；可按新目标选择当前绑定内调查 | 将旧 Run Evidence 当成本轮 Observation |
| 引用的 Knowledge 被替换、过期或不再适用 | 仍可识别“之前引用过什么”，明确标记历史/失效 | 查询当前合法版本或交付缺口 | 将失效版本放入当前有效 Knowledge/Evidence |
| 用户询问现在的业务状态 | 历史结果仅作线索；当前 Run 的 Evidence 单独提供 | 预算内调用当前绑定只读工具，或解释预算/信息缺口 | 继承旧 Run Evidence 充当当前事实 |
| 不同 Task/租户、其他 Session 或当前 S3 授权失效 | 不装配受限历史答案；记录可审计排除原因 | 在当前有效授权恢复后按正常入口重新取证 | 越域泄露历史回答或使用旧结果获得当前资格 |
| 分类器选择 INVESTIGATE | 历史结果进入 Investigator 的非权威上下文 | 只创建/执行该消息对应的只读 Investigator Run | 对该消息调用 Chat Provider 或提交业务 Diagnosis/写动作 |
| 分类器选择 EXPLAIN、假设或普通问答 | 有效的历史上下文进入 Chat Prompt | 只执行一个 Chat 回答 Run | 先行隐藏一个 Chat Provider 调用后再执行第二条回答链 |
| 分类器失败/延迟/Worker 重启 | 持久 Run 与路由状态可恢复；失效原因可见 | 有界重试；最终由同一消息的 Chat Run 安全降级或保留可重试状态 | 永久留在不可领取队列，或在迟到分类后重复执行两条链 |
| 正式关键纠错 | 原有确认流程与当前 TaskControl 版本 | 取消提议后允许原消息普通回答；确认后仅执行已受理的新纠错 Run | 分类前执行 Chat sidecar，或绕过确认修改 Task |

## 冻结验收用例

1. **HF-01 有效来源续接：** 已完成的 `ANSWERED` 补查（含 `receiver-ack-contract-v2` 的真实 ID/版本/digest）先持久化；下一条代词追问进入分类器和实际回答/Investigator Prompt。Context Manifest/Investigator Provenance 必须包含该答案与来源。有效材料足够时允许不再检索。
2. **HF-02 Knowledge 失效：** 将测试副本中的来源文档替换、过期或取消适用版本。历史答案可作为历史提示出现，但旧版本标为失效且不进入当前 Knowledge；模型可以查当前合法版本或给出缺口。
3. **HF-03 新业务事实：** 新 Run 用户问“接收方现在完成了吗”。Prompt 可含历史答案，但当前 MCP Evidence/Observation 只能来自新 Run。至少一条集成测试核对 Task/Run/Attempt/Observation 关联；真实演示记录实际模型选择与 MCP Trace。
4. **HF-04 隔离与授权：** 同 Task/同 Session/同租户且当前授权有效的正例可续接；同 Session 不同 Task、不同租户/Session、授权撤销/异常版本的反例不得带入受限答案。必须断言合法正例未被误拒。
5. **HF-05 重复 Chat 消除：** task-bound Chat Run 在分类路由完成前不可领取。INVESTIGATE 路径只产生 Investigator 回答链、零 Chat Answer/Compression Provider Attempt；EXPLAIN 路径在分类之后只产生一个 Chat 回答。假设/纠错确认与取消按冻结矩阵工作。分类失败可有界重试，失败后必须有可见且可恢复的结果；超时/无分类记录不能永久挂起。记录 Attempt 数与 Token，对照 REV1 E2E-04 隐藏 sidecar 的 3,709 tokens。
6. **HF-06 持续性：** 页面刷新、Worker 重启、相同 Message/Idempotency-Key 重放和重复 assessment 均保留原 Answer/来源关联；不重复消费预算、不创建重复 Investigator Run、不改变 TaskControl 或正式 Diagnosis。

## RED / GREEN 与真实验收次序

1. 将本文件先独立提交；随后新增定向测试并在当前实现运行 RED，原样保留日志和退出码，再提交 RED 证据。
2. RED 至少证明：分类器 Prompt 不含上一轮持久只读回答/来源；Chat/Investigator 后续 Prompt 不含历史补查；同一消息的 Chat Run 可在分类前被 Worker 领取并调用 Provider；跨 Task/过期版本/授权失效边界。
3. 仅修改既有来源装配与 Run 路由/调度职责，复用 `investigation_context.py`、TaskControl、Knowledge 版本校验、现有 Worker 与 Chat/Investigator；不增加通用历史平台、Goal 或 Runtime。
4. 先新鲜运行 HF-01～06 定向 RED/GREEN、C1/HF/S3/TaskControl 回归，再全量 pytest 与前端 typecheck/build。
5. 使用真实 Web、Provider、MCP 和本地 HTTP 运行连续旅程，保存实际输入、模型选择、Knowledge ID/version/digest、MCP Request/Observation、Run 与答案来源、Provider 请求及 Token。确定性替身只证明 Domain/Worker 契约，不计作真实模型证据。另保留失败尝试，不更改历史 Gold、E2E 与报告。

## 停止线与六个自问

1. **用户变化：** 用户可以说“刚才引用的那份协议”，后续追问能接续实际已持久化的回答；当前业务状态仍需当前 Run 取证。
2. **Agent 决策：** 分类器和回答模型利用历史来源判断解释还是调查；TaskBinding、Scope、预算、Run 输入及当前事实由可信程序控制。
3. **观察驱动：** 当前版本适用的协议足以解释时可直接回答；来源失效时查当前版本；询问“现在是否处理完”时必须选择当前合法取证或明确缺口。
4. **新增约束：** 分类之前不能执行 Chat Provider，以防隐藏重复费用及双重回答；普通解释、假设、纠错取消和 Taskless Chat 必须仍可生成单一回答，并覆盖失败/延迟/重启恢复。
5. **简化结果：** 优先共享一个历史结果与来源装配函数，不分别复制三套过滤器；沿用既有 Follow-up 记录和路由 assessment，不建新平台。
6. **证据与停止线：** 以 HF-01～06、真实浏览器/Provider/MCP/HTTP 轨迹和完整回归验收；所有未实际运行能力标 `NOT_RUN`，最终只提交 `ACCEPTANCE_CANDIDATE`，不合并、不启动 C2。
