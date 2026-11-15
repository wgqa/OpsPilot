# E03-D 首次真实模型运行手册

本手册只说明独立验收后的可执行步骤。当前授权仅覆盖 Fixture 与离线验证，**尚未批准创建 Grant 或发送真实 Provider 请求**。不得把离线 Fixture Runtime 用于 Live；它已经有 Session/Run。

## 1. 准备全新 E03 Runtime

在仓库根目录 PowerShell 执行。每次正式首次运行使用一个从未存在过的新名称；不要删除或重置任何旧 Runtime。

```powershell
$runtime = 'user-demo-r2-e03-live01'
python scripts/user-demo/run_r2_ar06_case.py prepare --case-id E03-D --runtime-name $runtime
python scripts/user-demo/run_r2_ar06_case.py preflight --case-id E03-D --runtime-name $runtime --mode offline
```

预检必须报告隔离注册表有效、项目 `orders-async-demo`、租户 `tenant-a`、仅两个 callback retry 文档、无 Session/Run、无 Grant、Provider 请求 0、UNKNOWN 0。若目录已存在或预检不符，换一个新 Runtime 名称，不覆盖数据。

## 2. 本地费用授权（需另行批准）

只有取得 E03-D 单例真实模型费用授权后再执行以下交互式授权。建议应用费用池上限不超过 **USD 0.06**；这是预算建议，不是本轮授权。先按 DeepSeek 官方当前费率核验 `.env` 中模型、费率与 Token 上限，不得填低费率绕过预留。配置过程需要操作者按 Runtime Grant 程序输入预算、过期时间并原样确认；不要绕过确认。

```powershell
python scripts/user-demo/runtime_admin.py configure --runtime-name $runtime
python scripts/user-demo/runtime_admin.py preflight --runtime-name $runtime
```

若既有每请求最坏预留乘以 Run 最多 8 次派发超过 USD 0.06，Runner 会拒绝执行。此时停止并请求新的预算裁决，不增加 Grant、不降低费率。

## 3. 启动和预检 Live

```powershell
./scripts/user-demo/Start-UserDemo.ps1 -Mode Live -RuntimeName $runtime
python scripts/user-demo/run_r2_ar06_case.py preflight --case-id E03-D --runtime-name $runtime --mode live --authorized-max-cost-usd 0.06
```

启动程序会因 Runtime 内存在 `assistant-access.json` 而将其作为可信进程启动配置；应用校验它必须是 Domain DB 同目录的普通文件。共享权限文件不会被更改。确认 Runner 报告服务、Grant、预算与 Runtime 一致后再继续。

## 4. 正式提交冻结题面一次

```powershell
python scripts/user-demo/run_r2_ar06_case.py run-live --case-id E03-D --runtime-name $runtime --authorized-case-id E03-D --authorized-max-cost-usd 0.06
```

Runner 从冻结 CASES 读取原文，通过正式 Web API 登录 SUPPORT、创建新 Session、验证并选择 `orders-async-demo`，再创建无 TaskBinding 的 Assistant Message。模型可自行选择合法 Knowledge、Comparison、Excerpt 与可选 Skill 工具；不注入 Gold 结果，也不固定唯一工具顺序。每个 Case 只提交一次；不自动重试或重新提交。

本 Run 最多沿用既有合同：8 次模型派发、6 次 MCP 调用；Grant 总应用费用不超过 USD 0.06。费用门禁失败、UNKNOWN、提交确认不明、Run 超时或授权异常时立即停止，不能再次运行同一 Runtime。先检查状态和账本，不要补发消息。

## 5. 停止、费用核对与证据导出

```powershell
./scripts/user-demo/Stop-UserDemo.ps1 -RuntimeName $runtime
python scripts/user-demo/runtime_admin.py summary --runtime-name $runtime
```

停止后记录 Grant 限额、Provider 请求/响应次数、UNKNOWN、实际 Usage 结算及剩余额度。应用账本费用是按配置费率估算，不等于供应商账单。

将 `<session-id>` 替换为 Runner 输出的 Session ID：

```powershell
python scripts/user-demo/export_live_evidence.py --runtime-name $runtime --session-id <session-id> --actor-id support-a --output .runtime/$runtime/evidence/E03-D.live.trace.json
```

导出必须含冻结输入、Run/Assistant 回答、模型请求与 Usage、MCP 工具结果、协议来源/版本/Digest/原文行号、费用记录及运行耗时。保存 Trace 和 Runner 输出；共享时继续使用脱敏导出，不粘贴 `.env`、Cookie 或 Authorization。

## 停止条件

- Preflight 或身份/隔离授权不匹配：不提交消息。
- 费用预留超限、Grant 暂停、UNKNOWN 或提交状态不明：不重试、不复用 Grant。
- 发现文档 Digest/来源失配：来源不再使用，保留失败证据。
- 不生成业务写入：E03 仅文档分析，无 TaskBinding、Approval、ActionIntent 或交接。
