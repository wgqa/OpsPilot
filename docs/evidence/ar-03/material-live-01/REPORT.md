# AR-03-MATERIAL-LIVE-01 — 真实模型材料调查验收报告

**结果：`BLOCKED_BEFORE_PROVIDER_SEND`**

**交付状态：`ACCEPTANCE_CANDIDATE`（本轮业务 Gold 未运行，等待主 Agent 独立裁决）**

## 用户旅程结果

没有用户问题进入正式 Assistant Run，也没有模型答复。七项冻结 Gold（MAT-01 至 MAT-06 的 Skill OFF/ON 对照）均为 `NOT_RUN`；真实模型决策、Skill ON/OFF 差异、协议引用、可信业务 Observation 与合法任务误拒绝均未得到验证。

实际只启动了一次正式 `run_live.py --execute-once`。Runner 通过重复发送前检查并创建一次性 claim 与独立实验数据库，随后在准备本地业务夹具时因 `IntegrityError: FOREIGN KEY constraint failed` 停止。它在任何 Provider HTTP 请求或 MCP `tools/call` 前停止。根据源码顺序和数据库审计，失败发生在 `_prepare_fixture()` 调用 `prepare_s3_fixture()` 的建档阶段：全新数据库只有 Schema、没有 `tenant-a` 行，而夹具首个 principal 写入依赖该 tenant。测试套件通过 `reset_fixture()` 先建立 tenant、credential 等演示基础资料；正式 Runner 漏掉了这一隔离环境初始化步骤。运行器只保存异常类型和消息，没有 Python 栈，因此具体首条失败 SQL 是根据源码执行顺序与落盘状态定位，未声称有原始 traceback。

夹具函数源码在数据库写入前会向临时 `127.0.0.1` Receiver 发一个本地测试 POST；失败前该调用未被 Runner Trace 单独记录。它不是 DeepSeek/MCP 请求，也没有形成业务表变更。只读数据库核对显示 Session、Task、Assistant、S3 事实、Diagnosis、Handoff 与业务动作表均为零行，外键检查为零项。

## 机器与预算结果

- 基线：`3ec06caa6a2d8ef370592d33164be3077a0a5f6f`；冻结提交：`434a8b027f0072036b46bc624d1defab8703b775`。
- 真实 Provider 调用：`0`；MCP 调用：`0`；业务写入：`0`；Provider Usage：无；应用费用估算：`USD 0`。
- 新实验账本：`OPEN`，Provider/MCP 使用数为 0，预留与结算均为 0。
- `EXECUTION_CLAIM.json` 状态为 `CLAIMED_ONE_SHOT_NO_RETRY`。按本任务停止规则，不能再次启动此 Runner；未来重跑需先修复隔离夹具初始化，并另行取得执行授权。
- AR-02/AR-03 旧实验账本与历史 UNKNOWN 记录未被本 Runner 访问或修改。
- 浏览器：`NOT_RUN`（本任务不授权）。

本次预检确认 `deepseek-flash`、non-thinking、`max_tokens=2048`、零 SDK/HTTP 重试、30 秒超时、16 Provider/10 MCP、单次 USD 0.645600 预留、总额 USD 10.50 与 12,000 Token Context 上限；实际运行的重复 preflight 为 `PREFLIGHT_READY`。最新远端核对结果来自该 preflight：远端 `main=ec8c3582f6d145eec9979c43607302731411ead8`，远端候选仍为 `3ec06caa6a2d8ef370592d33164be3077a0a5f6f`。该结果只证明预检，不代表 Agent 旅程成功。

费率复核依据 DeepSeek 官方[价格页](https://api-docs.deepseek.com/quick_start/pricing/)及[Chat Completions API 文档](https://api-docs.deepseek.com/api/create-chat-completion/)（2026-11-03）：`deepseek-flash` 当前列示版本为 `DeepSeek-V4.1-Flash-1017`，峰值未命中缓存费率为输入 $0.30/百万 token、输出 $1.20/百万 token；冻结预留保持不变。由于本次零 Provider 请求，实际供应商费用为零。

## 证据索引

- `RESULTS.json`：机器结果，0/7 case，`BLOCKED_BEFORE_PROVIDER_SEND`。
- `PREFLIGHT.json`：真实 one-shot 重复预检及当时 HEAD/远端 refs。
- `EXECUTION_CLAIM.json`：一次性执行身份已消费。
- `BUDGET_LEDGER.json`：新账本零使用、零费用预留。
- `TRACE.jsonl`：Runner 停止事件和独立只读 SQLite 状态核验。
- `FAILURES.md`：保留冻结前全部 RED/GREEN/预检失败，并追加本次停止原因。
- `runs/live-runner-invocation.jsonl`：本次命令退出码及机器结果索引。
- `runs/preflight-01/02/03` 和历史测试日志：原始日志保留；第三次 preflight exit code 为 0。
- `PROVIDER_HTTP.jsonl` 未生成：HTTPX Provider transport 从未接收请求。

## 失败归因与下一步边界

这是实验 Runner 的隔离测试资料准备缺口，不是模型策略或 Provider 连接故障。最小修正方向是在全新实验 DB 上、建立实验账本之前，调用项目既有受控 fixture bootstrap（或同等完整且仅限实验 DB 的 tenant/credential 初始化），然后再初始化 Campaign 并准备 `ar03-order`。本轮没有修改代码或重跑。任何修复后的真实实验都需由主 Agent/用户重新授权，不能复用本次已消费的 claim。

## Skill 六问

1. **用户变化：** 本轮未能让用户完成材料调查；没有提交问题或答复。
2. **Agent 决策：** 没有模型调用，未观察到任何 Agent 决策。
3. **观察驱动：** 没有 MCP Observation；QUEUED/PROCESSED 对照未运行。
4. **约束与合法任务：** 预算、作用域及零写入边界未被突破；但环境准备错误在合法旅程开始前阻断了全部用例。
5. **简化：** 没有新增业务架构；已定位为 Runner 未复用既有 fixture bootstrap。
6. **证据与停止线：** 预检通过，执行在首个 Provider 请求前以外键错误停止。零重试、零真实 Provider 请求；保持 `BLOCKED_BEFORE_PROVIDER_SEND` 并交独立评审。

**未验证：** MAT-01–MAT-06 全部业务效果、真实 Skill 差异、模型成本/Token、合法任务误拒绝、模型自主性。
