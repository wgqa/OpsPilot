# AR-03-03 验收计划与前置检查记录 (ACCEPTANCE_PLAN.md)

## 0. 任务元数据

- **任务卡：** OpsPilot — AR-03-03：协议比较进入真实 Agent 调查
- **任务状态：** `ACCEPTANCE_CANDIDATE`
- **基线提交（Base SHA）：** `antigravity/ar03-02-scoped-compare@af9d7433803c756f6f9a7baee3b16276e4da7f41`
- **开发分支：** `antigravity/ar03-03-agent-integration`
- **独立 Git Worktree：** `.worktrees/ar03-03-agent-integration`
- **目标：** 让用户通过正式 Assistant 对话提出协议升级影响问题，由 Agent 自主决定是否调用版本比较工具，并给出有来源的调查回答；补齐旧比较结果的 Session/租户/操作者关联校验，完成一条真实端到端 API -> Worker -> Assistant -> MCP -> 协议比较 -> Session 答案的旅程。

---

## 1. 审查前置核验区块

本轮开发严格在独立 Worktree `.worktrees/ar03-03-agent-integration` 中进行，前置只读核验确认：
1. **准则文档核验：**
   - `PROJECT_NORTH_STAR.md`（Blob: `1f737712c7a36ceb34433ac09c3fbba3c3305542`）已完整重新阅读并遵守
   - `AGENTS.md`（Blob: `32c45506cceeaa8c76a5c56bf8360ff476b58856`）已完整重新阅读并遵守
   - `.agents/skills/opspilot-slice-review/SKILL.md`（Blob: `d405c8d413d633824b279202cc1503dab4cf0b03`）已完整重新阅读并遵守
2. **原始根目录状态检查结果：**
   - 原始工作区处于 `antigravity/ar03-protocol-compare` 分支，tracked 文件无任何未提交改动。
   - `git stash list` 确认为空。
   - `.agents` 目录完整且 Blob 哈希一致（`d405c8d4...`），未作任何清理或删除。
   - 所有用户未跟踪目录完整保留。
3. **工作区隔离与 Codex 并行主线安全：**
   - Codex 的 AR-02 主线（`codex/ar02-live-01`）保持独立运行，未发生任何分支污染、合并或覆盖。
   - `main` 分支未做任何修改。

---

## 2. 冻结范围与修改边界

| 模块 | 权限 | 实际变更说明 |
|---|---|---|
| `opspilot/assistant_mcp.py` | 明确授权注册工具 | 注册只读 `compare_scoped_protocols` 工具，服务端自动从当前 Run 注入 Identity、Session、DB 路径与 Manifest Catalog；模型仅提供两个文档 ID 及可选版本，返回带 `deployment_version_verified: False` 结构化事实。 |
| `opspilot/domain/scoped_protocol_comparison.py` | 增强关联与防篡改 | 补齐 `scoped_comparison_is_current()` 中的 `session_id`、`tenant_id`、`actor_id` 强校验；增加重构摘要哈希防篡改校验（`COMPARISON_DIGEST_MISMATCH`）；支持模型传入简短版本（如 `"1"` 匹配 `"1.0.0"`）。 |
| `opspilot/domain/assistant.py` | 最小来源再验证适配 | 在 `sources_current()` 中接入 `compare_scoped_protocols` 结果的持续有效性再验证，拒绝跨 Session 或被篡改的比对历史。 |
| `tests/test_ar03_03_agent_integration.py` | 允许新增 | 新增端到端正式 API -> Worker -> Assistant -> MCP 真实流转旅程，覆盖越权文档拒绝、跨 Session 拒绝、模型篡改字典拒绝及 MCP stdio 协议直连验证。 |
| `docs/evidence/ar-03/agent-integration/*` | 允许新增 | 新增验收计划、交付报告、测试结果、失败模式与真实 LLM 离线/在线评测方案。 |
| `opspilot/assistant.py`, `worker.py`, `app.py`, `chat.py`, TaskControl | **无须修改** | 保持架构纯洁性，零修改。 |
| `main` 分支与 Codex 主线 | **绝对严禁合并或修改** | 保持 0 修改。 |

---

## 3. 验收用例规划与执行矩阵

- **AR03-03 专项测试（5 项全 PASS）：**
  1. `test_formal_api_worker_mcp_protocol_compare_journey`：完整正式链路旅程。用户通过 Web API 发起“客户反馈升级回调协议后行为变化”，Worker 调度 Assistant_V1，LangGraph Agent 决定调用 MCP `compare_scoped_protocols`，获取 `callback-retry-contract` v1 vs v2 真实比对，生成带具体差异、潜在影响和未确定事项（`deployment_version_verified: False`）的回答；Persisted MCP 调用状态为 OK 并通过 `sources_current` 校验。
  2. `test_unauthorized_document_compare_fails_closed_without_leakage`：越权防御旅程。调用未授权保密文档时，MCP 工具返回结构化拒绝对话，模型友好回答权限拒绝，无数据泄露，`sources_current` 维持安全。
  3. `test_cross_session_and_cross_tenant_old_result_rejection`：跨 Session 与跨租户重放拒绝。不同 Session、不同租户或不同操作者复用旧结果时，`scoped_comparison_is_current` 立即拦截并返回 `CROSS_SESSION_COMPARISON_REJECTED` / `CROSS_TENANT_COMPARISON_REJECTED` / `ACTOR_MISMATCH`。
  4. `test_tampered_model_modified_comparison_result_rejection`：防篡改重构验证。任何第三方或模型篡改 `identical` 标志、增删 `differences` 项或篡改数量，将被摘要重构机制捕获并拒绝（`COMPARISON_DIGEST_MISMATCH`）。
  5. `test_direct_mcp_client_tool_enumeration_and_call`：MCP stdio 接口契约。验证 `assistant_mcp` 真实子进程通过 stdio 正确暴露工具架构并支持客户端调用。

- **关联全量回归测试（63 项全 PASS）：**
  - `tests/test_ar03_02_scoped_protocol_comparison.py`：15/15 PASS
  - `tests/test_ar03_protocol_comparison.py`：28/28 PASS
  - `tests/test_ar02_assistant.py`：3/3 PASS
  - `tests/test_ar02_knowledge.py`：10/10 PASS
  - `tests/test_ar02_journey_p0.py`：7/7 PASS
  - **总计：68/68 项测试全部通过（0 失败，0 告警阻断）。**
