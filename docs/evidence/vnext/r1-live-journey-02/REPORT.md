# R1-LIVE-JOURNEY-02 报告

**状态：`ACCEPTANCE_CANDIDATE`（离线部分）；真实 Campaign：`BLOCKED_BEFORE_PROVIDER_SEND`**
**Branch：** `codex/r1-live-journey-02`
**Base：** `43d8b6728950793cae518812acd5b04c22948c9b`
**远端 main：** `60eee87bfe3cca522011316cb4cd2c0064ad291b`（本轮未修改）

开工实际核对的基线文件：`PROJECT_NORTH_STAR.md` Blob `43dabda468506717c6956e676dfad4304c4f38e6`；`AGENTS.md` Blob `807b928686a4dd2cac7b15b3c354b9943c93c910`；Review Skill Blob `d405c8d413d633824b279202cc1503dab4cf0b03`。继承的旅程 CASES Blob 为 `c31afbed3bf1cb11fa25906f1d7290ee9cdbfadd`，SHA-256 为 `a668240be2f816e66b39557daab5e58937f264fb258525d04765baf75974bf63`；未修改冻结文件。

## 结果摘要

本轮没有取得 `R1-LIVE-JOURNEY-02` 专属的真实 Provider 付费授权，因此没有发送 DeepSeek 请求，也没有创建或消费真实 Runtime Grant、Campaign Claim、运行数据库或额度。J1/J2 的新真实业务旅程均未运行。用户要求的真实模型闭环目标尚未达成，不能把离线回放标成真实成功。

离线部分完成了两件直接相关的事：

1. 核对上轮私有原始归档的 SHA-256 与既有审计清单一致，四条 HTTP 200 响应中的真实 tool_calls 与脱敏 Trace 逐项相符。两条捕获响应通过正式 API/Worker/Assistant/ToolNode/MCP 路径重放，合法 MCP Observation 进入下一次模型输入；后续答复由 FixtureModel 产生。
2. 在现有 Runtime Grant 账本中增加精确冻结的 `R1-LIVE-JOURNEY-02` 策略：最多 12 个已授权 Provider 发送，单次保守预留 USD 0.645600，应用费用池 USD 8.00。第 12 次允许、第 13 次拒绝、Worker 重启不重置计数、末槽并发仅一个请求取得发送许可、UNKNOWN 保留并停止、参数漂移拒绝及正式 Worker 的 MockTransport 路径均由测试覆盖。旧 `R1-LIVE-JOURNEY-01` 策略保持 16 次/USD 11 不变。

## 真实模型证据与限制

上一 Campaign 的四次真实 HTTP 200 均返回有效 Usage 和 `tool_calls`，但四个正式 Assistant Run 失败、MCP 调用数为零；应用账本结算估算为 USD 0.002914。那是 `R1-LIVE-JOURNEY-01` 的历史失败，不计入本次 Campaign，不修改其账本或结论。原运行为什么未进入 ToolNode，历史异常原因链和响应编码头未被保存，当前仍为 `UNCONFIRMED`。

本轮离线回放证明捕获到的具体 J1-01/J2-01 工具提议可由当前正式 Assistant 接入 MCP：J1-01 一次协议发现；J2-01 协议发现、Delivery、Receiver 三次调用。第二次模拟 Provider 响应及最终回答是 FixtureModel 内容，不能用于声称真实模型完成了用户任务。

## 新 Campaign 策略依据

2026-11-08 查阅 DeepSeek 官方模型与计费文档：`deepseek-flash` 当前标示模型版本为 `DeepSeek-V4.1-Flash-1017`，1M 上下文、最多 384K 输出；高峰缓存未命中输入 USD 0.30/M，输出 USD 1.20/M。按公开极端容量保守计算：`616,000 × $0.30/M + 384,000 × $1.20/M = $0.6456`。12 次保守预留合计 USD 7.7472，低于 USD 8.00。该价格是应用侧上界策略依据，不是供应商账单；真实执行当天仍须核对价格/容量/请求参数，漂移时停止。详见 [DeepSeek 官方价格页](https://api-docs.deepseek.com/quick_start/pricing/) 和 [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)。

## 改动与验证

- 生产改动仅扩展 `opspilot/domain/assistant_runtime_grant.py` 中现有冻结 Campaign 策略校验和绑定；未新增账本、Runtime、重试或工具路由。
- 测试改动仅扩展 `tests/test_r1_live_campaign_budget.py`，覆盖新策略、正式 Worker MockTransport、预算/次数边界与末槽竞争。
- 适用回归：Campaign、保存的真实 tool_calls 离线回放及 gzip 解码定向测试合计 30/30 通过，退出码 0。实际命令在 `TEST_LOG.txt`。
- 新的真实 Provider 请求：0；浏览器：0；外部业务写入：0。测试使用 MockTransport 与隔离临时 SQLite。

完整原始私有文件哈希与四组请求/响应哈希见 `CAPTURE_AUDIT.md`；案例与轨迹汇总见 `RESULTS.json`、`TRACE.jsonl`。旧失败和当前授权阻断见 `FAILURES.md`。
