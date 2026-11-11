# C01-B2-LIVE-01 本地人工测评启动说明

本工作树已准备独立 Domain / Checkpoint 数据库、单实例 Worker 启动方式、个人记忆设置、$1 Runtime Grant 和本地脱敏证据导出。Luna 没有发送真实 Provider 请求。用户必须在本机输入自己的 DeepSeek API Key 后才能启动 Live 模式；Key 不要粘贴到聊天或命令行参数。

## 启动

在 PowerShell 中执行：

```powershell
Set-Location 'D:\OpsPilot-C01-B2-LIVE-01-PREP'
.\scripts\user-demo\Set-C01B2LiveCredentials.ps1
.\.venv\Scripts\python.exe .\scripts\user-demo\runtime_admin.py preflight
.\scripts\user-demo\Start-UserDemo.ps1 -Profile S1 -Mode Live
```

第一条凭据脚本会通过隐藏输入分别询问 DeepSeek API Key 和你自行设定的 SUPPORT 密码。账号名固定为 `support-a`。脚本将 Key 与密码写入 Git 忽略的 `.env`，并把文件 ACL 限制为当前 Windows 账号与 SYSTEM；不要复制或分享 `.env`。脚本不发送 Provider 请求，也不会创建/补充费用池。

Live 预检必须显示：`ACTIVE` Grant、模型 `deepseek-flash`、预算/余额、发送许可次数 `0`、`UNKNOWN` 数 `0` 和到期时间。若预检失败，先停止，不要改价格、模型或 Grant 字段。准备时已预置独立的 `$1.00` 应用费用池；Grant 到期为 **2026-12-11 09:56 UTC**。预检也会核对本地 Key 存在、Provider 配置与 Grant 一致、剩余额度足以覆盖一个最大请求。

浏览器打开 [http://127.0.0.1:5173](http://127.0.0.1:5173)，以 `support-a` 和刚输入的 SUPPORT 密码登录。API 绑定 `127.0.0.1:8000`，Vue 绑定 `127.0.0.1:5173`；Live 启动脚本会启动 API 内部的单实例 Worker，不要再单独启动第二个 Worker。启动本身不会发模型请求；聊天或自动整理会产生费用。

## 人工测评

1. 在右侧“个人长期记忆”区域确认“使用个人长期记忆”开启；“自动从对话中学习”默认关闭。需要测试时由你手动开启。关闭个人记忆召回会同时暂停自动学习。
2. 创建 Session A，只用普通聊天输入你自己的问题。至少完成 6 条用户消息并等待每条回答成功；其中自然表达两项你长期稳定的偏好，其他消息保持普通技术问题。不要进入受控业务调查流程，也不要发送真实客户材料。
3. Worker 在同一 Session 累积 6 条成功用户消息后可创建整理 Job；第一次整理由后台 Worker 处理。每个成功批次后有 10 分钟整理节流，后续批次可能需要等待。每批最多读取 12 条、提出 4 条候选并产生至多 1 次额外提取模型调用。模型判断可能不写入记忆，这属于待测行为，不应预设成功。
4. 刷新右侧记忆区域，查看 Job 状态、`AUTO_LEARNED` 记录、来源消息和版本。然后新建 Session B，问一个相关但不同的技术问题。查看调用的 Memory 选择和真实模型输入，再判断偏好是否影响了回答。
5. 质量测试可继续进行：短暂偏好样本“我喜欢这次回答短一点”；关闭个人记忆召回后再发新问题；修改或撤销记忆后在新 Session 提问。检查新 Run 的实际模型输入与 Context Manifest，不只根据网页回答猜测是否召回。

保持请求简单并在每轮后查看费用账本。6 次普通模型回答、1 次整理调用和 1 次跨 Session 回答大约需要 8 次 Provider 调用；工具往返、重试或失败恢复会改变该数字。10 次是人工测试目标上限，**程序没有 10 次发送硬停**。达到你设定的调用数或费用停止线后，不要再发消息；`$1.00` 是按本地 Token 账本计算的应用预算上限，不是 DeepSeek 发票限额。未知请求会保留 `UNKNOWN` 记录及预算占用；不会自动追加费用池或恢复暂停的 Grant。

## 查看费用与导出证据

可在另一个 PowerShell 窗口随时查看 Grant 和费用账本：

```powershell
Set-Location 'D:\OpsPilot-C01-B2-LIVE-01-PREP'
.\.venv\Scripts\python.exe .\scripts\user-demo\runtime_admin.py summary
```

输出包含 Grant / 费用池状态、预算、已结算/预留/可用金额、发送许可次数、`UNKNOWN` 次数和到期时间。发送许可次数是保守尝试计数；若存在 `UNKNOWN`，无法证明这些请求实际到达 Provider。金额由配置费率和 Provider Usage 估算，不等同供应商发票。

导出前先取 Session 全 ID（网页只展示截断 ID）：

```powershell
@'
import sqlite3
db = sqlite3.connect('.runtime/user-demo/domain.sqlite3')
for row in db.execute('''SELECT s.session_id,s.updated_at,COUNT(m.message_id)
                         FROM sessions s LEFT JOIN messages m USING(session_id)
                         WHERE s.tenant_id='tenant-a' AND s.owner_id='support-a'
                         GROUP BY s.session_id ORDER BY s.updated_at DESC'''):
    print(row)
db.close()
'@ | .\.venv\Scripts\python.exe -
```

把需要检查的完整 ID 传给只读导出器；输出只能写进隔离 evidence 目录：

```powershell
.\.venv\Scripts\python.exe .\scripts\user-demo\export_live_evidence.py `
  --session-id '<完整 Session ID>' `
  --output '.runtime\user-demo\evidence\session-a.json'
```

导出含用户消息、实际 Model 请求/响应、调用与 Usage、Context Manifest、Memory 引用、整理 Job、Memory 来源/版本/事件和费用记录。它会清理 API Key、Cookie、Authorization、密码、常见 Bearer / `sk-` 形式；对话正文仍可能包含个人材料。证据只保存在本地，分享前请再次检查内容。

## 停止与重启

```powershell
Set-Location 'D:\OpsPilot-C01-B2-LIVE-01-PREP'
.\scripts\user-demo\Stop-UserDemo.ps1
.\.venv\Scripts\python.exe .\scripts\user-demo\runtime_admin.py summary
```

停止脚本会优雅关闭 API、Worker 与 Vue，并保留 Session、记忆、费用账本和 Checkpoint。再次启动仍使用同一隔离目录。已发出的请求可能在停止前完成，或被账本记为 `UNKNOWN`；检查 `summary` 后再决定是否继续。不要通过任务管理器强制结束服务。

## 当前费用与模型边界

模型和端点固定为 `deepseek-flash` / `https://api.deepseek.com`。目前官方峰值缓存未命中输入价格为 `$0.30/1M`，输出为 `$1.32/1M`；本地 Grant 用峰值输入/输出费率、每次最多 12,000 输入 Token 与 2,048 输出 Token，最大单请求预留 `$0.006304`。官方价格可变，若启动日期晚于 Grant 到期或官方费率变化，应停止并重新核验，不要手改本地费率。参考 [DeepSeek 官方模型与价格](https://api-docs.deepseek.com/quick_start/pricing/)。

### 费用与自动学习规则

- $1.00 是 OpsPilot Runtime Grant / Spend Pool 的本地应用账本上限，不是供应商侧消费硬上限。
- 没有通用的 10 次 Provider 调用硬限制。8 次请求为目标值，最多 10 次仅为人工流程约束。
- 自动整理是在满足用户消息门槛后由已有 Worker 排队执行；不会自动追加 Grant。
- API 或端口冲突时启动会失败并报告端口；当前脚本固定使用上述两个 loopback 端口，不会自动选端口。
