# OpsPilot vNext · Luna M1-01 实施任务卡
## Task Control 原子裁决 + 持久消息/命令受理的可信基础

> **状态：待 Luna 执行。本文件是首张实施任务卡，不是已实现或已验收的证明。**
>
> **基准仓库：** `wgqa/OpsPilot`，冻结起点 `main@a53e13a4243cc6c7fa545b3e3a92b838596b6242`（开工必须检查 HEAD，发现不一致先报告差异，不得盲目覆盖）。Windows 项目目录：`D:\学习\agent新项目`。
>
> **设计输入：** 用户已认可的 vNext 路线 B 与《OpsPilot vNext v0.3 开发合同_N1最终补正_待启动.md》，其 **附录 B 对 N1 具有最高解释优先级**；N2–N5 使用上一轮第三方认可的附录 A / 正文；原 `docs/baseline/v1.0-implementation-baseline.md` 的 S1/F1–F3 保持不变。
>
> **审查事实：** 第三方对 v0.2 的最后结论为 `REVISE_AND_REVIEW`，唯一未闭合的是 N1：Task 终止/关键纠错与新 Plan、修复动作提交之间的权威事务竞争。主 Agent 已在 v0.3 附录 B 提出补正，**该补正尚非第三方签字通过，也未编码**。用户要求停止昂贵的反复全文评审，转由明确的工程用例验证设计。不可把它写成“G0 已获第三方 APPROVE”。
>
> **本轮工作方式：** Luna 根据本卡在现有 `main` 开发、真实运行测试、记录事实、Commit/Push；不另起通用 Runtime、不开无关 PR/Issue。主 Agent 对代码和运行证据进行阶段验收。**完成 M1-01 即停，不自行扩展到 M1-02/03。**

---

## 0. 唯一目标、为什么必须先做

把目前仍可在无 Task 终止控制下推进的 S1 调查/Plan/REPAIR/DELIVER，适配到即将到来的浏览器 Session/Command/Run 交互中，并在 **同一 Domain SQLite 事务**内确立以下规则：

1. **无 Plan 时终止 Task 也能生效**；旧模型响应、旧 Graph checkpoint 或重启不能再激活新 Plan/审批或产生受限业务动作。
2. **关键纠错受理当刻就产生阻断**；旧 Run 不能在未消费更正时冻结 Plan、利用旧审批 REPAIR 或追加 DELIVER。更正应用后必须使用新的受信调查与新授权判定。
3. **COMMITTED 历史不可抹除**；REPAIR 若在终止/纠错前已提交，仍能在授权后回查原 Ledger/真实配置；后续未提交的 DELIVER 被阻断，不能假装撤回修复。
4. **新消息/命令/Queued Run 的接收不丢不重**；同一受理事务内落地，并用 request key + canonical digest 保证断线重试不会重建第二条任务。
5. **旧基线不退化**：现有 S1、D2/D3/D4、D5 Skill/Memory、D6/D7 的安全事实和 64 项旧 pytest 回归不得被破坏；旧的 `plan_hash`、ActionIntent/key/digest 和已提交回执不得偷偷重算。

本轮是 **M1 的执行安全基础切片**，**不是**完成前端或完整对话。本轮不得声称“已支持真正多轮聊天”。浏览器和完整 SSE 在 M1-02/M1-03；但本轮的持久记录须可供它们直接复用，而不是临时测试桩。

### 必须保持的老行为

- 模型真实 Function Calling → stdio MCP 只读查询 → deterministic Evidence Gate → immutable Plan → 可信 HITL → 持久 Intent → REPAIR CAS → 真实 HTTP 验证 → Report/DELIVER。
- 人工审批不能由聊天文字或模型自授；`cancel_plan` 默认仍只有原可信 SUPPORT 提交者可执行，不因 APPROVER 角色而自动有权取消。
- 修复与交付两个独立许可；ActionIntent/ActionLedger 是副作用的权威，Graph checkpoint 只保存续点。
- `ACTION_OUTCOME_UNKNOWN` 不能通过重试盲写掩盖。
- 当前仍是本地双租户/预置信任身份的有限 Demo，不宣称生产 IAM 或分布式 exactly-once。

---

## 1. 开工先读源码和约束（务必先取真实 HEAD）

先只读检查并列出函数签名/调用者/数据库事务范围；下列路径为当前基线实际存在的入口：

| 入口 | 要定位的责任与缺口 |
|---|---|
| `opspilot/domain/database.py` | SQLite schema、`connect()`、`initialize()`、`reset_fixture()`；新 schema 迁移不能破坏历史数据或凭证隔离 |
| `opspilot/domain/d2.py` | `create_task_binding()`、`get_task_binding()`、`authorize_thread_resume()`；Task 创建时初始化权威控制记录 |
| `opspilot/domain/d3.py` | `create_plan_from_gate()`、`_activate_plan_in_transaction()`、`activate_plan()`、`submit_plan_approval()`、`get_or_create_action_intent()`、`execute_repair()`、`execute_deliver()`、`cancel_plan()`；核心 Domain 同事务守卫 |
| `opspilot/investigator.py` | `run_investigation()`、`build_investigation_graph()`，特别是 `intake`、创建 Plan、审批 interrupt、resume 以及 stale checkpoint 的处理 |
| `tests/test_d3_actions.py`、`tests/test_d4_recovery.py` | 既有 F1–F3、取消/替换与提交竞态、进程崩溃后回查；新增 N1 不能替换旧断言 |
| `docs/baseline/v1.0-implementation-baseline.md`、D7 `CODE_READING_MAP.md` | 保留安全契约和真实运行边界，不从旧设计中的 `NOT IMPLEMENTED` 标题推断现在没有代码 |

开工记录：当前 `HEAD`/working tree、实际 Python/pytest 版本、现有 baseline 和有无未提交更改；任何环境上的阻断直接报告，不得删除用户本地数据、`.env` 或历史证据。

---

## 2. WP-A：权威数据结构、兼容迁移和受理原子性

### A1. 最小 Domain schema

在**现有 Domain SQLite 文件中**新增可事务化的结构，字段命名可以按仓库风格微调，但语义不能改变：

- `task_controls`：`tenant_id, task_id, terminal_state (ACTIVE|ABORTED), control_revision, pending_critical_message_seq, applied_critical_message_seq, changed_at/by, reason`，`task_id` 主键且 tenant FK/绑定校验；版本只增不减。
- 关联新计划的控制元数据：以独立关系/列绑定 `bound_control_revision`、已消费的关键消息高水位、Task 身份；**不得修改已冻结 Plan canonical 内容或默默改变历史 hash**。
- 最小 `sessions` / `messages` / `commands` / `task_runs`：具备 tenant + owner + message sequence + task/command/run 关系；完整用户体验和读 API 后续任务实现。本轮必须足以进行**同事务持久受理**，不能只存内存对象。
- 最小 `domain_outbox` / 受理事件记录：关键控制命令与其事件和控制修改同事务提交，持有稳定 `source_kind/source_id/event_kind` 去重约束。完整 Event projector 与 SSE 留给 M1-02；本轮不建另一个动作事实库。
- 需要有唯一键/索引限制重复 Command、同 Task 控制行、同 Session 递增 message_seq；并写明 SQLite 并发事务先后次序。不要仅靠前端禁用按钮或进程内 mutex。

**事务要求：** 关键消息受理（含 `CORRECT_TASK_INPUT`）需将 `Message + Command + task_runs(QUEUED) + acceptance/outbox event + task_controls 更新/Plan 失效` 在一次 `BEGIN IMMEDIATE` 内提交。普通只读消息可不改变 `task_controls`，但消息、Command、Run、受理事件仍必须原子落地。`202 Accepted` 只有真实事务提交后才成立。

**幂等要求：** `(tenant_id, authenticated_actor_id, command_kind, target_ref, idempotency_key)` + canonical request digest 是唯一受理标识：同 key 同摘要返回**同一** message/command/run；同 key 不同摘要返回明确冲突而不创建第二份。客户端可传 key/目标资源，但**不可自报并获得 actor、tenant、role**；本轮内部 API 应显式接收服务端已验证的可信身份对象，FastAPI 认证集成留给 M1-02。

### A2. 数据迁移与原命令兼容

- schema 迁移必须幂等，可对原 D7 本地数据的**拷贝**升级；不能直接修改旧冻结 SQLite 样本和 D6/D7 证据。重跑迁移不重复插入/重置修复事实。
- 新建 Task 在可信 `create_task_binding` 原事务中初始化 `task_controls(ACTIVE, revision=0)`；旧 Task 可迁移为 ACTIVE/revision0 **仅当能证明没有待处理的新控制请求**。不能把未知历史计划/Run 偷偷绑定到“最新 revision”以使旧执行合法；无法确定时安全阻断并解释。
- 既有 CLI/测试路径若需要兼容适配，不得开一个对所有调用者开放的 `expected_revision=None` / `ignore_task_control=True` 后门。可以使用内部**经验证的 legacy revision0** 路径，要求 Task 仍 ACTIVE、无 pending 关键消息、control_revision==0，并且必须检查真实权限；一旦 Task revision 增加，旧入口就不能绕过。
- 已提交 ActionIntent、Ledger、已有 Plan 的 canonical hash/digest 与业务配置版本保持原样；不强行把 control_revision 塞进既有 canonical request 再批量改测试预期。

交付 schema/migration 说明和最小兼容测试。记录若需要调现有 Python 入口签名，应把所有真实调用点一起更新并跑完整回归。

---

## 3. WP-B：Task abort 和关键纠错的原子控制命令

### B1. `abort_task`（Task 级终止，不是 `cancel_plan`）

- 只有该 Task 当前可信 SUPPORT owner 可发起（除非原合同另有经批准角色范围）；验证 tenant/task 归属。受理与效果、Command 幂等、Outbox 必须与 Domain control 同事务。
- **即使完全没有 Plan**，也将 `terminal_state` 设置为 `ABORTED` 并提高 `control_revision`；有 ACTIVE Plan 时同事务取消其可执行资格，阻断未提交 REPAIR/DELIVER，未来未消费 permission 需按既有语义失效或后续 guard 确保不可消费。
- 若业务 Task 已完整终结，明确 `TASK_ALREADY_TERMINAL` 而不是用 ABORTED 覆盖旧 COMPLETE；若已经 REPAIR COMMITTED 但 DELIVER 尚未提交，允许终止**后续工作**，保留已发生的修复历史与 Ledger。
- 重复命令相同 key/摘要只能返回原结果，不能反复增长版本；已经终止后另一请求按明确的任务终态契约处理并保留审计。
- `stop_answer`、`pause_investigation`、`cancel_plan`、`abort_task` 四种语义明确不同；本卡实现 `abort_task` 和必要的现有 Plan 取消连接，其余 UI 控件留给后续，不能用 `abort_task` 冒充暂停。

### B2. `CORRECT_TASK_INPUT`（关键更正）

- 明确的更正消息在原子受理事务里 `control_revision += 1`，登记 `pending_critical_message_seq`，使任何当前 ACTIVE Plan 不再有可执行资格；旧审批不应自动变成新 Plan 的批准。
- 允许多个更正排队且消息顺序不丢。只有受信新 Run 根据**实际完整有效输入及当前 Evidence** 消费相关消息后，才能在事务中记录 `applied_critical_message_seq`、清除 pending、增加新控制版本；不能直接从模型回答中把用户线索升格成受信事实。
- 更换 tenant、service、integration 等可信绑定对象需要新 Task；不能把一条聊天更正用作越权更改绑定的依据。
- 普通 `CHAT_READONLY` 不改变控制版本；对无法可信分清是否会改变处置目标、资源或审批依据的**未分类自由文本**，必须 fail-closed 为待分类关键输入或转入澄清，不能让旧修复先执行，再以“模型认为只是闲聊”为由放行。
- 明确 `RECEIVED_NOT_APPLIED` / `APPLIED_TO_RUN` 状态，由持久事实驱动。下一卡真正显示；不能只做一个布尔标志但没有可回查的 Message/Run 关联。

---

## 4. WP-C：在业务 Domain **提交事务内**阻断过时 Run/Plan

核心要求：**旧 Run 的 `expected_control_revision` 与 `consumed_message_seq` 在启动时锁定，旧 Plan/Intent 绑定其可信版本；不能在提交前读取当前 revision 然后冒充期望版本。**

在下列**确切真实入口**增加 Domain 内部守卫，使用同一个连接上的 `BEGIN IMMEDIATE`，在任何新资格/许可/意图/业务写入之前检查：

`task_controls.terminal_state == ACTIVE && pending_critical_message_seq IS NULL && expected_control_revision == task_controls.control_revision && bound_control_revision == current_revision && authorized_scope_matches`

此外，应校验用于构建 Plan 的已消费关键消息序号与高水位、Gate 当前事实和对应的可信 Task 绑定。

**强制覆盖：**

1. `create_plan_from_gate` 的首次落库、`_activate_plan_in_transaction()`（包括查到已 ACTIVE 想直接 return 的路径）、`activate_plan`。
2. `submit_plan_approval()` 与独立 REPAIR/DELIVER permission 的首次授予。
3. `get_or_create_action_intent()` 的首次登记。
4. `execute_repair()` 和 `execute_deliver()` **未提交动作的最终 COMMIT 路径**，包括恢复、Graph 重放、不同进程/两个连接竞争。
5. Graph `run_investigation()` 入口 / intake / 计划恢复前作尽早检查，避免已 ABORTED 继续浪费调用；**这些提前检查不能替代第 1–4 项的事务守卫**。

任何失败必须给出适当错误码：`TASK_ABORTED` / `TASK_INPUT_PENDING` / `TASK_CONTROL_STALE` 等，事务内受限业务新副作用应为零。相同 Request ID 的合法**历史已提交 Ledger 回查**在当前可信读取资格、key/digest、租户与 Task 匹配时依然允许；不能因 Task 已 ABORTED 就否认曾经 COMMITTED，更不能让跨租户使用他人的 Action ID 查回执。

**必须区分的提交先后顺序：**

- `abort/correct COMMIT` 在前 → 后到旧 Run 的新 Plan、Approval、REPAIR/DELIVER **拒绝**。
- `REPAIR COMMIT` 在前 → 后到 abort/correct **保留**原配置变更和 Ledger，阻断**未来**未提交 DELIVER，报告显示已修复未交付或等待核对，绝不假装回滚。
- 已成功 DELIVER/任务完成后，后到的 abort 必须按 Task 终态规则处理，不将完成成功事实覆盖成取消。

允许为了实现该规则在 `d3.py` 做**针对性的安全适配**，但不允许重写整个 D3 Graph、另建动作调度引擎，或把最终授权搬到模型 Prompt / FastAPI Middleware 里。

---

## 5. WP-D：强制故障与权限回归（本卡真实通过才算完成）

### D1. 三个不可删减的验收子例

| ID | 强制故障窗口 | 最终必须检查的权威事实 |
|---|---|---|
| **N1-09** | 无 Plan 的 Agent 已发送模型/MCP 请求，先用可信身份执行 `abort_task` COMMIT，然后旧响应回来或另 OS 进程恢复旧 checkpoint | 控制表 ABORTED；0 新 ACTIVE Plan、0 新 approval、0 新 ActionIntent/Ledger、0 新受限业务写入；读取历史审计仍允许 |
| **N1-10** | 老 READY/Plan 已获批，但旧 Run 尚未 REPAIR；关键纠错消息原子受理先 COMMIT，强制旧 Run 继续创建/激活/执行，再由新 Run 消费纠错 | 旧版返回 `TASK_INPUT_PENDING/TASK_CONTROL_STALE`；配置没有被旧修复修改；新的可信 Evidence/Plan/审批流程才可能合法执行 |
| **N1-11** | 同库 REPAIR 事务先 COMMIT，随后可信 `abort_task`，强制让旧 checkpoint 恢复并试图 DELIVER | 原 REPAIR Ledger/配置版本保留；新 DELIVER 0、工单条目 0；不得在 UI/投影谎称已回滚或已交付 |

至少 **N1-09 或 N1-11 有真实两个 OS 子进程**（不是只用 `pytest.raises` 或同进程假异常）。其他关键提交先后竞争使用独立 sqlite connections + 同步 barrier/failpoint，证明事务确实发生在目标窗口。

### D2. 同一受理事务/身份与幂等

- `N1-01` 消息与队列受理同事务：故障注入事务中断，绝无已提交 Message 却无 Command/Queued Run 的孤儿。
- `N1-02` 事务已提交但 HTTP/调用者尚未收到受理确认：相同 request key 重新提交得到原 3 个 ID、版本只增一次；相同 key 不同正文/命令摘要明确冲突。
- `N1-05` 两个独立线程/连接争用同一 Task 的业务执行权，至多一个拥有有效推进资格；worker 进程互斥将在 M1-02 连接，不可声称本卡已经完成跨进程工作队列管理。
- `N1-06/07` 关键输入高水位、审批后撤销、控制命令与角色隔离；SUPPORT/APPROVER、tenant-a/tenant-b 的真实 SQL 拒绝；同 key 不可把 owner 变成其他用户。
- 保证新的 App Domain 数据迁移重跑和旧 Task 的只读历史回查；未能安全迁移的旧执行必须 BLOCKED 而不是偷偷更新 control revision。

### D3. 不可退化的已有回归

执行并保留真实日志：

```powershell
cd "D:\学习\agent新项目"
New-Item -ItemType Directory -Path .runtime -Force | Out-Null
.\.venv\Scripts\python.exe -m pytest -q -s --basetemp=.runtime/m101-pytest-full
.\.venv\Scripts\python.exe -m compileall -q opspilot tests
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

原 D7 记录 64/64 是**历史数字**；本卡需汇报**本次新鲜全量**的实际通过/失败数量，不得自动照抄 64/64。新增测试可另建 `tests/test_m1_task_control.py`、`tests/test_m1_command_admission.py`、`tests/m1_crash_worker.py` 等最小集合，避免为了测试再做大规模框架。

有可用的本地模型凭据时，本卡至少复用一次实际 S1 全链路回归作为变更核验；如果真实模型不可用，需记录 `NOT_RUN` 和原因，不能把模拟工具或历史 D7 结果冒充新鲜真实模型通过。正式完整 Web/模型验收在 M1-06，不能提前宣布。

---

## 6. 本卡明确不做（防止开发漂移）

- **不做 Vue 页面、完整 FastAPI/SSE、聊天 UI、模型长上下文压缩、多层 Memory 效果、S2 403、Knowledge、第二 Skill、Multi-Agent、Sandbox、独立 AI Gateway、Redis/分布式锁。** 后续任务会按路线表实施。不要因为本卡没有 UI 就推断最终产品不做前端。
- 不改写/删除原 `docs/evidence/d6`、`d7` 中的失败、Gold、数据和证据；历史 E10 `PARTIAL` 不能洗白。
- 不接受单纯在页面/API/Graph 入口检查 Task 终止；必须在 Domain Plan/Approval/Intent/REPAIR/DELIVER 的**提交事务里**检查。
- 不接受“只建 `task_controls` 表但没有真实控制、数据库竞态测试”；不接受“只靠 `Plan CANCELLED` 支撑无 Plan 终止”；不接受“旧 Run 临时读取最新 revision 再继续修复”。
- 不接受重新造 Agent Runtime 或修改已审批业务权限语义来让测试通过。

---

## 7. 交付目录、运行证据、白皮书学习卡

**最少交付：**

1. 真实代码及 DB migration（设计与 schema SQL，迁移重放测试）；提交的新 Python/测试路径与具体函数一览。
2. `docs/evidence/vnext/m1-01/REPORT.md`：版本/commit、问题与最小修改、各 N1 case 真实命令、PASS/FAIL/NOT_RUN、因果证据、数据库回执、故障窗口、失败与局限。
3. `docs/evidence/vnext/m1-01/RESULTS.json` 与关键的脱敏原始 pytest/子进程日志（PID、退出码、action/ledger、state/control revision、实际副作用次数）；不能输出 API key、凭证实体值、Authorization。
4. `docs/baseline/vNext-product-baseline.md` 的**R0 已核验基线**或 `docs/baseline/vNext-product-baseline-candidate.md`（如果仍有待用户确认的设计决策，必须标 candidate，不虚称第三方签字）；以及最小 `STATE_TRANSITIONS.md`、`API_CONTRACT.md`、`ACCESS_MATRIX.md`、`EVENT_RECOVERY.md`、`MEMORY_LINEAGE.md`、`S2_OUTCOMES.md`、`EVAL_CASES.md` 文档**可先冻结跨阶段契约和边界，不实现 M2/M3 功能**。文档不可替代任何代码测试。
5. `docs/learning/HANDBOOK_MAP.md` 增量，以及 `docs/learning/M1-01/STUDY_NOTES.md`（≥3 个关键设计点）和 `INTERVIEW_QA.md`（≥5 组，含 30 秒/2 分钟回答、源码和实际证据索引）。重点对照《AI Agent Handbook》第 4–6 章的 Task/状态权威、交互/持久化、受控 Action：**引用的章是方法参考，本项目的具体事务方案是实现决策，不要冒充白皮书唯一规定**。
6. `README` 或 `TASKS` 简短状态更新：M1-01 的本轮真实结论；明确 M1-02 起点与尚未实现的前端对话能力。

**不在 Git 仓库中提交** `.env`、真实 Token、`.runtime` SQLite、临时备份、第三方审核的未脱敏资料或规模失控的原始日志。证据目录优先保存摘要、脱敏记录和确定性复现命令。

---

## 8. 停止条件、PASS 标准和向主 Agent 回报

M1-01 **只有**满足下面所有条件才可标 `PASS`：

- N1-09/10/11 新鲜验证且至少一个真实双 OS 进程故障窗口通过。
- 受理幂等/同事务、Task abort/更正待处理、Plan/审批/Intent/REPAIR/DELIVER 的最终同库事务守卫都由真实实现和测试证明。
- 已提交历史 Ledger 仍可按原可信身份和摘要回查；跨租户/伪造身份不能绕过控制；旧 F1–F3、安全回归无红线失败。
- 全量 pytest 与静态/依赖检查真实运行；迁移前后旧业务和数据安全；失败与重跑有完整分母。
- 证据/文档/学习映射与提交 SHA 可追溯，已推送（若存在未授权/环境阻断则报告，不虚称成功）。

如有上述任一阻断，报告 `BLOCKED` 或 `PARTIAL`，说明**具体复现和最小修复**，不要为了完成任务静默扩大范围或跳过测试。不要自行进入 M1-02。

### 必填的最终回报模板

```text
[M1-01 FINAL | main@<actual_SHA>]
起点 SHA / 终点 SHA / 工作树状态：
变更文件与核心函数（新 schema、Domain 守卫、受理控制）：
N1-09（无 Plan 终止）：PASS/FAIL/NOT_RUN；进程/事务证据：
N1-10（关键纠错先于旧提交）：PASS/FAIL/NOT_RUN；事实与修复次数：
N1-11（REPAIR 先于终止）：PASS/FAIL/NOT_RUN；Ledger/版本/工单数：
消息+Command+Run 原子受理/幂等：PASS/FAIL/NOT_RUN；重试 ID：
Task/Run/Plan 控制版本校验覆盖入口：
跨租户、审批权限、旧回执回查：
旧全量 pytest：<actual_passed>/<actual_total>，失败与重跑：
模型/MCP/HTTP 新鲜回归：PASS/FAIL/NOT_RUN，真实运行证据：
N1–N4 尚未实现的后续接口/前端/SSE/Memory 范围：
白皮书映射、学习卡、面试卡路径：
所有 evidence/log 路径和提交链接：
结论：PASS / PARTIAL / BLOCKED
下一张卡准备情况（只报告，不执行）：M1-02
```

**最后提醒：** 这是一次“把真实用户控制信号接到权威业务提交点”的最小安全适配。目标是为用户最终看到的高质量多轮对话、任务状态与审批工作台铺路，不是重新研究 Harness 或全面重构 D3。
