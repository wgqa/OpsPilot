# AR-03-01 协议知识版本比较独立切片验收报告 (REPORT.md)

## 审查前置核验

- **Repo / Branch：** `wgqa/OpsPilot` / `antigravity/ar03-protocol-compare`
- **Base SHA：** `5a53815b0baea50d7b99afa2b0020e7f96f62517`
- **Candidate HEAD SHA：** 待提交后记录（独立分支 `antigravity/ar03-protocol-compare`）
- **Diff 范围：** 纯新增 `opspilot/domain/protocol_comparison.py`、`tests/test_ar03_protocol_comparison.py`、`docs/evidence/ar-03/protocol-compare/**`，未修改任何受控核心文件。
- **`PROJECT_NORTH_STAR.md`：** 已实际读取；Blob `1f737712c7a36ceb34433ac09c3fbba3c3305542`
- **`AGENTS.md`：** 已实际读取；Blob `32c45506cceeaa8c76a5c56bf8360ff476b58856`
- **`.agents/skills/opspilot-slice-review/SKILL.md`：** 已实际读取；Blob `d405c8d413d633824b279202cc1503dab4cf0b03`
- **任务卡、冻结合同、遗留门禁：** AR-03-01 协议版本比较独立垂直切片任务卡；严格遵循不可修改 `assistant.py`, `worker.py`, `app.py`, `chat.py`, TaskControl 与审批的边界。
- **实际审查方法：** 源码静态核验、单元/集成测试亲自复跑 (19/19 PASSED)、知识回归测试亲自复跑 (10/10 PASSED)、样例比对输出生成与 JSON Schema 校验。
- **证据缺失与范围限制：** 本阶段为纯只读模块，不接入生产 Assistant/Worker/MCP 工具注册，不发起真实 Provider 请求，无数据库写副作用。

---

## 规划与设计六问回答

1. **用户变化：** 用户与调查 Agent 在排查涉及协议升级或版本演进的故障（如订单异步回调 v1 到 v2 的 SLA 参数、异步发布、重试次数限制变更）时，可以通过受信任的文档引用直接获取确定性的、带 SHA-256 证据摘录与行级定位的协议版本结构化差异，避免模型凭空捏造差异。
2. **Agent 决策：** Agent 可以在后续集成中自主决定何时调取两版本的协议差异进行对齐分析，但模型无法伪造证据摘要，且无法将静态文档差异等同于线上真实部署环境。
3. **观察驱动：** 成对观察驱动——当输入两个完全相同的合法版本引用时，系统确定性给出 `identical=True`, `diff_count=0`；当输入 v1 与 v2 协议时，系统输出精确的结构化差异（如新增 `attempt_count`, `max_attempts` 参数，新增 `ASYNC_PUBLICATION` 行为准则），并附带行号与原文 SHA-256。
4. **约束双向检查：**
   - **阻断的风险：** 伪造引用来源 (`DOCUMENT_SOURCE_MISMATCH`)、篡改的文件或引用 digest (`DOCUMENT_DIGEST_MISMATCH`)、过期或未生效文档 (`DOCUMENT_EXPIRED`)、目录穿越攻击 (`MALFORMED_CATALOG_FILE_ENTRY`)、提示词注入劫持、以及冒充线上已部署状态。
   - **保留的合法路径：** 相同版本幂等比对、合法新旧版本比对、包含 legacy 标记的历史文档比对、以及通过 `compare_protocols_safe` 提供的结构化优雅拒绝。
5. **责任归属和简化：** 沿用现有 `knowledge/` 资产目录与清单规范，不重复建设检索系统；比对逻辑纯函数化、确定性实现，不引入模型推理开销与外置工作流框架。
6. **证据与停止线：** 19 项专用测试全绿，10 项现有知识测试回归通过，6 份样例比对 JSON 落盘，严格保持在只读独立模块，不提前接入生产路由，停止线清晰。

---

## 核心实现说明

1. **`resolve_document` 函数：**
   - 严格校验 `DocumentRef`（`document_id`, `version`, `digest`, `source`）。
   - 在受信目录清单中匹配条目，严格核实清单 `source`。
   - 验证文件路径合法性，防止 `..` 目录遍历。
   - 读取磁盘原始字节，校验实际 SHA-256 与清单 digest 及引用 digest 的双向一致性。
   - 校验生效时间 `valid_from` 与过期时间 `expires_at`，支持传入 `as_of` 进行时间回溯或基准校验。
2. **`compare_protocol_versions` 函数：**
   - 相同内容与哈希判定：返回 `identical=True` 与 `diff_count=0`。
   - Markdown 章节级切分与差异比较：定位到 Heading 级别，识别新增、删除与修改的章节。
   - 关键协议特征提取：识别状态码（200, 202, 401, 403, 503 等）、协议参数（`event_id`, `processing_sla_seconds`, `attempt_count` 等）与行为约束（`PROHIBIT_AUTO_RESEND`, `ASYNC_PUBLICATION` 等）。
   - 证据链构建：每一处差异关联独一无二的 `evidence_id`，记录基线和目标文档的原文字节切片、行号及 SHA-256 摘录哈希。
   - **认知边界与不可确认部分：** 结果固定输出 `deployment_version_verified=False`，`authority="DOCUMENTED_SPECIFICATION_ONLY_NOT_LIVE_DEPLOYMENT_EVIDENCE"`，并在 `unconfirmed_aspects` 中明确指出文档规范无法证明线上当前集群运行的具体版本。
3. **`compare_protocols_safe` 安全包装：**
   - 捕获所有 `ProtocolComparisonError` 并映射为标准的结构化响应，返回 `status="REJECTED"` 及具体 `reason_code`，保证消费方不崩溃。

---

## 测试复跑记录

- **执行命令：** `python -m pytest tests/test_ar03_protocol_comparison.py -v --basetemp=.runtime/pytest-ar03-run`
- **运行结果：**
  ```text
  collected 19 items

  tests/test_ar03_protocol_comparison.py::test_identical_versions_comparison PASSED [  5%]
  tests/test_ar03_protocol_comparison.py::test_identical_versions_safe_wrapper PASSED [ 10%]
  tests/test_ar03_protocol_comparison.py::test_legitimate_differences_order_lifecycle PASSED [ 15%]
  tests/test_ar03_protocol_comparison.py::test_legitimate_differences_callback_retry PASSED [ 21%]
  tests/test_ar03_protocol_comparison.py::test_legitimate_differences_api_scope_legacy_vs_current PASSED [ 26%]
  tests/test_ar03_protocol_comparison.py::test_missing_or_empty_references PASSED [ 31%]
  tests/test_ar03_protocol_comparison.py::test_invalid_reference_fields PASSED [ 36%]
  tests/test_ar03_protocol_comparison.py::test_document_not_found PASSED   [ 42%]
  tests/test_ar03_protocol_comparison.py::test_source_mismatch_rejection PASSED [ 47%]
  tests/test_ar03_protocol_comparison.py::test_reference_digest_mismatch PASSED [ 52%]
  tests/test_ar03_protocol_comparison.py::test_disk_file_tampering_detected PASSED [ 57%]
  tests/test_ar03_protocol_comparison.py::test_expired_document_rejection PASSED [ 63%]
  tests/test_ar03_protocol_comparison.py::test_premature_document_rejection PASSED [ 68%]
  tests/test_ar03_protocol_comparison.py::test_inactive_document_rejection PASSED [ 73%]
  tests/test_ar03_protocol_comparison.py::test_cannot_prove_live_deployment_version PASSED [ 78%]
  tests/test_ar03_protocol_comparison.py::test_traceable_excerpts_and_hash_integrity PASSED [ 84%]
  tests/test_ar03_protocol_comparison.py::test_comparison_determinism PASSED [ 89%]
  tests/test_ar03_protocol_comparison.py::test_prompt_injection_in_document_content_is_treated_as_untrusted_data PASSED [ 94%]
  tests/test_ar03_protocol_comparison.py::test_path_traversal_in_manifest_fails_closed PASSED [100%]

  ============================= 19 passed in 0.16s ==============================
  ```
- **知识模块回归：** `python -m pytest tests/test_ar02_knowledge.py --basetemp=.runtime/pytest-ar03-reg`
  ```text
  collected 10 items
  tests\test_ar02_knowledge.py ..........                                  [100%]
  ============================= 10 passed in 1.89s ==============================
  ```

---

## 交付物与样例输出清单

- 源码：`opspilot/domain/protocol_comparison.py`
- 测试：`tests/test_ar03_protocol_comparison.py`
- 样例输出：
  - `docs/evidence/ar-03/protocol-compare/samples/sample_identical_result.json`
  - `docs/evidence/ar-03/protocol-compare/samples/sample_callback_retry_diff.json`
  - `docs/evidence/ar-03/protocol-compare/samples/sample_order_lifecycle_diff.json`
  - `docs/evidence/ar-03/protocol-compare/samples/sample_api_scope_diff.json`
  - `docs/evidence/ar-03/protocol-compare/samples/sample_rejection_digest_mismatch.json`
  - `docs/evidence/ar-03/protocol-compare/samples/sample_rejection_expired.json`
- 机器结果表：`docs/evidence/ar-03/protocol-compare/RESULTS.json`
- 负向测试门禁：`docs/evidence/ar-03/protocol-compare/FAILURES.md`

---

## 状态与结论

> **用户变化：** 新增可验证、带 SHA-256 摘录的只读协议版本比对能力，可结构化揭示协议差异与无法确认项。
> **Agent 决策：** Agent 可在后续流程中选择比对操作并依据可信差异推进分析；本阶段完成纯只读能力交付。
> **观察驱动：** 相同版本给出 zero-diff，不同版本精确给出参数与行为约束变更并附原文哈希。
> **新增约束：** 强约束 digest、source 与有效期校验，禁止将文档当成线上部署证据，严格防范注入与目录遍历。
> **简化结果：** 纯确定性算法，复用已有知识资产目录，无模型调用开销与平台膨胀。
> **证据与停止线：** 19 专测通过，10 现有测试回归通过，6 份真实样本已生成；状态保持 `ACCEPTANCE_CANDIDATE`，不自行合并 `main`。
