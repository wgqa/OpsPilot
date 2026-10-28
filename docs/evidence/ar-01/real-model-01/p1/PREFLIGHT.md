# P1 实际执行预检

状态：五对已执行完毕；付费入口已停止。此文记录本轮实际条件，不追溯修改 PROBE-01。

- Repo / Branch：`wgqa/OpsPilot` / `codex/ar01-free-agent`。
- Base：`88e8e8ab7577e02b960a27667950515e7c5e0c5a`。
- 冻结：`d667762e4a6feccf8701c0d6ec94bee22142b80e`；执行源码：`ff8fb4c48aca609c73d0aa77c4647b30c960c7f0`。
- 当前对话授权 `AUTHORIZED_FOR_BOUNDED_P1`：固定五对、最多 80 Provider / 60 MCP、USD 0.50；不包含额外探测、重跑或迁移。
- `RUN_STARTED.json` 为一次性运行标记；`LIVE_PREFLIGHT.json` 保存运行时配置、授权引用、原案例和摘要；`LIVE_RESULTS.json` 保存结算账本快照。
- 独立实验 worktree。原 `D:/学习/agent新项目` 未提交文件、实验 worktree 中既有未跟踪目录均保留，不暂存。

## 实际参数与费用

新配置 `P1_2048_V1` / `REQUEST_WIRE_P1_2048_V1`：`deepseek-flash`、`https://api.deepseek.com`、non-thinking、`max_tokens=2048`、`tool_choice=auto`、`parallel_tool_calls=false`、`stream=false`、`max_retries=0`。模型 30s、工具 12s、单次 Agent 执行 60s；每 Run 8 MODEL / 6 MCP。原 512 配置和证据不变。

2026-10-28 执行前核对官方[价格](https://api-docs.deepseek.com/quick_start/pricing/)和[Chat 协议](https://api-docs.deepseek.com/api/create-chat-completion/)。峰值无缓存单价分别为输入 USD 0.30/M、输出 USD 1.20/M。沿用 HF 已审的完整输入容量保守上界 1,048,576（包括 messages、六工具与协议开销），输出采用实际 wire 的 2048；不是用 12,000 estimated tokens 当严格计费上界。

单次预留：`ceil(1,048,576 * 0.30 + 2,048 * 1.20)` microUSD = **317,031 microUSD / USD 0.317031**。一请求在途，已结算费用 + 未决预留 + 下一请求预留不得超过 USD 0.50。失败、超时或未知收费不释放风险再发；相同逻辑请求不自动重发。Usage 已知后按峰值无缓存逐请求向上取整结算。本轮 28 条均 SETTLED、每条发送一次、无未决项；账本 USD **0.034451**。

该边界依赖供应商遵守上下文、输出限制、Usage 和价格协议，不能保证供应商违规时绝对不超支。账本是保守估算，不是账单。本轮返回的最大 completion_tokens 为 806，未出现 length、参数不兼容、缺失 Usage 或未知结果。

## 实际公平性检查

- A/B 每对从同一 seed 克隆到独立 SQLite；初态业务 digest 相同，Task/Run 身份各自独立，前组结果不进入后组。
- 同六种 MCP 工具、Schema、描述与权限；规范化 Schema 摘要 `93475a49f9a739be154b26d850a8a54ed70a1f4077b61fef7ab2b0f71bfa06e1`。真实出站也校验，不只检查 SDK 声明。
- 原 CASES 和用户目标未改；A 的 S3Nodes Prompt/策略、B 的标准 create_agent Prompt/策略不调优。仅传递输出参数与增加观察日志。
- 两组 Prompt/Context 和多工具执行机制不同，不能把差异全归因于 Agent Loop。虽然发送 `parallel_tool_calls=false`，本轮仍返回多工具提议：A 每次执行一个后再决策，B 将同批提议串行执行。这是已存在的比较混杂，不是并发付费请求。
- 首对放行检查协议、Usage、工具与执行完整性，不要求模型目标得分通过；此区别在付费前冻结并经单测。B 首题 Fallback 完整保留，没有换题或重跑。
- 返回模型 alias 全为 `deepseek-flash`，同 fingerprint `bc19ba97cbe016479903222bb1578db6`。官方当日列出 alias 对应版本 DeepSeek-V4.1-Flash-1017；响应本身不独立证明精确后端版本。

## 环境与执行

Windows PowerShell，Python 3.14.0；现有 `.venv-stageb`：langchain 1.4.1 / langchain-core 1.6.12 / langchain-openai 1.7.2 / langgraph 1.2.16 / mcp 2.3.0 / openai 3.33.0 / httpx 0.28.1。无依赖修改。

唯一付费入口实际执行一次：

```powershell
$env:PYTHONUTF8='1'
.venv-stageb/Scripts/python.exe -m experiments.ar01_free_agent.p1 --live
```

退出码 0，原始 stdout/stderr：`runs/05-live.log`；开始 2026-10-28T13:16:18.083Z，结束 13:17:47.621Z。**不要再次执行**，不追加样本。Key 只从本机环境读取，不进入文档或 Trace。关闭 LangSmith 外送。

免费本地 5 项预检、77 项原实验、72 项安全、1 项首对门禁测试先于付费执行。结束时对最终源码的 6 项 P1 测试再跑一次，仅 Loopback；精确命令和环境见 `runs/06-final-focused.log`。前四次原始日志只含 pytest 输出，其测试调用核心与复跑范围在 `RESULTS.json` 中分开记录，不把缺失的捕获包装命令伪称原始记录。

未执行：全仓 pytest、浏览器（STOP）、Stage B 验收、生产系统、付费评分模型、第二轮/重复样本、迁移。原 HOLD 与 DEFERRED_GATES 不因此解除。
