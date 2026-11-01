# AR-03-01 失败模式与负向门禁测试记录 (FAILURES.md)

本文件记录 AR-03-01 协议版本比较独立垂直切片在开发与测试过程中所覆盖的负向测试矩阵、异常路径及失败防御边界。

## 负向测试与防御矩阵

| 编号 | 测试用例 | 触发条件 | 预期行为 / 状态码 | 实际测试状态 |
|---|---|---|---|---|
| F-01 | `test_missing_or_empty_references` | `base_ref=None` 或缺少 `document_id` / `version` | 抛出 `InvalidReferenceError`，安全包装返回 `MISSING_OR_INVALID_REFERENCE`，拒绝比较 | PASS (通过) |
| F-02 | `test_invalid_reference_fields` | `digest` 不是 64 位十六进制 SHA-256 字符串 | 抛出 `InvalidReferenceError`，拒绝比较 | PASS (通过) |
| F-03 | `test_document_not_found` | 引用不存在的协议文档 ID 或版本号 | 抛出 `DocumentNotFoundError`，安全包装返回 `DOCUMENT_NOT_FOUND` | PASS (通过) |
| F-04 | `test_source_mismatch_rejection` | 引用声明的 `source` 与目录清单 `source` 不一致 | 抛出 `DocumentSourceMismatchError`，安全包装返回 `DOCUMENT_SOURCE_MISMATCH`，防冒充来源 | PASS (通过) |
| F-05 | `test_reference_digest_mismatch` | 引用给出的 `digest` 与文档实际 SHA-256 不符 | 抛出 `DocumentIntegrityError`，安全包装返回 `DOCUMENT_DIGEST_MISMATCH` | PASS (通过) |
| F-06 | `test_disk_file_tampering_detected` | 磁盘文件内容被篡改，与清单 SHA-256 不一致 | 抛出 `DocumentIntegrityError`，识别文档完整性被破坏 | PASS (通过) |
| F-07 | `test_expired_document_rejection` | 检查时间在 `expires_at` 之后 | 抛出 `DocumentExpiredError`，安全包装返回 `DOCUMENT_EXPIRED`，阻断过期规范比较 | PASS (通过) |
| F-08 | `test_premature_document_rejection` | 检查时间在 `valid_from` 之前 | 抛出 `DocumentExpiredError`，识别文档尚未生效 | PASS (通过) |
| F-09 | `test_inactive_document_rejection` | 清单中标记 `active=false` | 抛出 `DocumentExpiredError`，阻断停用规范比较 | PASS (通过) |
| F-10 | `test_cannot_prove_live_deployment_version` | 任何版本的文档比较请求 | `deployment_version_verified` 恒为 `False`，`unconfirmed_aspects` 包含明确线上未验证警示 | PASS (通过) |
| F-11 | `test_prompt_injection_in_document_content_is_treated_as_untrusted_data` | 文档内容注入越权指令（如要求跳过审批、自动修复） | 纯作为不可信数据文本进行差异比对，不改变权限、不执行指令、不影响安全门禁 | PASS (通过) |
| F-12 | `test_path_traversal_in_manifest_fails_closed` | 清单中使用 `../` 目录遍历试图读取外部文件 | 抛出 `DocumentIntegrityError`，安全闭锁，禁止文件逃逸 | PASS (通过) |

## 边界与防 Workflow 漂移确认

1. **认知边界（Epistemic Boundary）：** 文档比较是静态只读规范比对，绝对不能代替线上环境实际部署版本的探针结果。即便 v2 协议文档是最新的，也不得推断生产集群当前运行的就是 v2。
2. **安全隔离（Safety Isolation）：** 本切片为纯只读模块，不注册任何写动作、不修改数据库事务、不接入外部网络或付费 Provider。
3. **内容指令防御（Prompt Injection Defense）：** 文档全文作为不可信数据流解析，算法基于确定性差异引擎，严禁将文档文本拼接为系统指令或交由模型无界执行。
