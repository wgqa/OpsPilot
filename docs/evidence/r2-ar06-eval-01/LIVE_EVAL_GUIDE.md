# R2-AR06-LIVE-PREFLIGHT-01 · Live 评测准备手册

## 状态与环境

- 基线：`codex/r2-ar06-eval-01-hf01@d8e30bcb82557e370f8fec664803a952b8d06e14`
- 候选分支：`codex/r2-ar06-live-preflight-01`。请以交付消息中的完整候选 SHA 核对当前 `HEAD`；Gold 和本手册不包含自引用的候选 SHA。
- 工作树：`D:\OpsPilot-LIVE-02-FIX-01-HF02`
- 本机地址：API `http://127.0.0.1:8000`，网页 `http://127.0.0.1:5173`。API、Worker 与 Vue 只使用本机回环地址；Worker 是 API 进程内的单实例 Worker。
- 所有 Live 案例必须使用**新建且唯一**的 `.runtime/user-demo-*` 目录。初始化脚本拒绝复用已有隔离目录；不要选择 `.runtime/user-demo`，也不要复制旧 Demo 数据。
- 本手册只说明离线准备。没有运行真实模型评测：Provider 请求 `0`、正式评测运行库中的 Runtime Grant/Spend Pool 创建 `0`、浏览器自动化 `0`、外部业务写入 `0`。注意：本轮运行既有 Grant 生命周期回归时，测试夹具在 4 个 pytest 临时 SQLite 目录中创建了共 16 条模拟 Grant/Pool 记录，Spend 为 0；这些目录见文末且不是用户评测库。现有 `.runtime/user-demo` 的状态未读取，继续标为 `UNVERIFIED`。

## SUPPORT 登录与本地费用授权

登录身份为本地 `SUPPORT · support-a`（`tenant-a`）。用户应在本工作树被忽略的 `.env` 中自行设置私有 `OPSPILOT_WEB_SUPPORT_PASSWORD`；口令至少 12 个字符，不能使用示例占位值。不要把口令、API Key、Cookie 或 `Authorization` 内容放入命令历史、截图、聊天或报告。

当前本地 Provider 配置不能通过 Live Preflight：它报告 `OPSPILOT_MODEL_API_KEY`、模型配置/价格版本及输入/输出费率缺失或不可用；该隔离库也没有 Grant/费用池。没有自动修补 `.env`、创建 Grant 或增加预算。只有在用户另行核实官方费率并明确授权费用后，才为**每个全新隔离运行目录**配置 Provider 环境变量并运行 `Configure-UserDemoLive.ps1`。该命令会创建持久 Grant/Spend Pool；它不发送 Provider 请求，但之后的 Live 消息可能收费。

授权后的顺序为：先在 `.env` 配置正确的 `deepseek-flash` Provider、端点、配置/价格版本、Service Identity、费率和 API Key；再执行该隔离目录的交互式 Grant 配置；检查 Preflight 和费用状态；最后才以 `-Mode Live` 启动。准确的 Grant 命令为 `.\scripts\user-demo\Configure-UserDemoLive.ps1 -RuntimeName $runtimeName`。预算和单请求 Token 上限由现有 Runtime Grant 合同执行。若预算池暂停，不要通过自动追加或重建 Grant 恢复。

## 隔离运行命令

以下命令每个案例都要使用新的别名。若目录已存在，停止并另选新名字；不要删除或重置目录。

```powershell
Set-Location 'D:\OpsPilot-LIVE-02-FIX-01-HF02'
$runtimeName = 'user-demo-r2-ar06-e01'
.\scripts\user-demo\Initialize-UserDemo.ps1 -RuntimeName $runtimeName
.\scripts\user-demo\Start-UserDemo.ps1 -RuntimeName $runtimeName -Profile S1 -Mode Offline
```

离线模式用于登录和数据/界面预检，真实 Provider 与 Legacy Provider 均关闭，不能用于评判模型回答。停止并保留数据：

```powershell
.\scripts\user-demo\Stop-UserDemo.ps1 -RuntimeName $runtimeName
.\scripts\user-demo\Show-UserDemoSpend.ps1 -RuntimeName $runtimeName
```

费用与授权检查也可直接执行：

```powershell
python .\scripts\user-demo\runtime_admin.py summary --runtime-name $runtimeName
python .\scripts\user-demo\runtime_admin.py preflight --runtime-name $runtimeName
```

没有 Grant 时，费用查询显示所选隔离目录且明确说明没有费用池；Live Preflight 会因缺少本地配置或 Grant 而失败，不会发请求。Live 启动会再次对**同一别名**执行 Preflight。

服务日志位于 `.runtime\<runtimeName>\logs`。Stop 发送本地优雅关闭请求并保留 Domain、Checkpoint、会话和账本。不要手动删除 `processes.json` 或运行中的数据目录。

## 冻结输入复制方式

冻结输入唯一来源是 `docs/evidence/r2-ar06-eval-01/CASES.json`。以下 PowerShell 会把完整的一轮输入放入剪贴板，不把长材料打印到终端。粘贴前请核对 Case ID；不要改写或追加内容。

```powershell
$gold = Get-Content .\docs\evidence\r2-ar06-eval-01\CASES.json -Raw | ConvertFrom-Json
$case = $gold.cases | Where-Object { $_.case_id -eq 'E01-D' }
Set-Clipboard -Value ([string]$case.user_turns[0])
```

更换 `$case_id` 后可复制其他案例：

```powershell
$case_id = 'E05-D'
$case = $gold.cases | Where-Object { $_.case_id -eq $case_id }
Set-Clipboard -Value ([string]$case.user_turns[0])
```

## 案例准备状态

| Case | 隔离初态和输入 | 当前结论 |
|---|---|---|
| E01-D | 新运行目录、新 Session、无 Task。逐字输入只有 HTTP 202 问题。 | **Live 数据就绪**；仍需用户授权 Provider/费用后才能评测。答案不得声称具体订单已处理。 |
| E03-D | Gold 要求项目 `orders-async-demo`。本候选实际登录核验到的唯一 SUPPORT 可选项目为 `orders-callback`；虽然其中有 v1/v2 回调资料，但它不是 Gold 的授权项目。 | **BLOCKED_FOR_EXACT_GOLD**。不要改选 `orders-callback` 后把结果记作 E03，也不要擅自改项目授权。需要主 Agent/项目所有者裁决并批准正确资料范围。 |
| E05-D | 新运行目录、新 Session、无 Task。冻结的一条 User Message 已含合成 JSON 和 503 日志材料。 | **Live 数据就绪**；将 E05-D 全文逐字粘贴。不要将材料里的状态当作当前业务 Observation。 |
| E07-D | 用 `r2-e07-queued` Profile 建新库；Support 通过当前会话的受控订单绑定选择 `async-order`。目标 Delivery/Receiver 指向同一固定 Event `event-00000000-0000-4000-8000-000000000001`，状态为 `ACKNOWLEDGED / HTTP 202` 与 `QUEUED`。 | **Fixture 与可信绑定路径已离线验证**；Live 评测仍需新目录与费用授权。只读当前同 Event，不得把 202 说成处理完成。 |
| E08-H | 用 `r2-e08-processed-decoy` Profile 建新库；目标 `async-order` 为 PROCESSED，目标 Event 为 `...000000000101`；独立 `async-order-decoy` 为 QUEUED，Event 为 `...000000000102`。受控绑定只选目标 `async-order`。 | **数据已准备，留出评测仍待运行**。冻结题面提及历史 QUEUED 与另一 Event 的日志，但干净 Session 中没有预置旧 Assistant 回答；当前 Message 中的说法仍是用户材料。不要另加轮次后宣称逐字初态完全匹配。需主 Agent 对历史线索表示法作裁决后再作正式独立评分。 |
| E09-D | Gold 仅描述长会话情境，没有冻结逐轮消息、附件正文与压缩材料。 | **NOT_READY**。不得拼接临时文本、复用 AR-04 多轮测试或以映射用例代替冻结输入。 |

E07/E08 的 S3 订单绑定通过 UI 的**“关联授权订单进行只读调查”**，选择目标订单并在同一次受理中粘贴 Gold 用户输入。这调用当前支持的 `/api/sessions/{session_id}/assistant/order`，由可信身份和 Domain 建立 TaskBinding；不要用 SQL、用户消息或模型输出制造绑定。E08 的 `async-order-decoy` 只作为未绑定的隔离对照资源，不要把它绑定到目标任务。

### 网页手工步骤

1. 为该案例新建并初始化专属运行目录，完成单独的费用授权后才启动 Live。先看运行目录名及 Preflight，确认没有指向旧 `user-demo`。
2. 打开 `http://127.0.0.1:5173`，以 `support-a` 登录。普通聊天案例创建新 Session；E07/E08 需要当前 Assistant 面板中的“关联授权订单进行只读调查”。
3. E01/E05：在全新 Session 中只发送剪贴板里的冻结输入。E07/E08：选择 `async-order`，将对应冻结输入填入只读调查表单并确认。
4. 记录 Session ID、Run ID、最终答案、Run-scoped Observation/Evidence ID、相同 Event ID、Runtime Usage/Spend 和错误码。Run 成功本身不是语义通过。
5. E07 只有 Delivery 与 Receiver 都是同一 Event 的本轮观察才支持结论。E08 必须围绕绑定目标当前 Event 判断；用户提到的历史/其他 Event 状态不能代替目标证据。
6. 停止服务后用 `Show-UserDemoSpend.ps1 -RuntimeName $runtimeName` 查看本隔离账本。失败结果原样保留，不要重跑以覆盖首次尝试。

`export_live_evidence.py` 支持安全别名 `--runtime-name`，读取与输出都限定在该 Runtime，且只接受该库中当前 SUPPORT Owner 的 Session。Domain SQLite 以只读模式打开；导出包括该 Session 的消息、Runs、Assistant/MCP 调用、Observation、Evidence、Context Manifest、Usage/Spend 和必要的个人记忆来源，并继续脱敏密钥、口令、Cookie、CSRF 与 Authorization。费用与 Run 只按指定 Session 导出，不汇总同一 Runtime 的其他 Session。缺少 Token/Usage 时保留 `null`，不填 0。

### 脱敏证据导出

在仓库根目录 PowerShell 中运行。先从当前页面或只读 Session 记录取得准确 Session ID；每个评测案例使用自己的 Session 和隔离 Runtime。

```powershell
$runtimeName = 'user-demo-r2-ar06-e01'
$sessionId = 'session-替换为实际ID'
$output = ".runtime\$runtimeName\evidence\$sessionId.json"
python .\scripts\user-demo\export_live_evidence.py `
  --runtime-name $runtimeName `
  --actor-id support-a `
  --session-id $sessionId `
  --output $output
```

省略 `--runtime-name` 时沿用旧默认 `.runtime/user-demo`；`--output` 仍必须位于所选 Runtime 的 `evidence` 子目录。别名不允许路径片段；不存在的 Runtime/Domain、符号链接逃逸、不同 Owner/Tenant 的 Session 和 Runtime 外输出都会被拒绝。导出不会调用 Provider、创建 Grant 或修改费用账本。

导出 JSON 与冻结 Rubric 的字段关系：

| Rubric | 可核对字段 | 自动导出边界 |
|---|---|---|
| M1 Goal completion | `messages`, `runs`, `assistant_calls_actual_model_input_output` | 保存用户输入、最终答案及 Run 状态；PASS/PARTIAL/FAIL 仍按冻结定义人工评分。 |
| M2 Facts and sources | `task_bindings`, `observations`, `evidence`, `context_manifests` | 保留 Task/Event/资源与来源引用，支持核对来源存在和作用域；来源适用性、当前性及无依据断言需审阅。 |
| M3 Agent decision quality | `assistant_calls_actual_model_input_output`, `observations`, `messages` | 保留实际模型输入、工具选择、工具结果及后续回答；是否合理、是否漏掉合法下一步由人工语义评分。 |
| M4 Business outcome | `runs`, `observations`, `evidence`, `messages` | 能查看 Run 与当前可信观察；Domain Outcome 需按案例单独判断，Run 成功不等于业务完成。 |
| M5 Cost and performance | `runtime_spends`, `chat_attempts`, `session_spend_summary`, `compression_attempts` | 保留发送许可、响应状态、原始 Usage、Token、结算与耗时字段；任何缺失值保留 `null`，UNKNOWN 单独可见。 |
| M6 Safety | `task_bindings`, `observations`, `evidence`, `assistant_calls_actual_model_input_output`, `runtime_spends` | 提供租户、Task、来源和动作线索；越权/错误确定性等红线仍须按 Rubric 独立人工核验。 |

`session_spend_summary` 明确标记 `SELECTED_SESSION_ONLY`，只给出该 Session 账本的记录数，不读取费用池汇总接口（其完整性检查可能更新池状态），也不合并同 Runtime 的其他 Session。`runtime_spends.usage_json` 和 `chat_attempts` 的 Token 字段才是逐请求 Usage 证据；若没有记录，应保持缺失而不能用零替代。

## 本轮离线验证记录

- 新建隔离初始化只从空目录创建 Domain/Checkpoint；测试断言 Session、Message、TaskBinding、Task Run、Personal Memory、Runtime Grant、Pool、Spend 均为空。E07/E08 Profile 验证固定同 Event 及目标/decoy 状态；Support 通过 API 目录可见对应订单，并能只绑定目标订单。
- 实际启动过一个**仅用于离线 smoke、不可作评测初态**的目录 `user-demo-r2-ar06-offline-smoke`。验证 SUPPORT 登录、Session 在停止/重启后仍可读取、SSE 返回 `200 text/event-stream`、订单列表、`async-order` 的可信 TaskBinding、E07 同 Event 状态，以及 API/Worker/Vue 优雅停止。该目录保留了 smoke Session/Task，不要拿去跑正式案例。
- smoke Domain 的 Runtime Grant、Spend Pool、Provider Spend 均为 `0`；实际 Provider 请求 `0`。Preflight 发现本地 Provider 配置缺少/不可用项并且无 Grant，未进入 Live 模式。全程没有启动浏览器自动化。
- 前端 `npm run build` 通过。User Demo 路径、空库、Grant 前置条件和 S3 API 绑定定向回归：`22 passed, 1 skipped`；跳过项是 Windows 环境不允许创建目录 symlink 的安全负例。S3/AR-03 集成回归：`19 passed`。开放 SSE 流下的 Windows API 优雅关闭回归：`1 passed`。Python 编译、Node 语法检查和 PowerShell 安全别名解析检查通过。
- 测试使用全新 `.runtime` basetemp；重跑时也必须换用新目录，不要复用本轮测试目录。完整执行命令见候选交付记录。
- 既有 `test_user_demo_live_mode.py` 的全量回归会通过测试代码创建本地模拟 Grant/Pool；本轮四次此类回归合计 16 条 Grant、16 条 Pool、0 条 Spend、0 次 Provider 发送。临时测试目录目前仍在 `.runtime`：`r2-ar06-live-preflight-pytest`、`r2-ar06-live-preflight-pytest-20261114`、`r2-ar06-live-preflight-pytest-20261114-b`、`r2-ar06-live-preflight-pytest-20261114-c`。不要把它们当作 Live 评测运行库。
- 本轮其他 pytest 临时目录也仍保留且不是评测库：`r2-ar06-final-s3-20261114`、`r2-ar06-final-userdemo-20261114-b`、`r2-ar06-final-userdemo-20261114-c`、`r2-ar06-final-sse-20261114`。仅 `user-demo-r2-ar06-offline-smoke` 是启停 smoke Domain；它含一条离线 Session/TaskBinding，也不能作正式案例初态。

本准备结果不代表 E01/E05/E07/E08 已由真实模型评测，不产生 Phase B 成功率。正式 Live 结果须以冻结 Rubric 独立评分，并保留失败、费用与 Trace。
