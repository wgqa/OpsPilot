# P0-02-A-GREEN-01 有效任务条件恢复

**2026-11-23 · ACCEPTANCE_CANDIDATE · 待主 Agent 独立裁决。**

用户在同一个调查 Task 内确认过的要求可以跨摘要代际继续使用。普通聊天保留为候选和背景。用户更换时段、撤销报告格式或提出假设时，当前要求及其来源可单独核对。现有 Agent 仍可决定合法工具、查询顺序、补查、澄清或停止。

## 基线与范围

| 核验项 | 实际读取和验证 |
|---|---|
| 仓库与分支 | wgqa/OpsPilot，隔离工作树 codex/p0-02-a-green-01，从精确 Base e37f4387e36aad9f23629bfa4f9c48bde2556638 创建。 |
| 上游 | Git ls-remote 核实 P0-02 RED e37f4387e36aad9f23629bfa4f9c48bde2556638、P0-01 93d5ac831447c5d23c677bd477958f9817ad8c2a、main 60eee87bfe3cca522011316cb4cd2c0064ad291b。ACCEPT_WITH_LIMITS 来自本轮卡，候选分支无合并。AR-03 的本地杂项留在原工作树。 |
| 项目规则 | 目标提交实际读取 [总纲](../../../PROJECT_NORTH_STAR.md) e36f2f75509738551ac6d4a2de5b4f9cf44a7991、[AGENTS](../../../AGENTS.md) f174a6ab7f23f9e6d8b3ef98d455b99a75193143、[评审 Skill](../../../.agents/skills/opspilot-slice-review/SKILL.md) d405c8d413d633824b279202cc1503dab4cf0b03、[开源参考](../../learning/OPEN_SOURCE_AGENT_REFERENCES.md)。 |
| 冻结和遗留 | AR-04A/B Gold 6c8ba3867e2dad983abe6f1b85bd559fc28e36ac / f5056cbb3344208e2e34671ea08a50963d3aea3d；M2-01/02 遗留门禁 2e65870acb26a7c1383fdd96b5b8619748dda6b9 / 2536030b5b942bf9e3765e0916607549fa919934；核对 API、State、Recovery、Lineage 和原 RED 设计。用户任务卡规定本轮范围，历史业务及授权合同继续适用。 |
| 实际证据 | 实施方亲跑 API、SQLite、Worker/LangGraph、stdio MCP 工具发现、OpenAI SDK 的 HTTPX MockTransport 和定向回归。真实模型、真正的业务结果、浏览器和全量测试为 NOT_RUN；AR-04B 仍为 HOLD / UNVERIFIED。 |

## 方案 A 的可行性

先在 e37f438 的原生 TaskControl 上运行离线探针。探针只在临时 DB 的两次 Outbox 写入前给事件添加私有载荷，未修改生产文件。ADD、REPLACE、REVOKE 分别在控制版本 2、4、6 生效。受理阶段应用水位未前移，读回仍是上次有效版本。同键同摘要返回原始结果，同键异摘要拒绝。旧 API 收据与公开事件白名单保持兼容。[探针](prove_storage.py) · [原始日志](storage-proof.log)

| 检查项 | 落点 |
|---|---|
| 事件保存 | 正式纠错的 COMMAND / MESSAGE_ACCEPTED 私有 condition_changes_v1 字段，包含 operation_id、期望控制版本和逐项 ADD／REPLACE／REVOKE、item_id、旧版本、来源 ID 与 digest。 |
| 正式生效 | TaskControl 仲裁并领取持久调查 Run 后，apply_pending_critical_inputs 在现有写事务消费严格有序的纠错消息，写 task_run_inputs、前移应用水位，并在 RUN / CRITICAL_INPUTS_APPLIED 私有 condition_state_v1 保存当前快照和撤销墓碑。受理状态本身没有应用资格。 |
| 幂等与版本 | 相同操作键和完整 canonical digest 回放同一现有 Command 结果；不同事件或版本发生冲突。仅允许在没有待应用纠错时提交一批结构化变更。普通纠错继续走原路径，新代码会携带已有快照。 |
| 有界查询 | 应用水位通过 (task_id, sequence) 定位 Message，使用 message_id 定位 task_run_inputs，再按 Outbox 三列唯一键查快照。最多 32 个有稳定 ID 的槽位，包含撤销墓碑，每项源文本最多 1,200 字符。重新使用已撤销槽位须带其当前版本。 |
| 历史兼容 | commands.result_json 继续保存原始受理收据，发布到 SSE 的字段仍走已有白名单。每个 Task 首次结构化确认为生效边界，既有普通聊天和普通纠错无需迁表或回填。 |

## 调用链与出站

1. 受信 Task owner 使用既有 POST /api/sessions/{sid}/messages，选择 CORRECT_TASK_INPUT，并提交 expected_control_revision、Idempotency-Key 和 condition_changes 数组。每项包含 item_id、operation、expected_version、source_message_id、source_digest。digest 应针对已保存的原文。当前 API 需要调用方显式提交所确认的事件及来源。普通 /assistant/messages 不接受此载荷。[入口与 DTO](../../../opspilot/web/app.py) · [Domain 受理与应用](../../../opspilot/domain/task_control.py)
2. 来源使用 P0-01 的 Command、原始 Run、消息、Session、Task 关联校验，并复算原文 digest。TaskControl 在应用事务按版本重放，校验确认消息和实际应用 revision。当前读视图在 Run revision 与水位一致时才读取快照，逐条重新验证活跃项来源。[存储与回放](../../../opspilot/domain/task_conditions.py)
3. Context Builder 把当前条件作为必需输入，与控制、事实、当前消息和工具预留预算共用一个窗口。历史摘要保存原样，出站视图把 constraints 重命名为 historical_constraints，标明是历史。来源失效或整组条件放不下会停止当前 Run；默认 S3 辅助调用预算仍由原账本判定。[Context Builder](../../../opspilot/domain/chat.py)
4. Assistant 恢复时用新生成的 seed 检查 checkpoint，出站前再次核对当前读视图和资源权限。持久化答复时在写事务以 manifest 条件块 digest 校验，答复依赖记录引用来源消息。旧 Investigator 复用同一条件读视图，在持久 Run 校验和提示中携带条件，仍走自己的工具预算及授权。[Assistant](../../../opspilot/assistant.py) · [Investigator Run Context](../../../opspilot/domain/investigation_context.py)

## 验收口径与剩余取舍

- 冻结 24 轮中四条均由普通聊天进入。原脚本不变时仍是兼容对照；若只凭末句“按之前四项继续”就补记为已确认，会与正式受理边界冲突。配对旅程复用原 24 条文字，在最后一轮前新增一次显式确认，四项都指向原始来源。既有历史的自动提取、确认 UI 和对用户漏选项的引导不在本次证据中。
- 复用 CORRECT_TASK_INPUT 会按现有合同推进全局 TaskControl，可能失效旧 Run 和 Plan。输出格式一类低风险要求长期也许适合更细粒度的生命周期。本轮保持合同，避免在并行控制链中制造绕过。
- 历史摘要和旧用户文字仍存在，历史标签与当前条件块可在 SDK 输入中分别核对。真实模型能否稳定遵守新的条件优先级仍待验证。现有 Outbox 成为条件状态的保留依赖，后续清理策略和混合版本降级需要单独评审。低于本切片的旧 Worker 不具备快照接续能力。
- 本轮 CODE 与 API 已接入离线正式调用链。合规正例包括四项确认、合法公共材料、无须确认的假设解释和干净恢复；负例分别覆盖跨 Task、无效来源、过预算、脏 checkpoint 和默认累计上限。未扩大工具、Memory、审批或业务写入规则。主 Agent 仍需按证据独立裁决。[证据、成本与复跑](EVIDENCE.md)
