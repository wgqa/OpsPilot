# R2-AR04-LIVE-RECHECK-V2-PREP-01

**状态：`ACCEPTANCE_CANDIDATE`（离线准备与 Mock 验收）**
**Provider 请求：0；费用：USD 0；外部 MCP：0；生产数据库写入：0**

## 开工核验

| 项目 | 核验 |
|---|---|
| Repo / Worktree | `wgqa/OpsPilot`，复用 `.worktrees/ar04a-context-journey-01`；未新建 Worktree |
| 分支 / Base | `codex/r2-ar04-live-recheck-v2-prep-01` / `d8a526daa9c811814a5e2463b34eb37037ae1a8e` |
| 开工 HEAD | Base SHA；远端旧候选 `codex/r2-ar04-live-summary-persist-hf01` 同为此 SHA |
| 远端 main（开工核对） | `60eee87bfe3cca522011316cb4cd2c0064ad291b` |
| 本候选远端分支 | 开工时不存在；推送后核验 |
| `PROJECT_NORTH_STAR.md` | 实际读取；Base blob `43dabda468506717c6956e676dfad4304c4f38e6` |
| `AGENTS.md` | 实际读取；Base blob `807b928686a4dd2cac7b15b3c354b9943c93c910` |
| `opspilot-slice-review` Skill | 实际读取；Base blob `d405c8d413d633824b279202cc1503dab4cf0b03` |
| v1.0 冻结实施基线 | 实际读取；Base blob `30e18d7ddbade7cdf7712d035d6fd8488bcb9676`。本轮仅离线 Context 实验，不触及业务动作授权/执行 |
| AR-04 冻结依据 | Setup-HF01、HF-02 / Summary-Fact-Retention、Retention-Recheck-01 原任务与原 Trace；均只读 |
| 遗留门禁 | C06 RED 与 F01 `completed_tools` 既有记录保留；通过 Git blob 与 Base 对照核验未改写。M2-01/M2-02 Deferred Gates 已读，受控业务写入门禁不属于本轮实验 |
| 保存的正式主 Agent 裁决 | 旧 `RESULTS.json` 标为 `independent_main_agent_review: NOT_PERFORMED`；本轮不把实施方结果写成主 Agent 验收 |
| 开工工作树 | 已有多项历史未跟踪测试输出；全部原样保留。本轮只提交本任务证据目录的明确文件 |

## 任务判断

用户的学习目标是把 Context Compression 修复放回真实 Assistant + Runtime Grant + Domain 路径复测，并保证未来真实复测对当前生产版本和冻结输入有可审计的绑定。本轮没有产品行为变化；Mock 成功只证明运行与持久化链路，不证明模型记忆、自然语言答案或 L3 语义效果。

V2 只开放 `mock` 与 `preflight` 两种 CLI 模式。V2 没有 live-send 路径；旧付费授权、旧授权任务名或旧账本都不能启动真实调用。后续真实评测需单独新授权和一个经审阅的执行入口。

## 固定矩阵与配置

| Case | 策略 | 最终 Prompt 必须包含 |
|---|---|---|
| Q02-A | HYBRID | seq3 的 `endpoint=/callback`，并带有效来源 |
| Q02-B | ROLLING_SUMMARY | seq3 的 `endpoint=/callback`，并带有效来源 |
| Q06-B | ROLLING_SUMMARY | seq11 的 `v1.2 → v1.3`、`max_attempts 3 → 5`，并带有效来源 |

三例各自 seed 相同的 29 条合成历史，问题全文、Gold/Rubric、工具 Schema、可信 Prompt 前缀、模型别名与参数由冻结 SHA/Digest 固定。Runtime 输入硬上限 12,000 Token，Assistant Context 设置 12,000；最终运行有效 Context 预算实测为 Q02-A 8,185、Q02-B 8,188、Q06-B 8,184 Token。摘要输出上限 512 Token。回答使用 `tool_choice=none`。九个逻辑请求槽共享一个隔离 Mock 账本；实际 Provider 发送及费用恒为 0。

## 六问

1. **用户变化：** 本轮是学习实验，不让用户完成新的业务任务；验证后续复测能否复用当前 Assistant、Grant 与摘要持久化路径。
2. **Agent 决策：** 历史回忆 Track 不允许模型调查工具；本轮 Mock 回复不是 Agent 决策证据，也不增加自主性。
3. **观察驱动：** Q02 目标由 seq3 来源支持，Q06 的版本和参数变化由 seq11 支持；来源撤销时停止压缩后续，而不是继续回答。真实模型看到何种事实会如何作答，本轮不判定。
4. **约束双向检查：** 固定源码/输入/Schema 可阻止旧代码和 Gold 混入新复测；按冻结值运行的三例仍可经完整路径通过。UNKNOWN/撤权/持久化失败阻断后续请求；正常 Mock 调用继续受理。所有边界均有正反用例。
5. **责任与简化：** 复用 Setup-HF01 Runtime Grant、Assistant API、Domain 和 ABC 全局账本；新增版本适配与冻结声明，不改旧 Runner，不新增 Runtime、Memory 或评测平台。
6. **证据与停止线：** 保存完整 Mock Trace、Domain 持久摘要、Answer Manifest 输入、来源诊断、Mock 账本、离线预检和 C01–C08 测试。停止于 `READY_FOR_AUTHORIZATION`；不发真实请求，不执行 MCP，不自动开始付费轮次。

## 验收范围

- 实施代码与测试：本目录 `run_v2.py`、`test_runner_v2.py`。
- 实际路径：`Session History → Assistant Context Builder → Mock 摘要 → Domain Summary 持久化 → 第二轮摘要 → 最终 Answer Prompt → Mock Answer → Answer Manifest`。
- C01–C08 失败及来源边界见 [`FAILURE_MATRIX.json`](FAILURE_MATRIX.json)。完整成功链与请求 Trace 见 [`MOCK_RESULTS.json`](MOCK_RESULTS.json) 和 [`MOCK_TRACE.jsonl.gz`](MOCK_TRACE.jsonl.gz)。
- 零费用预检为 [`PREFLIGHT.json`](PREFLIGHT.json)，其状态仅为 `READY_FOR_AUTHORIZATION`。
- 测试命令和实际退出码见 [`TEST_RUN.txt`](TEST_RUN.txt)。
