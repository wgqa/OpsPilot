# AR-02-LIVE-01 P1 冻结执行计划

- **状态：** `AUTHORIZED_FOR_BOUNDED_P1`；最终仅提交 `ACCEPTANCE_CANDIDATE`
- **Repo / branch：** `wgqa/OpsPilot` / `codex/ar02-live-01`
- **执行 Base：** `b4e1c543fb5efbcae533bd37e131902f927611b2`
- **P0 前置裁决：** `ACCEPT_WITH_LIMITS`；P0 报告中的真实 Provider 请求数为 0。
- **范围：** 冻结 S01 一次、同一个 S02 Session 五轮。六个用户操作按顺序至多各提交一次；任何失败不改题、不重试、不补跑。
- **冻结输入来源：** `docs/evidence/ar-02/hf-01/SMOKE_INPUTS.md`，Blob `ee9b1623a2296905c425449709a2f9ae6563caca`。S01/S02 正文直接使用该文件，不在本计划重写。

## 模型、费用与调用边界

- DeepSeek 官方 Chat Completions，模型 `deepseek-flash`，`thinking.type=disabled`。
- 每个 Provider 请求：`max_tokens=2048`、`tool_choice=auto`、`parallel_tool_calls=false`、30 秒超时、`max_retries=0`。
- 整轮最多 16 次 Provider dispatch、12 次 MCP `tools/call`；发送前由持久 SQLite 实验账本预留。
- 每次 Provider dispatch 预留 USD `0.645600`；实验账本上限 USD `10.50`。未知/超时/取消/响应丢失保留完整预留并计数，不重发。应用侧上限不宣称为供应商账户硬封顶。
- 只使用本次正式 Worker 与本地授权的只读 MCP/Knowledge。只允许通过受信 API 建立会话并在 S02 第三轮确认 `ar02-order` TaskBinding；该绑定是查询范围设置，不执行订单修复、审批或交接。

## 隔离与事实初态

- Domain DB 与 LangGraph Checkpoint 使用 `.runtime/ar02-live-01-p1-20261101-01/` 下互不相同的新路径；本库从空路径初始化，无其他任务/Session/Run。
- 单一正式 API `TestClient` lifespan 内启动一个 `SingleInstanceWorker`。运行中不启动第二个 Worker、不接入其他用户请求。
- 在 Agent 调用前以本地测试准备程序创建 `ar02-order`：订单 `COMPLETED`、配置合同版本 2、同一 Event 回调 HTTP 202、Receiver `QUEUED`。准备服务为 loopback 临时 HTTP server；它只写入隔离测试库，单独记录为 `setup`，不是 Agent 行为或生产业务修复。
- S02 用户粘贴的 `event-e1 / req-e1-1 / HTTP202 / unknown` 始终是不可信示例线索；当前 Event/Transport/Receiver 事实必须来自本次 Worker 触发的 MCP/Domain 观察。

## 评价

每轮记录用户输入、实际模型请求体/响应、Tool 选择、MCP Observation、持久 Answer、Run/Message/Session/Task ID、Usage、停止原因和额度快照。分别区分模型动作、工具/Domain 事实与持久用户交付。

允许模型零工具回答、查合法 Knowledge、查询当前事实、澄清或停止；不规定工具序列。HTTP 202 不等于处理完成；不同 Event 不能互证；没命中文档不得声称引用。

## 立即停止条件

预算/参数不符、Provider 协议失败、无效或缺失 Usage、结果未知、模型版本异常、来源或授权异常、请求重放、越域读取、意外业务写入或证据无法完整关联时停止；保留已发生事实及预留，不重试。

本计划不授权浏览器自动化、其他 Provider 请求、Task 以外的业务写入、S1/S2 修复、Approval、Handoff、工单提交、修改 `main`、新增样本或进入 AR-03。
