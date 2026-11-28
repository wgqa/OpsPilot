# 审计执行记录

本轮为归档可复现性审查。命令均只读；未运行模型或应用服务。

| 检查 | 命令 / 方法 | 结果 |
|---|---|---|
| 候选基线 | `git rev-parse HEAD`; `git status --short --branch` | Base `9e9f7b05afcdd51e05c4c4af605bb225c53bd2bd`；原执行 worktree 仅有既存 `.pytest-tmp-r1-j2-live-recheck-02-*` 未跟踪目录，未触碰。 |
| 远端状态 | `git ls-remote origin refs/heads/codex/r1-j2-live-recheck-02 refs/heads/main` | 候选 `9e9f7b05afcdd51e05c4c4af605bb225c53bd2bd`；main `60eee87bfe3cca522011316cb4cd2c0064ad291b`。 |
| 冻结输入 | `git rev-parse HEAD:docs/evidence/vnext/r1-j2-live-recheck-01/CASES.json` | `320bab6afc5668c675455d370e6a3ded51119b08`，与任务卡一致。 |
| 私有归档盘点 | PowerShell `Get-ChildItem -Force -Recurse -File`，限于原 Campaign 目录 | 发现最终 DB、Checkpoint、日志、最终摘要、Claim/授权及其 hash manifest；没有事前快照文件。 |
| SQLite 只读检查 | Python `sqlite3.connect('file:...?...mode=ro', uri=True)` 查询表行数 | Domain 与 Checkpoint 均为 Campaign 最终状态；1 Session/4 Runs/4 答案；22 checkpoints/53 writes/4 threads。 |
| 私有证据完整性 | Python SHA-256 对照原 `PRIVATE_HASHES.json` | 所检查的 DB、Checkpoint、摘要、Claim、turn/Provider/Assistant 日志均匹配。 |
| 历史 Gold 结果 | 读取 `LIVE_RESULTS.json`、`LIVE_REPORT.md` | J2-02 仍为 PARTIAL；未修改。 |
| 代码与测试 | 未修改源码；未运行 pytest | `0` 代码改动、`0` 测试运行。 |
| 外部动作 | 无 Provider / MCP / Browser / 业务执行 | Provider `0`、MCP `0`、Browser `0`、外部业务写入 `0`。 |
| 发布 | `git push -u origin codex/r1-j2-02-repeat-01`；官方 GitHub connector 创建 Blob | Git transport 无法连接 `github.com:443`；connector 返回 HTTP 403 `Resource not accessible by integration`。没有创建远端候选分支，也没有绕过限制。 |

注意：SQLite 检查通过只读 URI 执行，未执行 SQL 写入、删行或重置。原始私有文件未复制到 Git。
