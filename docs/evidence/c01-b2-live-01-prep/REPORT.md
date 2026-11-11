# C01-B2-LIVE-01 环境准备记录

**状态：** READY_FOR_USER_LIVE_TEST（需用户在本机输入 Provider Key）

**工作树 / 分支：** `D:\OpsPilot-C01-B2-LIVE-01-PREP` / `codex/c01-b2-live-01-prep`

**审计对象：** `d26bf7cf11b01f24f9c0b288d4b3a363ffd825f8`

**候选 SHA：** 交付时以分支 HEAD 为准；本报告随同候选提交。
**Luna 的真实 Provider 发送：** 0。没有业务写入、费用结算或 UNKNOWN 请求。

## 基线核验与合同

在目标基线工作树实际读取并核对：

| 文件 | 目标 Blob |
| --- | --- |
| `PROJECT_NORTH_STAR.md` | `43dabda468506717c6956e676dfad4304c4f38e6` |
| `AGENTS.md` | `807b928686a4dd2cac7b15b3c354b9943c93c910` |
| `.agents/skills/opspilot-slice-review/SKILL.md` | `d405c8d413d633824b279202cc1503dab4cf0b03` |
| `docs/evidence/c01-b2-b/ADR-001-personal-memory-auto-consolidation.md` | `a7a0639ef3ff466bd2b1cffd6c7fb158d49a258e` |
| `opspilot/domain/assistant_runtime_grant.py` | `805d5a1dbff4774f9c7f91ee17782ad32d3e7119` |
| `opspilot/web/worker.py` | `c0ffbb8fca30820dd2ed5101ab32abceb30b53e8` |
| `opspilot/domain/semantic_memory.py` | `b1eb530fc25ad8715a5ca30f3abc8d3a2a2c313a` |
| `opspilot/domain/personal_memory_consolidation.py` | `5d321d5614d53e4c70798519a72937d61106ccaf` |
| `scripts/user-demo/Start-UserDemo.ps1` | `81fa80d8a3cbfca22b49c24c17cbf561e33d97de` |
| `scripts/user-demo/runtime_admin.py` | `b79d0ff14179335c261fd2d95219fff64c90cbe1` |
| `scripts/user-demo/Stop-UserDemo.ps1` | `cb1264e4e28d537eafd4ac94985969b96e836320` |

本轮遵守当前用户任务卡与 North Star；沿用现有 Runtime Grant、个人记忆、Consolidation Job、FastAPI Worker 和启动器，没有改 Provider 适配器、Schema、安全合同或业务 Domain。自动学习规则取自 B2-B ADR：同一 Session 至少 6 条成功用户消息；Worker 每批最多读取 12 条、至多 4 条提案、一个额外提取调用；成功批次后至少间隔 10 分钟。HF01 最近一次主 Agent 裁决不在目标提交的仓库证据中找到，标为 `UNVERIFIED`，没有据此扩展代码范围。

## 环境与费用配置

- 独立工作树只基于指定 B2-B HF01 提交建立；没有在当前其他工作树改动，也没有合并 `main`。
- 初始化专用 `.runtime/user-demo/domain.sqlite3` 和 Checkpoint；Domain Schema 为 v24。仅含本地测试身份/Fixture，没有聊天消息、Run、Assistant Call、Memory 或费用支出。
- 在官方价格复核时发现原先待用输出费率 `$1.20/1M` 已过时，修订为当前官方峰值 `$1.32/1M`。旧的、由本轮创建且零发送/零支出的准备数据库及其日志完整保存在被忽略的 `.runtime/user-demo-preprice-20261111`；活动环境从干净隔离库重建，启动器只使用 `.runtime/user-demo`。
- 活动数据库有独立 ACTIVE `$1.00` Grant/Spend Pool：`deepseek-flash`、官方端点、12,000 输入 / 2,048 输出 Token、输入 `$0.30/1M`、输出 `$1.32/1M`、单次最大预留 `$0.006304`，Grant 到期 `2026-12-11T09:56:00Z`。当前已用 `$0.000000`、可用 `$1.000000`、发送许可次数 0、UNKNOWN 0。
- Grant 是 OpsPilot 应用账本预算，不保证供应商发票绝不超过该数。系统没有 10 次硬停止；10 次是人工流程目标。预算根据固定费率与实际/预留 Token 检查，不会自动增加或自动解冻。
- `.env` 是 Git 忽略文件。当前未保存用户 API Key；本机 Live preflight 返回 `USER_DEMO_LIVE_CONFIG_MISSING:OPSPILOT_MODEL_API_KEY`（预期结果），没有发出请求。用户运行 `Set-C01B2LiveCredentials.ps1` 输入自己的 Key 后即可执行成功预检；这不需要代码调试。
- Provider 费率按 [DeepSeek 官方定价文档](https://api-docs.deepseek.com/quick_start/pricing/) 核对。官方文档说明 `deepseek-flash` 使用 `https://api.deepseek.com`，官方价格可能变化，过期后须复核。

## 实际改动

- `scripts/user-demo/runtime_admin.py`：预检和费用摘要额外读取 `send_granted_at` 次数及 `UNKNOWN` 数，供用户观察发送许可与不确定请求；不更改 Runtime Grant 的发放或花费逻辑。
- `scripts/user-demo/Set-C01B2LiveCredentials.ps1`：隐藏输入 Provider Key 和私密 SUPPORT 密码，写入被忽略 `.env` 并设置当前用户/SYSTEM ACL；固定模型端点、版本与官方峰值费率。没有打印秘密或发送 Provider 请求。
- `scripts/user-demo/export_live_evidence.py`：只读导出 SUPPORT 自有 Session 的消息、Runs、模型输入/输出、Context Manifest、整理 Job、Memory 来源/版本/事件和账本；输出限制在隔离 evidence 目录，并清理 API Key、Authorization、Cookie、密码及常见令牌形式。
- 新增本文件及 `USER_GUIDE.md`。无生产 Python、前端、Schema、依赖锁或冻结合同改动。

## 离线验证

| 验证 | 结果 |
| --- | --- |
| `python -m compileall -q opspilot scripts/user-demo` | PASS |
| `python -m pip check` | PASS，无坏依赖 |
| B2-B / B2-A / Runtime Grant 4 个相关测试文件 | PASS，75 passed，260.09 秒 |
| `npm run build` | PASS |
| `npm run test:e2e:c01-b` | PASS，使用 Mock API，不是真实模型测评 |
| PowerShell `scripts/user-demo/*.ps1` 解析 | PASS |
| `npm ci` 使用本地隔离 cache | PASS，147 包；此前共享 cache 有一次权限拒绝，未改依赖锁 |
| `npm audit` | 报告 10 个 moderate advisory；没有升级依赖或改锁文件 |
| 活动隔离环境 Offline 启停 | PASS：API 200，Worker ready/running，Vue 200，`support-a` 登录 SUPPORT 成功，个人设置读取成功；默认 auto learning 为 false、Offline 可用性为 false；Stop 脚本优雅关闭并保留数据 |
| 导出器正向/越权路径烟测 | PASS：SUPPORT 自有 Session 可导出；未知/越权 Session 被拒绝且不创建目标输出；正向烟测使用临时隔离 DB 和假账本响应，不触发 Provider |
| Personal Memory 设置 API 读写 | PASS：默认 recall=true / auto-learn=false；API 成功关闭再恢复 recall；Offline 模式下 auto-learning 仍不可用且未开启 |
| 活动 Runtime Grant 摘要 | ACTIVE，预算/余额 `$1.00`，费用 `$0`，发送许可 0，UNKNOWN 0 |
| Live preflight（未提供真实 Key） | BLOCKED as expected：缺少 `OPSPILOT_MODEL_API_KEY`；没有调用 Provider |

### 实际执行命令

```powershell
.\.venv\Scripts\python.exe -m compileall -q opspilot scripts/user-demo
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q tests/test_c01_b2_b_personal_memory_auto_consolidation.py tests/test_c01_b2_a_personal_memory.py tests/test_product_01_runtime_grant_01.py tests/test_product_01_runtime_grant_01_hf01.py --basetemp=.runtime\c01-b2-live-01-pytest --tb=short
Push-Location frontend
npm run build
npm run test:e2e:c01-b
Pop-Location
```

隔离 API/UI 烟测使用 `Start-UserDemo.ps1 -Profile S1 -Mode Offline`，登录 SUPPORT、GET/PUT `/api/personal-memory-settings`，再用 `Stop-UserDemo.ps1` 优雅停止。Live 只执行只读 `runtime_admin.py preflight`；因 Key 尚未由用户输入，预期退出码为 2，不启动 Live 服务。

曾有几次一次性命令行烟测错误（Python 模块路径含连字符、临时 DB 身份路径校验和烟测补丁作用域），均发生在隔离脚本验证；最终正向/负向导出烟测通过，活动 Runtime DB 与测试样本分离。没有遗留应用测试失败。历史 HF01 裁决缺少仓库文件，仍为 `UNVERIFIED`。

## 剩余限制

- 真实 Key 与 SUPPORT 密码必须由用户本机自行输入；因此候选没有真实 Live Provider 端到端结果。Luna 的实际 Provider 发送数为 **0**。
- 用户目标 8 次调用、最多 10 次是流程控制；系统不具备 10 次硬限。`send_granted_at` 是“获准外发”的保守尝试计数，若请求在崩溃窗口不确定，需同时查看 UNKNOWN，不能声称全部确实到达供应商。
- 测评不能预判模型会生成有效 `AUTO_LEARNED` 记录、跨 Session 一定召回或避免短期偏好误记；这些均由用户亲自执行并依脱敏导出证据判定。
- 端口 8000 / 5173 固定且已通过本机离线检查可用；脚本若检测端口冲突会停止，不会自动切换端口。
