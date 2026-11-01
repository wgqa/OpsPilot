# AR-03-03 交付报告与六问自检 (REPORT.md)

## 0. 审查前置核验区块

- **Repo / Branch：** `wgqa/OpsPilot` / `antigravity/ar03-03-agent-integration`
- **Base SHA：** `af9d7433803c756f6f9a7baee3b16276e4da7f41`（`antigravity/ar03-02-scoped-compare`）
- **Candidate HEAD SHA：** `d458256ffb7d07d45c8cf4d24e4079030e7c3824`
- **隔离 Worktree：** `.worktrees/ar03-03-agent-integration`
- **准则文档实际阅读与哈希：**
  - `PROJECT_NORTH_STAR.md`（Blob: `1f737712c7a36ceb34433ac09c3fbba3c3305542`）已于本次会话重新核验
  - `AGENTS.md`（Blob: `32c45506cceeaa8c76a5c56bf8360ff476b58856`）已于本次会话重新核验
  - `.agents/skills/opspilot-slice-review/SKILL.md`（Blob: `d405c8d413d633824b279202cc1503dab4cf0b03`）已于本次会话重新核验
- **原始根目录状态检查结果：**
  - 原始工作区处于 `antigravity/ar03-protocol-compare` 分支，tracked 文件无任何未提交修改。
  - `git stash list` 确认为空，无遗留未处理 stash。
  - `.agents` 目录完整存在，Blob 哈希为 `d405c8d413d633824b279202cc1503dab4cf0b03`，与远程基线完全一致，无任何损毁。
  - 用户未跟踪目录完整保留，未进行任何清理、覆盖或删除。
- **实际核查与测试方法：**
  - 静态源码审查与 Diff 核验
  - 专项测试套件执行：5 项 AR-03-03 测试全部通过
  - 关联历史回归套件：
    - `test_ar03_02_scoped_protocol_comparison.py`: 15 项全部通过
    - `test_ar03_protocol_comparison.py`: 28 项全部通过
    - `test_ar02_assistant.py`: 3 项全部通过
    - `test_ar02_knowledge.py`: 10 项全部通过
    - `test_ar02_journey_p0.py`: 7 项全部通过
  - 总计 68 项测试全部通过（0 失败，0 告警阻断）
  - 生成并核查真实对话记录与工具调用追踪文件：`docs/evidence/ar-03/agent-integration/dialog_trace.json`

---

## 1. 本轮实际改动说明

本轮聚焦于实现 AR-03-03 **协议比较进入真实 Agent 调查**，让用户通过正式 Assistant 对话提出协议升级影响问题，由 Agent 自主决定是否调用版本比较工具，并给出有来源的调查回答：

1. **MCP 接入层注册只读比对工具（`opspilot/assistant_mcp.py`）**
   - 在受信 Run 作用域下的 MCP Server 中注册 `compare_scoped_protocols`。
   - 工具仅暴露模型决策所需的高层参数：`base_document_id`, `target_document_id`, `base_version`, `target_version`。
   - 会话 ID、操作者身份（`TrustedIdentity`）、数据库路径及受信 Manifest 目录完全由服务端上下文安全注入，杜绝模型输入假路径、假 Digest 或跨租户会话 ID。
   - 标注 `read_only_hint=True, open_world_hint=False`，输出始终携带 `deployment_version_verified: False`。

2. **强化跨会话/跨租户/跨操作者关联与防篡改（`opspilot/domain/scoped_protocol_comparison.py`）**
   - 补齐 `scoped_comparison_is_current()` 中的 `session_id`、`tenant_id`、`actor_id` 强校验，坚决拦截跨 Session、跨租户与跨操作者历史比对结果的冒用与重放。
   - 引入比较摘要重构校验（`COMPARISON_DIGEST_MISMATCH`）：即使第三方或模型试图伪造或修改比对结果字典（如擅自将 `identical` 篡改为 `True`，或增删 `differences` 列表），通过重新计算 `res_data` 的 SHA-256 Digest 即可立刻识别并拒绝。
   - 增强版本宽容匹配器：支持模型输入 `"1"` 自动匹配清单中的 `"1.0.0"` 或 `contract_versions: [1]`。

3. **核心会话来源持续有效性再验证（`opspilot/domain/assistant.py`）**
   - 在 `sources_current()` 中无缝对接 `scoped_comparison_is_current`。
   - 当历史 Assistant 运行包含协议比对 MCP 观察时，持续校验项目授权、文档授权及底层磁盘文档哈希，确保只有未经篡改且授权有效的观察结果才能作为后续轮次的合法来源。

4. **端到端完整链路与旅程落地（`tests/test_ar03_03_agent_integration.py`）**
   - 实现了自然语言输入 -> 真实 FastAPI Web 接口 -> 后台异步 Worker -> LangGraph Assistant 调度 -> stdio MCP 子进程 -> SQLite/Manifest 比对 -> 最终自然语言回答并持久化入库的全流程。
   - 完整验证了正常比对旅程、越权保密文档阻断、跨 Session/跨租户/跨 Actor 阻断、字典篡改阻断及 MCP stdio 契约。

---

## 2. 剩余限制与停止线

1. **零付费开销与免费替身先行：** 本切片使用确定性高拟真模型替身（`ProtocolCompareSurrogateModel`）验证了完整的异步 API、Worker 与 MCP 子进程接线，真实付费 LLM 调用计数为 0。同时交付了可执行的 `REAL_LLM_PLAN.md` 供授权后运行。
2. **只读调查边界：** 协议比较仅产生用于解释与排查的只读事实，绝不自动触发任何 TaskControl 状态变更、配置修改、审批或业务写操作。
3. **认知边界严格锁定：** 静态协议比对仅说明规范文本的演进差异，系统与模型均在输出中明确提示 `deployment_version_verified: False`，严禁将文档差异当成集群线上部署成功的证据。
4. **范围停止线：** 明确保持在 `antigravity/ar03-03-agent-integration` 独立分支中，交付候选状态保持为 `ACCEPTANCE_CANDIDATE`，不触碰 `codex/ar02-live-01` 主线，不合并 `main`。

---

## 3. 正式六问自检（North Star 第 8 节 / SKILL.md B 节）

1. **用户现在能获得什么更准确的协议差异信息？**  
   用户可在正式 Assistant 对话界面以连续自然语言提问（如“客户反馈升级回调协议后行为变化，请检查旧版和新版规范”）。Agent 会自主发起针对受信协议库的精准比对，向用户输出结构化差异分类、具体参数（如 `attempt_count`, `max_attempts`）变化及其对下游回调接收者的潜在影响，同时明确澄清静态比对无法证明生产集群实际部署状态。

2. **为什么确认这不会导致误报或虚假修复？**  
   - 工具结果中恒定带有 `deployment_version_verified: False` 与 `unconfirmed_aspects` 警示，模型在最终回复中必须包含这一认知边界。
   - 所有比对摘录与差异必须可追溯到底层 Manifest 和加密哈希，任何篡改均被 `COMPARISON_DIGEST_MISMATCH` 拦截。
   - 比对操作不修改任何配置，不触碰 CAS，不触发 REPAIR。

3. **真实系统在执行时怎么防止被模型幻觉利用？**  
   - 模型无权指定文件路径、Digest、租户 ID 或 Session ID；所有关键上下文均由服务端从当前受信 Run 注入。
   - 即使模型在多轮对话中伪造比对结果字典，`sources_current` 和 `scoped_comparison_is_current` 每次在提交前重新验证哈希和授权，阻止虚假历史证据污染后续会话。

4. **怎么证明没有引入外部副作用或非只读操作？**  
   - 数据库事务审计确认：全流程仅写入 Session 消息表及 `assistant_calls` 审计表，`d3_action_intents`、`d3_action_ledgers` 和 `task_bindings` 的写入记录为 0。
   - MCP 工具被声明为严格只读（`read_only_hint=True, open_world_hint=False`）。

5. **为什么没有破坏已有规范或破坏历史回归？**  
   - 全套回归套件运行通过：包含 15 项 AR-03-02 测试、28 项 AR-03 核心测试、3 项 AR-02 Assistant 契约测试、10 项 AR-02 Knowledge 权限测试及 7 项 AR-02 真实异步 Journey 测试，总计 68 项测试 100% PASS，0 失败。

6. **这次改动如何服务于大厂面试所要求的“Agent Engineering / 系统落地”表达？**  
   - 展示了标准的 **Context Engineering 与 Tool Use 生产级落地链**：高风险调查能力不直接开放裸函数或自由文件读取，而是通过 Run-scoped stdio MCP、Server-side 上下文注入、细粒度文档白名单鉴权（Grant）及加密 Digest 防篡改实现全闭环。
   - 建立了明确的 **Epistemic Boundary（认知与事实边界）**：区分“文档规范设计”与“生产运行部署事实”，防止 LLM 将文档当成系统状态从而发生越权断言。
