# E04-H 首次真实模型 Runbook

本手册只在主 Agent 独立验收通过、并取得新的 E04-H 单例费用授权后执行。建议应用费用池上限 USD 0.06；**本轮没有创建 Grant 或授权任何 Provider 费用**。不得复用本轮 Fixture Runtime、其他案例 Grant 或旧 Runtime。

## 1. 新建 E04 专属空 Runtime

从仓库根目录用 PowerShell 执行。选择从未存在过的新名称；若目录已存在，换一个新名称，绝不重置：

```powershell
$runtime = 'user-demo-r2-e04-live01'
python scripts/user-demo/run_r2_ar06_case.py prepare --case-id E04-H --runtime-name $runtime
python scripts/user-demo/run_r2_ar06_case.py preflight --case-id E04-H --runtime-name $runtime --mode offline
```

离线预检应显示项目 `orders-e04-absence`、两个授权文档、`POST_FREEZE_FIXTURE_SPECIFIED`、当前授权范围内无 v1.4、无 Session/Run、无 Grant、Provider 请求 0 和 UNKNOWN 0。验证共享知识授权文件未改变。

## 2. 费用授权与 Provider 配置

取得本案例明确的费用授权后，先根据 DeepSeek 官方当日价格检查仓库本地 `.env` 中的模型、Endpoint、费率版本、输入/输出费率和 Token 上限。不要将密钥复制到终端日志、报告或 Git。用户需要在原有 Runtime Grant 交互程序中输入预算、过期时间并逐字确认；不要绕过确认。

```powershell
python scripts/user-demo/runtime_admin.py configure --runtime-name $runtime
python scripts/user-demo/runtime_admin.py preflight --runtime-name $runtime
```

上限建议 USD 0.06，Run 最多使用既有 8 次模型派发合同。实际每请求预留由当前费率和 Token 上限计算；如果 8 次最坏预留超过该预算，停止并申请新的预算裁决，不调低费率、不提高费用池、不迁移 Grant。

## 3. 启动 Live 并预检

```powershell
./scripts/user-demo/Start-UserDemo.ps1 -Mode Live -RuntimeName $runtime
python scripts/user-demo/run_r2_ar06_case.py preflight --case-id E04-H --runtime-name $runtime --mode live --authorized-max-cost-usd 0.06
```

只有 Preflight 证明 API/Worker、此 Runtime 的 Domain DB、Grant、项目隔离授权和预算一致后，才继续。E04 无 TaskBinding；模型可以读取列表、比较现有协议、查看原文、请求缺失材料或安全停止，不固定工具序列。Gold/Rubric/预期答案不进入模型上下文。

## 4. 提交冻结原题一次

```powershell
python scripts/user-demo/run_r2_ar06_case.py run-live --case-id E04-H --runtime-name $runtime --authorized-case-id E04-H --authorized-max-cost-usd 0.06
```

Runner 从冻结 CASES 读取逐字题面，通过正式 Assistant 消息 API 建立单个新 Session 并提交一次。不要修改题面、补发提示或自动重试。Provider UNKNOWN、提交状态不明、预算不足、Scope 不匹配或 Run 超时都立即停止；先检查原 Run 与账本，不能重跑该 Runtime。

## 5. 停止、账本和证据

```powershell
./scripts/user-demo/Stop-UserDemo.ps1 -RuntimeName $runtime
python scripts/user-demo/runtime_admin.py summary --runtime-name $runtime
```

从 Runner 结果取得 Session ID 并替换下面变量值，导出脱敏 Session Trace：

```powershell
$sessionId = '<RUNNER_OUTPUT_SESSION_ID>'
python scripts/user-demo/export_live_evidence.py --runtime-name $runtime --session-id $sessionId --actor-id support-a --output ".runtime/$runtime/evidence/E04-H.live.trace.json"
```

保留首次运行结果、Trace、Provider Usage、费用账本和错误/UNKNOWN 状态。应用账本按配置费率估算，不等于供应商账单。评分由主 Agent 对照冻结 Rubric 独立完成；Runner `SUCCEEDED` 不代表 Rubric PASS。
