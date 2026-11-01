# AR-03-01-HF01 验收计划与前置检查记录 (ACCEPTANCE_PLAN.md)

## 0. 任务元数据

- **任务卡：** OpsPilot — AR-03-01-HF01 正式开发任务卡
- **任务状态：** `AUTHORIZED_FREE_IMPLEMENTATION_ONLY`
- **基线 Commit（Base SHA）：** `9abad4de9903ee26a62930a89f7e0392c6f888b2`（分支 `antigravity/ar03-protocol-compare`）
- **开发分支：** `antigravity/ar03-01-hf01`
- **独立 Git Worktree：** `.worktrees/ar03-01-hf01`
- **目标：** 收口 AR-03-01 独立协议比较能力中已确认的产品正确性问题（重名章节覆盖、语义过度断言、长文本摘录盲区、后续集成契约），为未来 LLM 自主选择协议比对工具奠定坚实基础。

---

## 1. 原始根目录工作区核验（无破坏只读检查）

本轮开始前，按任务卡要求对项目原始根目录（`D:\学习\agent新项目`）执行严格只读核验：

1. **未提交修改与工作树状态：**
   - 原始根目录当前处于分支 `antigravity/ar03-protocol-compare`。
   - `git status` 显示 tracked 文件无任何未提交修改（working tree clean）。
   - 存在的未跟踪目录均为历史测试产物（`.pytest-*`）、历史日志（`docs/evidence/vnext/...`）与用户中文资料（`开发目录/...`），本轮未作任何触碰或清理。
2. **Git Stash 状态：**
   - 执行 `git stash list`，输出为空。未遗留任何临时 stash。
3. **`.agents` 目录状态：**
   - 经只读核对，`.agents/skills/opspilot-slice-review/SKILL.md` 完整存在于根目录中，大小为 6079 字节。
   - `git hash-object` 计算结果为 `d405c8d413d633824b279202cc1503dab4cf0b03`，与目标提交树中的 Blob SHA 完全一致，状态健康无缺失。
4. **Worktree 占用情况：**
   - 存在 Codex 并行工作区（如 `codex/ar02-live-01` 在 `.worktrees/ar02-live-01` 及外部用户目录）。
   - 本任务完全隔离在独立的 `.worktrees/ar03-01-hf01` 中进行，未干扰任何其他 worktree。

---

## 2. 冻结范围与修改边界

| 模块 | 允许操作 | 实际范围 |
|---|---|---|
| `opspilot/domain/protocol_comparison.py` | 允许修改 | 实现 HF01-01（重名章节安全列表）、HF01-02（否定/历史上下文过滤、区分文本差异与候选线索）、HF01-03（基于 SequenceMatcher 的真实变更窗口摘录） |
| `tests/test_ar03_protocol_comparison.py` | 允许新增测试 | 新增 7 项定向测试，总用例数达到 26 项 |
| `docs/evidence/ar-03/protocol-compare-hf01/` | 允许新增 | 新增 `ACCEPTANCE_PLAN.md`, `REPORT.md`, `RESULTS.json`, `FAILURES.md`, `INTEGRATION_CONTRACT.md` 及样例 JSON |
| `opspilot/assistant*.py`, `worker.py`, `app.py`, `chat.py`, TaskControl | **绝对严禁修改** | 保持 0 修改 |
| `main` 分支与 Codex 分支 | **绝对严禁合并或修改** | 保持 0 修改 |

---

## 3. 验收用例规划

- **原有基础回归（19 项）：**
  - 相同版本 zero-diff
  - 合法新旧版本差异提取
  - 缺失/无效引用拒绝
  - 来源不匹配拒绝
  - 摘要篡改与完整性违例阻断
  - 过期/未生效/停用文档阻断
  - 线上部署不可证明性（`deployment_version_verified=False`）
  - 提示词注入不可信数据防御
  - 清单路径遍历防御
- **本轮新增 HF01 专项（7 项）：**
  - `test_duplicate_markdown_headings_both_compared_without_overwrite`：多重名章节均被提取与对比，无后者覆盖前者。
  - `test_duplicate_markdown_headings_identical_produces_zero_diff`：含重名章节的相同文档比对结果确为 zero-diff。
  - `test_duplicate_markdown_headings_count_mismatch`：新版本增加同名章节时正确识别为 `SECTION_ADDED`。
  - `test_no_headings_plain_markdown_document`：无 Heading 纯文本协议归入 `"Root"` 正常比对。
  - `test_negative_and_historical_context_avoids_over_assertion`：历史/否定语境下的关键词不提升为活跃行为指令。
  - `test_unrecognized_text_diff_categorized_without_false_assertions`：纯文本措辞变动如实作为 `TEXT_DIFFERENCE` 输出，不编造候选参数。
  - `test_excerpt_localization_at_end_of_long_section`：长段落尾部的微小变动能被摘录窗口精确捕获，避免摘录盲区。
- **关联回归：**
  - `tests/test_ar02_knowledge.py`（10 项通过）
