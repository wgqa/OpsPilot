# R2-AR03 用户手工测评指南

## 候选与环境

- 仓库：`wgqa/OpsPilot`
- Base：`codex/r2-ar03-integrated-journey-01@6543fdd63b6d66ef2c7042c7da6e329cefbe73de`
- 候选分支：`codex/r2-ar03-user-test-ready-01`
- 候选 SHA：提交后补入
- 工作树：`D:\OpsPilot-LIVE-02-FIX-01-HF02`
- Web：`http://127.0.0.1:5173`
- API：`http://127.0.0.1:8000`
- 本轮复用已有工作树，新增 Worktree 数量为 0。没有访问或改动 `D:\OpsPilot-C01-B2-LIVE-01-HF02`。

本地 Demo 数据独立存放在 `.runtime\user-demo\domain.sqlite3` 和 `.runtime\user-demo\checkpoint.sqlite3`。当前目录已初始化，初始化脚本会拒绝覆盖已有数据库；之后不要再次运行初始化脚本来“清理”数据。停止与重启不会删除 Session、Message、Domain 或 Checkpoint。

### SUPPORT 登录

- 账号：`support-a`（`tenant-a` / `SUPPORT`）。
- 密码保存在本工作树被 Git 忽略的 `.env` 中，键名为 `OPSPILOT_WEB_SUPPORT_PASSWORD`。本地查看并输入密码，不要把 `.env` 内容、密码、Cookie 或 CSRF 值复制到报告、截图或聊天中。
- `approver-a` 仅为本地角色测试账号；本旅程是只读调查，不需要审批。

启动器现在只把 `.env` 中四个 Web 账号密码传给 API 子进程，并在启动前端进程前恢复环境变量；密码不会放进 Vite 进程、启动输出或 Git。之前启动器只校验了 `.env` 密码、没有传给 API，导致服务启动后登录失败。

## 启动和停止

在 PowerShell 中：

```powershell
Set-Location 'D:\OpsPilot-LIVE-02-FIX-01-HF02'
.\scripts\user-demo\Start-UserDemo.ps1 -Mode Offline
```

`Offline` 用于登录、Session、服务和页面连通性检查；它会显式关闭 Provider，不会悄悄改用 Fixture，也不能完成模型分析。不要把 Offline 下的错误状态当作模型结论。

完成后用仓库脚本优雅停止 API、内部单实例 Worker、Vue/Vite；它会通知打开的 SSE 流收口：

```powershell
Set-Location 'D:\OpsPilot-LIVE-02-FIX-01-HF02'
.\scripts\user-demo\Stop-UserDemo.ps1
```

当前 Demo 没有 Provider 密钥、计价版本或 Runtime Grant。Live 启动会在发出任何请求前被 Preflight 拒绝。等你决定授权真实模型测评后，先仅在本工作树 `.env` 本地配置真实 Provider 信息（不要使用示例费率），然后显式运行：

```powershell
Set-Location 'D:\OpsPilot-LIVE-02-FIX-01-HF02'
python .\scripts\user-demo\runtime_admin.py configure
python .\scripts\user-demo\runtime_admin.py preflight
.\scripts\user-demo\Start-UserDemo.ps1 -Mode Live
```

`configure` 是会创建本地 Runtime Grant 和 Spend Pool 的授权操作；本轮没有替你运行。Provider Key、真实官方费率、Grant 预算和有效期由你在本地按当前授权决定。Preflight 和启动本身不发送模型请求；聊天消息会产生实际 Provider 请求和费用。不会自动追加费用池或恢复暂停的 Grant。

配置项至少包括 `OPSPILOT_MODEL_API_KEY`、`OPSPILOT_MODEL_CONFIG_VERSION`、`OPSPILOT_MODEL_PRICE_VERSION`、`OPSPILOT_MODEL_INPUT_RATE_MICRO_PER_MILLION`、`OPSPILOT_MODEL_OUTPUT_RATE_MICRO_PER_MILLION`，以及模型名、官方 API Base URL、服务身份。当前 Preflight 报告前五项尚未配置。没有有效配置时应用会明确停止 Live 启动，不会回退到 Fixture。

## 资料范围和订单绑定

登录后，在 Assistant 顶部的“资料项目”选择 `订单与异步回调资料`（项目 ID `orders-callback`）。该项目由服务器端 `knowledge/assistant-access.json` 授权给 `tenant-a` 的 `support-a`；版本 1 与版本 2 的协议文档都在允许范围内。资料项目的配置版本是 v2，但它不能证明生产部署版本。

项目资料目录包含 `order-lifecycle-contract` v1.0.0 / `order-lifecycle-contract-v2` v2.0.0、`callback-retry-contract` v1.0.0 / `callback-retry-contract-v2` v2.0.0、`callback-ack-contract` v1.0.0 及 `receiver-ack-contract-v2` v2.1.0。搜索或比较工具只会返回该项目授权且版本适用的文档。

普通协议分析不要创建 Task。需要查当前订单时，再在同一个 Assistant Session 中选择“关联授权订单进行只读调查”，选 `async-order` 并提交问题。`Start-UserDemo.ps1 -Profile S1` 只决定另一套同步 S1 调查资源；统一 Assistant 的订单入口会由服务器固定绑定 `orders-async-demo`，并重新核验 SUPPORT 身份、Tenant、订单注册和只读范围，因此 S1 Profile 不会替代或绕过 S3 授权。

本地 `async-order` 初始状态是 Delivery `ACKNOWLEDGED` / HTTP 202，Receiver `QUEUED`，Delivery 与 Receiver 关联同一 Event。`async-order-2` 是另一个已注册选项；本旅程选 `async-order`。当前事件是合成 Demo 数据，不代表真实客户订单。

## J1：无 Task 的协议和材料分析

在选定资料项目且没有绑定订单的 Session 中，发送下列内容。示例 JSON 和日志是冻结 Gold 使用的合成材料：

```text
我们正在把回调 API 从 v1 升级到 v2。这是我们当前的 JSON 配置和最近的回调失败日志。请分析哪些地方需要修改、会有什么兼容性风险、哪些可以直接从材料判断，以及当前订单的处理情况。最后帮我整理一份可以发给研发同事的升级检查清单。

JSON 配置：
{
  "api_version": "v1",
  "callback": {
    "retry": {
      "max_attempts": 5,
      "backoff": "fixed"
    }
  }
}

失败日志：
event_id=event-00000000-0000-4000-8000-000000000001
request_id=request-r2-sample-01
http_status=503
error_code=TEMPORARY_UNAVAILABLE
attempt_count=1
max_attempts=5
retry_state=SCHEDULED
retry_at=2026-11-12T10:15:00Z
```

**通过条件：**

- 说明 JSON 和日志是用户提供的材料；引用有作用域的 v1/v2 协议资料、比较结果和带版本/行号的原文。
- 区分日志里的字面事实、条件性解释和未知项；当前 Session 未绑定订单时，不能声称已经查询当前处理状态。
- 明确资料版本不能证明线上部署版本；给出有来源、风险及验证步骤的迁移检查清单。
- 普通问题可以不加载 Protocol Upgrade Skill；复杂升级任务可由模型自行选择加载。

**失败条件：** 把样例 `503` 或 `QUEUED` 说成当前订单观察；声称生产部署已是 v1/v2；没有来源却断言重试配置必须修改；或没有绑定订单仍宣称业务已处理/未处理。

## J2：同 Session 查询 QUEUED 订单

保留 J1 的 Session 和材料。点“关联授权订单进行只读调查”，选 `async-order`，首条调查问题填：

```text
请结合刚才的材料，核对这个订单当前同一 Event 的处理状态。
```

**通过条件：** 系统显示服务器受理的 TaskBinding；本轮模型输入/Trace 使用当前 Run 的 Delivery 和 Receiver 观察，二者指向同一 Event；结论说明 HTTP 202 / `ACKNOWLEDGED` 只表示接收方已接受，`QUEUED` 不等于处理完成。J1 的协议答案是历史内容，不能冒充本轮重读。没有审批、修复、交接、Action 或业务写入。

**失败条件：** 把 HTTP 202 或 Delivery `ACKNOWLEDGED` 当作 Receiver 已处理；Event 不一致；跨 Tenant 订单绑定成功；引用 J1 的旧信息冒充本轮观察；或出现未授权业务写入。

## 可选：隔离的 PROCESSED 对照

不要把真实 Demo DB 中的 `async-order` 改成 PROCESSED。下面命令由现有 J2 参数化 Fixture 在全新的 pytest 临时 Demo DB/Checkpoint 中分别运行 QUEUED 和 PROCESSED；PROCESSED 只写入那个临时数据库，不调用真实 Provider，也不碰 `.runtime\user-demo`：

```powershell
Set-Location 'D:\OpsPilot-LIVE-02-FIX-01-HF02'
$case = Join-Path (Get-Location) ('.runtime\pytest-r2-j2-' + [guid]::NewGuid().ToString('N'))
if (Test-Path -LiteralPath $case) { throw 'Fixture path already exists; choose another unique path.' }
python -m pytest -q --basetemp="$case" tests/test_r2_ar03_integrated_journey_01.py -k j2_same_session_binding_uses_current_same_event_observation
```

预期 2 项通过，两个独立观察只在 Receiver 状态不同；结论也随之改变。它是 Fixture 验证，不是浏览器或真实模型验收。

## 费用、Run 和证据

查看本地 Grant、预算余额、Provider sends、UNKNOWN、Token 和费用估算：

```powershell
Set-Location 'D:\OpsPilot-LIVE-02-FIX-01-HF02'
python .\scripts\user-demo\runtime_admin.py summary
```

没有 Grant 时应显示 `Runtime Grant not configured. No fee pool exists.`。在网页的 Session/Run 记录中查看回答与活动；`.runtime\user-demo\logs` 保存 API 和 Web 启动日志。如果需要列出当前本地 Session ID（此查询只读 Domain DB）：

```powershell
Set-Location 'D:\OpsPilot-LIVE-02-FIX-01-HF02'
python -c 'import sqlite3; c=sqlite3.connect(".runtime/user-demo/domain.sqlite3"); print(*c.execute("SELECT session_id,updated_at FROM sessions WHERE tenant_id=? AND owner_id=? ORDER BY updated_at DESC", ("tenant-a", "support-a")), sep="\n"); c.close()'
```

获取当前 SUPPORT 的 Session ID 后，用既有单 Session 脱敏导出器保存完整上下文、Run、Observation、模型调用、Token/费用和来源：

```powershell
$sessionId = '<从当前 SUPPORT 会话记录复制>'
$output = ".runtime\user-demo\evidence\$sessionId.json"
python .\scripts\user-demo\export_live_evidence.py --session-id $sessionId --output $output
```

此导出器需要可读取的 Runtime Spend 汇总；在没有 Grant 的空白离线 Session 上会返回 `RUNTIME_GRANT_NOT_PROVISIONED`。真实 Live 测试完成并已有本地 Grant 后再导出；当前没有 Grant 时，先用 `runtime_admin.py summary` 查看状态即可。

不要导出整个账号数据或把 `.runtime`、`.env` 提交 Git。导出器会脱敏凭据；分享前仍需检查用户材料、订单号、事件/请求 ID、回答和截图是否含有客户或个人信息。截图及日志必须遮住密码、API Key、`Authorization`、Cookie、CSRF 和浏览器存储值。不要截图浏览器 DevTools 的 Request Headers。

## 离线预检结论与边界

- 本地 API、内部 Worker、Vue 页面 HTTP、SUPPORT 登录、Session 创建、资料项目列表、`async-order` 资源列表、SSE 握手和携带活动 SSE 的 Stop/EOF、停止后重启的 Session 持久性均已验证。
- 离线 Fixture 回归覆盖无 Task 的文档发现/对比/原文、同 Session 订单绑定、QUEUED/PROCESSED 同 Event 对照、跨 Tenant 绑定拒绝后继续合法资料分析。离线模式的实际应用不会伪装成 Fixture；上述 Agent 行为由明确标记的 Fixture 测试验证。
- 本次真实 Provider 请求：`0`；Runtime Grant、Spend Pool、Spend 记录和 `assistant_calls` 均为 `0`。没有运行浏览器自动化，也没有生产 MCP、业务写入、审批、交接或费用授权。
- **就当前本机配置而言，真实 Provider 手工测评状态为 `BLOCKED`**：Live Preflight 缺 API Key、计价/配置版本与 Token 费率，Demo DB 也没有 Runtime Grant。你决定授权后按上文配置并再次 Preflight；在此之前只能用真实浏览器检查登录/UI，不能获得真实模型分析。没有通过提高风险边界或静默回退 Fixture 来掩盖该状态。
- 当前候选只修改了 User Demo 启动器的凭据传递，并增加本指南和离线证据。没有生产业务代码、Schema、依赖、Gold 或冻结合同变更。
