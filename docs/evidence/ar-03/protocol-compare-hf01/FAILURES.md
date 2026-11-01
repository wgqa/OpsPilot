# AR-03-01-HF01 失败模式与修复分析 (FAILURES.md)

本文件记录 AR-03-01-HF01 热修切片所解决的具体产品缺陷、负向防御门禁以及未解决/保留的不确定性边界。

## 1. HF01 修复的关键缺陷复盘

| 缺陷编号 | 缺陷现象 | 根因分析 | 修复方案 | 验证用例 |
|---|---|---|---|---|
| BUG-01 | Markdown 文档中若存在相同 Heading（如多个 `# Configuration`），只有最后一个章节参与比对，前面的章节被覆盖丢失。 | 早期版本使用 `dict[str, ...]` 以章节标题作为字典键，导致同名标题发生 key 覆盖。 | 重构章节表示为 `MarkdownSection` 结构体，跟踪每个标题的出现频次 `(title, occurrence)`，使所有章节完整进入比对流水线。 | `test_duplicate_markdown_headings_both_compared_without_overwrite` |
| BUG-02 | 文档中若出现历史说明或否定句（如“早期草案曾测试异步发布但未采用”），被简单正则误判为“目标版本引入异步发布行为指令”。 | 早期 `_extract_protocol_features()` 采用纯文本词频匹配，缺乏否定、历史与示例语境的识别与区分。 | 增加 `_NEGATIVE_OR_HISTORICAL_PATTERN` 上下文检测；将关键词严格降级为探索参考的候选线索 (`candidate_directives` / `candidate lexical cues`)，不再无条件宣称“引入行为指令”。 | `test_negative_and_historical_context_avoids_over_assertion` |
| BUG-03 | 当章节长度超过 500 字符且修改发生在尾部时，证据摘录只截取前 500 字符，导致报告报出差异但证据摘录中全是未修改的头部样板文本。 | 早期 `base_excerpt` 直接取 `b_text[:500]`，存在盲目头部截断。 | 引入 `difflib.SequenceMatcher` 定位实际变更行，以变更行为中心构建滑动上下文窗口（前后保留 2 行 context），并在摘录截断时明确标注 `[...]` 与 `[truncated]`。 | `test_excerpt_localization_at_end_of_long_section` |

---

## 2. 负向安全与完整性门禁矩阵（全部保持 PASS）

| 编号 | 触发场景 | 预期拦截与状态 | 实际结果 |
|---|---|---|---|
| SEC-01 | `base_ref=None` 或缺少必填字段 | 抛出 `InvalidReferenceError`，safe 模式返回 `MISSING_OR_INVALID_REFERENCE` | PASS |
| SEC-02 | 引用中声明虚假的 `source` | 抛出 `DocumentSourceMismatchError`，拒绝非受信来源冒充 | PASS |
| SEC-03 | 篡改 `digest` 或磁盘内容与清单不一致 | 抛出 `DocumentIntegrityError`，拒绝哈希违例 | PASS |
| SEC-04 | 文档过期（`expires_at` 在基准时间之前）或未生效 | 抛出 `DocumentExpiredError`，阻断失效规范 | PASS |
| SEC-05 | 清单中配置 `../` 目录遍历试图读取外部文件 | 抛出 `DocumentIntegrityError`，拒绝越界路径 | PASS |
| SEC-06 | 文档内容包含系统指令注入文本 | 仅作为不可信数据文本进行差异呈现，绝不执行注入指令 | PASS |
| SEC-07 | 试图借静态文档比较推断线上集群部署状态 | `deployment_version_verified` 恒定为 `False`，认知边界不可逾越 | PASS |

---

## 3. 保留的不确定性与显式限制

1. **自然语言语义多样性局限：** 文档比较模块不承担完整自然语言理解（NLU）或定理证明职责。对于非标准形式的否定句（如双重否定、复杂的跨段落代词指代），系统保持保守态度，统一归入 `TEXT_DIFFERENCE` 并附带原文行号，保留证据供后续 Agent 或人工进一步核查，不武断下达业务结论。
2. **纯离线静态规范属性：** 文档比较无法代替线上网络探针。线上到底部署了哪个版本、调用方是否兼容，必须由专门的实时观测工具进行验证。
