# AR-04A-CONTEXT-JOURNEY-01 — 实施报告（验收候选）

**状态：** `ACCEPTANCE_CANDIDATE`（实施方不得自签阶段 PASS）
**实施方：** 主代码开发 Agent（隔离工作树）
**基线：** `48234e5dabb6ed28ea816b8ebc438288409353b8`
**候选分支：** `codex/ar04a-context-journey-01`
**候选提交：** 见本目录 `RESULTS.json` 的 `candidate_sha`（提交后回填）；代码提交与其关系也在该文件记录
**Gold：** [GOLD.md](GOLD.md)（含一次实施前修订记录） ｜ **审计：** [AUDIT.md](AUDIT.md) ｜ **限制：** [FAILURES.md](FAILURES.md)

## 1. 能力矩阵（摘要，完整见 AUDIT.md）

| 能力 | 普通聊天 | 正式调查链路（ASSISTANT_V1） | 结论 |
|---|---|---|---|
| Token 预算 / 估算 | 生效 | 仅整请求度量 | 两套预算口径不一致（本切片修复） |
| 滚动摘要 / 压缩 / DAG | 生效（经典 Worker） | 未接线 | 本切片复用接线 |
| 摘要 currentness / 失效 | 生效 | 未使用 | 本切片沿用同一校验 |
| 任务输入锚点（原始输入/最近纠错） | 生效 | 经 `_prepare_context` 间接生效 | 未改动 |
| 真实模型输入持久化 | manifest + digest | `assistant_calls.request_json` 逐字 | 可核验 |

## 2. 真实调查链路中确认的缺口

1. **预算口径不一致 → 长会话硬失败。** 聊天选择按 12000 选历史，但正式 wire 还含固定 system、WORK_CONTEXT 与工具 schema；`investigator_context_budget` 合并计数后抛 `INVESTIGATOR_CONTEXT_EXCEEDS_BUDGET`。
   - 复现（未修改基线，同一旅程测试）：第 6 轮 `FAILED`，用户提示 `..._BUDGET (15466 > 12000 tokens)`，绑定轮同样失败。
2. **调查链路不执行压缩。** `prepare_chat_attempt` 返回 `CHAT_CONTEXT_COMPRESSION_REQUIRED` 后直接结束。
3. **摘要不进入模型输入。** `_run_assistant` 只取 user/assistant 初始消息，system 摘要被丢弃。

## 3. 用户旅程与冻结 Gold

见 [GOLD.md](GOLD.md) §3–§4：J1 协议咨询 → J2 粘贴配置材料 → J3 多轮无关追问 → J4 可信 API 绑定订单 → J5 当前 Delivery/Receiver 事实 → J6 正式纠错（本轮 `NOT_COVERED`）→ J7 处理情况与下一步。判据 G1–G8。G3 在实施前做过一次有记录的修订（原措辞与既有 Task 作用域隔离冲突）。

## 4. 源码 Diff 与最小实现理由

`git diff --stat`（相对基线）：3 个生产文件，`+181 / −28`；新增 1 个测试文件与 1 个证据目录。

- `opspilot/domain/chat.py`
  - `_prepare_context(..., reserved_tokens)`：为工具 schema / 固定 system / WORK_CONTEXT 预留同一输入预算，选择和压缩判断都改用有效预算；`context_budget` 记录 `reserved_tokens` 与 `configured_input_budget_tokens`。
  - `prepare_chat_attempt` / `prepare_chat_compression_attempt` / `_current_compression_work` / `assert_chat_context_current`：透传 `reserved_tokens`，压缩尝试把它写入 `source_dependencies_json`，恢复/校验时从同一记录读取，避免“预留不同导致 prompt 摘要不一致”。
- `opspilot/assistant.py`
  - 新增 `_prepare_assistant_context`：在首次 Provider 调用前复用既有 `context_compression_attempts` / `context_summaries` Domain 原语完成压缩；预算失败仍 fail-closed。
  - 首次出站前计算 `reserved_tokens = 工具 schema + SYSTEM + WORK_CONTEXT + 一次有界只读观察`；MCP 客户端建立后先探针装配一次上下文，再创建正式 attempt，保证选择预算与真实 wire 一致。
  - 初始消息保留 `HISTORICAL SESSION SUMMARY` system 块（未信任历史），并把 `summary_refs` 写入 `WORK_CONTEXT` 与 provenance。
- `opspilot/domain/context_engineering.py`
  - `investigator_context_budget` 按实际传入的 `summary_refs` 把 `HISTORICAL_SUMMARY` 标为 `SELECTED/UNTRUSTED_DERIVED_CONTEXT`，不再无条件 `NOT_APPLICABLE`。

**为什么不是新框架：** 没有新增表、没有新增运行时、没有新的 Memory/Context 服务；压缩、摘要、依赖与失效全部沿用既有 Domain 代码，只补齐调用点与预算口径。**为什么不是硬编码 Workflow：** 模型仍自行选择工具、澄清或结束；本切片只保证它看得到合法上下文且不会因预算口径错位而崩溃。

## 5. 模型实际 Context 输入与来源证据

`TRACE.jsonl` 由测试在真实 `assistant_calls.request_json` 上生成（每行一个 Run）：

| 用例 | 状态 | 模型调用 | 最大出站估算 | 含摘要 | 含目标 | 含材料 |
|---|---|---|---|---|---|---|
| J1 | SUCCEEDED | 1 | 1263 | – | ✔ | – |
| J2 | SUCCEEDED | 1 | 6741 | – | ✔ | ✔ |
| J3 | SUCCEEDED | 1 | 8437 | – | ✔ | ✔ |
| J4 | SUCCEEDED | 1 | 10131 | – | ✔ | ✔ |
| J5 | SUCCEEDED | 1 | 6818 | – | ✔ | – |
| J6 | SUCCEEDED | 1 | 8498 | – | ✔ | – |
| J7 | SUCCEEDED | 1 | 10404 | **✔** | ✔ | – |
| J4-BIND | SUCCEEDED | 3 | 11179 | – | ✔ | ✔ |
| J5-CURRENT-FACTS | SUCCEEDED | 3 | 10941 | – | ✔ | ✔ |
| J7-FOLLOWUP | SUCCEEDED | 1 | 9923 | – | ✔ | ✔ |

- 预算上限均为 12000；全部出站估算低于上限。
- J7 的 wire 出现 `HISTORICAL SESSION SUMMARY` 且含真实 `summary_id`（测试断言），证明压缩产物确实进入模型输入。
- J4/J5 的 wire 保留 J1 目标与 J2 材料原文；绑定轮不含摘要——这是既有 Task 作用域隔离，测试固定为断言。
- `get_callback_delivery` / `get_receiver_processing` 由 `assistant_calls` 中本 Run 的真实 MCP 调用证实，回答只使用本 Run 观察。

## 6. 新鲜测试、对照与已知限制

- 新增测试：`tests/test_ar04a_context_journey_01.py`，4 passed（41.14s，见 `runs/pytest-ar04a-journey.log`）。
- 对照（同一测试、同一夹具、未修改基线 `48234e5`）：第 6 轮 `FAILED`，绑定轮 `FAILED`，用户提示 `..._BUDGET (15466 > 12000 tokens)`；候选版本全部 `SUCCEEDED`。原始日志 `runs/red-baseline-journey.log`。
- 定向回归：`test_m302_context.py`、`test_ar02_journey_p0.py`、`test_ar02_context_continuity_01.py`、`test_m1_chat.py`、`test_ar02_assistant.py`，32 passed（43.61s）。
- 全量 pytest（工作树根目录，单独运行）：679 收集 / 678 passed / 1 failed / 832.02s；唯一失败是冻结的历史 C1 RED（`test_m4_autonomy_c1_red.py::test_explicit_protocol_followup_is_accepted_as_same_task_readonly_run_before_ttl_fix`，使用废弃 `READONLY_FOLLOWUP`），未修改。原始日志 `runs/pytest-full-suite.log`。
- 限制（详见 FAILURES.md）：J6 未覆盖；Task 作用域摘要不复用；绑定前材料早于最近窗口时可能被淘汰；工具观察预留为 1024 token 的有界估计；真实 Provider / 浏览器 `NOT_RUN`。
- Provider 调用：0。业务写入：0（测试断言 `d3_action_intents`/`d3_action_ledgers`/`d3_approvals`/`s3_handoff_receipts` 均为 0）。

## 7. 最终候选 SHA

- 代码 + 测试 + 证据提交：`b6f3ea54b2dcc2589b5c3172303faa7bcb307082`（已推送到 `origin/codex/ar04a-context-journey-01`）
- 分支 head 上可能再有一个仅更新本文件/RESULTS 记录字段的 bookkeeping 提交，代码树与 `b6f3ea5` 相同；以 `git rev-parse origin/codex/ar04a-context-journey-01` 为准
- 本任务只提交隔离候选，不合并 `main`

## 8. 建议

`ACCEPT_WITH_LIMITS`（候选）。理由：真实缺口已被独立复现并由同一测试证明修复；安全边界未放宽（失效摘要不回流、超预算仍 fail-closed、零业务写入、任务作用域隔离被固定为断言）。限制在于 J6 正式纠错未在本旅程内端到端复验、Task 作用域摘要不复用，以及缺少真实 Provider 与浏览器证据。请主 Agent 独立核验后再决定是否合并与进入下一个切片。
