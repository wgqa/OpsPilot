# R1-LIVE-JOURNEY-01 CONTINUE 报告

**状态：`PARTIAL / ACCEPTANCE_CANDIDATE`**

**基线：** `7c78148f50e2852d4cf12d06c175b452ca5a38eb`

**代码候选提交：** `0f39d1e667d1ec31b0289c897e87f0a975741876`；本报告随最终证据和 Runtime 响应修复另行提交。
**分支：** `codex/r1-live-journey-01`。main 未修改。

## 用户旅程结果

| 旅程 | 真实运行结果 | 用户获得的结果 |
|---|---|---|
| J1-01 协议差异咨询 | Provider HTTP 200；模型选择 `list_scoped_protocol_documents(topic="回调重试")`；Assistant Run FAILED；MCP 0 | 程序失败通知。未检索协议，不是模型答案 |
| J1-02 配置材料分析 | Provider HTTP 200；模型再次选择协议发现；Assistant Run FAILED；MCP 0 | 程序失败通知。没有协议依据，未完成 JSON 分析 |
| J2-01 当前 Event 查询 | 可信 API 建立 `r1-readiness-order` TaskBinding；Provider HTTP 200；模型提出协议、Delivery、Receiver 工具；Run FAILED；MCP 0 | 程序失败通知。未取得当前业务 Observation |
| J2-02 Event 更正及客户说明 | Provider HTTP 200；模型提出协议、Delivery、Receiver、transport-history 工具；Run FAILED；MCP 0 | 程序失败通知。未核查 event-previous，也未生成说明草稿 |
| J3 S2 结果回读 | NOT_RUN：隔离 Campaign DB 无既有可信 S2 Receipt | 无结果 |
| J4 S1 结果回读 | NOT_RUN：隔离 Campaign DB 无既有可信 S1 Outcome | 无结果 |

全部四轮是同一 Session、四个 Run、一个可信 Task。真实模型累计提出 9 个工具调用，但没有一个到达 ToolNode/MCP。模型行动证据只证明它提出了查询选择，不证明其获得 Observation 或完成调查。逐轮 ID、原始输入、工具提议、响应和程序答复见 [`TRACE.jsonl`](TRACE.jsonl) 与 [`PROVIDER_HTTP.jsonl`](PROVIDER_HTTP.jsonl)。

## 已证实的费用与资源边界

- 真实 Provider 请求 4/16；HTTP 状态 200；自动和人工重试均为 0。
- MCP `tools/call` 0；当前业务 Observation 0。
- 发送前每次持久预留 USD 0.645600，共记录 USD 2.582400；有效 Usage 结算 USD 0.002914，账本剩余 USD 10.997086。
- 四个 Runtime Spend 状态为 `RESPONSE_STORED`，含 Completion ID 和 Usage；Assistant 层四个调用仍标 `UNKNOWN`，四个 Run `FAILED`。Campaign 最后停止，余下 12 次不再可用。
- 隔离夹具使用 2 次本地 loopback HTTP 记录；外部业务写入、ActionIntent、ActionLedger、DeliveryRecord、HandoffReceipt 均为 0。
- 浏览器 0；main 合并 0。

逐请求费率修正及 Usage 结算见 [`COST_LEDGER.md`](COST_LEDGER.md) 与 [`ERRATA.md`](ERRATA.md)。当前 DeepSeek 官方价格核对结果为 input cache miss USD 0.30/M、output USD 1.20/M，1M context / 384K max output；以此计算 16 次公开容量极端预留为 USD 10.3296，低于获批 USD 11.00。[官方价格表](https://api-docs.deepseek.com/quick_start/pricing/)

## 真实失败与最小修正

真实 HTTP 成功后，Assistant 仍在 SDK/Runtime 响应处理阶段失败。模型本身四次都返回了格式可解析的工具调用响应，但工具没有执行。离线复现确认 Runtime 包装层对已解码 HTTP 正文保留原压缩头会触发 HTTPX `DecodingError`；已最小修复响应重建头并加入回归。因为真实 Provider 的 `Content-Encoding` 未保存在原始记录中，这一缺陷与实况强相关但不构成真实失败根因的最终证明。详见 [`FAILURES.md`](FAILURES.md)。

当前程序失败通知将结果称为“连接失败”和“费用未知”，但本次 Runtime Ledger 已保存有效 Usage 并结算。这个表述缺陷未在本轮追加重构；它会误导用户，但没有造成重发或账本释放。

## 验证与 R1-ENGINE 判断

新增 gzip 响应包装测试先 RED（`HTTPX DecodingError`），修复后转 GREEN。Runtime Grant、费用池、16 次持久 Campaign 上限、未知结果保护、旧路径隔离、正式 API/Worker 模拟响应及 R1 J1/J2 离线回归合计 **44/44 通过**，31.56 秒，退出码 0。一次早期调用的临时目录父路径不存在，42 项 setup 错误；修正外部测试临时目录后完成 44/44。实际命令和日志摘要见 [`TEST_LOG.txt`](TEST_LOG.txt)。

这些测试证明费用与次数守卫及模拟传输路径有效，不证明真实用户旅程成功。**本次不支持把 R1-ENGINE 连续真实调查冻结为已完成**：J1/J2 未交付模型答案或观察驱动结果，J3/J4 未运行。可将代码候选和失败证据供主 Agent 独立评审，但真实业务完成状态为 PARTIAL，R1-INTERACTIVE 仍受浏览器 STOP 限制。

## 私有原始证据

原始脱敏前的完整 HTTP 请求/响应、Domain SQLite、Checkpoint、完整执行 Trace 和控制台日志留在私有目录：`D:\学习\agent新项目\.private\r1-live-journey-01-continue-01-20261108`。密钥从环境文件读取但从未输出、复制或提交。公开 `PROVIDER_HTTP.jsonl` 只保留核验所需字段，不含 Authorization 值、完整 System Prompt 或工具 Schema。私有文件 SHA-256 与公开 Trace/账本关联记录在本目录的测试日志末尾。

本报告未改写原始 [`../REPORT.md`](../REPORT.md)、原始费用失败记录、Gold 或 Trace。实施方仅提交 `ACCEPTANCE_CANDIDATE`，等待主 Agent 独立验收。
