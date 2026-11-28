# OpsPilot · ABC-LIVE-ENV-UNBLOCK-01 执行报告

**状态：`ACCEPTANCE_CANDIDATE`**
**Base：** `e8ddb1cae60dc2782d0d3581856d1aaa3ea35775`
**初始 HEAD：** 与 Base 相同
**候选分支：** `codex/r2-ar04-live-semantic-abc-01`

## 结论

使用主仓库根目录 `.env` 的隔离路径已修复并验证。最终零费用预检通过后，按冻结范围完成了 A/B/C × Q02/Q03/Q06 九个真实 Provider Case：12 次摘要、9 次回答，共 21 次请求，费用 **USD 0.032708**，低于 USD 0.15 上限。无未知发送、自动重试、模型漂移、输出截断或工具调用；所有请求、Usage、响应 ID 和账本均已保存。

真实语义结果同时显示可复现的信息损失：A、B 的第二次摘要分别丢失早期 `/callback`；B 的第二次摘要丢失 `v1.2 → v1.3` 和 `max_attempts 3 → 5`。原始 Provider 请求、响应、Fixture、Gold、旧账本均未修改。本任务没有改动生产压缩代码。

## 开工基线与范围

- 已在目标 Worktree 实际读取 `PROJECT_NORTH_STAR.md`、`AGENTS.md`、`.agents/skills/opspilot-slice-review/SKILL.md`，并复核冻结实验配置和 Setup-HF01 Grant / Mock Harness 证据。
- 本轮目标文件版本记录：`PROJECT_NORTH_STAR.md` Blob `43dabda468506717c6956e676dfad4304c4f38e6`；`AGENTS.md` Blob `807b928686a4dd2cac7b15b3c354b9943c93c910`；Review Skill Blob `d405c8d413d633824b279202cc1503dab4cf0b03`。
- 复用现有 Worktree；没有创建 Worktree。修改仅在本任务证据目录中。
- 保留原有 `.pytest-tmp/`、Setup-HF01 `.pytest-basetemp-budget/` 和所有历史 Demo、Session、Memory、Domain、账本与冻结结果。

## 环境读取和零费用预检

Runner 显式使用 `ROOT.parent.parent / ".env"` 并调用 `load_local_environment(main_env)`。主目录 `.env` 找到且成功读取。输出只包含六项配置的存在布尔值：API Key、模型名和 Base URL 已存在；Config Version、Price Version、Service Identity 缺失，并由本任务补充为非敏感实验配置。任何凭据值均未输出、复制或写入证据。

`.env` 中的官方 DeepSeek 地址带 OpenAI 兼容 `/v1` 后缀。Runtime Grant 接受该地址，但 DeepSeek Chat Completions 的官方端点为根路径 `/chat/completions`；Runner 只在 HTTPS 官方主机及根路径或 `/v1` 范围内将它规范化为官方根地址，未改全局环境加载函数。该行为由离线断言覆盖。参考：[Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)、[DeepSeek 官方 OpenAI 兼容集成说明](https://api-docs.deepseek.com/quick_start/agent_integrations/oh_my_pi/)。

首次零费用预检因 Runner 将 `/v1` 后缀与根地址做严格字符串比较而阻断，结果保留在 `live_run_01/PREFLIGHT.json`，Provider 请求数为 0。规范化后重新预检通过：隔离临时 Domain 中的 Runtime Grant 合法绑定 Assistant Run，模型由 Mock Transport 构造，Transport 调用数和 Provider 请求数均为 0；未打开生产数据库。六项有效配置存在性、补充字段和 Grant 结果见 `live_run_02/PREFLIGHT.json`。

## 执行结果

| 组 | 策略 | 摘要请求 | 回答请求 | 结果 |
|---|---|---:|---:|---|
| A | HYBRID | 6 | 3 | 3 Case 完成 |
| B | ROLLING_SUMMARY | 6 | 3 | 3 Case 完成 |
| C | RECENT_WINDOW | 0 | 3 | 3 Case 完成 |

九个 Case 使用相同 29 条固定合成历史、问题、工具 Schema、受信任 Prompt 前缀和 12,000 Token 输入上限；Domain、Checkpoint 和 Runtime Grant 均按 Case 隔离。答案请求均使用 `tool_choice=none`、temperature 0、`thinking.type=disabled`，最大输出 512 Token。Gold 和评分规则未进入任何请求。未提供或执行外部 MCP、DeepSeek Search/Fetch 或业务动作。

DeepSeek 官方价格页在执行前核对的峰值未缓存输入价为 USD 0.30/M、输出价 USD 1.20/M；按每次 12,000 输入 / 512 输出的上界向上取整，每请求预留 USD 0.004215，21 次总预留 USD 0.088515，低于 USD 0.15。实际费用为 **USD 0.032708**。参考：[Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)、[Chat Completions 参数](https://api-docs.deepseek.com/api/create-chat-completion/)。

真实调用证据：`live_run_02/LIVE_REQUESTS.jsonl.gz`、`live_run_02/COST_LEDGER.json`、`live_run_02/LIVE_RESULTS.json`。Trace 有 21 个唯一 Provider 响应 ID 和 21 组完整 Usage；所有响应模型为 `deepseek-flash`、HTTP 200、`finish_reason=stop`。账本没有 `UNKNOWN`、未结预留或停止原因。

## 初步语义结果

| 问题 | A · HYBRID | B · ROLLING_SUMMARY | C · RECENT_WINDOW |
|---|---|---|---|
| Q02 `/callback` | `SAFE_ABSTENTION`：最终 Summary 和实际回答 Prompt 均不含早期 endpoint | `SAFE_ABSTENTION`：第二次摘要丢失 endpoint | `SAFE_ABSTENTION`：近期窗口中没有 endpoint |
| Q03 `req-483` 正式更正 | `CORRECT_SUPPORTED` | `CORRECT_SUPPORTED` | `CORRECT_UNSUPPORTED`：Prompt 有 `req-483`，但没有 `req-482` 和正式更正来源；答案把该值归因于更正 |
| Q06 `v1.2 → v1.3` | `CORRECT_SUPPORTED`，并正确保留 `max_attempts 3 → 5`、部署版本未知 | `SAFE_ABSTENTION`：第二次摘要没有保留版本变更文本 | `SAFE_ABSTENTION`：近期窗口没有版本变更事实 |

计数为 3 `CORRECT_SUPPORTED`、1 `CORRECT_UNSUPPORTED`、5 `SAFE_ABSTENTION`、0 `INCORRECT_OR_UNSAFE`。这是小型选题样本，不能作为总体准确率。评分文件标记为 `IMPLEMENTER_PRELIMINARY_REVIEW`；主 Agent 独立复核尚未执行。

实际摘要版本和逐条事实可见性见 `VERIFY_RESULTS.json`。Q02-A/B 第一次摘要都含源序列 3 的 endpoint，第二次摘要和最终回答输入均不含 `/callback`。Q06-B 最终摘要声明过源序列 11，但没有保留版本变更文本；最终回答输入也没有 `v1.2` / `v1.3`。这些是模型摘要内容和实际发送 Prompt 的证据，不是 Fixture 对模型记忆效果的替代。

## 安全、失败记录与验收

- 最终机器证据复核全部通过，包含 21 次账本与 Trace 对账、请求上限与费用、身份绑定、隔离、Prompt / Schema 对齐、Gold 泄漏、工具边界和 API Key 扫描：`VERIFY_RESULTS.json`。
- 离线测试 8/8 通过，覆盖主目录环境读取、凭据不打印、非敏感默认配置、预算发送前拒绝、UNKNOWN 停止、逻辑请求不可重发和工具调用拦截：`test_abc_runner.py`。
- 首次 Mock 的 9 Case 已执行完，但产物打包发生跨盘 `WinError 17`；原结果及可恢复 Trace 保留在 `mock_run_01/`，随后改为目标目录同盘打包。`mock_run_02/` 和 `mock_run_03/` 均完整通过，最终代码对应 `mock_run_03/`。
- pytest 首次默认临时目录因 Windows `WinError 5` 无法枚举而失败；改用本证据目录下全新 basetemp 后通过。完整命令、退出状态和失败说明见 `TEST_RUN.txt`。
- 本目录未包含 `.env`，最终扫描没有在证据文件中找到 API Key。未修改生产算法、Gold、旧 Trace 或旧账本；未合并 main。

**验收请求：** 请主 Agent 独立检查 Base / HEAD / Diff、完整原始 Trace、实际摘要与最终输入，并复核九个回答和信息损失结论。当前只提交 `ACCEPTANCE_CANDIDATE`。

## 实施方候选验收摘要

> **用户变化：** 没有新增产品能力；本轮解除真实评测环境阻断，并产出了首轮真实 A/B/C 长会话语义证据。
> **Agent 决策：** 历史回忆请求使用 `tool_choice=none`；模型可依据输入回答或安全弃答，不执行工具。
> **观察驱动：** Summary v2 保留或丢失关键事实，分别导致有证据回答、无证据弃答或无证据归因。
> **新增约束：** 任务级 Runner 限制 Provider、Token、费用、请求数和重试；Mock 正向路径、预算阻断和 UNKNOWN 停止均有断言。
> **简化结果：** 复用 Setup-HF01 Harness 与 Runtime Grant；不新增授权系统，不修改生产代码。
> **证据与停止线：** 真实请求 21 次、USD 0.032708、无 UNKNOWN；完整 Trace 和账本已保存。当前切片停止，等待独立主 Agent 验收。

**实施方状态：** `ACCEPTANCE_CANDIDATE`；主 Agent 裁决：`NOT_PERFORMED`。
