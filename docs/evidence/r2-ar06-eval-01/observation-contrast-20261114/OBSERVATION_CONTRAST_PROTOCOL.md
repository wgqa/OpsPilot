# R2-AR06-OBSERVATION-CONTRAST-01

**状态：** `ACCEPTANCE_CANDIDATE`（仅离线准备完成；真实模型对照尚未执行）
**Base：** `codex/r2-ar06-complex-case-ready-01@f4d106b35e75b8eb654b6a508cfe807579c59fed`
**候选分支：** `codex/r2-ar06-observation-contrast-01`
**工作树：** `D:\OpsPilot-LIVE-02-FIX-01-HF02`

## 1. 目的与实验边界

本实验复用 E07-D 已冻结的用户原题，只改变新隔离 Runtime 中目标订单的当前 Receiver 状态，用来观察模型是否根据当前 MCP Observation 改变结论。它是探索性反事实对照，**不是 E08-H 的首次正式执行、评分或通过记录，也不进入冻结 12 题分母**。

模型可以自行决定是否及如何调用可见工具；Runner 只创建可信目标订单 TaskBinding、验证隔离 Fixture、等待终态并导出 Trace。Runner 不规定 MCP 工具顺序。`CASES.json` 仍为 SHA-256 `c1acd3fa789befa733aa96bf3a49b08357ff071f3b627b4c40319882e2805cf8`；Gold、Rubric、评测协议和历史 Trace 均未修改。

## 2. 已有 E07-D 首次真实运行（只读基线）

复用且不重跑的原始文件：

- `runs/LIVE_E07-D_TRACE.json` SHA-256：`aacf15bdb81a24461b612551a23800a12c86f54a275f95185a3d24cdb34ebb59`
- `runs/LIVE_E07-D_RUN_RESULT.json` SHA-256：`d31a82dd7f39e961a8b0398d6b554b40f6b5d609d8b66362989489cd0494ebd0`
- Runtime：`user-demo-r2-e07-live01`
- Session：`session-300f9d82-85f7-4bff-a3d6-6da8d99324b3`
- TaskBinding：`task-73c28480-0392-47c4-866d-8a5e505ae619`
- Run：`run-c6be60b9-e6b0-4310-8c8f-853c00934d4f`，`SUCCEEDED`
- Provider：2 次发送、2 次收到响应、0 UNKNOWN；Input/Output Token `7629 / 675`；应用账本费用 `USD 0.003099`；Runner elapsed `8023 ms`。
- 自主 MCP：`get_order_status`、`get_callback_delivery`、`get_receiver_processing`；共 3 次调用、3 个 Observation 和 3 个 Evidence。
- 目标 `async-order` 的 Delivery 为 `ACKNOWLEDGED / HTTP 202`；Receiver Observation 为 `QUEUED`，Event 为 `event-00000000-0000-4000-8000-000000000001`，Observation ID 为 `observation-7299a755-b33a-412e-8f42-750520853656`。

原回答的相关结论为回调已被接收，但 Receiver 仍排队、处理未完成。它还单独读取到订单状态 `COMPLETED`；这个订单状态不能替代同 Event 的 Receiver 处理状态。该真实结果保持原样。

原题逐字为：

> 请核查这个授权订单当前回调处理到了哪一步。HTTP 202 是否表示已经处理完成？

## 3. 新探索性 Fixture 与身份关系

Runner 新入口名：`OBSERVATION-CONTRAST-PROCESSED`。它在内存中引用 `E07-D` 的冻结输入，但输出标记为 `EXPLORATORY`，带 `EXPLORATORY_COUNTERFACTUAL_NOT_FROZEN_CASE`，不会伪装成 E07-D 或 E08-H 的一次 Gold 执行。

`r2-e08-processed-decoy` Profile 的现有合成数据库提供：

| 资源 | Order | Event | Delivery | Receiver |
|---|---|---|---|---|
| 目标 | `async-order` | `event-00000000-0000-4000-8000-000000000101` | `ACKNOWLEDGED / HTTP 202` | `PROCESSED` |
| 独立 decoy | `async-order-decoy` | `event-00000000-0000-4000-8000-000000000102` | `ACKNOWLEDGED / HTTP 202` | `QUEUED` |

准备阶段以只读 SQLite 检查两条 Delivery/Receiver 的 Event ID 各自相等、目标与 decoy Event 不同、状态符合表格。模型 Run 仍通过正式 Assistant API 对 `async-order` 建立 TaskBinding；Runner 在结果导出时再通过 Domain `get_s3_binding()` 只读核验 Tenant、Service、Actor 和 Order。

MCP 边界沿用现有实现：`opspilot/domain/s3_mcp.py` 的 `get_receiver_processing` 只读取可信绑定订单的 Receiver 并返回实际 Event ID；Transport History 查询也只允许绑定订单内的 Event，Domain 会拒绝不属于该订单的 Event。Fixture 中的 decoy 不会替代目标绑定。

导出后的资格审计只统计同时关联到本 Run 的 MCP 调用、本 Task、本 Tenant、目标 Order/Event 的成功 `s3_receiver` Observation。只有这条当前 Observation 状态为 `PROCESSED`、且带 Observation/Evidence ID 与来源引用时，结果字段 `supports_target_processed_conclusion` 才为真。decoy Event、其它 Run 的 Observation、Delivery 中历史响应体均不能满足这一条件。该字段只校验可用证据，不自动给模型答案打分。

## 4. Runner 最小适配

只扩展现有 `scripts/user-demo/run_r2_ar06_case.py`：

1. 新实验 ID 映射到 E07-D 的冻结用户问题；模型 Context 不包含 Gold 预期、Rubric 字段或实验标记。
2. `prepare` 复用 `initialize_user_demo()`，选择已有 `r2-e08-processed-decoy` Profile，要求从未存在的新 Runtime 名称。
3. `preflight` 只读核验目标/decoy Event、数据库空 Session、空 Task、无 Runtime Grant、无 Provider Send/UNKNOWN。Live Preflight 仍要求独立 Grant、Managed Live Runtime、健康 API 和费用余额；每 Run 的 8 次模型派发上限仍来自现有 Runner 合同。
4. `run-live` 仍只提交一条冻结题面、使用正式 `/api/sessions/{session_id}/assistant/order` API、等待 Run 终态并导出该 Session Trace；无自动重试。
5. Runner 结果另记 `source_question_case_id=E07-D`、探索性分类、TaskBinding 目标和本 Run Receiver Observation 关联；不更新既有 `LIVE_RESULTS.json`、E07 Trace 或 Gold 聚合结果。

## 5. 对照判据（只供评测者使用）

- **E07-D 原基线：** 本 Run 目标 Event Receiver 为 `QUEUED`，回答应说接收已确认、处理完成尚未确认；HTTP 202 本身不表示处理完成。
- **本探索实验：** 若本 Run 的 TaskBinding-scoped Observation 确认目标 Event Receiver 为 `PROCESSED`，回答应将结论改为该目标 Receiver 已处理，同时仍说明 HTTP 202 单独只表示接收确认，不能泛化到其它 Event。
- 只有 Observation ID、Run/Task 关联和目标 Event 全部核对后，才由主 Agent 对最终回答作独立语义评定。Fixture 运行只验路由与来源关联，不证明真实模型会自主作出该结论。
- 本轮不会把探索结果回灌 Prompt，也不会重跑或更改 E07-D 首次成绩。

## 6. 离线验证证据

最终定向命令与 `23 passed` 结果见同目录 `TARGETED_TESTS.txt`。测试覆盖 Runner 单次正式 API 提交、精确冻结输入、处理态目标与排队 decoy 的隔离数据、正式 TaskBinding 的目标订单、当前 Run Observation 审计、错误 Event 拒绝、费用 Preflight 上限，以及既有 E07/Setup 回归。Fixture Model 使用独立 pytest 临时目录；真实 Provider 调用为 0。

首次测试 RED 记录在日志中：两项是测试生成的 Runtime 别名超过已有安全长度合同；一项是合成 Observation 缺少现实 Trace 中必需的 Tenant 字段。修正测试 Fixture 后，最终定向回归通过；没有放宽 Runtime 别名规则或 Observation 校验。

本轮未创建 User Demo Runtime、Grant、Spend、Session、TaskBinding 或业务写入；未运行正式服务、浏览器、真实 MCP Server 或收费 Provider。

## 7. 未来 Live 执行命令（仅在单独费用批准后）

建议独立 Runtime：`user-demo-r2-obscontrast-live01`。建议该例独立 Application Spend Pool 上限 `USD 0.05`；不迁移或复用任何 E05/E07 Grant。当前本地 Provider 配置读取（密钥值未显示）为 `deepseek-flash` / `api.deepseek.com`，价格版本 `DEEPSEEK_FLASH_PEAK_2026-11-14`，Input/Output 费率分别为每百万 Token `300000 / 1200000` micro-USD，单请求保守 reserve `USD 0.006058`。现有 8 派发合同需要至少 `USD 0.048464` 的预留空间，因此 `USD 0.05` 可通过当前配置下的预留检查，余额余量很小；Runner 会在 Live Preflight 按实际本地价格和 Grant 再核算。账本金额是应用侧估算，不等同 Provider 发票。

**以下命令只供新的独立费用授权通过后执行；本次没有创建 Grant，也没有执行这些命令：**

```powershell
$RuntimeName = 'user-demo-r2-obscontrast-live01'
python .\scripts\user-demo\run_r2_ar06_case.py prepare --case-id OBSERVATION-CONTRAST-PROCESSED --runtime-name $RuntimeName
python .\scripts\user-demo\runtime_admin.py configure --runtime-name $RuntimeName
python .\scripts\user-demo\runtime_admin.py preflight --runtime-name $RuntimeName
.\scripts\user-demo\Start-UserDemo.ps1 -Profile S1 -Mode Live -RuntimeName $RuntimeName
python .\scripts\user-demo\run_r2_ar06_case.py preflight --case-id OBSERVATION-CONTRAST-PROCESSED --runtime-name $RuntimeName --mode live --authorized-max-cost-usd 0.05
python .\scripts\user-demo\run_r2_ar06_case.py run-live --case-id OBSERVATION-CONTRAST-PROCESSED --runtime-name $RuntimeName --authorized-case-id OBSERVATION-CONTRAST-PROCESSED --authorized-max-cost-usd 0.05
python .\scripts\user-demo\runtime_admin.py summary --runtime-name $RuntimeName
.\scripts\user-demo\Stop-UserDemo.ps1 -RuntimeName $RuntimeName
```

`runtime_admin.py configure` 会交互式配置 Grant，并要求输入准确确认语句；不得绕过该交互。Preflight 失败、余额不够、UNKNOWN、请求确认不明或超时均立即停止；不再次 POST、不自动恢复或增加预算。结果与 Trace 会留在新 Runtime 的 `evidence` 目录。

## 8. 保留的阻断案例

- **E03-D：`BLOCKED`。** 保留 `orders-async-demo` 与 `orders-callback` 的原授权差异；不替换项目 ID，不改 Gold。若要改合同，先由主 Agent 单独冻结版本。
- **E11-D：`BLOCKED`。** 不开 legacy Provider。Investigator 与持久 Runtime Grant/Spend Ledger 的集成只在正式业务确有需要时单独评审，不为评测分数开展安全敏感重构。
- 本实验不解决 E08-H 所需的历史 QUEUED 消息身份/来源初态；本探索不得计作 E08-H。

## 9. 停止线

离线 Runner、身份/事件校验和费用前置检查完成后即停止。下一步只能由主 Agent 核查本候选，并由用户对这一个独立探索 Runtime 作出新的明确费用授权；未经授权，不进行 Live 调用。
