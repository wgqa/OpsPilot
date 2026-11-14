# R2-AR06-HOLDOUT-READY-01 · 离线留出案例准备

## 状态与冻结边界

- Base：`codex/r2-ar06-auto-live-eval-01@92b543b22cdd91d42c70b38268d820dde405758e`
- 本候选分支：`codex/r2-ar06-holdout-ready-01`
- 工作树：`D:\OpsPilot-LIVE-02-FIX-01-HF02`，复用既有目录；新增 Worktree：0。
- 冻结 `CASES.json` SHA-256：`c1acd3fa789befa733aa96bf3a49b08357ff071f3b627b4c40319882e2805cf8`
- 本轮仅扩展 Runner 对 E02-H、E06-H 的单轮题面读取和正式 API Fixture 路由。未改 `CASES.json`、`RUBRIC.json`、`EVAL_PROTOCOL.md`、Assistant/Domain 权限、Gold 或历史 Trace。
- 离线 Fixture 路由结果不是真实模型结果，也不构成 E02-H/E06-H 的语义评分或 Benchmark PASS；两例仍是 `UNVERIFIED / NOT_LIVE_EXECUTED`。

## 冻结输入与路由忠实度

Runner 在读取前校验 `FROZEN_HASHES.json`。只把 Case ID、split、逐字 `user_turns[0]` 和整个冻结文件的 SHA 交给执行逻辑；不会加载 `acceptable_decisions`、`expected_user_outcome`、`required_evidence`、`forbidden` 或评分解释。Fixture 测试检查实际模型输入中的 Human 消息与冻结题面完全一致，并确认评分字段没有进入 Prompt。

| Case | H 评估目标（仅由评审者使用） | 初态/正式路径 | Fixture 实际证据 | 忠实度结论 |
|---|---|---|---|---|
| E02-H | 已知/未知区分、澄清是否有用、是否捏造根因 | 新隔离标准 Runtime、新 Session、无 TaskBinding；Assistant Message Web API | 冻结单条输入逐字持久化；Run `SUCCEEDED`；Fixture 1 次；TaskBinding、MCP、Observation、Provider Send Grant 均为 0 | 题面和路由完全匹配；语义质量未评定 |
| E06-H | 冲突识别、Event 关联边界、避免无依据确定性 | 新隔离标准 Runtime、新 Session、无 TaskBinding；Assistant Message Web API | 冻结单条输入逐字持久化；Run `SUCCEEDED`；Fixture 1 次；TaskBinding、MCP、Observation、Provider Send Grant 均为 0 | 题面和路由完全匹配；语义质量未评定 |

两例的测试响应都明确写入 `FIXTURE_ONLY`，仅用于证明模型调用与持久回答接线正常。测试不会比较这段固定文字是否满足 Gold，也不把 Fixture Token 当 Provider Token。

本准备不新增或更新 `RUNS.jsonl`、`RESULTS.json` 中的语义评定，所以 Phase A 的原始 6 PASS、3 PARTIAL、3 NOT_RUN 统计保持不变。只有以后按冻结题面、独立 Runtime 和真实 Provider 执行并由独立评审评分后，才可登记为 H 真实评测。

## E08-H 的最小初态差异

现有 `initialize_demo.py` 的 `r2-e08-processed-decoy` Profile 已符合两条业务数据条件，现有隔离初始化回归也核对过：

- 目标 `async-order`：Delivery `ACKNOWLEDGED`；目标 Delivery/Receiver 共用 Event `event-00000000-0000-4000-8000-000000000101`；Receiver `PROCESSED`。
- 未绑定 decoy `async-order-decoy`：Delivery `ACKNOWLEDGED`；Delivery/Receiver 共用另一个 Event `event-00000000-0000-4000-8000-000000000102`；Receiver `QUEUED`。
- 新库没有 Session、Message、TaskBinding、Task Run 或个人记忆。已有测试证明 SUPPORT 可以通过正式 Assistant API 绑定目标 `async-order`，并未绑定 decoy。

Gold 另外要求 `history_state=QUEUED`、一条可区分身份的历史 Message，以及目标的当前 Run Observation。当前隔离 Profile 不创建历史会话/消息/绑定/Run。冻结描述同时把 Session 标为 `fresh`，又要求历史回答/历史消息；Gold 未指定历史 Message 的来源、身份、时间和“fresh”的含义。不能把当前用户题面中的“历史回答说 QUEUED”冒充成真实预置历史，也不能用 SQL 或 Fixture Model 伪造历史来源。

因此 E08-H 的精确执行仍待主 Agent 裁决其“fresh Session + 历史 Message”初态表示方法。裁决前只可复用已验证的目标/decoy Profile 做离线数据准备分析，不创建历史 Message、不改冻结初态、不声称完整 H 忠实度。若仍按当前 Gold 逐字评分，缺少可追溯历史身份时应保留 PARTIAL/NOT_READY。

## 可复跑命令

以下命令只跑 Fixture/Mock，不联系真实 Provider。每次生成新的 basetemp，不复用或清理旧临时库：

```powershell
Set-Location 'D:\OpsPilot-LIVE-02-FIX-01-HF02'
$caseTemp = Join-Path (Get-Location) ('.runtime\pytest-r2-ar06-holdout-' + [guid]::NewGuid().ToString('N'))
python -m pytest `
  tests/test_r2_ar06_auto_live_eval.py::test_holdout_route_uses_exact_frozen_input_in_fresh_formal_session_without_gold `
  -q --basetemp $caseTemp
```

该参数化测试分别为 E02-H 和 E06-H 建立空 Domain/Checkpoint、SUPPORT 登录、新 Session，并通过正式 `/api/sessions/{id}/assistant/messages` 路由各提交一次冻结输入。两个案例的 SQLite 文件位于不同测试临时 Runtime 下。

如需在独立命名目录中查看只读离线 Preflight（本次未创建额外持久 Runtime；使用前需选一个此前不存在的新别名）：

```powershell
$runtimeName = 'user-demo-r2-e02h-' + [guid]::NewGuid().ToString('N')
python .\scripts\user-demo\run_r2_ar06_case.py prepare --case-id E02-H --runtime-name $runtimeName
python .\scripts\user-demo\run_r2_ar06_case.py preflight --case-id E02-H --runtime-name $runtimeName --mode offline
```

E06-H 用 `user-demo-r2-e06h-` 前缀单独执行上述两条命令。`prepare` 仅初始化一个新隔离 Runtime；`preflight --mode offline` 读取所选库，不发聊天请求。不要将两例放在同一个 Runtime。

## 未来 Live 预算与门禁

当前 Runner 每 Run 最多允许 8 次 Provider Dispatch、6 次 MCP `tools/call`；这是授权/费用预留合同上限，不是预期工具顺序。E02-H/E06-H 各是一条用户消息；Fixture 各只调用模型一次，但不能据此保证真实模型同样只调用一次。

按本任务时核对的 DeepSeek 官方 `deepseek-flash` Peak、Cache Miss 输入价 USD 0.30/百万 Token，输出价 USD 1.20/百万 Token，以及既有 Runtime Grant 单请求预留上限 12,000 输入 / 2,048 输出 Token，单次最大预留约 USD 0.006058，8 次约 USD 0.048464。来源：[DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)。价格可能变化；真实评测前须再核对费率和 Runtime Grant 配置，Preflight 会按该隔离库中的实际费率重新计算，不以此文档数值替代费用授权。

若沿用上述费率和上限，预算准备可按 **每个案例独立 USD 0.05，两个 Runtime 合计最多 USD 0.10** 估算；这只是未来授权需求估计，不是本轮费用许可或 Grant。每例必须新建独立 Runtime 和 Grant；E01 Grant 不得迁移。没有新的明确授权前，不执行 `Configure-UserDemoLive.ps1`、Live Preflight、`Start-UserDemo.ps1 -Mode Live` 或 `run-live`。

未来经授权的单例命令仍需按现有流程执行：`prepare` → 正式费用授权/Grant → Live 启动 → `preflight --mode live --authorized-max-cost-usd 0.05` → `run-live --authorized-case-id <同一 Case ID> --authorized-max-cost-usd 0.05`。任何 UNKNOWN、HTTP 确认丢失、预算不足或 Preflight 失败都停止，不重发。

## 本轮验证边界

- Fixture Runner 定向测试：见 [HOLDOUT_FIXTURE_TEST_LOG.txt](HOLDOUT_FIXTURE_TEST_LOG.txt)。
- E08 既有 Profile 初始化和可信 API 绑定测试复用记录：同一日志文件；它们只验证现有初态数据/绑定合同，不是 E08 真实运行。
- 真实 Provider 请求：0；Runtime Grant 创建：0；外部业务写入：0；浏览器自动化：0；新增 Worktree：0。
- E02-H/E06-H 真实回答质量、独立 Rubric 评分、Live Trace/Usage/费用：未运行。
- E08-H 精确历史初态：待主 Agent 裁决；未创建或修改。
