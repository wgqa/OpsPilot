# P0‑02‑RED‑DESIGN‑01 有效任务条件保真

2026‑11‑23 · **ACCEPTANCE_CANDIDATE** · 审计、离线 RED 与设计，待主 Agent 独立评审

**24 轮正式离线请求复现了条件丢失。** 四项都属于同一 Task，原始记录仍在。首次收到四项的压缩结果只持久化三项，最终 SDK 请求缺少 `Only event E7`，现有锚点和近期原文均未补回。推荐优先以已受理的结构化条件操作重放任务工作上下文，在原 Context Builder 中与普通的有损摘要分别装配。[实测与复现](EVIDENCE.md)

## 基线核验

| 项目 | 本轮范围 |
|---|---|
| Repo、分支、Base | `wgqa/OpsPilot`，隔离候选 `codex/p0-02-red-design-01`，精确 Base `93d5ac831447c5d23c677bd477958f9817ad8c2a`。GitHub 核对此 SHA 是 `codex/p0-01-task-context-green` 的远端 HEAD。按用户裁决，P0‑01 为 ACCEPT_WITH_LIMITS，尚未授权合并。 |
| 主线与 Diff | GitHub 核实 `main@60eee87bfe3cca522011316cb4cd2c0064ad291b`。本轮 Diff 从 P0‑01 HEAD 起算，只新建本目录。P0‑01 的三个生产文件和测试均由 Base 继承。主目录继续在 AR‑03 分支，纯函数主线对照使用另一处 detached worktree。交付 HEAD 由提交和远端分支核验。 |
| 实读治理 | Base 的 [总纲](../../../PROJECT_NORTH_STAR.md) Blob `e36f2f75509738551ac6d4a2de5b4f9cf44a7991`、[AGENTS](../../../AGENTS.md) `f174a6ab7f23f9e6d8b3ef98d455b99a75193143`、[评审 Skill](../../../.agents/skills/opspilot-slice-review/SKILL.md) `d405c8d413d633824b279202cc1503dab4cf0b03`。核对了仓内 Context 职责与有损压缩参考。[开源参考](../../learning/OPEN_SOURCE_AGENT_REFERENCES.md) |
| 冻结合同 | AR‑04A/B Gold Blobs `6c8ba3867e2dad983abe6f1b85bd559fc28e36ac` / `f5056cbb3344208e2e34671ea08a50963d3aea3d`。核对 AR‑04A G3–G8 的摘要范围、锚点、失效与预算，AR‑04B 的来源隔离。M2‑01/M2‑02 遗留门禁 `2e65870a` / `2536030b`，API/State/Recovery/Lineage 同 Base。 [原审计](../interview-task-continuity-20261123/EVIDENCE.md) · [P0‑01 交付](../p0-01-task-context-20261123/GREEN.md) |
| 已验证层次 | 本人复跑纯函数、正式 HTTP 受理、Worker、MCP stdio 工具发现、SDK/本地 MockTransport、SQLite 来源链。固定 mock 回答只验证请求。真实模型任务结果和线上行为为 NOT_RUN；AR‑04B 历史停滞独立 HOLD / UNVERIFIED。 |

## 实际调用链

1. 工作台选择当前 Task，`/assistant/order` 建立受信绑定，`/assistant/messages` 用该 Task ID 接收同一 Session 的追问。P0‑01 的 Pinned Base 通过 Command、来源 Run、Message 归属和序号验证，普通历史在排序和数量限制前隔离。公共背景也有独立受理记录。 [API](../../../opspilot/web/app.py) · [受理](../../../opspilot/domain/task_control.py)
2. `_dispatch_run` 受信 claim 后进 `ASSISTANT_V1`。 `_prepare_assistant_context_impl` 复用 `_prepare_context` 的 HYBRID 窗口与预算，从超过窗口的历史及前代摘要构造压缩输入。每次压缩先登记和检查来源，实际序列化请求经过独立模型调用入口。 [Worker](../../../opspilot/web/worker.py) · [Assistant](../../../opspilot/assistant.py)
3. `_validate_summary_document` 校验 JSON、序号并映射到消息 ID。 `_compact_summary_document` 先尝试每个分类的最新条目，之后只填至每类三项。保存后的正文和依赖各有 digest，旧摘要可逐代投影到下一次压缩。摘要覆盖序号水位在回答装配中会跳过早期普通历史。进入回答的原始任务和最近正式纠错是专门锚点，本样本中早期 E7 属于普通历史，且早于覆盖水位。 [压缩与来源依赖](../../../opspilot/domain/chat.py)
4. 最终 `create_agent`/LangGraph 把现有历史投影送入 `Loop.awrap_model_call`，再与 `WORK_CONTEXT` 和合法工具 Schema 一起由 ChatOpenAI/OpenAI SDK 序列化。SDK 的实际 `messages` 和内部账本交叉核验。工作台和答复状态本身无法反映早期条件是否在请求里。 [最终 SDK 请求](runs/verified/final-sdk.json)

**根因有两层。** 当前压缩提示要求每分类最多三条，持久化 compactor 独立执行三条限制。即使一个有效 JSON 在 512 Token 内列出四条，持久化仍会删到三条。Context Builder 当前没有独立的有效条件来源。压缩水位越过早期普通消息后，摘要里的损失可能直接传到请求。来源依赖能做撤销和作用域检验，未必携带条件文本，也无法表达哪一项已被替代。对照旅程还观察到经过正式应用的纠错和旧摘要条件同时进请求。用户任务条件的权威状态需要独立于有损背景表达。

## 两种方案

| 维度 | A · 复用消息和已确认操作 | B · 最小的任务条件投影 |
|---|---|---|
| 真相来源 | 创建任务或既有正式纠错确认入口保存版本化的内部条件事件。包含稳定 `item_id`、类型、变更前版本、来源引用/digest 和 `ADD/REPLACE/REVOKE`，复用受理 Command 和操作幂等。初次候选由模型提取时，由用户确认显示的具体差异。正式变更沿 TaskControl 和应用水位，在相同 Domain 事务协调提交。 | 复用同样的合法受理和确认，在同一事务维护一份工作状态投影。键为 tenant/task/item，含类型、文本或结构化引用、source_message_id、source_digest、effective_revision、supersedes_item_id 或前版 revision、ACTIVE/SUPERSEDED/REVOKED、operation_id、更新时间、schema_version。需按任务和活跃状态建索引。 |
| 生效与冲突 | 只回放已有受理记录、来源验证并满足该 Run 应用水位的结构化事件。替换显式指向旧版本，撤销留下墓碑。重试同键同摘要返回原结果，异摘要、过期版本或未匹配的旧锚点显式冲突。假设、未确认冲突和普通聊天保留在背景；未确认候选不得覆盖当前有效项。 | 相同语义，投影只存可追溯的状态。用 CAS 和相同 operation_id 防重，投影应用修订必须与 Domain 对齐。掉线后可以从确认事件重建，无法对齐时停止向运行时发布该任务的条件。 |
| 查询与成本 | 通过 `messages(task_id, sequence)`、已受理 Command/Run 关联及 `task_run_inputs` 定位正式事件，按同一 Task 的确定序号读取并限定页数。CREATE_TASK 经来源 Run 定位，避免把 Session 命令查询当 Task 查询。新事件可在既有内部 Command 记录中承载经核验的结构化载荷，避免每轮扫描全部原文；高变更任务可在确认时持久化有界聚合，读取后回放其后的事件。API 重放应保持现有响应契约。 | 活跃项可以用索引直接查询。投影写放大、事务一致性、版本和迁移都要测试。额外行数约为保留的项版本数，真实页、索引、审计和回滚成本须用同一 fixture 测量。 |
| 旧数据与局限 | 旧普通消息能证明谁说了什么，无法可靠证明提议的时段是否替代过早期约束。有界读取同 Task 原文可提候选并引用原句；缺少证据、冲突或超出检索页数时，显示候选并请用户确认缺少的项，不能假定状态。如果需要自动接续任意历史且不允许确认，A 不足。 | 同样无法可靠地从旧自由文本补出确切的变更关系，仍需来源复核和确认。增表解决近期读取与定向失效，不解决旧语义缺失。 |

### 推荐先以 A 验证一个 Task 的四条条件

- **受理层**保留原始消息与已有 TaskControl 语义。仅在已有正式确认路径承载确定的结构化事件，或在受信任务初始输入存一份经确认的条件集合。首先验证能否复用现有 Command 存储并保持 API 幂等与 replay 兼容。尚未确认的语义解析、自然语言建议和用户原话只作候选。
- **装配层**先按 P0‑01 验证 Session/Task、消息来源、digest 和当前授权。按 Run 可见的已应用修订回放，给模型一个独立的有效条件块，每项带 ID、当前文本和出处，标明是 user requirements。背景仍由现有摘要、近期窗口与合法 Memory/Knowledge 策略选择。旧摘要中冲突文本标为历史或排除冲突的那一项。业务事实、许可或审批仍走原 Domain。
- **预算层**先为可信控制、当前问题、有效条件、必要工具协议预留，然后给背景分配余额。先压缩可选背景并按引用延迟取回详细材料。完整有效条件仍超预算时，可信程序在外发前返回哪几项无法同时执行的可读说明；允许用户明确选范围，或在条件可独立且关联可追溯时由 Agent 建议有界批次。用户必须看到每批范围与未完成条件。全局限制类条件应贯穿每批。
- **门槛**以四条保真和单项变更为第一轮授权边界，记录 SQL 页数、实际输入和调整开销。若确认操作无法在当前存储中实现有界查询、兼容幂等或定向失效，才把 B 作为下一份最小 Schema 提案。当前交付 Schema 变更为零，A 设计先验证无迁表实现。B 会新增投影表及索引。

### 风险和成本

A 的主要成本在确认与兼容语义，期望每轮只读活跃项/少量正式事件，精确 Token 和 stored bytes 等待实施后测量。单条原文短，不代表大规模变更或失效链便宜。出现超出预算、引用跨 Task、失效材料或复用老 checkpoint 的情况，要重查同一修订和权限；无需固定工具顺序。默认 S3 任务的累计辅助调用门槛是单独的现实限制。长对话基线先观察到第 9 轮 `TASK_AUX_PROVIDER_LIMIT`，24 轮实验依赖仓库现有的隔离配置。保真修复不能凭这份离线结果宣称默认配置已支持 24 轮。

## 规划六问与停止线

1. 用户可在长对话后继续同一调查，按现行条件推进，并清楚看到哪个条件被替换、撤回或需要确认。
2. 模型可以提条件变更、澄清、选择合法调查工具及观察顺序。受理与上下文版本由程序核对。
3. 同一条“继续调查”，已确认的全天替换应改变查询范围；仅提出假设时可继续现行范围或询问确认。
4. 需要挡住旧条件回流、越域引用与预算静默截断。合法公共材料、四条件完整和独立分批均应有正例。
5. 优先复用 Command/Run/TaskControl、来源依赖、现有 Assistant 与预算。独立的有效条件块是新的表示职责，摘要继续承担历史解释。
6. 本次只锁定 RED 与验收判据，真实模型效果和实施独立验收未运行。完成候选后停在用户授权范围。 [验收设计](EVALUATION.md)
