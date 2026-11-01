# AR-03-04 交付报告与六问自检 (REPORT.md)

## 0. 审查前置核验区块

- **Repo / Branch：** `wgqa/OpsPilot` / `antigravity/ar03-04-upgrade-investigation`
- **Base SHA：** `7dfdf2525243fe9049703fd47703e2b1a7257345`（`antigravity/ar03-03-agent-integration`）
- **Candidate Branch：** `antigravity/ar03-04-upgrade-investigation`
- **隔离 Worktree：** `.worktrees/ar03-04-upgrade-investigation`
- **准则文档实际阅读与哈希：**
  - `PROJECT_NORTH_STAR.md`（Blob: `1f737712c7a36ceb34433ac09c3fbba3c3305542`）已于本次会话重新核验并严格遵守
  - `AGENTS.md`（Blob: `32c45506cceeaa8c76a5c56bf8360ff476b58856`）已于本次会话重新核验并严格遵守
  - `.agents/skills/opspilot-slice-review/SKILL.md`（Blob: `d405c8d413d633824b279202cc1503dab4cf0b03`）已于本次会话重新核验并严格遵守
- **原始根目录状态检查结果：**
  - 原始工作区处于 `antigravity/ar03-protocol-compare` 分支，tracked 文件无任何未提交修改。
  - `git stash list` 确认为空，无遗留未处理 stash。
  - `.agents` 目录完整存在，Blob 哈希为 `d405c8d413d633824b279202cc1503dab4cf0b03`，未作任何清理或删除。
  - 用户未跟踪目录完整保留。
- **并行分支与外部边界：**
  - Codex 的 AR-02 主线（`codex/ar02-live-01`）保持独立运行，未发生任何分支合并、覆盖或污染。
  - `main` 分支保持 0 修改。
  - 零真实 Provider 付费调用，零未授权写入操作。

---

## 1. 本轮实际改动说明

本轮聚焦于解决 AR-03-04 的业务核心闭环：**用户无需记忆内部文档 ID（如 `callback-retry-contract-v2`），即可通过自然语言提问完成“发现授权协议版本 → 比对演进差异 → 结合业务观察判断影响 → 输出交接建议与未知事项”的调查闭环。**

1. **协议规范安全发现桥接（`opspilot/domain/scoped_protocol_comparison.py`）**
   - 新增 `list_scoped_protocols(db, identity, session_id, topic=None)`：
     - 在当前会话激活的项目授权（`get_session_project`）范围内，严格按 `project['document_ids']` 白名单扫描受信目录清单。
     - 支持模型传入可选的自然语言主题（如 `topic="retry"`、`topic="callback"`），按 `document_id`、`title`、`keywords` 过滤。
     - 自动归类为结构化协议族（`protocols`，如 `callback-retry` 包含 v1 与 v2）与明细列表（`protocol_documents`），免除用户与模型对内部文档 ID 的死记硬背。
     - 结果强制标记 `deployment_version_verified: False` 与 `authority: "SESSION_AUTHORIZED_DISCOVERY_NOT_ACTION_AUTHORIZATION"`。
   - 新增 `scoped_discovery_is_current(db, identity, session_id, discovery_result)`：
     - 会话来源再验证：对发现结果实施 `session_id`、`tenant_id`、`actor_id` 强校验。
     - 项目授权版本与摘要校验（`scope_digest`）。
     - 严防未授权注入：检查返回的全部文档 ID 是否仍在项目白名单中（`DOCUMENT_AUTHORIZATION_REVOKED`）。
     - 磁盘清单与文件哈希完整性校验（`DOCUMENT_INTEGRITY_OR_EXPIRED`）。

2. **Run 级 MCP 工具注册（`opspilot/assistant_mcp.py`）**
   - 注册只读工具 `list_scoped_protocol_documents(topic: str | None = None) -> dict`。
   - 上下文注入：从当前受信 Run 自动注入 DB 路径、操作者身份与 `session_id`。模型仅需决定是否调用及传入主题关键字。
   - 标注 `read_only_hint=True, open_world_hint=False`。

3. **核心会话来源持续有效性再验证（`opspilot/domain/assistant.py`）**
   - 在 `sources_current()` 中接入 `scoped_discovery_is_current()`。
   - 确保包含协议发现观察的 Assistant 历史在跨轮交互中同样接受严格审查，拒绝跨会话伪造。

4. **端到端两段核心旅程测试与闭环验证（`tests/test_ar03_04_upgrade_investigation.py`）**
   - **旅程 A（未绑定订单）：** 用户自然语言咨询协议变化及客户完成情况。模型自主调用协议发现与比对，分析差异与退避影响，并**诚实指出因当前尚未绑定订单（未建立 TaskBinding），无法核查客户订单或 Receiver 实时状态**，给出绑定建议操作。
   - **旅程 B（绑定订单下的事实区分）：** 绑定 `ar02-order` 后，用户在同一提示词下提问。模型结合真实 S3 工具观察：
     - 当 Receiver 为 `QUEUED`（HTTP 202）时：准确断言“尚未处理完成”（202 仅为排队受理），整理技术支持交接草稿，建议一线支持耐心观察，切勿重复重试。
     - 当 Receiver 为 `PROCESSED` 时：准确断言“已处理完成”，整理确认完毕的交接草稿。
     - 证明成对观察驱动了完全不同的业务事实结论与处置建议。
   - **安全与防篡改：** 严密验证未授权文档（如 `api-scope-current`）不可发现，跨会话、跨租户与篡改文档注入被强硬拒绝。
   - **Trace 审计持久化：** 自动导出包含 29 条完整真实记录的 `dialog_trace.json`。

---

## 2. 正式六问自检（North Star 第 8 节 / SKILL.md B 节）

1. **用户变化：**
   用户现在完全不需要知道类似 `callback-retry-contract-v2` 的内部 ID，就能在自然语言对话中获得两项新业务能力：① 自动获知授权范围内的协议版本演进与重试退避差异；② 结合订单绑定状态获得可靠结论——未绑定时诚实说明无法核查，绑定后根据 QUEUED vs PROCESSED 准确区分 HTTP 202 的传输受理与下游业务完成，并获得结构化的技术支持交接草稿。

2. **Agent 决策：**
   模型自主决定：① 何时调用 `list_scoped_protocol_documents` 发现版本；② 是否继续调用 `compare_scoped_protocols` 比对差异；③ 在未绑定订单时自主判断缺乏业务观测上下文，决定不凭空虚构客户订单状态并提出绑定建议；④ 在绑定订单后自主调用 `get_callback_delivery` 与 `get_receiver_processing` 收集事实并输出分析。程序只守住会话、项目白名单和不可变 TaskBinding 边界。

3. **观察驱动：**
   成对观察驱动完全不同的合法行动：
   - 观察 1：无 `task_id`（未绑定）→ 模型输出“未建立 TaskBinding，无法核查具体客户处理事实”，行动为建议用户绑定；
   - 观察 2：有绑定且 Receiver 状态为 `QUEUED`（HTTP 202）→ 结论为“尚未处理完成”，行动为建议技术支持监控队列且切勿重复重试；
   - 观察 3：有绑定且 Receiver 状态为 `PROCESSED`（HTTP 202）→ 结论为“已处理完成”，行动为建议办结交接。

4. **约束双向检查：**
   - 拦截风险：严格阻断未授权文档发现与比对（如 `api-scope-current` 或恶意 ID）；拒绝跨会话、跨租户冒用发现结果；拒绝将 HTTP 202 误认为处理终态。
   - 保护合法：已授权的合法历史协议（如 v1.0.0 与 v2.0.0 回调重试规范）始终能够顺畅发现与比对，正反向用例均经过严格测试验证通过。

5. **责任归属与简化：**
   未新增任何多余的全局权限体系、流程引擎或状态机。复用了已有的 `get_session_project()` 机制和 Manifest 清单解析，代码增量仅聚焦于一个发现函数、一个 MCP 工具及一个来源校验分支。

6. **证据与停止线：**
   - 冻结证据：4 项 AR-03-04 业务闭环测试全部通过，全量 72 项关联测试 100% 通过（0 失败）。
   - 持久化 Trace：生成 `docs/evidence/ar-03/upgrade-investigation/dialog_trace.json`（包含 3 个 Runs、13 个 Calls、10 个 Messages、3 个 Model Summaries）。
   - 停止线：本切片到此收口，不进入多 Agent、不触碰 Codex 主线、不修改 `main`。

---

## 3. 验收核验与裁决建议

> **用户变化：** 实现了无需内部文档 ID 的自然语言协议版本发现、比对差异分析，以及区分未绑定/QUEUED/PROCESSED 的完整业务闭环。
> **Agent 决策：** 模型自主决定是否发现协议、是否比对、何时拒绝虚构订单状态、何时结合 S3 事实整理交接草稿。
> **观察驱动：** 未绑定 vs QUEUED vs PROCESSED 成对观察驱动了截然不同的事实结论与处置建议。
> **新增约束：** 保护未授权文档隔离与来源防伪造；经双向核验合法版本比对与合规调查完全畅通。
> **简化结果：** 零新增框架，零新增数据库表，纯复用现有项目注册表与 MCP 机制。
> **证据与停止线：** 4/4 专项测试通过，全量 72/72 回归通过；生成完整 dialog_trace.json；真实付费 LLM 调用为 0。

**状态提交：`ACCEPTANCE_CANDIDATE`**
