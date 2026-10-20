# OpsPilot vNext — M3-01-HF-01 补充验收任务卡

**签发方：** 主 Agent  
**执行方：** Luna / Codex  
**任务类型：** Acceptance Evidence Hardening + Bounded Fix  
**优先级：** P1  
**执行基线：** `main@22823acc519789c14e2cefe8e0f4c16a05fb4b72`  
**验收权限：** 仅主 Agent 有权签署最终裁决  
**授权范围：** 仅 M3-01-HF-01，不得进入 M3-02。

---

## 0. 本轮任务目标

M3-01 已完成可信 Episodic Memory 纵向切片，包括：

- 可信来源 Task A → Case Memory Candidate。
- APPROVER 人工确认，Memory 进入 ACTIVE。
- 不同 Task B 在当前 Evidence 允许下使用 Memory。
- APPROVER 撤销，后续 Context 排除旧 Memory。
- LangGraph Checkpoint 跨进程恢复。
- 真实 Edge + DeepSeek + MCP Web 旅程。
- 冻结 8 对、16 臂 ON/OFF 评测。

原阶段报告为 `PARTIAL`，不得自行改成 PASS。

主 Agent 独立复核认为，核心实现已有较充分证据，但需要完成以下补证：

1. 最终源码版本与完整真实 Web 验收版本一致。
2. 完整测试日志能够从提交后的仓库独立核对。
3. 撤销、模型出站竞争和历史 Assistant 来源失效边界得到更直接的验证。

**最终目标：** 为 M3-01 建立可核对、同版本、可复现的验收证据链，而不是提高指标或增加功能。

## 1. 冻结规则与工作区保护

### 1.1 基线

开始前必须执行：

```powershell
git fetch origin
git rev-parse HEAD
git rev-parse origin/main
git status --short
```

确认 `main` 和 `origin/main` 均为指定 SHA。如存在新的远端提交或基线不一致，停止并报告，不覆盖其他人的工作。

先登记：

- 当前 Git SHA、branch 与工作区状态。
- Python、依赖锁与 Node 环境。
- DeepSeek 模型 ID 与 MCP Server 配置摘要。
- 本轮涉及文件与预期变更范围。

### 1.2 历史资料保护

不得修改、覆盖或删除：

- M3-01 `GOLD.json`、`RUBRIC.json`、`EVAL_PROTOCOL.md`。
- 原 M3-01 `REPORT.md`、`RESULTS.json`、`TRACE.json`、`FAILURES.md`。
- `paired-eval-01` 至 `paired-eval-05` 和原 `web-chain-07`。
- 历史 M1/M2/D1–D7 证据。
- 用户本地未提交的 `AGENTS.md`、`PROJECT_NORTH_STAR.md`、`开发目录/` 等文件。

建议使用临时干净 worktree 或隔离工作目录完成复验。不要通过 `git reset --hard`、`git clean -fd`、强制 checkout 等操作清除用户文件。

新证据统一进入：

`docs/evidence/vnext/m3-01-hf-01/`

所有新运行按编号独立建目录，保留失败及其原因。

### 1.3 修改权限

默认只允许新增测试、验收脚本、日志与文档。

只有当定向测试证实某项冻结安全要求确实违反时，才允许针对 M3-01 已有代码路径做最小修复。

不得新增：

- 新 Memory 产品功能或通用平台。
- 新数据库、向量检索平台。
- 新 Agent、多 Agent 或工具权限。
- 新授权、自动修复和交接能力。
- 长历史压缩及其他 M3-02 功能。

不得借本轮任务对架构进行重构。

---

## 2. HF-A：最终源码真实 Web 复验

**优先级：P1，必须执行。**

### 2.1 已知问题

原成功记录：

`runs/web-chain-07/RESULTS.json`

其中 `git_head=8f04cfb`。

但之后 `f0c56b7` 又修改了 Investigator 根据当前 Run Evidence 选择 Memory 类型的核心逻辑。

因此，原成功结果不能直接替代最终版本的完整复验。

### 2.2 执行要求

从最终固定源码启动实际 Web 后端、前端、SQLite Domain、LangGraph、真实 MCP stdio Server 和 DeepSeek Provider。

真实 Microsoft Edge / Playwright 完成以下同一产品旅程：

1. Task A 是具有可信来源的真实 S1 修复任务。必须存在 COMMITTED REPAIR、真实 HTTP 200 VerificationReceipt、冻结报告及 Evidence。
2. 来源 Task 的 SUPPORT owner 在 Web 创建案例 Candidate。
3. APPROVER 使用可信 Web 身份确认，状态变为 ACTIVE。
4. 创建不同 `task_id` 的 Task B，初始状态为真实 API 401。
5. Task B 的 Investigator 通过真实 MCP 获取当前 Evidence。
6. 新模型出站 Context 真实选入 Task A 的已确认 Memory，Context Provenance 可核对。
7. APPROVER 在 Web 撤销该 Memory。
8. 后续新 Investigator Context（如适用）和新 CHAT_READONLY Context 均不再引入撤销资产。
9. 在 Web 中追问调查结果，确认历史经验不是当前证据，且没有虚假的修复宣称。

对于 Investigator，在现有模型/工具预算和授权范围内验证，不得为了凑次数强制模型调用。

### 2.3 强制业务断言

必须满足：

- Task A 与 Task B 不同。
- 使用前 Memory 为 ACTIVE、来源和 digest 有效。
- 使用后可从实际 Provenance 定位来源 Task A。
- 撤销后版本递增，状态为 REVOKED。
- 后续新模型 Context 不包含撤销 Memory。
- 无越租户或跨项目泄漏。
- Task B 未经批准不得产生 REPAIR/DELIVER Ledger。
- Scope Grant/Policy 不发生未授权变更。
- 未发生实际恢复时不能声称 REPAIRED_VERIFIED。
- Web 401、403、SCOPE_ESCALATED 等业务结果不得混淆。

### 2.4 交付证据

保存至少以下内容：

- 完整源码 SHA、测试开始/结束 SHA、工作区状态。
- 真实 Provider Model ID、调用次数、usage。
- MCP tools/list、tools/call 和 Observation。
- Task A/B、Memory、Run、Attempt、Context Provenance 关联 ID。
- Web API、SSE、Domain 变化前后快照。
- 8 张按步骤命名的真实浏览器截图。
- 执行命令、stdout/stderr、退出码和异常。
- 新鲜 `RESULTS.json` 与 `TRACE.json`。

截图必须来自本次运行，不得复制原 `web-chain-07`。

**HF-A PASS：** 完整旅程在固定最终源码下通过，所有关键状态及模型出站可由证据关联。

---

## 3. HF-B：可独立核对的测试日志

**优先级：P1，必须执行。**

### 3.1 已知问题

原报告引用 `runs/full-05/pytest.log`，但独立审查时未能从 GitHub 取得该文件。

目前可核对 `exit-code.txt=0`，但这不能完全替代详细原始日志。

### 3.2 执行要求

使用项目原有 `.venv` 和锁定依赖，在新证据目录执行完整回归。

覆盖：

- 全量 pytest，包括 D1–D7、M1、M2、M3。
- M3-01 定向测试。
- S1/S2 原有关键安全回归。
- 前端生产 build 和 lint。
- 必要真实 MCP/HTTP smoke。

完整保存命令、stdout/stderr、退出码、实际运行环境和 pytest 测试分子/分母。

如果 Python 或 npm 因环境错误失败，必须保留原失败日志，修正环境后另建新 run。不得仅上传最终成功摘要。

### 3.3 日志归档

例如：

```text
docs/evidence/vnext/m3-01-hf-01/
  runs/
    full-01/
      command.txt
      pytest.log
      exit-code.txt
    focused-01/
      command.txt
      pytest.log
      exit-code.txt
    frontend-01/
      build.log
      lint.log
      exit-codes.json
```

Git 忽略规则如阻止必要日志归档，可针对本任务文件采用明确的 `git add -f`，不得全局扩大提交范围。

如果因文件大小或敏感信息无法直接提交原始日志，必须提供脱敏但完整可审计的替代文件、SHA-256、未提交原因及可复现命令。禁止把日志缺失标记为已完成归档。

**HF-B PASS：** 新鲜回归通过，提交后的证据可读取，并可绑定实际源码版本。若测试失败，如实记 FAIL，不为恢复历史数字调整断言。

---

## 4. HF-C：Memory 撤销与出站时序验证

**优先级：P1，安全敏感。**

### 4.1 验证对象

重点审查：

- `opspilot/domain/episodic_memory.py`
- `opspilot/investigator.py`
- `opspilot/domain/chat.py`
- Worker 与 Checkpoint 恢复路径
- `reserve_attempt` 及 Context Provenance

### 4.2 必须验证的时序

| ID | 竞争或恢复情形 | 预期结果 |
|---|---|---|
| HF-C01 | Prompt 构建后、attempt 预留前撤销 | 失效 Context 被拒绝或重建 |
| HF-C02 | 预留后、首次 Provider I/O 前撤销 | 按冻结语义不得新发出包含失效 Memory 的请求 |
| HF-C03 | 撤销前已真正开始的 Provider 请求 | 不把已开始请求冒充为撤销后新请求；记录明确的发生顺序 |
| HF-C04 | Checkpoint 保存 ACTIVE 引用，撤销后 Worker 重启 | 新 Context 不重新使用旧资产 |
| HF-C05 | Memory 过期、版本变化、来源失效 | 新 Context 排除，不能仅靠缓存或 checkpoint 继续使用 |
| HF-C06 | 历史 Assistant 消息依赖已撤销 Memory | 后续 Chat Prompt 不重新注入失效 Assistant 内容 |

### 4.3 实施方式

优先使用可控线程同步点、failpoint、事务屏障及确定性 Provider 捕获实际出站参数。

不要使用随机 `sleep` 作为竞态正确性的唯一证明。

特别注意：

**撤销之前已真正开始的 Provider 请求，与撤销之后新发出的 Provider 请求不是同一种情况。**

本轮要求明确线性化边界，不要求取消已经成功进入外部 Provider 的不可撤销网络请求。

如果发现 HF-C02 存在真实竞态，先做最小复现 RED 并报告根因，再进行局部修复。修复必须保持 Provider 预算、attempt 身份和 Context Provenance 一致。

不能通过提高预算、关闭撤销入口或绕过校验来让测试通过。

如果无法安全地完成最小修复，保留失败证据并停止，交主 Agent 裁决。

### 4.4 历史 Assistant 依赖检查

创建一段实际使用 ACTIVE Memory 的历史 Assistant 回答，再撤销该 Memory。

在后续 Chat 中：

- 检查 `chat_message_sources`。
- 验证历史 Assistant 的来源版本/digest。
- 证明旧 Assistant 内容未进入新 Prompt。
- 保留历史审计记录，不物理删除历史业务消息。
- 验证不会通过摘要、缓存或其他间接路径重新引入该失效内容。

必须检查最终实际发送给 Provider 的 Context，而不只是内存列表。

**HF-C PASS：** 冻结时序全部符合预期，有可复现断言；任何已发现的安全竞态已封闭或如实标记阻断。

---

## 5. 不得修改的负面实验结论

原 M3-01 冻结评测永久保留：

- 8 对、16 臂。
- 12/16 Outcome 符合 Gold。
- P03/P04 的 ON/OFF 均为 `HANDOFF_READY`，与冻结允许 Outcome 不一致。
- `UTILITY_NOT_PROVEN`。
- Provider 账单费用 `NOT_REPORTED`。
- 原失败与完整 Trace 均保留。

禁止修改 Gold、删除失败、选择性重跑或声称 Memory 已证明提升准确率。

P01 ON/OFF 的工具顺序有所不同，但缺少足够证据证明差异由 Memory 引起，不得据此将效用改为 PROVEN。

本轮不要求重新执行完整 16 臂评测；除非最小修复改变了调查策略或其他会影响冻结结果的核心代码路径。若确实改变，需要先报告影响并单独申请复评，不得静默覆盖旧结果。

---

## 6. 验收矩阵

| 门禁 | PASS 条件 |
|---|---|
| HF01-01 | 基线、工作区和冻结资料完整 |
| HF01-02 | 原历史证据及 Gold 未修改 |
| HF01-03 | 最终版本真实 Web 全链通过 |
| HF01-04 | DeepSeek/MCP/HTTP/Domain Trace 可互相关联 |
| HF01-05 | Task A/B 和 Memory 生命周期可信 |
| HF01-06 | 撤销后新 Context 不重用旧资产 |
| HF01-07 | 预留/出站竞态安全 |
| HF01-08 | 历史 Assistant 失效依赖被过滤 |
| HF01-09 | 跨进程恢复保持撤销语义 |
| HF01-10 | 全量、定向及前端新鲜回归通过 |
| HF01-11 | 原始失败、日志和 SHA 完整可审 |
| HF01-12 | 无越权写入、无假业务恢复、无新增功能漂移 |

安全硬红线任一违反，本轮即为 `BLOCK`，不得与其他通过项平均抵消。

不要求 Memory 效用提升，也不因为 `UTILITY_NOT_PROVEN` 自动判定机制实现失败。

---

## 7. 最终交付格式

新目录：

```text
docs/evidence/vnext/m3-01-hf-01/
  TASK_CARD.md
  ACCEPTANCE_PLAN.md
  REPORT.md
  RESULTS.json
  TRACE.json
  FAILURES.md
  RUN_INDEX.md
  FROZEN_SHA256SUMS.txt
  runs/
    freeze-check-01/
    web-final-01/
    focused-01/
    full-01/
    frontend-01/
    revoke-race-01/
    restart-recovery-01/
```

可根据实际验证追加编号目录。不存在的实验不得创建虚假结果。

`REPORT.md` 必须分开陈述：

1. 真实实现与安全门禁结果。
2. 最终源码版本的 Web 复验结果。
3. ON/OFF 历史评测及其局限。
4. 新发现的问题、修复及未解决风险。
5. 哪些结果来自真实 DeepSeek，哪些来自确定性测试 Provider。
6. 是否建议主 Agent 验收及其依据。

不得在报告中自行签署 M3-01 PASS。

### 提交规范

采用单人工作流直接提交 `main`，无需 PR。

建议：

- 提交 1：冻结本次补充验收协议。
- 提交 2：必要 RED 测试和原始失败证据。
- 提交 3：仅在必要时提交最小代码修复。
- 提交 4：GREEN、真实 Web 证据与完整测试日志。
- 提交 5：最终报告与机器索引。

无代码修复时，可省略实现提交，不得制造空的修复记录。

每次只 stage 本轮明确管理的文件，提交前检查 `git diff --cached --name-only`。

完成后推送远端并核对：

```powershell
git fetch origin
git rev-parse HEAD
git rev-parse origin/main
git status --short
```

最终向主 Agent 报告完整 SHA、测试结果、原始失败、实际受控写入及工作区剩余状态。

---

## 8. 停止线与最终裁决

执行方完成补证后必须停止。

- 不启动 M3-02。
- 不新增 Memory 产品功能。
- 不修改原 M3-01 冻结 Gold。
- 不把 `UTILITY_NOT_PROVEN` 改写成收益已证明。
- 不替主 Agent 签署阶段 PASS。

主 Agent 根据实际证据决定：

- **PASS：** 本轮要求完全满足，原 M3-01 的历史局限照实保留。
- **ACCEPT_WITH_LIMITS：** 安全硬门禁满足、业务闭环可验，但仍存在明确且不阻断后续阶段的功能或评测限制。
- **PARTIAL / BLOCK：** 核心证据未闭合或存在实际安全硬门禁失败。

**本轮最重要的原则：证明已经完成的能力，而不是继续扩大系统。**

完成后仅交付 M3-01-HF-01 的证据与结果，等待主 Agent 独立验收。