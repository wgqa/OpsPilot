# AR-03-04 验收计划与前置检查记录 (ACCEPTANCE_PLAN.md)

## 0. 任务元数据

- **任务卡：** OpsPilot — AR-03-04：协议升级影响调查业务闭环
- **任务状态：** `ACCEPTANCE_CANDIDATE`
- **基线提交（Base SHA）：** `antigravity/ar03-03-agent-integration@7dfdf2525243fe9049703fd47703e2b1a7257345`
- **开发分支：** `antigravity/ar03-04-upgrade-investigation`
- **独立 Git Worktree：** `.worktrees/ar03-04-upgrade-investigation`
- **目标：** 用户无需记忆或提供内部文档 ID（如 `callback-retry-contract-v2`），通过自然语言提出协议升级影响调查问题，Agent 自主完成“授权文档发现 → 版本比对 → 结合可信业务观察判断影响 → 输出技术支持交接草稿与未知事项”的业务闭环。

---

## 1. 审查前置核验区块

本轮开发严格在独立 Worktree `.worktrees/ar03-04-upgrade-investigation` 中进行，前置只读核验确认：
1. **权威准则文档核验：**
   - `PROJECT_NORTH_STAR.md`（Blob: `1f737712c7a36ceb34433ac09c3fbba3c3305542`）已完整重新阅读并严格遵守
   - `AGENTS.md`（Blob: `32c45506cceeaa8c76a5c56bf8360ff476b58856`）已完整重新阅读并严格遵守
   - `.agents/skills/opspilot-slice-review/SKILL.md`（Blob: `d405c8d413d633824b279202cc1503dab4cf0b03`）已完整重新阅读并严格执行
2. **原始根目录状态检查结果：**
   - 原始工作区处于 `antigravity/ar03-protocol-compare` 分支，tracked 文件无任何未提交改动。
   - `git stash list` 确认为空。
   - `.agents` 目录完整且 Blob 哈希一致（`d405c8d4...`），未作任何破坏性修改或删除。
   - 所有用户未跟踪目录完整保留。
3. **工作区隔离与并行分支安全：**
   - Codex 的 AR-02 主线（`codex/ar02-live-01`）保持独立运行，绝对零合并、零覆盖、零污染。
   - `main` 分支未做任何修改。
   - 零付费 Provider 调用，零外部未经授权副作用。

---

## 2. 冻结范围与修改边界

| 模块 | 权限 | 实际变更说明 |
|---|---|---|
| `opspilot/domain/scoped_protocol_comparison.py` | 明确授权扩展 | 1. 新增 `list_scoped_protocols(db, identity, session_id, topic=None)`：在会话受信项目授权下发现真实存在的协议版本与协议族，支持 topic 关键字过滤，严防越权泄露，带 `deployment_version_verified: False`。<br>2. 新增 `scoped_discovery_is_current(db, identity, session_id, discovery_result)`：对发现结果实施会话、租户、操作者、项目范围及清单摘要完整性校验。 |
| `opspilot/assistant_mcp.py` | 明确授权扩展 | 注册只读工具 `list_scoped_protocol_documents(topic: str | None = None)`，从受信 Run 上下文注入身份与会话，使模型在无需预知内部文档 ID 的情况下自主发现合法协议版本。 |
| `opspilot/domain/assistant.py` | 最小来源再验证适配 | 在 `sources_current()` 中为 `protocol_documents` / `protocols` 接入 `scoped_discovery_is_current` 校验，实现协议发现结果的持续有效性保护。 |
| `tests/test_ar03_04_upgrade_investigation.py` | 允许新增 | 新增业务闭环核心测试：旅程 A（未绑定订单诚实比对与拒绝冒充查询）、旅程 B（绑定订单下 QUEUED vs PROCESSED 截然不同的事实结论与交接草稿）、发现授权隔离与防篡改单测、以及全链路 Trace 持久化。 |
| `docs/evidence/ar-03/upgrade-investigation/*` | 允许新增 | 新增验收计划、交付报告（含六问长表）、测试结果与已知缺陷说明、全链路执行 Trace。 |
| `opspilot/assistant.py`, `worker.py`, `app.py`, `chat.py`, TaskControl | **无须修改** | 保持架构纯洁性，零修改。 |
| `main` 分支与 Codex 主线 | **绝对严禁合并或修改** | 保持 0 修改。 |

---

## 3. 验收用例规划与执行矩阵

- **AR03-04 专项业务与安全闭环测试（4/4 全 PASS）：**
  1. `test_journey_a_unbound_order_discovers_and_compares_protocols`：旅程 A 闭环。用户未提供内部文档 ID 提问“我们最近升级了回调协议，客户反馈重试行为变了。你帮我找一下旧版、新版规范，分析有什么变化，再看看客户是不是已经处理完成了。”模型自主调用 `list_scoped_protocol_documents(topic='retry')` 发现 v1 与 v2，调用 `compare_scoped_protocols` 分析差异，明确说明未绑定订单无法核查客户实际处理状态，建议用户通过可信订单操作绑定 `ar02-order`。状态为 SUCCEEDED，`sources_current` 校验通过。
  2. `test_journey_b_bound_order_queued_vs_processed_distinction[QUEUED]`：旅程 B1。绑定 `ar02-order`，接收端为 QUEUED，HTTP 202。模型准确区分传输受理与下游业务完成，得出“尚未处理完成”结论，整理技术支持交接草稿，建议一线支持耐心等待排队消费，切勿重复重试。零业务写入与修改。
  3. `test_journey_b_bound_order_queued_vs_processed_distinction[PROCESSED]`：旅程 B2。同一用户提问，接收端为 PROCESSED，模型基于真实事实得出“已处理完成”结论，整理技术支持交接草稿，确认处理完毕。证明不同客观事实产出不同结论。
  4. `test_scoped_protocol_discovery_safety_and_revalidation`：安全底线双向核验。未授权文档（如 `api-scope-current`）绝对不可被发现；伪造跨会话、跨租户、操作者不匹配、未授权文档注入均被 `scoped_discovery_is_current` 严格拦截拒绝。

- **关联全量回归测试（68/68 项全 PASS）：**
  - `tests/test_ar03_03_agent_integration.py`：5/5 PASS
  - `tests/test_ar03_02_scoped_protocol_comparison.py`：15/15 PASS
  - `tests/test_ar03_protocol_comparison.py`：28/28 PASS
  - `tests/test_ar02_assistant.py`：3/3 PASS
  - `tests/test_ar02_knowledge.py`：10/10 PASS
  - `tests/test_ar02_journey_p0.py`：7/7 PASS
  - **总计：72/72 项测试全部通过（0 失败，0 告警阻断）。**
