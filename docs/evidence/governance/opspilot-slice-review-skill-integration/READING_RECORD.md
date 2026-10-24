# OpsPilot Slice Review Skill 集成读取与发现记录

日期：2026-10-24（Asia/Shanghai）
仓库：`wgqa/OpsPilot`（`https://github.com/wgqa/OpsPilot.git`）
本轮 Base：`77ea80e87e538f0f1fae8118ef231ec622601755`
候选分支：`codex/opspilot-slice-review-skill-20261024`

## 范围与基线

候选 worktree 建立于本轮开始时刚核验的 `origin/main`，起始 HEAD 与 Base 均为 `77ea80e87e538f0f1fae8118ef231ec622601755`，初始状态干净。实现前重新 `git fetch origin main` 成功，远端 SHA 仍为该 Base。原工作区本地 `main` 为较旧的 `add47ec…`；本轮没有修改原工作区。只集成项目级开发指导 Skill、在根 `AGENTS.md` 顶部增加入口，并记录实际读取与调用结果；不触及业务源码、运行时、Gate、Gold 或测试结果。

本轮任务合同来自用户当前消息及 ZIP 内 `AGENTS_INSERTION.md`（SHA-256：`DD5254B5308FC46C39E62B2C5AE741EDC358DFF9DBCB35E6AF66BD42A37CCC3A`）。继续 C1 主线所需的 `M4-AUTONOMY-C1-REV1` 任务卡已在执行会话中实际读取，来源为用户附件（SHA-256：`67B673EE3846C1B99C5E36863AA3374667EEADCF2349F6AE4E4A1F213C189F95`）；它只用于辨别后续产品范围，不扩大本轮文档切片。

## 实际读取记录

| 文件或合同 | 实际读取方式 | 版本 / Blob / 状态 |
|---|---|---|
| `.agents/skills/opspilot-slice-review/SKILL.md` | 先读取 ZIP 原文，复制后又完整读取 worktree 安装文件 | ZIP SHA-256 与 worktree SHA-256 均为 `9F95B7BBF2AF6C7B1F6BFE56B0171779D1CC28FE52FB539FBF1403A0FD39EA53`；Git blob `d405c8d413d633824b279202cc1503dab4cf0b03` |
| `PROJECT_NORTH_STAR.md` | 完整读取当前 `main` 版本 | Base Blob `1f737712c7a36ceb34433ac09c3fbba3c3305542`；本轮不修改 |
| `AGENTS.md` | 完整读取 Base 文件；修改后又完整读取候选文件 | Base Blob `30319000ed0054007e9b7b6b46bf98b1493c8179`；候选工作树 Blob `32c45506cceeaa8c76a5c56bf8360ff476b58856` |
| `TASKS.md` | 完整读取，核对历史状态与当前范围标注 | Base Blob `7b17c634692f7ca3ee4d70649674b53ff8cb772c` |
| `PROJECT_NORTH_STAR.md` §8 | 随总纲完整读取，作为唯一正式治理准则 | 未复制其评审协议；AGENTS 入口明确 Skill 仅组织流程 |
| 用户本轮任务卡与 ZIP `AGENTS_INSERTION.md` | 完整读取用户消息与 ZIP 条目 | 当前消息无仓库 Blob；ZIP 条目 SHA-256 如上 |
| M4-AUTONOMY-C1-REV1 用户附件 | 完整读取，保留 C1 后续产品范围背景 | 外部附件 SHA-256：`67B673EE3846C1B99C5E36863AA3374667EEADCF2349F6AE4E4A1F213C189F95`；不属于本轮仓库 Diff |
| vNext v0.3 架构合同 | 本轮文档集成不改变业务合同；未将其作为本轮验收依据全文重读 | `NOT_RUN`（当前任务合同是本轮用户任务卡与北极星 §8） |

北极星匹配：本切片改善开发会话的实际合同读取、Skill 发现和证据分级；没有新增业务能力或用户可见业务结果，因此不计作 C1 产品体验进展。

## Codex Skill 发现与开工核验测试

Codex CLI 版本：`codex-cli 0.145.0`。

1. `codex debug prompt-input 'Use the $opspilot-slice-review skill …'`，退出码 `0`。实际模型可见输入中出现 Skill 名称、完整描述和 worktree 的 `.agents/skills/opspilot-slice-review/SKILL.md` 路径。**结论：发现通过；该命令只证明元数据可见，不证明正文已读取或 Skill 已执行。** 经检查原始 prompt-input 含有额外全局上下文，未把完整文件提交到仓库。
2. 首次 `codex exec` 使用配置默认模型 `gpt-6.1-sol`，退出码 `1`；原始事件报告该模型不支持当前 ChatGPT 登录。记录为失败尝试，不算 Skill 执行通过。
3. 重试使用 CLI 模型目录支持的 `gpt-5.6-sol`，显式提示 `$opspilot-slice-review` 并执行 A 节。Codex CLI 退出码 `0`，产生 `turn.completed` 和完整开工核验结果；事件记录其实际读取 Skill、总纲及 `AGENTS.md`，并继续核对当前任务合同与历史门禁。**结论：独立 CLI 开工核验通过。** 运行中虽有重连、插件目录网络及模型缓存警告，最终 turn 完成；CLI 内 `git ls-remote origin main` 因环境无法连接 GitHub 而失败，所以 CLI 的实时远端状态为 `UNVERIFIED`。父会话在创建候选 worktree 前已通过 `git fetch origin main` 核实 Base 为 `77ea80e…`。
4. 独立 Codex CLI 最终输出将主 Agent 裁决、业务测试及浏览器检查标为 `UNVERIFIED` / `NOT_RUN`，没有把本轮说成主 Agent 审查或产品验收。

原始 JSONL 及 prompt-input 含有与本次提交无关的完整模型上下文、用户环境路径和记忆条目，仅在临时候选 worktree 中用于检查，没有纳入提交。上面的命令、退出码、提取出的模型可见 Skill 元数据和最终核验状态来自实际运行记录。

## 正式评审 Section C 调用

本节是本实施会话对实现提交的 Skill Section C 调用演练。目标版本为提交 `6943c10f5effd334ad1ed890f78057f8ebe40a4a`；该提交版本的 Skill 与 `AGENTS.md` 已从 Git 实际读取，Section C 按提交内容执行。它是实施方自检，不是主 Agent 独立审查。

**审查前置核验**

- Repo / Branch：`wgqa/OpsPilot` / `codex/opspilot-slice-review-skill-20261024`
- Base SHA / Candidate HEAD SHA：`77ea80e87e538f0f1fae8118ef231ec622601755` / `6943c10f5effd334ad1ed890f78057f8ebe40a4a`
- Diff：1 个提交；`AGENTS.md` 顶部入口、项目级 Skill、读取记录，共 3 个文件，+111 行；无合并历史。
- `PROJECT_NORTH_STAR.md`：目标提交 Blob `1f737712c7a36ceb34433ac09c3fbba3c3305542`，完整读取；`AGENTS.md`：Base Blob `30319000ed0054007e9b7b6b46bf98b1493c8179`、候选 Blob `32c45506cceeaa8c76a5c56bf8360ff476b58856`，均实际读取。
- 冻结合同：本轮用户任务卡、ZIP `AGENTS_INSERTION.md`；`PROJECT_NORTH_STAR.md` §8 是权威评审准则。没有新增或复制产品 Gold/业务合同。
- 核验范围：Skill 文件与入口 Diff、Codex model-visible Skill 元数据、A 节运行输出、Git whitespace。业务源码、pytest、HTTP、MCP、Provider、浏览器、独立主 Agent 复跑均 `NOT_RUN`；CLI 实时远端查询 `UNVERIFIED`，父会话 `git fetch origin main` 确认远端 SHA 仍为 Base。

**主 Agent 六维裁决演练**

> **用户变化：** 不增加 OpsPilot 业务能力；后续开发会话会获得实际读取当前 Skill、总纲和阶段合同的清楚入口。
> **Agent 决策：** 产品 Agent 行为未改变；Codex Skill 元数据确实进入模型可见输入，CLI 开工运行实际读取并执行了 A 节。
> **观察驱动：** 发现 Skill 元数据只证明可发现；只有 `codex exec` 读取 Skill 并核验文件才证明开工流程执行。默认模型不支持时，换用 CLI 支持模型后流程完成。
> **新增约束：** 未增加业务 Gate；要求新开发会话读取准则以避免过期记忆覆盖当前合同，同时保留普通问答豁免。CLI 实测证明开工流程可执行；未做业务路径双向测试，因为本轮无业务行为变更。
> **简化结果：** `PROJECT_NORTH_STAR.md` §8 保持唯一权威；`AGENTS.md` 只增加一段入口，没有复制六问、裁决协议或增加脚本、Hook、CI。
> **证据与停止线：** Codex discovery 与 Section A 通过；Section C 为实施方只读自检。实时 GitHub 查询失败、业务测试未运行、主 Agent 独立验收未发生；完成文档集成与读取记录后停止。

**实施状态：** `ACCEPTANCE_CANDIDATE`；不签署 `PASS`，不合并，不进入下一产品阶段，交主 Agent 独立验收。
