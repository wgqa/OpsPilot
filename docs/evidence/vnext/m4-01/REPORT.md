# M4-01 对话驱动调查交付报告

状态：**实现与本轮检查完成，等待主 Agent 独立验收**。本报告不签署 M4 总体验收，不启动 M4-02。

## 1. 基线与提交

| 项目 | Git SHA |
|---|---|
| 开工实际 main / origin/main | `90c80fd57a85af5abc745c7602acd871646e4735` |
| 实现前独立冻结标准、Gold、Rubric 和 RED 测试 | `cf9c9fbd312375b7a2cef7bf203cbfb510587480` |
| 核心实现 | `050509d83463ebdede2b2fd5ab167dd74959b3d9` |
| 最终源码与终态负例、Web 完成提示断言 | `6ae53a97edc6efec92ab55f90b8b34d5d58618dc` |
| 最终证据提交 | 本报告所在提交；准确 SHA 由最终交付消息及 Git 给出，避免文件自引用 |

直接在 main 工作，没有分支或 PR。原有未提交的 `开发目录/`、旧 pytest 临时目录和历史证据未被覆盖、清理或暂存。`AGENTS.md`、`PROJECT_NORTH_STAR.md` 和冻结合同未改写。依赖锁文件无变化，实际版本与摘要见 [ENVIRONMENT.json](ENVIRONMENT.json)。

本阶段按用户新任务卡命名为 **M4-01 对话驱动调查**；原合同中的 M4 总验收仍保留，由后续独立验收裁决。

## 2. 用户实际获得的能力

- **用户多完成了什么：** 同一 Task 中的自然语言纠错先成为可审阅提议；用户可以核对当前输入、原消息、摘要和控制版本，再确认或取消。确认后同一原文通过既有 `CORRECT_TASK_INPUT` 进入一个新的 Investigator Run，而非仅得到聊天回答。刷新和 API 重启后仍能查看持久 Task、提议和 Run。
- **模型实际决定了什么：** 分类普通追问、关键纠错、假设或越界请求，并生成用户变更摘要。真实 Investigator 随后选择现有受限 MCP 调查工具。模型不决定是否有权修改 Task，不设置资源、版本、Gate、审批或动作权限。
- **可信程序控制什么：** 身份/owner/Session、提议来源与摘要、Task 终态和控制版本、稳定 operation ID、重复提交回查、旧 Run/Plan 失效、唯一新 Run，以及现有 MCP 范围、Evidence Gate 和动作事务守卫。
- **真实证据证明什么：** 用户说“403”但事实仍为 401 时，新 Run 实际 Probe 继续返回 401；独立准备为真实 403 的环境中，新 Probe、同一 Request ID 的 Authz Decision、Scope Evidence 和 DiagnosisReceipt 一致。用户文字仍为 `USER_INPUT_UNTRUSTED`。

## 3. 实现与安全边界

新增两张 Domain 表保存评估/提议和 Provider Attempt，SQLite 从 v11 迁移到 v12；已有表与历史 Plan hash 不重建。模型外发前登记 Attempt，记录模型、Prompt/input/response digest、Provider ID 与 Token；同来源消息重复评估复用结果。无效输出失败关闭，明确失败最多两次尝试。

确认复用 `admit_task_message()`，在同一 `BEGIN IMMEDIATE` 中校验身份、提议状态、原消息摘要、当前 TaskControl revision、任务终态和幂等身份，然后受理原始消息和新调查 Run。确认重放回查相同消息/Run；取消或版本变化阻断提交。真实 Web 的 S1 旧 Plan 已变为 `CANCELLED`；新增 HTTP 测试还证明了旧排队 Run 被 `TASK_CONTROL_STALE` 阻断。

**版本解释：** 冻结计划中“确认 revision 增加一次”指受理事务：0→1。既有 `apply_pending_critical_inputs()` 应用输入时另记 1→2，新 Run 的 expected revision 为 2。这是原 TaskControl 语义；本轮未重写它。首轮浏览器把最终 revision 错断言为 1，失败日志保留。

真实浏览器发现 Inspector 会把 S2 的 `NOT_APPLICABLE` 投影覆盖到当前 S1 Gate。唯一相关修复是在该投影中保留 S1 Gate；S1/S2 判据、审批、ActionIntent、Ledger 和业务事务未改。S2 授权明细通过可信 Receipt/Gate 与 Domain 原始记录关联，未把公开的 S1 Evidence 投影误当完整 S2 Evidence 列表。

没有新增业务场景、Memory 类型、Skill 或 MCP 工具；没有新增 Scope 修改、审批、REPAIR、DELIVER 或 Handoff 能力。M4 两组 Web Agent 运行前后 Config、Principal、AuthPolicy、Grant 和 Route Policy 完全一致，动作/审批/交接写入计数为零。终态负例和既有回归会在各自隔离测试库中执行已批准的 S1 修复交付，不能把上述“零写入”扩展成全体 pytest 从未执行动作。

## 4. 新鲜验证

| 类别 | 结果 | 原始入口 |
|---|---|---|
| 最终全量 pytest，含原有 227 项及本阶段 15 项 | **242/242，172.40 秒，exit 0** | [pytest.log](runs/full-04/pytest.log) |
| M4 HTTP/Domain 定向 | **15/15** | [pytest.log](runs/targeted-03/pytest.log) |
| 真实 Provider 冻结意图 Gold，提示 v1 | **8/10**，两条漏判，不改历史 | [RESULTS.json](runs/intents-20261022T171607Z-c0fa8d67/RESULTS.json) |
| 真实 Provider 同一 Gold，提示 v2 | **10/10** | [RESULTS.json](runs/intents-20261022T171819Z-ce631d9c/RESULTS.json) |
| 最终真实 Edge 401/403 连续旅程，含页面完成提示断言 | **2/2** | [RESULTS.json](runs/web-20261022T172814Z/RESULTS.json) |
| API 实进程重启，同库、同 Task/Session/Run | **2/2** | 两组 `SERVICE_RESTART.json` / `RESUME.json` |
| 最终 Web 真实 MCP stdio tools/call | **10 Attempt / 10 Observation** | 两组 `DOMAIN_SNAPSHOT.json` |
| 最终 Web 真实业务 HTTP Probe | **4 次**（初查与纠错后各两次） | Probe Evidence + Authn/Authz 事件 |
| frontend typecheck + production build | **exit 0** | [build.log](runs/frontend-build-03/build.log) |
| frontend lint | **exit 0** | [frontend-lint.log](frontend-lint.log) |

`node --check`、Python 语法检查及 Git whitespace 检查均通过。tools/list 没有单独计数，不杜撰分母。现有 N1、M1-HF-01、S1/S2、审批、恢复、动作与交接幂等测试包含在本轮 242 项新鲜全量运行中。

确定性测试替换的是分类模型输出，以验证真实 HTTP 身份、提议、事务与状态边界；它们不冒充真实模型。真实意图 Gold 关闭 Worker，仅验证分类；真实 Edge 旅程才包含真实 Chat、Investigator、Provider、MCP、HTTP 和重启。

## 5. 两组成对事实实验

最终关联链可直接从 [TRACE.json](TRACE.json) 进入原始记录：source message → model assessment → proposal/version → operation ID → correction message → 新 Investigator Run → MCP observation → Evidence → Gate/Receipt。

| 项目 | 事实不变：401 | 独立准备：403 |
|---|---|---|
| Task | `task-a3635355-14c5-43b6-94f6-c6f0310768a6` | `task-0aa30fb6-ad69-43cb-84f9-a5dc90c03f53` |
| 新 Run | `run-18eb405a-f4ea-461a-8577-a6e121717517` | `run-46ccb722-a7ca-4621-9b21-15a834b1c7df` |
| 新 Probe Request ID | `dded2cb7053fea53` | `3df5d6657b582e5d` |
| 当前 Gate | `READY`：启用主体与凭证引用失配 | `DIAGNOSED`：当前认证成功、Scope 不足 |
| 实际结果 | HTTP 401，未修复，等待新 Plan 审批 | HTTP 403，DiagnosisReceipt + 冻结草稿，尚未提交交接 |
| 业务写入 | 0 | 0；Scope/Grant 未变 |

S1 的旧 Plan `5fdd6f5c9e3953f9016b569989e91408af87fb4e08b7a5ac9d49537cb92b0a37` 在纠错确认后取消，不能再支撑后续动作。S2 最新回执为 `s2-receipt-1152c486-ae23-44bc-9575-32242aaf8955`，其 Probe、授权 Evidence 与持久 Authz Decision 的 Request/Decision ID 一致。S2 的 `HANDOFF_READY` 只表示草稿存在；没有本阶段 HandoffReceipt、自动授权或恢复成功。

两组 `PREPARATION.json` 明确记载 `reset_fixture(S1_POS)` / `reset_fixture(S2_SCOPE_DENIED)` 是 **Agent 开始前的测试环境准备**。S2 的正确凭证引用和空 Scope Grant 由该准备程序独立设置，不能算 Agent 自行修改环境或恢复业务。浏览器为 Playwright 驱动的真实 Microsoft Edge，截图来自实际 Vue 页面；没有模拟截图或人工点击声明。

## 6. 失败、成本与限制

完整失败清单见 [FAILURES.md](FAILURES.md)：先行 RED 404、初版 Session 关联 500、测试 SQL/状态码假设、错误 Python 环境、含糊表达被保守分类、revision 断言错误、Gate 投影问题、错误 S2 取证字段及 Gold 的两次漏判均保留。提示 v2 只增加对“明确修订/撤回旧前提并要求重新调查”的说明，没有提高预算、改 Gold 或删除失败。

保留的全部五轮 Web 尝试与两轮意图矩阵，共 **127 条真实 Provider 记录、307,985 个已提供 Token、48 个 MCP Attempt / 48 个 Observation**；Usage 缺失为 0。最终一轮 Web 为 21 条 Provider 记录、59,155 Token、10 个 MCP 调用。金额未由 Provider Usage 提供，记为未知。逐次成本及失败尝试均在 [COSTS.json](COSTS.json)，没有只统计最终成功运行。

限制：

- 10/10 只证明这十条冻结表达；没有盲测或新的 R/H/A 收益评估，不声称泛化准确率或动态 Agent 胜过规则。
- 已确认 Task/Run 的 API 重启恢复已测试。分类调用进行中进程崩溃的自动恢复未测试；源码尚无分类 Attempt 的 lease 回收，可能留下 `ASSESSING` 记录。该窗口不创建业务 Run 或授权，不能宣称其可用性已验证。
- S2 的公开 S1 Evidence 列表并非完整授权事实视图；本轮通过 Receipt/Gate、真实 MCP 与 Domain 关联校验 S2 事实。
- 原 M3 Summary DAG 的 PARTIAL、历史 Worker 根因 `ROOT_CAUSE_NOT_PROVEN` 保留；本轮未扩展去修复这些历史问题。
- 本地 SQLite/loopback 和可信演示角色不代表生产 IAM；M4 总体验收和后续阶段均待授权。

## 7. 复跑与阅读入口

在仓库根目录运行，模型配置保持在本地 `.env`，不要提交或把密钥写进命令：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -q --basetemp .runtime/m4-01-repro-full
.\.venv\Scripts\python.exe -X utf8 -m pytest -q tests/test_m4_01_dialogue_updates.py tests/test_m4_01_dialogue_update_safety.py --basetemp .runtime/m4-01-repro-directed
.\.venv\Scripts\python.exe -X utf8 -u -m opspilot.smokes.m4_01_intents
.\.venv\Scripts\python.exe -X utf8 -u -m opspilot.smokes.m4_01
npm --prefix frontend run build
npm --prefix frontend run lint
```

Smoke 每次创建仓库 `.runtime/` 内的新隔离数据库和随机演示凭据，服务只绑定 loopback，不改变用户当前工作台。`DOMAIN_SNAPSHOT.json` 标为运行后只读快照，补充关联与成本；原始浏览器/API 日志和失败文件仍保留。

本证据目录单独设为 Git `-text`，避免跨平台换行转换改变原始日志及 SHA-256；已核对四份先行冻结文件与冻结提交的字节完全相同。

机器结果：[RESULTS.json](RESULTS.json)。源码阅读与设计取舍：[SOURCE_LEARNING.md](SOURCE_LEARNING.md)。面试表达：[INTERVIEW.md](INTERVIEW.md)。全部纳入提交的证据及 SHA-256 见 `ARTIFACT_MANIFEST.json`。

**交付后停止开发，等待主 Agent 独立审查。**
