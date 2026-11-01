# AR-03-01-HF01 验收报告与六问自检 (REPORT.md)

## 0. 审查前置核验区块

- **Repo / Branch：** `wgqa/OpsPilot` / `antigravity/ar03-01-hf01`
- **Base SHA：** `9abad4de9903ee26a62930a89f7e0392c6f888b2`（`antigravity/ar03-protocol-compare`）
- **Candidate HEAD SHA：** 待在交付信息中报告并推送到 `origin/antigravity/ar03-01-hf01`
- **隔离 Worktree：** `.worktrees/ar03-01-hf01`
- **准则文档实际阅读与哈希：**
  - `PROJECT_NORTH_STAR.md`（Blob: `1f737712c7a36ceb34433ac09c3fbba3c3305542`）已完整阅读
  - `AGENTS.md`（Blob: `32c45506cceeaa8c76a5c56bf8360ff476b58856`）已完整阅读
  - `.agents/skills/opspilot-slice-review/SKILL.md`（Blob: `d405c8d413d633824b279202cc1503dab4cf0b03`）已完整阅读
- **原始根目录状态检查结果：**
  - 原始工作区处于 `antigravity/ar03-protocol-compare` 分支，tracked 文件无未提交修改。
  - `git stash list` 确认为空，无遗留 stash。
  - `.agents` 目录完整存在，文件内容哈希 `d405c8d413d633824b279202cc1503dab4cf0b03` 与 HEAD 完全一致，无异常丢失。
  - 未清理或修改任何用户未跟踪文件（`.pytest-*`, `开发目录/...`）。
- **实际核查与测试方法：**
  - 源码与 Diff 静态独立核验
  - 单元测试套件复跑：28 项测试全部通过（19 项原有基线 + 7 项 HF01 初始专项测试 + 2 项主 Agent 定向修正负例）
  - 关联知识测试回归：10 项现有测试全部通过
  - 生成 4 份真实比对样例并完成 JSON 格式与 Schema 校验

---

## 1. 本轮实际改动说明

主 Agent 审查上一候选版本后给出裁决 `HOLD`，指出摘录定位正确性仍存两处遗留缺陷。已验收成立的 HF01-01 重名章节、HF01-02 词法线索降级、HF01-04 集成契约均保持冻结不重做。本次完成两项最小化定向修复：

1. **定向修复 1：超长单行正文的尾部变更摘录定位**
   - 针对单行且超过 900 字符的协议文档，若仅在尾部变更状态（如 `receiver_state=QUEUED` -> `receiver_state=PROCESSED`），原逻辑由于行级 diff 无法细分单行且 `len(b_sub_text) > max_chars`，盲目切片 `[:max_chars - 7]`，导致摘录仅展示未变化的头部样板前缀。
   - 实现 `_truncate_around_span()` 辅助函数，基于 `difflib.SequenceMatcher` 定位字符级实际变更跨度，动态居中构建有限长度（<=600字符）滑动窗口，在截断处显式标记 `[...]`。
   - 确保 `receiver_state=QUEUED` 与 `receiver_state=PROCESSED` 完整呈现在各自摘录末尾，两边摘录不同且各自 SHA-256 Digest 与实际摘录字符串完全一致。

2. **定向修复 2：新旧文档的独立行号定位**
   - 当目标文档因前文新增段落导致同名章节产生行号偏移时，原 `_extract_diff_excerpt()` 仅使用基线起始行号，导致 `target_location` 错误共用了旧文档起点。
   - 重构参数为 `b_start_line, b_end_line, t_start_line, t_end_line`，在差异（`ProtocolDifference`）与证据（`DiffEvidence`）中分别使用旧文档实际行号（如 `Lines 1-2`）与新文档实际行号（如 `Lines 6-7`），彻底解除了行号共用错误。

3. **保留已验收基线能力：**
   - HF01-01（Markdown 重名章节保留与有序比对）、HF01-02（词法线索严格降级与否定/历史语境过滤）、HF01-04（Agent 最小集成契约）均完整保持。

---

## 2. 剩余限制与停止线

1. **未接入生产链路：** 本阶段依然为纯独立只读 Domain 计算函数，未在 `assistant.py` 或 `assistant_mcp.py` 中注册工具，未接入 Web UI 或真实对话图。
2. **零模型与零网络开销：** 未调用真实 Provider，未发送外部网络请求，未读写业务数据库。
3. **认知与业务边界：** 协议比较结果恒定保留 `deployment_version_verified=False`，无法证明集群当前部署版本，亦不能作为绕过审批或直接执行变更的凭据。

---

## 3. 正式六问自检（Section 7）

1. **用户现在能获得什么更准确的协议差异信息？**  
   用户能够获得完整不遗漏（覆盖全部重名章节）、位置精确（长章节尾部变动不被头部盲截断掩盖）、且语义客观克制（区分真实文本变更与候选检索词，不把历史否定句当成现行新规）的高保真协议版本差异报告。
2. **这项能力将来为 Agent 保留了哪些自主选择，而不是增加固定 Workflow？**  
   Agent 可以根据多轮调查中的具体报错自由决定是否比对、比对哪些版本，由模型依据上下文线索自主推进，而非由写死的规则脚本在固定状态码下强行触发比较。
3. **哪些不同文档观察产生了不同且合理的比较结果？**  
   - 相同文档输入：确定性输出 `identical=True`, `diff_count=0`；
   - 含有历史草案否定句的文档：输出 `TEXT_DIFFERENCE`，识别为措辞变动而不误报引入行为指令；
   - 真实引入新参数（如 `attempt_count`）的协议：输出差异并列出候选参数提示；
   - 尾部变动的长章节：输出精确聚焦于尾部变动行的摘录片段及真实哈希。
4. **修复是否既阻止错误解释，又保留了合法的版本比较？**  
   是的。既阻止了“关键词命中即断言行为改变”的过度推断与重名章节静默丢失，又完全保留了合法协议新旧版本的行级证据追溯与相同版本的零差异判定。
5. **是否有重复抽象、新 Guard 或不必要的模块膨胀？**  
   否。未引入任何重型 Markdown AST 解析器、状态机或规则引擎，仅依托标准库 `difflib` 与轻量数据类（`MarkdownSection`），代码增量简洁克制。
6. **哪些结果是真实验证的，哪些仍未接入 Agent、未通过真实模型证明？**  
   28 项定向单元/集成测试与 10 项知识回归测试经过离线真实复跑验证；本能力尚未接入真实 Agent 对话流程，未通过真实 LLM Provider 进行端到端旅程检验（留待主线授权后续集成）。

---

## 4. 裁决状态

- **当前状态：** `ACCEPTANCE_CANDIDATE`
- **建议动作：** 推送 `antigravity/ar03-01-hf01` 分支，保持 `main` 分支不受影响，等待主 Agent 独立审查。
