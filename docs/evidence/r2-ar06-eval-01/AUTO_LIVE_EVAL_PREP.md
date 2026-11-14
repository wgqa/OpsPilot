# R2-AR06 自动真实模型评测准备

## 当前状态

- Base：`aa55c9e8bd32b54cfe1419af0faad61f8f4700e5`
- 候选分支：`codex/r2-ar06-auto-live-eval-01`
- 当前交付：E01 首次真实结果的候选评分；E05-D/E07-D 的自动执行器及 Fixture 离线预演。
- 本轮真实 Provider 请求：**0**；新 Runtime Grant/费用池：**0**；外部业务写入：**0**；新增 Worktree：**0**。
- 本文不把 Fixture 通过当成真实模型结果。E05-D/E07-D 仍为真实 Live `NOT_RUN`，等待每个案例的单独授权。

## E01-D 已有首次结果

在本轮开始前已有的 `.runtime/user-demo-r2-e01-1114a` 只读核验如下，未重跑、未修改数据库、Checkpoint、Session、Grant、Spend 或 Trace：

- Gold 输入和唯一用户消息逐字一致；Gold 的原始 SHA256 为 `c1acd3fa789befa733aa96bf3a49b08357ff071f3b627b4c40319882e2805cf8`。
- Session `session-57d5d0a8-bb16-4be9-ab6a-c58f18049976` 有 2 条消息、1 个 `CHAT_READONLY` Run；Run `run-7ff06937-6268-4fa3-a51e-4ce63100436e` 为 `SUCCEEDED`，回答与用户消息关联。
- 1 次真实 Provider Send Grant、1 个已持久化响应；`deepseek-flash` Usage 为 input 2,487、output 491、total 2,978；应用费用账本结算 1,336 micro-USD（USD 0.001336）；UNKNOWN、Usage 缺失和结算缺失均为 0。
- MCP 调用、Observation、Evidence 均为 0。答案解释 202 是受理，不证明异步处理完成；没有声称查询了特定订单。
- 候选评分在 [E01_CANDIDATE_SCORE.json](E01_CANDIDATE_SCORE.json)。结果为 `PASS_CANDIDATE`，仍需主 Agent 独立评分。该费用是应用账本估算，不等于供应商账单。
- 脱敏导出原件 SHA256：`abdd1c66c9a8e33ee30e237131e2575a8ddad0e4b1866d453f65b694d7493688`。Domain 和 Checkpoint 的 SHA256 仅用于只读保护记录，见评分 JSON。

## 自动执行入口

新增 `scripts/user-demo/run_r2_ar06_case.py`，只开放已准备的单轮开发集 E05-D、E07-D。它从冻结 `CASES.json` 读取题面，并先校验 `FROZEN_HASHES.json` 中的 CASES SHA。Gold Outcome、Rubric 和禁止结论不会传入模型。

- `prepare` 复用 `initialize_demo.py`，创建新命名 Runtime；拒绝默认 `user-demo`、已有目录、任意路径、符号链接和重置。E05 使用 `standard` 初始化；E07 使用现有 `r2-e07-queued` 初始化，确认 `async-order` 的 Delivery `ACKNOWLEDGED` / HTTP 202 与 Receiver `QUEUED` 共用冻结 Event ID。
- `preflight --mode offline` 只读检查隔离 Domain/Checkpoint、空 Session/Run/Task/Memory/Spend、无 Runtime Grant，以及 E07 当前同 Event 状态。
- Live 入口要求 `--authorized-case-id` 与实际 Case ID 相同，且提供本案例的 `--authorized-max-cost-usd`。它不会创建或扩大 Grant；只接受新 Runtime 中零历史发送/UNKNOWN、费用池总限额不超过本案例授权值、剩余额度足以覆盖 8 次最大单请求预留，并验证 `Start-UserDemo.ps1` 的 Managed Process Manifest 记录了所选 Runtime、Domain/Checkpoint 和 `Live` Mode。
- 执行使用正式 API：创建 Session；E05 调用 `/api/sessions/{id}/assistant/messages`，E07 调用 `/api/sessions/{id}/assistant/order`，由可信 SUPPORT 身份绑定 `async-order` 并将冻结题面作为首次消息。此绑定是本地授权 Task，不是外部业务写入。
- 单次执行只提交一次消息 POST。网络确认丢失、超时或 Run 失败时不重新提交；保留当前 Runtime 供检查。UNKNOWN/预算不足/Preflight 失败停止。成功或失败终态都导出指定 Session 的完整脱敏 Trace 和一份结构化 `*.result.json`；评分状态默认 `UNVERIFIED`，不会由 Run 状态推导 PASS。
- 运行器以隔离 Runtime 内的独占锁拒绝并发 Case。若进程异常终止导致锁文件残留，先核实没有该 Runtime 的活动执行，再人工处理；执行器不会自动删除或绕过残留锁。
- `Start-UserDemo.ps1` 的进程清单现在记录 `mode`，使 Live Preflight 可以拒绝 Offline Worker。

## 已完成 Fixture 预演

通过 FastAPI `TestClient`、真实 API 路由、单 Worker、临时隔离 Domain/Checkpoint、Fixture Model 与本地 Mock MCP 执行。没有调用远端 Provider。

| 案例 | Web API 路径 | Fixture 结果 | Provider | MCP/Observation | 结论 |
|---|---|---|---:|---:|---|
| E05-D | 新 Session → Assistant Message → Run | Run `SUCCEEDED`；发送的用户文本与冻结题面完全一致；导出 Trace 可读 | 0 | 0 / 0 | 仅证明自动化接线与证据导出，不是 E05 真实质量评测 |
| E07-D | 新 Session → 可信 `/assistant/order` 绑定 → Run | Run `SUCCEEDED`；可信 TaskBinding 指向 `async-order` | 0 | 2 / 2 | 两条 Observation 都属于 Run 且 Event ID 相同；状态为 `ACKNOWLEDGED` 与 `QUEUED` |

候选离线测试：`tests/test_r2_ar06_auto_live_eval.py`，共 11 项通过。测试还验证 Live Manifest 必须匹配选定 Runtime/模式、授权 Case 不匹配时在网络请求前停止、同一 Runtime 并发运行被锁定、授权预算/8 次最大预留门禁，以及 API 已受理但客户端丢失 POST 确认时不重复提交。E07 Fixture 的 3 次模型派发和 2 次 MCP 调用只是测试行为，不是预计真实模型的固定工具顺序。

RED/GREEN 记录：实现前，新测试因 `run_r2_ar06_case` 入口不存在而在收集时失败；实现后 11/11 新测试通过。首轮接线时的额外失败来自 TestClient 使用非回环 Origin 与测试读取了不同 Trace 字段；Fixture 改为 `127.0.0.1` 并按现有导出结构断言后通过。这些没有要求改动生产 Agent/Domain。

本轮合并回归命令覆盖新执行器、Runtime 路径与 Grant、脱敏 Trace 导出、E01/E05 工程用例和 AR-03 J1/J2/J3：**44 passed, 3 skipped**。三项跳过均因 Windows 测试环境不支持目录符号链接；未发现新增失败。完整 pytest 输出在 [AUTO_LIVE_TEST_LOG.txt](AUTO_LIVE_TEST_LOG.txt)。

```powershell
$python = (Get-Command python).Source
$baseTemp = Join-Path (Get-Location) ('.runtime\pytest-r2-ar06-auto-live-final-confirm-' + [guid]::NewGuid().ToString('N'))
& $python -m pytest `
  tests/test_r2_ar06_auto_live_eval.py `
  tests/test_user_demo_runtime_paths.py `
  tests/test_user_demo_live_mode.py `
  tests/test_r2_ar06_live_evidence_export.py `
  tests/test_r2_ar06_eval_01_material_case.py `
  tests/test_r2_ar03_integrated_journey_01.py `
  -q --basetemp $baseTemp
```

## 用户后续授权后操作

以下命令**本轮没有运行**。只有用户为某一个案例另行明确 Provider 与费用授权，并在新隔离 Runtime 手工建立 Grant 后，才执行 Live 部分。不要用 E01 的 Grant 或 Spend。

```powershell
$python = (Get-Command python).Source
$runtime = 'user-demo-r2-e05-live01'

# 创建全新 E05 Runtime；已有目录会被拒绝，不会重置。
& $python .\scripts\user-demo\run_r2_ar06_case.py prepare `
  --case-id E05-D --runtime-name $runtime

# 用户明确授权该案例与费用后，才手工配置这个 Runtime 的 Grant。
# 该命令会修改所选隔离库，当前任务没有运行它。
& $python .\scripts\user-demo\runtime_admin.py configure --runtime-name $runtime

& $python .\scripts\user-demo\Start-UserDemo.ps1 -RuntimeName $runtime -Mode Live

# 先做无聊天发送的 Live Preflight。
& $python .\scripts\user-demo\run_r2_ar06_case.py preflight `
  --mode live --case-id E05-D --runtime-name $runtime `
  --authorized-max-cost-usd 0.05

# 只有上述授权和 Preflight 都有效时才提交一次冻结题面。
& $python .\scripts\user-demo\run_r2_ar06_case.py run-live `
  --case-id E05-D --runtime-name $runtime `
  --authorized-case-id E05-D --authorized-max-cost-usd 0.05

& $python .\scripts\user-demo\Show-UserDemoSpend.ps1 -RuntimeName $runtime
& .\scripts\user-demo\Stop-UserDemo.ps1 -RuntimeName $runtime
```

E07 必须另用全新 Runtime，例如 `user-demo-r2-e07-live01`，并把以上每个 `E05-D` 替换为 `E07-D`。不要在 E05 Runtime 上接着跑 E07。若运行请求的 HTTP 确认不明确，不重复运行 `run-live`；先用已有导出器按该 Runtime 和已持久 Session ID 导出证据。

## 请求与费用上界

- 普通 Assistant Run 的持久模型派发上限是 **8 次**，MCP `tools/call` 上限是 **6 次**；这是源码 `opspilot/domain/assistant.py::run_limits_for_experiment()` 和 `reserve()` 当前生效的每 Run 合同。E05 通常 1 次模型请求、0 次 MCP；E07 通常约 2–3 次模型请求并需要 Delivery/Receiver 两个当前读观察，但模型可以不同方式分组工具调用，不能把典型值当固定顺序。
- Runtime Grant 单次预留上限为 12,000 input / 2,048 output Token。基于 DeepSeek 官方当前高峰、无缓存输入费率 USD 0.30/百万 input Token 与 USD 1.20/百万 output Token，一次最大预留约 USD 0.006058；8 次约 USD 0.048464。因此示例每案例授权 USD 0.05，分开配置；Live Preflight 用所选库当前 Grant 实际配置费率重新计算并要求足额，不使用硬编码费率。
- 该费用是应用 Runtime Grant 依据已配置费率做的上限/结算估算，不是供应商侧发票保证。若本地 Grant 上限高于明确授权值、费率与官方现价不一致、预算不足或出现 UNKNOWN，Live 自动化会停止在聊天 POST 之前。
- 当前无 Runtime Grant，也没有授权在本分支上创建。目标模型价格应在使用时再次以[DeepSeek 官方 Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)核对。

## 未准备或未验证

- E03、E08、E09 没有加入自动执行器。E08-H 继续等待其冻结目标/decoy 初态，E09 继续等待缺失的逐轮输入/压缩材料；不拼接替代 Gold。
- 未真实启动 Windows API/Vue 服务、未使用真实登录或浏览器；离线 Web API 路由由 FastAPI TestClient 验证。
- 未创建 Grant、未做真实 Provider Live、未向订单或外部业务系统写入，也未重跑 E01。
- E05/E07 真实输入、Provider Trace、费用和 Rubric 语义评分必须分别记录首次尝试；评分仍交主 Agent。
