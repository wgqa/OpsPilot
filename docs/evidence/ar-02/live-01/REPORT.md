# AR-02-LIVE-01 P0 交付报告

- **状态：** `P0_READY / P1_NOT_AUTHORIZED`
- **仓库/候选分支：** `wgqa/OpsPilot` / `codex/ar02-live-01`
- **基线：** `88e00126aaca7af0cbfd454e8f833eae90eae39c`
- **工作目录：** `D:\学习\agent新项目\.worktrees\ar02-live-01`
- **最后测试：** 2026-11-01；完整原始结果见 `runs/` 与 `RESULTS.json`。

## P0 实际交付

真实 Provider 工厂仍默认关闭；仅有密钥不会打开。显式启用时要求固定实验 ID `AR-02-LIVE-01`、固定模型 `deepseek-flash`、官方 HTTPS endpoint 与完整配置。工厂创建模型对象不发请求。`httpx.MockTransport` 捕获的实际序列化请求包含 `model=deepseek-flash`、`max_tokens=2048`、`thinking.type=disabled`、`tool_choice=auto`、`parallel_tool_calls=false`，没有 SDK 的 `max_completion_tokens` 别名；测试中没有访问网络。

在现有 `assistant.py` AgentMiddleware 的 Provider 与 MCP 出站点增加实验账本挂接。独立 `assistant_experiment.py` 只实现固定实验 ID 的延迟 SQLite 表，不增加通用费用平台，也不升级 DB `user_version`。预留通过 `BEGIN IMMEDIATE` 和唯一 `(experiment, run, kind, logical_key)` 实现跨 Run/Session 原子额度、同请求幂等、异摘要冲突拒绝；UNKNOWN/超时保留完整预留，不自动重发。原有每 Run/Task 预算仍先行生效。标准应用未显式选择此实验时，不创建实验账本。

确定性模型通过正式 FastAPI TestClient、单实例 Worker、`ASSISTANT_V1`、LangGraph/MCP stdio 和 SQLite 完成两条独立 Session 的本地旅程：第一条模型选择查询 Knowledge，MCP 实际返回空文档/空引用，模型随后按“本次未检索到资料”生成一般解释；第二条直接回答。持久结果显示 3 次模型 middleware dispatch、1 次本地 `tools/call`、2 条与原 Message 关联的 Assistant 答复。该证据证明正式入口与总额度记录已接线，不代表真实模型决策或完整 S01/S02 旅程。

对照本地 DB，S3 Diagnosis、ActionIntent、Handoff Receipt 数量均为 0；本轮没有执行业务修复、审批或外部写入。脱敏/限范围的本地持久轨迹见 `TRACE.jsonl`。

## 费用预检与 P1 停点

2026-11-01 重核 DeepSeek 官方价目表后，确认 `deepseek-flash` 峰时 cache-miss 输入价为 `$0.30/M`、输出为 `$1.20/M`，上下文 1M、最大输出 384K。每次按输入最多 616K、输出 384K 预留 `$0.645600`，不计算 cache-hit 优惠；16 次全未知结果的预留总计 `$10.329600`，低于冻结 `$10.50`，余 `$0.170400`。账本超额、超次数、畸形/缺失 Usage、响应未知和预算 Breach 均有本地正反测试。

供应商模型及价格资料可能变化；应用侧账本不能取代供应商账户硬额度，也不能保证 Provider 违反公开边界时不超账。价格与参数根据[官方价目表](https://api-docs.deepseek.com/quick_start/pricing/)、[Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/) 和[Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/) 预检；真实 Provider 兼容性尚未实测。

**P1 申请参数（尚未授权、未执行）：** 仅运行冻结的 S01 一次及同一 Session 的 S02 五轮；DeepSeek `deepseek-flash` Chat Completions、非思考模式、`max_tokens=2048`、`tool_choice=auto`、`parallel_tool_calls=false`；请求超时 30 秒，`max_retries=0`；整个实验最多 16 次 Provider、12 次 MCP `tools/call`；应用费用预留上限 USD 10.50，每次预留 USD 0.645600，合法 Usage 后结算，未知/超时/取消/丢失响应不释放、不重试。仅用已有只读工具和可信授权，不做修复、审批、交接、浏览器操作或外部写入。须由用户对这组完整参数另行明确授权后才可开始。

## 测试与限制

- P0 focused：24 passed；见 `runs/green-focused-final-02.log`。
- AR-02、Assistant、Knowledge、HF-01、TaskControl 与 Worker 定向回归：73 passed；见 `runs/regression-final-02.log`。
- `git diff --check`：通过。
- RED、两次中间失败、环境依赖失败及旧中间结果原样保留；逐项归因见 `FAILURES.md`。
- 全量仓库 pytest：未运行。真实 Provider、真实 S01/S02、浏览器自动化：均 `NOT_RUN`。也未做在线 business HTTP 验证。
- 当前没有真实 Provider 请求 ID、Usage、账单或模型行为证据；MockTransport 和 FixtureModel 只用于免费协议/接线检查。

## 改动范围

- `opspilot/assistant.py`：固定 Provider 配置、非思考请求体、实验级 Provider/MCP 原子预留与结算。
- `opspilot/domain/assistant_experiment.py`：仅 AR-02-LIVE-01 的隔离账本。
- `opspilot/web/app.py`、`opspilot/web/worker.py`：把显式实验作用域从正式 app 传到 Worker/Assistant。
- `tests/test_ar02_live_budget.py`、`tests/test_ar02_smoke_provider_factory.py`：RED/GREEN、幂等/未知/并发/额度/正式 API Worker/Provider wire 与安全反例。
- `docs/evidence/ar-02/live-01/`：冻结验收、费用预检、机器结果、失败与实际本地 trace。

未修改生产 Investigator、Chat/TaskControl/Gate、S1/S2 Gold 或业务写入协议；未改 `main`，未执行付费或浏览器验收。本报告仅提交 P0 候选，需主 Agent独立核验。

## Skill 六项收尾

1. **用户变化：** P0 让同一正式 API/Worker 路径具备固定实验下的持久跨会话额度，并已用免费替身获得可读取的持久答复。
2. **Agent 决策：** 确定性替身演示了直接解释与选择 Knowledge 两种动作；真实模型的决策尚未观察。
3. **观察驱动：** MCP 返回空文档/引用后，最终替身答复不声称引用了资料；实际模型是否遵循仍未知。
4. **新增约束与合法任务影响：** 实验额度保护限定 Provider/MCP 次数及应用预留；预算内零工具回答、Knowledge 和只读 MCP 正例仍通过。额度拒绝发生在外发前。
5. **简化结果：** 只增加单实验 SQLite 账本并沿用现有 Run/Task 预留、Worker 与 MCP，不新增通用费用服务、状态机或业务 Gate。
6. **证据与停止线：** focused 24/24、相关回归 73/73、全量 pytest 未跑；Provider/浏览器/真实 S01/S02 为 NOT_RUN。状态为 `P0_READY / P1_NOT_AUTHORIZED`，现在停止等待裁决。
