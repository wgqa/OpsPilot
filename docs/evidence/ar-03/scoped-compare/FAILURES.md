# AR-03-02 失败模式与安全拦截矩阵 (FAILURES.md)

本文件记录 AR-03-02 会话授权协议比较切片的负向防御机制、越权拦截矩阵与未解决/保留的不确定性边界。

## 1. 负向安全与越权拦截矩阵（全部经过真实测试验证）

| 编号 | 触发场景 | 拦截异常 / 错误码 | 保护机制 | 对应测试 |
|---|---|---|---|---|
| NEG-01 | 跨租户调用：`tenant-b` 角色试图访问 `tenant-a` 的项目或 Session | `KnowledgeScopeDenied("SESSION_SCOPE_DENIED" / "KNOWLEDGE_SCOPE_DENIED")` | SQLite Session 归属校验及 `REGISTRY` 租户严格匹配 | `test_cross_tenant_access_denied` |
| NEG-02 | 越权文档访问：Session 仅授权 `orders-callback` 项目，试图比较未授权的 `api-scope-current` | `DocumentNotAuthorizedError("DOCUMENT_NOT_AUTHORIZED")` | 服务端核验 `document_id in project["document_ids"]`，阻断跨项目/任意目录读取 | `test_unauthorized_document_rejected` |
| NEG-03 | 伪造路径或摘要：调用方试图向服务传入任意磁盘文件绝对路径或伪造的可信 Digest | 编译期与运行时接口拒绝：接口仅接收 `document_id` 与可选 `version`；摘要由可信 Catalog 读取 | 严格服务端解析，模型无权输入 path/digest | `test_scoped_comparison_callback_retry_real_business_documents` |
| NEG-04 | 范围歧义未选择：存在多个合法项目但会话尚未指定 `selected_project` | `KnowledgeScopeDenied("KNOWLEDGE_SCOPE_SELECTION_REQUIRED")` | 阻止在未明确项目时模糊匹配文档 | `test_selection_required_when_multiple_projects_unselected` |
| NEG-05 | 切换上下文后重放：使用旧项目生成的比较结果在新项目会话中请求持续有效性 | `is_valid=False, reason="KNOWLEDGE_SESSION_SCOPE_CHANGED"` | `scoped_comparison_is_current` 校验 `result.project_id == active_project` | `test_scope_switch_invalidates_previous_result` |
| NEG-06 | 授权撤销拦截：项目在注册表中被标记为 `active: false` | `KnowledgeScopeDenied("KNOWLEDGE_SCOPE_DENIED")` | 每次调用均动态重新读取注册表，停用后立即拒绝 | `test_project_deactivation_revokes_authorization` |
| NEG-07 | 授权版本升级：管理端更新了授权定义（`grant_version` 从 1 升为 2） | `is_valid=False, reason="KNOWLEDGE_GRANT_CHANGED"` | 校验 `result.grant_version == active_grant_version` 与 `scope_digest` | `test_grant_version_bump_invalidates_old_result` |
| NEG-08 | 单文档移出授权：管理员将某一版本文档移出 `document_ids` | `is_valid=False, reason="DOCUMENT_AUTHORIZATION_REVOKED"` | 校验双方文档是否依然属于当前授权集合 | `test_document_removal_from_grant_revokes_result` |
| NEG-09 | 磁盘文件篡改或哈希不匹配：底层 Markdown 文件被外部修改 | `is_valid=False, reason="DOCUMENT_INTEGRITY_OR_EXPIRED"` | 实时核对实际内容 SHA-256 与 manifest 记录摘要 | `test_disk_file_tampering_invalidates_scoped_comparison` |
| NEG-10 | 空或非法引用参数：输入空字符串或全空格作为文档 ID | `InvalidReferenceError("MISSING_OR_INVALID_REFERENCE")` | 输入前置合法性防护 | `test_invalid_input_parameters_fail_closed` |

---

## 2. 认知边界与停止线声明

1. **静态文档差异无法证明线上运行状态：**
   - 比较结果中恒定保留 `deployment_version_verified: False` 与 `unconfirmed_aspects` 警示。
   - 即使比较双方是当前项目的 v1 与 v2 规范，Agent 也绝对不能断言“客户系统当前部署了 v2”。确认部署行为必须依赖独立且经过安全验证的运行时观测工具。
2. **只读调查证据，不构成动作授权：**
   - 本服务输出携带 `"authority": "SESSION_AUTHORIZED_INVESTIGATION_EVIDENCE_NOT_ACTION_AUTHORIZATION"`。
   - 输出属于 Agent 调查阶段的 Observation/Evidence，不得作为绕过 Policy、TaskControl、Approval 或 ActionIntent 写入的凭证。
