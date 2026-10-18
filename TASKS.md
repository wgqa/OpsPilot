# TASKS.md — OpsPilot 相对 D1 的实施追踪

**主合同**：[`docs/baseline/v1.0-implementation-baseline.md`](docs/baseline/v1.0-implementation-baseline.md)
**设计放行**：2026-10-17 R5 · DESIGN APPROVED。**D1–D5 已通过主 Agent 验收；D2 PR #2 合入 `main@171f028`。D6 E01–E10 评测及证据已完成，交主 Agent 复核。**

**vNext 执行登记：** v1.0 基线继续约束 D1–D7 历史实现；vNext 范围依据 [v0.3 合同](docs/handoff/vnext/OpsPilot-vNext-v0.3-product-architecture-contract.md)、当前阶段任务卡与 [候选实现基线](docs/baseline/vNext-product-baseline-candidate.md)。M1-01 已通过主 Agent 验收；M1-02 实施与新鲜测试已完成，等待本轮源码/证据审查；不表示 M1 总体或第三方审查通过。

> 本表只勾选已执行且有证据的项目。D1–D7 代表实际开发的相对顺序，**不是**把 2026-10-17—23 自动当作已经执行。评审阶段累计的时间不当作有效编码时间。

## D1 — 环境实证 + S1 无模型真实因果链

- [x] 锁定 Python、LangChain、LangGraph、MCP SDK、模型适配器和测试依赖；记录 lockfile 与不包含密钥的 `.env.example`。干净 CPython 3.14.0 环境安装与 `pip check` 通过。
- [x] 真实模型 Tool Call smoke：`deepseek-flash` 返回结构化调用参数，实际执行一次受控只读工具；记录 `tool_call_id`、Schema、Observation 和失败尝试。
- [x] 真 MCP stdio smoke：客户端 tools/list 发现服务器工具，tools/call 返回真实 Domain 数据；证据含 Schema、structured result、scope 错误处理。
- [x] LangGraph 持久 interrupt smoke：进程 A 退出后，进程 B 用原 thread_id 恢复；前置状态保留，越权 actor 在读取前被拒绝。
- [x] Demo Domain 和两种 fixture：S1-POS 真实 HTTP 401→fixture-only 配置切换→同主体、同路由 200/订单字段；S1-DISABLED 切换凭证后仍为 401。
- [x] 独立干净环境完整运行测试；提交 D1 报告、脱敏日志、失败尝试与 D2 建议。

**停止线**：三个技术 smoke 有任何一个失败，优先修复兼容/部署；S1 无模型真实因果链不通过，不叠加 Agent 执行逻辑。Fixture 修改必须限制为离线测试驱动专属，不暴露为无审批的 Agent 写工具。

## D2 — 只读动态调查与证据门禁

- [x] WP1：保留 `get_demo_service_info` 仅作 D1 回归；D2 MCP 只暴露按来源拆分的 `get_integration_config`、`get_principal_status`、`get_auth_policy`、`probe_endpoint`。持久 TaskBinding 绑定 actor/tenant/thread/service/integration，Domain 每次请求重验资源归属。
- [x] WP2：LangGraph `intake → prepare_context → investigate ↔ execute_read_tools → evidence_gate → report`；真实模型 Function Calling 只提出 MCP 工具调用，真实 stdio Client/Server 执行。记录 `tool_call_id → call_id/attempt_id → Observation → Evidence ID`。
- [x] WP3：Gate 的四值为 READY/NEED_MORE/NO_ACTION/INCONCLUSIVE；模型请求上限 8、MCP `tools/call` attempt 上限 6，预登记台账持久化在 Domain SQLite；跨进程预算重启测试通过。READY 只产生候选诊断，不执行写入。
- [x] WP4：真实模型 + MCP 的 POS 得 READY、DISABLED 得 NO_ACTION、策略证据源缺失时 401 得 INCONCLUSIVE；三种路径均保持 config_version=7。另验证跨租户调用拒绝、严格模型参数、恶意事实不能提升 Gate、重复无增量停止。
- [x] WP5：D1 回归 8/8 通过；D2 新增 pytest 9/9 通过；真实模型 POS/DISABLED/INSUFFICIENT 轨迹及一次保留的并行调用失败样本见 `docs/evidence/d2/`。
- [x] WP6：更新 README/TASKS/AGENTS，提供锁定依赖、实际命令、脱敏轨迹、已知问题与 `docs/evidence/d2/REPORT.md`；未实现 D3/D4、Memory、Skills 或 Multi-Agent。

**停止线**：门禁漏放或跨作用域读失控，则禁止接写操作。

## D3 — 第一次真实审批 → 修复 → 业务验证 → 交付

- [x] WP-01：不可变 Plan、Domain 权威计划资格和分项 REPAIR/DELIVER Approval；LangGraph interrupt 由独立进程审批并恢复，checkpoint 只存业务对象引用。
- [x] WP-02：两个动作首次发出前预登记唯一 ActionIntent；各自授权、幂等身份、ActionLedger 分别持久化，事务入口只接受 Intent ID。
- [x] WP-03：REPAIR 事务 CAS；同一 TaskBinding 的真实业务路由在线验证 HTTP 200 和订单字段；VerificationReceipt 持久化。
- [x] WP-04：固定 ReportArtifact；DELIVER 使用独立 Intent、许可、ledger 和 receipt，工单处置条目只追加一次。
- [x] WP-05：拒绝、DISABLED、过期版本和失败在线验证均阻断受限写入；重复 Probe 新 request/auth-event ID 不再误判冲突，稳定事实变化仍触发 INCONCLUSIVE。
- [x] 真实 D3 smoke、D1/D2 回归、全套 pytest 及 `docs/evidence/d3/REPORT.md` 已执行并记录；未扩展 D4、Memory、Skills 或 Multi-Agent。

**停止线**：无法显示真实 401→200 或受限操作不安全，停留 D3 修复，不添加 Memory/Skill。

## D4 — 丢响应/恢复/旧计划/越界安全门禁

- [x] E04 拒绝/未审批：`test_d3_rejection_creates_no_action_intents_or_business_writes` 与未批准 ActionIntent 检查通过；配置版本保持 7，工单条目、Intent、Ledger 均为零。
- [x] E05：取消和 Plan 替换的动作前阻断、动作提交后取消回执重放、REPAIR/DELIVER 竞争及重复批准后授权不复活均通过；旧 Plan 无法重新 activate。
- [x] E06/E07：跨租户/角色任务、计划、审批、Intent 和工单读取拒绝；真实只读 MCP 返回含恶意指令的未信任事实，Gate 保持确定性且未审批动作被拒。Memory 尚未进入 D5，按冻结范围标记 N/A。
- [x] E08：LangGraph 审批中断可等待和跨调用恢复；两个并行相同 REPAIR 或 DELIVER 只生成一条 ledger，配置只改一次、工单只追加一条。
- [x] E09：真实 OS 子进程在 ActionIntent、REPAIR 事务前/后、冻结报告和 DELIVER 事务前/后强制退出；陈旧 checkpoint 重放恢复相同 action/report/ledger 身份，配置只递增一次，工单仅一条。无 Domain 回执的终态被阻断为 `ACTION_OUTCOME_UNKNOWN`。
- [x] D1–D4 全量回归、真实 D2 POS/DISABLED/INSUFFICIENT 模型/MCP 复测、真实 D3 闭环 smoke、进程/并发故障轨迹和 `docs/evidence/d4/REPORT.md` 已记录；仅保留本地 SQLite Demo Domain 的适用边界。

**停止线**：任一已承诺的安全红线失败，不进入 D5；失败不能被平均成功率掩盖。

## D5 — Memory / Skill / Context

- [x] 一种经来源核验、人工批准后 ACTIVE 的 Episodic Memory；候选仅引用同任务 COMMITTED REPAIR、真实 `RECOVERED` 在线验证、冻结报告和可查 Evidence；重复候选幂等，过期/撤销/跨租户/跨项目均不进入检索。
- [x] 一个版本化 `auth-incident-triage` Skill，manifest 与 SHA-256 正文一致时按需加载；恢复时校验版本/digest，不新增工具或操作权限。
- [x] 每个真实模型调用出站前，在同一预算事务登记 Context Provenance：call/attempt、prompt 与工具 schema digest、当前 Evidence IDs、Skill 与 Memory ID/version；模型失败也可审计。
- [x] 真实跨任务轨迹：D3 成功任务 A → CANDIDATE（未进 Prompt）→ `approver-a` 确认 → 新 Task B 首次真实模型请求使用 Memory/Skill → 撤销 → 独立进程恢复后新模型请求无旧 Memory；Memory 保持在 MCP Evidence/Evidence Gate/审批之外。
- [x] 真实模型/MCP 安全反例：Memory ACTIVE 时主体 DISABLED 的 401 仍为 `NO_ACTION`；独立证据不足的 401 仍为 `INCONCLUSIVE`。
- [x] D5 定向测试 7/7、全量 pytest 62/62、19/19 真实 D5 smoke 断言、`py_compile` 与 `pip check` 通过；完整日志和跨任务轨迹见 `docs/evidence/d5/`。

## D6 — 离线评测与故障归因

- [x] 在真实 smoke 前冻结 E01–E10 离线 Gold 与类型/测试映射；E07 后续仅更正真实 MCP 控制测试的运行类型，Gold 未变，初始冻结版留在 commit `151a1cea`。
- [x] E01 D3 真实闭环、E02 DISABLED、E03 INSUFFICIENT 各新鲜运行一次；E10 D5 跨任务 smoke 保留一次真实失败，并在独立 Domain/checkpoint 下重跑通过。
- [x] E04–E10 控制断言映射到全量 pytest；64/64 总测试通过，45 个唯一映射控制测试项全部通过；错误、ActionLedger、Evidence、Provider Token 和 MCP 轨迹均归档。
- [x] Correct Handling、Actual Recovery、Control Safety 分开统计；E10 场景族记 PARTIAL（首次失败、隔离重跑通过），安全门禁独立 PASS。
- [x] D5 Memory 固定通用提示及其与 Skill 重叠情况如实记录；未声称准确率/效率提升，Memory ON/OFF 消融按冻结条件标记 NOT_RUN。
- [x] 更新报告、CASE/RESULTS 机器文件及复现日志；完整结果见 [`docs/evidence/d6/REPORT.md`](docs/evidence/d6/REPORT.md) 和 [`RESULTS.json`](docs/evidence/d6/RESULTS.json)。

## D7 — 独立复现、材料与面试准备

- [x] 两次独立源码目录、全新 venv/数据库/checkpoint；首轮 Skill CRLF 摘要失败保留；仅 `.gitattributes` 固定 LF 后，真实模型/MCP/HITL 业务闭环 13/13，401→200、配置 7→8、独立 Ledger 和单条工单均有证据。
- [x] 复用两个已有 D4 真进程 COMMIT 后退出用例，exit 75→0，Action/Ledger 身份相同、无重复副作用；定向 2/2、修正后全量 pytest 64/64、pip check 与语法检查通过。首轮全量 61/64 和采集入口 exit 4 均保留。
- [x] README 最短路线、人工两进程 CLI、DEMO、源码地图、两个 STAR 与十个追问、报告及机器结果完成。
- [x] 准备实际代码/合同/测试/脱敏证据的离线审计附件和逐文件来源清单；第三方不需 GitHub 权限即可阅读核心实现。
- [x] D6 9 PASS + E10 PARTIAL、4/5 模型 smoke 和固定通用 Memory 局限原样保留；D7 E02/E03/E10 模型证据标注历史复用，未冒充新跑。
- [ ] 主 Agent D7 验收（等待）。
- [ ] 一次独立第三方实现/漂移审计（尚未开始，不预写审查意见）。
- [ ] 用户最终亲自阅读与审阅（尚未开始）。

**停止线**：D7 开发完成后停止扩展；只就经证明确有 P0 阻断的具体问题做最小修复，不启动下一开发阶段。实际结果见 [`docs/evidence/d7/REPORT.md`](docs/evidence/d7/REPORT.md)。

## vNext M1-01 — Task 终止、关键纠错与动作原子裁决

- [x] 在现有 Domain SQLite 增加 TaskControl、Session、Message、Command、TaskRun、Outbox 与 Plan-control 绑定；迁移重放两次保持原 Plan hash，未知旧历史不升级成新控制权限。
- [x] 消息受理、幂等 Command、排队 Run 与 Outbox 同事务；Task abort / 关键纠错提高可信控制版本、使旧 Run/Plan 失效。更正以 `USER_INPUT_UNTRUSTED` 进入新调查，不能替代 Evidence。
- [x] D3 的 Plan、审批、ActionIntent、REPAIR、DELIVER 在 Domain 事务内校验 Task/Run/Plan 控制绑定；同身份历史已提交 Ledger 可回查，终态 Task 不会被后到 abort 覆盖。
- [x] N1-09、N1-10、N1-11 新鲜通过；N1-09 与 N1-11 使用真实独立 OS 子进程恢复旧 checkpoint。N1-01/02 受理回滚与幂等、N1-05 独立连接争用及迁移回归通过。
- [x] 本轮全量 pytest **73/73**；`compileall`、`pip check`、Git whitespace 检查通过；真实模型/MCP TaskRun smoke 与既有 D3 S1 401→200 smoke 各有本轮轨迹。报告与原始证据：[`docs/evidence/vnext/m1-01/REPORT.md`](docs/evidence/vnext/m1-01/REPORT.md)。
- [x] 主 Agent M1-01 审查通过；本节保留其实现与验收历史。

**历史停止线**：M1-01 当时完成后停止等待主 Agent；v0.3 附录 B 未获第三方重新签字，不把阶段测试称为第三方审批。

## vNext M1-02 — FastAPI 会话与可靠事件

- [x] FastAPI 本地服务、随机 HttpOnly Session、服务端可信角色、Origin/CSRF、owner/tenant 鉴权；只绑定 loopback，拒绝多 worker。
- [x] Session/Message/Task/Run API；Task、首条 Message、Command、INVESTIGATE Run、budget 与事件在 Domain 单事务原子受理，幂等重试返回原 IDs。
- [x] 单实例后台 worker 复用既有 Investigator/TaskControl/LangGraph/D3 Domain；人工等待释放 worker；跨进程恢复复用同一 Run/checkpoint，revision 0 恢复权限回归通过；活跃 C1 超限转 BLOCKED/INCONCLUSIVE。
- [x] Outbox → 持久 `session_events` → SSE；`Last-Event-ID` 游标回放、断线重连、旧 Ledger 只补事件，SSE 不触发副作用。
- [x] WEB-01..07、N2-01..05、OPS-01..02 与 N1-09/10/11 fresh test 通过；完整 pytest **91/91**，M1 定向测试 **27/27**；5 个成功真实模型响应 trace、1 个进程退出时 RESERVED attempt、4 次真实 MCP tools/call。
- [x] 报告、RESULTS、脱敏 HTTP/SSE/worker/模型日志、首次失败与修复记录、baseline/学习文档已提交到 `docs/evidence/vnext/m1-02/`。
- [ ] 主 Agent M1-02 审查（等待）；M1-03 未开始。

**停止线**：本轮到 M1-02 为止；提交并推送 main 后等待主 Agent 审查。不得自行进入 M1-03。

## 实际进度登记

| 日期（实际） | 阶段 | Commit / 版本 | 结果（测试分子/分母） | 阻断与下一步 |
|---|---|---|---|---|
| 2026-10-17 | D1（已验收） | `1a038be` / PR #1 merged | WP-01–06 通过；pytest 8/8；真实模型、MCP、跨进程 checkpoint、S1 POS/DISABLED 均有日志 | 主 Agent 已通过审查。报告见 `docs/evidence/d1/REPORT.md` |
| 2026-10-17 | D2（已验收并合入 main） | PR #2 / `171f028` | WP1–WP6 通过；D1 回归 8/8、D2 新增测试 9/9；真实模型/MCP 三场景有轨迹 | 主 Agent 已验收。报告见 `docs/evidence/d2/REPORT.md` |
| 2026-10-17 | D3（主 Agent 已审查通过） | `main` / `5529990` | 全量 pytest 29/29；D3 真实跨进程模型/MCP/HITL smoke 13 项检查通过；D2 POS/DISABLED/INSUFFICIENT 三场景回归通过 | 真实 401→200、订单字段、固定报告与单条工单交付见 `docs/evidence/d3/REPORT.md` |
| 2026-10-17 | D4（主 Agent 已审查通过） | `main` / 本轮 D4 提交 | 全量 pytest **55/55**；D3 真实 smoke **13/13**；D2 三场景均 PASS，详见 `docs/evidence/d4/REPORT.md` | E04–E09 通过；无 Domain 回执的终态安全阻断 |
| 2026-10-17 | D5（主 Agent 已审查通过） | `main` / D5 implementation commit（见 D5 报告） | 全量 pytest **62/62**；D5 真实模型/MCP **19/19**；D3 来源闭环及 D2 主体禁用/证据不足控制有真实轨迹 | 跨任务经验激活、撤销和跨进程不复用通过；详见 `docs/evidence/d5/REPORT.md` |
| 2026-10-17 | D6（历史评测冻结） | `main` / 运行代码 `f2c9403`；评测 Gold 冻结于 `151a1ce`；最终证据 `28c3e1a` | 全量 pytest **64/64**；E04–E10 映射控制测试唯一项 **45/45**；E01/E02/E03 新鲜真实模型场景均 PASS；E10 attempt 01 FAIL、attempt 02 PASS | 场景族 9 PASS / 1 PARTIAL；无 P0 安全红线失败；D7 不改写其结果 |
| 2026-10-17 | D7（交付完成，等待主 Agent 验收） | 运行实现 `a2517fdbe2b66e4490867cc388aadc32ec5b5197`；最终交付 SHA 见 Git/交付消息，附件来源 SHA 见 MANIFEST | 首轮 E01 FAIL、pytest **61/64**；修正后 E01 **13/13**、恢复 **2/2**、pytest **64/64**；模型 7 / MCP 6 / 19,244 tokens | 仅修 Skill 导出 LF，未改 Agent/Domain 执行逻辑；离线包和源码/面试材料齐备；开发停止，外部审查未执行 |
| 2026-10-18 | vNext M1-01（本轮测试完成，待主 Agent 审查） | 基于 `main@a53e13a4243cc6c7fa545b3e3a92b838596b6242`；交付 SHA 以本轮 Git 终点为准 | N1-09/10/11 通过；新鲜全量 pytest **73/73**；模型/MCP TaskRun、D3 S1 真实 smoke 通过 | 仅 M1-01；不声称 M1 总体或第三方审查通过；等待主 Agent 决定是否启动 M1-02 |
| 2026-10-18 | vNext M1-02（实现完成，待主 Agent 审查） | 起点 `main@9658aa3a02513a41cfd40ce1e5974d49ec9fe9ed`；终点以本轮最新 main 提交为准 | 全量 pytest **91/91**；M1 定向 **27/27**；真实 HTTP 双身份、SSE、同一 Run 跨进程模型/MCP 恢复通过 | 仅 M1-02；真实 S1 等待审批且未发生审批/业务写入；M1-03 未开始 |

**时间估计**：27–37 小时有效开发 + 3–5 小时排错是独立评审的初步规划；若每天只能保障 3 小时，改为约 10–14 天，不缩减恢复和安全门禁。
