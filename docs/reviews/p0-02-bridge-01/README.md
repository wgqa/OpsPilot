# OpsPilot P0-02-BRIDGE-01 自然语言任务条件核对

**ACCEPTANCE_CANDIDATE · 2026-11-23 · 等待主 Agent 独立验收。**

工作台在当前专业助手订单 Task 提供「任务条件」。用户可以照常说“按之前四项继续”，然后选择「从对话核对条件」。页面把找到的原话、消息序号、已生效值与候选操作放在同一处。确认所选项会提交一次正式纠错，应用后后续调查使用已有的 CURRENT TASK CONDITIONS 块。

## 开工核验

| 项目 | 核验 |
|---|---|
| 版本和工作树 | wgqa/OpsPilot，隔离分支 codex/p0-02-bridge-01，Base 7786aa95331bba06af767a3f758eb320ab9e733a，开始时 HEAD 相同且工作树干净。通过 GitHub ref API 核实远端 P0-02-A-GREEN 同 SHA、main 为 60eee87bfe3cca522011316cb4cd2c0064ad291b。P0-02-A ACCEPT_WITH_LIMITS 采用本轮任务卡。 |
| 治理文件 | 实际读取目标提交的 [总纲](../../../PROJECT_NORTH_STAR.md) Blob e36f2f75509738551ac6d4a2de5b4f9cf44a7991、[AGENTS](../../../AGENTS.md) f174a6ab7f23f9e6d8b3ef98d455b99a75193143、[评审 Skill](../../../.agents/skills/opspilot-slice-review/SKILL.md) d405c8d413d633824b279202cc1503dab4cf0b03、[开源参考](../../learning/OPEN_SOURCE_AGENT_REFERENCES.md)。 |
| 适用合同 | AR-04A/B Gold 6c8ba3867e2dad983abe6f1b85bd559fc28e36ac / f5056cbb3344208e2e34671ea08a50963d3aea3d；M2-01/02 遗留 2e65870acb26a7c1383fdd96b5b8619748dda6b9 / 2536030b5b942bf9e3765e0916607549fa919934；原 [24 轮 RED](../p0-02-red-design-01/EVIDENCE.md) 与 [A-GREEN](../p0-02-a-green-01/EVIDENCE.md)。历史业务资格、作用域与写入合同继续适用。 |

## 实际调用链

1. **从原消息取材。** 用户主动请求核对，Web 使用当前 Task 最后一条用户消息为锚点。Domain 校验身份、Session owner、S3 资源 Grant、接受 Command、来源 Run、序号和原文 digest。候选材料只读取同 Task 持久用户消息；公共背景继续由普通 Assistant Context 处理。[工作台审核卡](../../../frontend/src/TaskConditionReview.vue) · [API](../../../opspilot/web/app.py) · [来源与候选](../../../opspilot/domain/condition_review.py)
2. **发现只产生提案。** 最多取 48 条；每条超过 360 字符给模型片段且无确认资格。模型只可返回槽名、操作和已供应消息序号。已生效重复项折叠为展示，冲突、假设、引用、待核实为不可勾选。服务端以原文的消息序号和 digest 还原候选，用户编辑时回到普通输入框提交新消息。每个锚点最多一个持久模型尝试，输入上限 5,200、输出上限 640，使用已存在的 Task AUX 计数和调查更新尝试账本。已有模型实验配置不会通过这条新路旁路派发。 [提案与账本](../../../opspilot/domain/investigation_updates.py)
3. **确认复用旧事务。** 页面只提交勾选的候选编号和稳定 operation_id。TaskControl 在原有纠错事务检查候选集合、来源、最新消息、版本和权限，按 ConditionChange 提交所选变更与一次正式纠错。原应用事务推进水位，Outbox 继续保存唯一的有效状态。刷新用同一读接口核对待确认、已受理、已应用。放弃整份审核不提交纠错。[用户确认](../../../opspilot/domain/task_control.py) · [当前有效条件](../../../opspilot/domain/task_conditions.py)
4. **迁移只增加提案字段。** SQLite 由 v18 升到 v19，已有 investigation_update_assessments 新增可空 condition_review_json，复用 investigation_update_attempts。没有增加表。旧分类器原来把一条待路由消息关联到一个提案，桥接只能使用专业助手消息且独立筛选；同一消息仍只有一个提案行。七个迁移回归仅将期望的最终版本改为 19，原有业务断言和冻结 Gold 保留。[迁移](../../../opspilot/domain/database.py)

## 设计判断与局限

- **把长历史发现做成显式操作。** 没有必要让每个自然语言回合都跑模型分类。一般追问继续自由回答。候选列表打开后以真实覆盖计数提示片段、分页和缺口，只有原文候选经确认才跨轮生效。
- **只借鉴持久历史与有限派生。** Codex 的记忆写入把会话 rollout 抽取与后续有界整理分开，选择版本可追踪；Pi 在压缩后仍保留底层 Session 记录。这里使用 Task 作用域的原消息做按需发现，并将生效权留在已有 TaskControl。没有跨 Task 学习、后台整理和额外 Agent。[Codex memories](https://github.com/openai/codex/blob/main/codex-rs/memories/README.md) · [Pi compaction](https://github.com/earendil-works/pi/blob/d8981c7ba00a722c897d7270b7f421418512a784/packages/coding-agent/docs/compaction.md)
- **任务预算是已验证的现实限制。** 默认 S3 AUX 用尽时，条件发现与普通回答分别在各自原有入口止损，不能承诺从任意长历史无损恢复。24 轮旅程使用既有隔离配置。长句中多个不可分割条件当前需要用户重新表述，退出或未知结果后的同一锚点不会自动重复付费。现有确认会依法推进 TaskControl revision，适合重要且持久的调查要求，一次性表达可留在当前对话。
- **经验结论限于流程证据。** MockTransport 的候选语义来自确定性夹具。真实 Provider 的提取质量、多语言泛化和实际调查结果为 NOT_RUN。浏览器跑的是各分支另行说明的本地隔离交互。付费请求与外部业务写入为零，AR-04B 保持独立 HOLD / UNVERIFIED。
