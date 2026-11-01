# AR-03-02 交付报告与六问自检 (REPORT.md)

## 0. 审查前置核验区块

- **Repo / Branch：** `wgqa/OpsPilot` / `antigravity/ar03-02-scoped-compare`
- **Base SHA：** `9d024781c62deba457522a5dd5b66dcca0a97930`（`antigravity/ar03-01-hf01`）
- **Candidate HEAD SHA：** 待在提交与交付信息中完整记录并推送到远端
- **隔离 Worktree：** `.worktrees/ar03-02-scoped-compare`
- **准则文档实际阅读与哈希：**
  - `PROJECT_NORTH_STAR.md`（Blob: `1f737712c7a36ceb34433ac09c3fbba3c3305542`）已于本次会话重新核验
  - `AGENTS.md`（Blob: `32c45506cceeaa8c76a5c56bf8360ff476b58856`）已于本次会话重新核验
  - `.agents/skills/opspilot-slice-review/SKILL.md`（Blob: `d405c8d413d633824b279202cc1503dab4cf0b03`）已于本次会话重新核验
- **原始根目录状态检查结果：**
  - 原始工作区处于 `antigravity/ar03-protocol-compare` 分支，tracked 文件无任何未提交修改。
  - `git stash list` 确认为空，无遗留未处理 stash。
  - `.agents` 目录完整存在，Blob 哈希为 `d405c8d413d633824b279202cc1503dab4cf0b03`，与远程基线完全一致，无任何损毁。
  - 用户未跟踪目录（`.pytest-*`, `开发目录/...`）完整保留，未进行任何清理、覆盖或删除。
- **实际核查与测试方法：**
  - 静态源码审查与 Diff 核验
  - 专项测试套件执行：15 项 AR-03-02 测试全部通过
  - 关联历史回归套件：28 项 AR-03 测试 + 10 项 AR-02 Knowledge 测试全部通过（总计 53 项通过，无失败）
  - 生成 4 份真实业务比对与越权拦截样例（JSON）并核实 Schema

---

## 1. 本轮实际改动说明

本轮聚焦于实现 AR-03-02 **会话授权的协议版本比较**，将 AR-03-01 的独立比较计算能力安全接入基于 Session 和 Project 的受信权限体系中：

1. **AR03-02-01：最小会话授权桥接**
   - 在 `opspilot/domain/assistant_knowledge.py` 中新增 `get_session_project()` 接口（约 26 行），复用现有的 SQLite 会话所有权校验、身份校验及注册表项目匹配逻辑，支持动态获取活动会话的受限项目授权。
   - 新增 `opspilot/domain/scoped_protocol_comparison.py`，实现 `compare_scoped_protocols()`。调用者仅需提供可信 `identity`、`session_id` 以及受限的文档标识符（`base_document_id`, `target_document_id`）。
   - 服务端严格校验双方文档是否属于当前项目的 `document_ids`，并直接从受信清单读取真实摘要与来源，杜绝调用方伪造路径或假哈希。
   - 彻底区分了“授权范围”与“检索排名”：文档是否可比较取决于项目授权清单，绝不受限于全文检索 Top-3 限制。
2. **AR03-02-02：真实业务资料的离线比较**
   - 针对仓库中真实存在的 `callback-retry-contract` v1 与 v2 以及 `order-lifecycle-contract` v1 与 v2，执行了会话授权下的真实服务调用。
   - 成功生成结构化差异报告，确认参数变化（`attempt_count`, `max_attempts`）与状态变更摘录均准确呈现。
   - 明确标注 `deployment_version_verified: False` 与非动作授权声明（`SESSION_AUTHORIZED_INVESTIGATION_EVIDENCE_NOT_ACTION_AUTHORIZATION`），产出格式可直接供未来 Agent 工具使用。
3. **AR03-02-03：全量反向与越权防御**
   - 实现了跨租户调用拦截（`support-b` 无法调用 `tenant-a` 项目）。
   - 实现了未授权文档拦截（访问 `orders-callback` 未授权的 `api-scope` 文档报错 `DOCUMENT_NOT_AUTHORIZED`）。
   - 实现了多项目未选择防护（抛出 `KNOWLEDGE_SCOPE_SELECTION_REQUIRED`）。
   - 实现了结果持续有效性校验（`scoped_comparison_is_current`）：在项目切换、项目停用、授权版本升级、单文档被移出授权、磁盘文件被篡改时，历史结果均能被可靠识别为失效。
   - 证明合法的历史版本比较（v1）不会因当前项目配置版本为 v2 而被错误拒绝。

---

## 2. 剩余限制与停止线

1. **纯只读 Domain 计算桥接：** 本阶段未在 `opspilot/assistant.py` 或 `assistant_mcp.py` 中注册工具，亦未修改 Web 或 Worker，未接入前台聊天。
2. **零外部开销与零业务副作用：** 真实 LLM 请求为 0，外部网络 API 调用为 0，外部业务写操作为 0。
3. **认知与权限边界：** 协议比较结果属于调查只读证据，绝不等于线上真实部署，亦不可作为审批通过或动作执行的合法输入。
4. **范围停止线：** 明确仅完成“独立能力”与“授权桥接”，未声称已接入真实 Agent，更未声称已通过真实 Agent 自主选择证明。

---

## 3. 正式六问自检（North Star 第 8 节 / SKILL.md B 节）

1. **用户现在能获得什么更准确的协议差异信息？**  
   在真实会话中，用户和系统能够安全调用真实业务协议（如回调重试策略、订单状态机）的新旧版本比较，获得经过会话授权背书、带有真实行号、局部滑动窗口摘录和加密证据摘要的高保真差异报告，同时彻底排除了跨租户和未授权文档的越权风险。
2. **这项能力将来为 Agent 保留了哪些自主选择，而不是增加固定 Workflow？**  
   Agent 在多轮交互中，可以自主根据客户反映的报错，自由决定是否调用协议版本比对、选择比较授权范围内的哪两个版本，而无需依赖固定脚本或死板的状态机流转。
3. **哪些不同文档观察产生了不同且合理的比较结果？**  
   - 回调重试协议 v1 vs v2：准确识别出候选参数 `attempt_count` 与 `max_attempts` 的引入及重试策略措辞变动；
   - 订单生命周期协议 v1 vs v2：准确识别出异步发布指令变化；
   - 跨租户 / 未授权文档输入：坚决阻断并返回类型化错误码（`DOCUMENT_NOT_AUTHORIZED` / `SESSION_SCOPE_DENIED`）。
4. **修复是否既阻止错误解释，又保留了合法的版本比较？**  
   是的。既阻止了“未命中 Top3 就拒绝历史版本比较”或“随意指定文件路径/篡改摘要”的缺陷，又完整保留了跨历史版本合法比对的能力。
5. **是否有重复抽象、新 Guard 或不必要的模块膨胀？**  
   否。未新建任何多余权限框架，完全复用了已有的 `assistant-access.json` 注册表、`sessions` 数据表与 D2 摘要机制；代码增量仅为一个轻量桥接文件与一个工具函数。
6. **哪些结果是真实验证的，哪些仍未接入 Agent、未通过真实模型证明？**  
   15 项会话授权测试、28 项 AR-03 定向测试与 10 项知识回归测试经过隔离工作区离线复跑验证；本能力尚未接入真实 Assistant 对话流程，未通过真实 LLM Provider 进行端到端旅程检验（留待后续阶段授权集成）。

---

## 4. 裁决状态

- **当前状态：** `ACCEPTANCE_CANDIDATE`
- **建议动作：** 推送 `antigravity/ar03-02-scoped-compare` 分支，保持 `main` 和 Codex 并行分支不受影响，等待主 Agent 独立审查。
