# AR-03-03 失败模式与安全拦截矩阵 (FAILURES.md)

本文件记录 AR-03-03 协议比较进入真实 Agent 调查切片的负向防御机制、越权拦截矩阵与认知边界。

## 1. 负向安全与越权拦截矩阵（全部经过真实测试验证）

| 编号 | 触发场景 | 拦截结果 / 错误码 | 保护机制 | 对应测试 |
|---|---|---|---|---|
| NEG-01 | 模型请求未授权文档：模型尝试对比 `unauthorized-secret-spec` | `success=False, error="DOCUMENT_NOT_AUTHORIZED", authority="TOOL_REFUSAL_NOT_FACT"` | 服务端核验文档属于当前 Session 的 project["document_ids"]，不返回任何正文或摘要 | `test_unauthorized_document_compare_fails_closed_without_leakage` |
| NEG-02 | 跨 Session 历史结果冒用：攻击者或上下文将 Session-A 的有效比对结果置入 Session-B | `is_valid=False, reason="CROSS_SESSION_COMPARISON_REJECTED"` | `scoped_comparison_is_current` 严格核验 `data["session_id"] == session_id` | `test_cross_session_and_cross_tenant_old_result_rejection` |
| NEG-03 | 跨租户结果冒用：Tenant-B 试图引用 Tenant-A 的比对结果 | `is_valid=False, reason="CROSS_TENANT_COMPARISON_REJECTED"` | 严格核验 `data["tenant_id"] == identity.tenant_id` | `test_cross_session_and_cross_tenant_old_result_rejection` |
| NEG-04 | 跨操作者结果冒用：不同 Actor 试图接管彼此的对比证据 | `is_valid=False, reason="ACTOR_MISMATCH"` | 严格核验 `data["actor_id"] == identity.actor_id` | `test_cross_session_and_cross_tenant_old_result_rejection` |
| NEG-05 | 模型篡改结果字段：模型伪造/修改比对字典，将 `identical` 改为 `True` | `is_valid=False, reason="COMPARISON_DIGEST_MISMATCH"` | 重构 `res_data` 并核对 SHA-256 `comparison_digest`，检测任何单字段篡改 | `test_tampered_model_modified_comparison_result_rejection` |
| NEG-06 | 模型增删差异项：模型人为删除部分差异条目，掩盖协议变更 | `is_valid=False, reason="COMPARISON_DIGEST_MISMATCH"` | 差异数组与摘录哈希进入摘要校验，列表改变导致摘要不符 | `test_tampered_model_modified_comparison_result_rejection` |
| NEG-07 | 篡改 `diff_count`：模型虚报差异条数 | `is_valid=False, reason="COMPARISON_DIGEST_MISMATCH"` | `diff_count` 纳入摘要比对，篡改即被拒绝 | `test_tampered_model_modified_comparison_result_rejection` |
| NEG-08 | 试图输入任意文件路径：模型在工具参数中尝试传参绝对路径或 URL | MCP 契约拒绝：工具 schema 仅接受 `base_document_id`, `target_document_id` 等，路径解析完全在服务端限制的 Manifest 目录中 | 杜绝任意路径穿越与越权文件读取 | `test_direct_mcp_client_tool_enumeration_and_call` |

---

## 2. 认知边界与停止线声明

1. **静态协议比对不能替代线上集群真实状态：**
   - 比较工具返回明确的 `deployment_version_verified: False` 标志与 `unconfirmed_aspects` 列表。
   - Agent 必须在回答中向技术支持人员澄清：静态规范仅定义了设计预期与错误代码分类；当前线上网关是否已经部署或启用了该规范，必须依靠真实的线上观测或控制台确认。
2. **只读调查工具不得产生任何业务写入：**
   - `compare_scoped_protocols` 带有 `read_only_hint=True, open_world_hint=False` 强注解。
   - 不生成任何 TaskBinding、ActionIntent、审批或修复回执。
