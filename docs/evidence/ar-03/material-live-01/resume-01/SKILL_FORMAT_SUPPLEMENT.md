# AR-03-MATERIAL-LIVE-01 Resume-01 — Skill 字节完整性补证

## 范围

仅处理付费前回归中的 `protocol-upgrade-impact-analysis` Skill 完整性失败。没有修改业务运行逻辑、Gold、manifest、历史失败、费用账本或一次性 claim。

- Base：`2b4367e68ce622d7017bf530224c58f3ddc95cd0`
- 修复提交：`9c04af1193936c8a4a6b21a09929b0f2aeca6c93`
- 分支：`codex/ar03-material-live-01-exec-prep`
- main：`ec8c3582f6d145eec9979c43607302731411ead8`（未修改）

## 根因

当前 Windows Git 配置为 `core.autocrlf=true`。该路径原先没有对应的 `.gitattributes` 规则，因此 Git 索引中的 LF 文件被检出为 CRLF。

| 对象 | 字节数 | SHA-256 | 换行 |
|---|---:|---|---|
| 本地原始工作树文件（修复前） | 1730 | `6546b5531a0478d87cd83468e1a8b23b9d6a63d030e847e4cc2ac91b9899a46d` | 12 CRLF |
| LF 归一化后的内容 | 1718 | `aea84ee9efe7cea60fe0262681251bdbba51866de58dcd67c575a8c8b581fd40` | LF |
| Git blob / manifest digest | 1718 | `aea84ee9efe7cea60fe0262681251bdbba51866de58dcd67c575a8c8b581fd40` | LF |

LF 归一化内容与 Git blob 逐字节一致；manifest 的原摘要正确。三个 Run 失败与完整性测试失败具有同一直接原因，原始 Domain SQLite 的 `task_runs.blocked_reason` 均为 `ASSISTANT_STOP:TaskControlError:PROTOCOL_UPGRADE_SKILL_SOURCE_INVALID`。这三项分别是材料 Skill ON/OFF 调查及同 Event QUEUED、PROCESSED 两条路径。未修改摘要校验或错误处理。

修复只在根 `.gitattributes` 为此 Skill 文件增加 `text eol=lf`。修复后 `git ls-files --eol` 显示索引 `i/lf`、工作树 `w/lf`，manifest 与文件字节摘要一致。

## 验证

定向免费测试：9 passed，包括 Skill digest / 按需加载、Skill OFF/ON、正式 Assistant 材料调查，以及同 Event Receiver `QUEUED` 和 `PROCESSED` 的只读路径。

零费用 Preflight：提交后的修复提交 `9c04af1` 上通过，状态为 `PREFLIGHT_READY_AWAITING_PAID_AUTHORIZATION`。结果确认 `paid_dispatch_authorized=false`、`one_shot_consumed=false`、Provider 请求 0、MCP 调用 0、无业务写工具暴露，独立运行数据库不存在。首次在未提交工作树运行 Preflight 时，其按预期以 `WORKTREE_OR_INDEX_NOT_CLEAN` 拒绝；Provider 请求仍为 0。最终文档提交后的再次 Preflight 结果见交付消息记录。

私有原始日志保留在本机 `.private-evidence/ar03-material-live-01-exec-prep/`，未提交到公开仓库：

- `hf01-targeted-01.log` SHA-256：`b2dd226a254c93865e6d89f31d47c8a3b53b15090bed775e416aaf19ae2715f4`
- 首次被干净树门禁拒绝的 `hf01-preflight.log` SHA-256：`876df30a31f8741fcccbb4845f4f53bbf072b8d0f5478a215c845a0b66d3de46`
- 修复后通过的 `hf01-preflight-after-fix.log` SHA-256：`bb715dfacb43506983981c3ea3bbb8ad1d5d88ce61f83ac9694de589f42b4f46`

此前的 73 passed / 4 failed、未修改安全基线上的 6 passed / 同 4 failed，以及原 SQLite 错误记录均保留；未重跑全量 pytest。新定向测试覆盖了这四项相关路径。

## 未解决风险与停止线

本地 Skill 完整性和相关离线材料旅程已验证。真实 DeepSeek 调用仍未授权、未运行；没有证明真实模型行为。此补证未消费 one-shot claim、未进行业务写入、未更改 main。等待主 Agent 独立复核后再决定是否另行授权收费执行。
