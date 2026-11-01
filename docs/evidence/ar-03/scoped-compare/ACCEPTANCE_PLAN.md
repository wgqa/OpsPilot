# AR-03-02 验收计划与前置检查记录 (ACCEPTANCE_PLAN.md)

## 0. 任务元数据

- **任务卡：** OpsPilot — AR-03-02：会话授权的协议版本比较
- **任务状态：** `AUTHORIZED_FREE_IMPLEMENTATION_ONLY`
- **基线提交（Base SHA）：** `antigravity/ar03-01-hf01@9d024781c62deba457522a5dd5b66dcca0a97930`
- **开发分支：** `antigravity/ar03-02-scoped-compare`
- **独立 Git Worktree：** `.worktrees/ar03-02-scoped-compare`
- **目标：** 让已有独立协议比较能力能够在受信 Session 和 Project 授权范围内被安全、真实地调用，阻断越权和未授权访问，为未来由 LLM 自主选择调用协议比对工具完成授权闭环。

---

## 1. 审查前置核验区块

本轮开发严格在独立 Worktree `.worktrees/ar03-02-scoped-compare` 中进行，前置只读核验确认：
1. **准则文档核验：**
   - `PROJECT_NORTH_STAR.md`（Blob: `1f737712c7a36ceb34433ac09c3fbba3c3305542`）已完整阅读并遵守
   - `AGENTS.md`（Blob: `32c45506cceeaa8c76a5c56bf8360ff476b58856`）已完整阅读并遵守
   - `.agents/skills/opspilot-slice-review/SKILL.md`（Blob: `d405c8d413d633824b279202cc1503dab4cf0b03`）已完整阅读并遵守
2. **原始根目录状态检查结果：**
   - 原始工作区处于 `antigravity/ar03-protocol-compare` 分支，tracked 文件无任何未提交改动。
   - `git stash list` 确认为空。
   - `.agents` 目录完整且 Blob 哈希一致，未作任何清理或删除。
   - 所有用户未跟踪目录（`.pytest-*`, `开发目录/...`）完整保留。
3. **工作区隔离与 Codex 并行主线安全：**
   - Codex 的 AR-02 主线（`codex/ar02-live-01`）保持独立运行，未发生任何分支污染、合并或覆盖。

---

## 2. 冻结范围与修改边界

| 模块 | 权限 | 实际变更说明 |
|---|---|---|
| `opspilot/domain/assistant_knowledge.py` | 最小接口扩展 | 新增 26 行可复用只读接口 `get_session_project()`，支持 Session 鉴权、租户校验与项目解析，不修改任何现有逻辑 |
| `opspilot/domain/scoped_protocol_comparison.py` | 允许新增 | 新增轻量 Domain 桥接模块，实现 `compare_scoped_protocols`, `compare_scoped_protocols_safe`, `scoped_comparison_is_current` |
| `tests/test_ar03_02_scoped_protocol_comparison.py` | 允许新增 | 新增 15 项专项测试覆盖真实业务文档比较与全量反向越权测试 |
| `docs/evidence/ar-03/scoped-compare/*` | 允许新增 | 新增验收计划、交付报告、测试结果、失败模式与未来 Assistant 集成注册点契约 |
| `opspilot/assistant*.py`, `worker.py`, `app.py`, `chat.py`, TaskControl | **绝对严禁修改** | 保持 0 修改 |
| `main` 分支与 Codex 分支 | **绝对严禁合并或修改** | 保持 0 修改 |

---

## 3. 验收用例规划与执行矩阵

- **AR03-02 专项测试（15 项全 PASS）：**
  1. `test_scoped_comparison_callback_retry_real_business_documents`：真实 `callback-retry-contract` v1 vs v2 会话授权比较成功，差异、摘录与摘要准确。
  2. `test_scoped_comparison_order_lifecycle_real_business_documents`：真实 `order-lifecycle-contract` v1 vs v2 比较成功，Digest 与版本号一致。
  3. `test_unauthorized_document_rejected`：跨目录访问未授权文档（`api-scope-current`）被坚决拒绝（`DOCUMENT_NOT_AUTHORIZED`）。
  4. `test_cross_tenant_access_denied`：跨租户（tenant-b 调用 tenant-a 资源或篡改 Session）被坚决拒绝（`SESSION_SCOPE_DENIED`）。
  5. `test_selection_required_when_multiple_projects_unselected`：多项目未明确选择时抛出 `KNOWLEDGE_SCOPE_SELECTION_REQUIRED`。
  6. `test_scope_switch_invalidates_previous_result`：会话切换项目后，旧项目的比较结果重新校验失败（`KNOWLEDGE_SESSION_SCOPE_CHANGED`）。
  7. `test_project_deactivation_revokes_authorization`：项目停用（`active: false`）阻断新比对并立即使历史结果失效。
  8. `test_grant_version_bump_invalidates_old_result`：授权策略版本升级（`grant_version` 从 1 升为 2）使旧结果失效。
  9. `test_document_removal_from_grant_revokes_result`：文档被移出授权清单（`document_ids`）后历史结果失效（`DOCUMENT_AUTHORIZATION_REVOKED`）。
  10. `test_historical_version_comparison_permitted`：合法历史版本（v1）不因当前项目配置版本为 v2 而被错误拒绝。
  11. `test_invalid_input_parameters_fail_closed`：空文档引用参数拒绝执行（`MISSING_OR_INVALID_REFERENCE`）。
  12. `test_nonexistent_document_fails_closed`：清单中存在但磁盘缺失的文档拒绝执行（`DOCUMENT_NOT_FOUND`）。
  13. `test_disk_file_tampering_invalidates_scoped_comparison`：磁盘文件内容被篡改后，重新校验检测到摘要不匹配并报错。
  14. `test_safe_wrapper_returns_structured_error_on_various_failures`：Safe 包装器捕获鉴权、授权及文件错误并返回结构化错误码，不崩溃。
  15. `test_same_document_id_with_explicit_versions`：支持单个 `document_id` 拥有多个 `version` 时的显式版本选择比较。
- **历史回归测试（38 项全 PASS）：**
  - `tests/test_ar03_protocol_comparison.py`（28 项全部通过）
  - `tests/test_ar02_knowledge.py`（10 项全部通过）
