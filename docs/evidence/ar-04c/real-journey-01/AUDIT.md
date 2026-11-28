# AR-04C-REAL-JOURNEY-01 — 开工与差异审计

## 仓库与范围

- Repo：`wgqa/OpsPilot`
- 隔离工作树：`D:\学习\agent新项目\.worktrees\ar04c-real-journey-01`
- 分支：`codex/ar04c-real-journey-01`
- 授权基线：`main@60eee87bfe3cca522011316cb4cd2c0064ad291b`
- 冻结合同提交：`d5ba562c5234e86036ae714451b23e398faf8acf`
- 测试源码提交：`6951bcd7a2d791a1454c46b3b70077ebdf909cba`
- 最近复核的 `origin/main`：`60eee87bfe3cca522011316cb4cd2c0064ad291b`
- 本轮未修改 main；没有清理原工作区、历史实验数据库或 pytest 临时目录。

## 实际读取的规则和合同

| 文件 | HEAD Blob | 读取/用途 |
|---|---|---|
| `PROJECT_NORTH_STAR.md` | `e36f2f75509738551ac6d4a2de5b4f9cf44a7991` | 按正式评审前置要求实际读取 |
| `AGENTS.md` | `f174a6ab7f23f9e6d8b3ef98d455b99a75193143` | 实际读取；确认 Skill、证据和停止要求 |
| `.agents/skills/opspilot-slice-review/SKILL.md` | `d405c8d413d633824b279202cc1503dab4cf0b03` | 开工时实际读取并应用 A/B 核验 |
| `docs/learning/OPEN_SOURCE_AGENT_REFERENCES.md` | `5c422316164e20a922ad0596233070716225be07` | 实际读取 |
| 初始 `PLAN.md` | `adff796cc35692fae8e98b2c3ef6c2cebbff1fcb` | 冻结提交版本；价格更正保留为后续提交 |
| `GOLD.md` | `f57913861101b9a0aaff6c3219d908dc8ce18762` | 冻结且本轮未修改 |
| `CASES.json` | `4301b7feb2c79d4965105ae9587a07ade7226cdd` | 冻结且本轮未修改 |
| 初始 `BUDGET.md` | `e4d87e70b5fbc4a3c9b65bd0e2edb340e2ae3d40` | 冻结初稿；后续仅作官方价格勘误，见下文 |

文件 Blob 指 Git 对象 ID；初始冻结合同和原始运行日志均保留在 Git 历史与 `runs/`，没有重写 Gold。

## 定价更正

重新打开 DeepSeek 官方 [Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/) 后确认：`deepseek-flash` 对应 `DeepSeek-V4.1-Flash-1017`；峰值缓存未命中输入为 `$0.30/M`、峰值输出为 `$1.20/M`。初稿将同一表中 V4 Pro 的 `$1.32/M` 输入价误读成 Flash 输出价。修正后最坏预留为 `$0.645600`；每条件 8 次为 `$5.164800`，两条件 16 次为 `$10.329600`，均低于冻结的 `$5.25/$10.50` 上限。该勘误在任何真实 Provider 出站和付费授权前完成，旧实验费率、记录和账本未变。

## 变更范围

实现只为 `AR-04C-REAL-JOURNEY-01` 增加显式 Memory ON/OFF 上下文、独立价格/费用预留、Campaign 预算行和 `orders-async-demo` Task 预算策略。默认应用及旧实验价格、预算、MCP 上限和 Memory 行为保持原逻辑。未改 Memory 生命周期、授权模型、业务工具 Schema、Gold、Approval、ActionIntent、Ledger 或 Handoff。

当前源码 Diff：6 个 Python 源文件；另有 1 个新定向测试模块和 `PLAN.md`/`BUDGET.md` 勘误。没有依赖升级。

## 执行权限

- 真实 DeepSeek Provider 请求：0。
- 浏览器/Playwright：0。
- 外部业务写入：0。
- S3/D3 业务审批、ActionIntent、ActionLedger、Handoff Receipt：0。
- 测试夹具按 J1 要求通过既有 Memory Candidate API 与 Confirm API 建立/确认一条 Memory；这属于测试 Domain 中有意执行的 Memory 生命周期，不是外部业务交接或 S3/D3 写入。
- 真实授权记录、one-shot claim 和授权 token 均未创建；离线测试中的 API Key 字符串为占位符，只传入显式 MockTransport。

工作树中的历史失败、Trace、Gold 和临时目录均保留。正式报告将离线 FixtureModel 的固定行动明确标为模拟，不推断真实模型自主性或 Memory 效果。
