# M4-03 S3 最终产品补强报告

**状态：** 验收候选（Knowledge 显式检索稳定性为 PARTIAL），等待主 Agent 独立复核
**冻结基线：** `main@f7c739f4e3d02988fc125b377dfa85a902bc2a0d`
**冻结提交：** Gold/旅程 `98a1d1e83b689702752a93e84e6901a84eff8c64`；检索查询 `42f4281e5f47e14f9285608458f0f4d7789799aa`；Knowledge 在线检查 `a4cd231bddcf898c2b705646b3a118289dc7e0a1`
**实现提交：** `6446e60a8d82f81361f7356c58f0b1e1a7ffeec4`；最终证据文档和运行记录随后的提交一并推送。

## 产品结果

S3 已能从真实用户对话推进到本地人工接收节点。当前租户的资源目录和 Domain 测试都验证了两个不同预注册订单 `async-order` 与 `async-order-2`；任意未登记订单无法创建 Task。真实 Web 旅程中，用户选择并确认 `async-order-2` 后才建立绑定，并在同一绑定上调查。首轮的可信 HTTP/MCP 事实显示订单仍为 `PROCESSING`，Gate 要求等待订单完成。演示准备程序随后独立把本地接收端和关联投递事实切换为 503 重试耗尽；用户正式提交“订单已完成但回调仍失败”的关键纠错后，TaskControl 增加控制版本并启动新 Run。新 Run 针对同一订单重新取证，Gate 得到 `CALLBACK_DELIVERY_FAILED / CONTACT_CALLBACK_OPERATOR`。用户再次明确确认后，Domain 原子提交队列条目、`HANDOFF_ACCEPTED` 回执、命令、Task 终态和 Outbox；重复确认回放同一回执。重启 API 后，页面仍可追问并准确解释回执只代表待人工审核，不代表回调恢复或重发。

最终真实浏览器结果位于 [`runs/web-20261023T101521Z/RESULTS.json`](runs/web-20261023T101521Z/RESULTS.json)，Edge 六张截图在同目录 `screenshots/`。Task 为 `task-50ba3bd0-d26f-4a52-8318-e2f137bee8f6`，纠错 Run 为 `run-2de277c8-226d-4929-85b7-baccf04452cc`，Receipt 为 `s3-handoff-7809c635-d2d9-4884-a169-18fb2e972b0f`。首次调查、关键纠错 Run、新 HTTP/MCP 请求关联、队列和回执数量、API 重启前后服务进程、页面刷新恢复及结果追问均保存在 `TRACE.json`、`JOURNEY.json` 和 `HANDOFF-BEFORE-RESTART.json`。最终运行页面刷新一次后恢复回执与 Task 状态；重复确认回放同一 Receipt。

Domain 增加的授权订单目录仅允许当前租户受支持者身份列出。Task 创建时在同一事务中保存用户确认的订单绑定；之后聊天内容、模型输出和 MCP 参数都不能改绑定。调查只读工具包括订单状态、关联回调投递、接收方处理、版本化知识检索和按需 Skill；Gate 仍由 Domain 对当前 Evidence 确定性裁决。S3 交接使用独立表和事务协议，不复用 S2 Scope 审批；`HANDOFF_ACCEPTED` 不表示业务恢复。

## 冻结评测

冻结文件是 [`FROZEN_PLAN.md`](FROZEN_PLAN.md)、[`GOLD.json`](GOLD.json)、[`RUBRIC.json`](RUBRIC.json) 和 [`RETRIEVAL_QUERIES.json`](RETRIEVAL_QUERIES.json)。评测冻结在实现前以连续提交追加到基线上，未修改历史 Gold。8 个冻结案例由 6 个开发案例和 2 个留出案例组成，真实运行 DeepSeek 与 MCP；每个 case/strategy 只运行一次。R/H/A 冻结运行使用 prompt provenance v1。所有 24 个策略单元均正确满足 Gold 诊断、处理方向、Evidence、可信绑定和零业务副作用。R、H、A 各 8/8；S3 本身是诊断与交接，不包含自动业务恢复，因此真实恢复为 0/8，RHA 中没有持久交接回执，确认提交由独立浏览器旅程证明。

| 策略 | 正确诊断/方向 | 平均 Provider token | 平均延迟 | MCP 调用总数 | 无效调用 |
|---|---:|---:|---:|---:|---:|
| R：确定性最小调查 | 8/8 | 0 | 1.596 秒 | 17 | 0 |
| H：模型理解、规则选工具 | 8/8 | 1,424 | 7.862 秒 | 17 | 0 |
| A：模型自主选择只读行动 | 8/8 | 7,093 | 14.221 秒 | 18 | 0 |

A 没有在冻结 Gold 上胜过 R/H；它确实在不同中间事实下改变工具序列，例如接收方 202 排队的案例会继续查询接收处理，处理中的订单在订单事实充分时停止。其代价是更多 token 和延迟。模型贡献是理解描述、按需选取只读知识/Skill/工具并生成解释；资源绑定、当前事实、Gate、是否可交接以及写入仍由可信 Domain 与用户明确确认决定。完整逐 case 指标在 [`runs/rha-20261023-frozen-01/RESULTS.json`](runs/rha-20261023-frozen-01/RESULTS.json)，每个单元的模型/MCP/HTTP 轨迹在对应 `S3-xx-{R,H,A}/TRACE.json`。

## 资产价值与限制

冻结知识查询集比较了词法排序与无嵌入的 BM25-lite。v2 资产集两种方法均为 Recall@1 0.875、MRR 0.875、nDCG@1 0.708；词法平均 0.470 ms，BM25-lite 0.517 ms。BM25-lite 没带来测得的排序收益，平均略慢，不值得在本切片增加额外依赖。旧 v1 的 Recall@1 均为 0.75；v2 知识修订后两种排序都提高。详见 [`runs/retrieval-20261023T074302Z/RESULTS.json`](runs/retrieval-20261023T074302Z/RESULTS.json)。

在线使用单独冻结于 [`KNOWLEDGE_LIVE_CHECK.md`](KNOWLEDGE_LIVE_CHECK.md)。原提示下，用户明确询问“按当前协议版本解释 202”时，真实模型没有调用 Knowledge，尽管正确完成了当前 HTTP/MCP 调查。加入窄范围指令后，一条真实 Run 调用了两次 MCP Knowledge，取得 `order-lifecycle-contract-v2` 和 `receiver-ack-contract-v2`，随后核对当前订单、投递事件和接收队列；Gate 仍为 `RECEIVER_PROCESSING_UNCONFIRMED` 且业务写入为零。但该次运行的 Prompt provenance 误记为 v1；修正版本号后的新鲜复验再次没有调用 Knowledge。Trace 保留在 `runs/knowledge-explicit-*`。这条补验是在冻结 R/H/A 后响应明确 Knowledge 检查要求而进行，当前 prompt provenance 为 v2；为遵守有限实验预算，没有重跑冻结 R/H/A。因此本报告只把原 R/H/A 结果归属于 v1，不推断 prompt v2 下的 R/H/A 性能。显式检索履约不稳定，最终标记 **PARTIAL**，也不继续重试。

真实跨 Task Memory 运行使用 13 次 DeepSeek 请求（上限 30）。来源 Task A 的经批准 S3 案例被 Task B 选择并出现在 Provider Context；B 的当前 503 证据仍决定 `CALLBACK_DELIVERY_FAILED`。Task C 的真实 202/QUEUED 接收事实出现后，矛盾历史提示被排除，下一步查询接收处理并由 Gate 得到 `RECEIVER_PROCESSING_UNCONFIRMED`。中文无关的“供应商发票”任务没有加载该回调案例，Gate 因无当前订单事实停止为 `INCONCLUSIVE`。撤销后，后续 Task 的 Provider Context 记录 `MEMORY_REVOKED`，没有恢复历史文本。细节见 [`runs/memory-20261023T092400Z/RESULTS.json`](runs/memory-20261023T092400Z/RESULTS.json) 和 5 个逐任务 JSON。

Memory 实验证明了跨 Task 注入、冲突/相关性排除和撤销失效，但正确经验并未改变 B 的诊断或其两次工具查询，与撤销/不注入情况下没有形成可量化的因果增益；不得把“被选中”说成提高任务成功率。当前相关性是小型、可解释的字段匹配分数；中文采用字符双元组缓解单字符泛化误匹配，仍需更多留出语料验证。Skill 和 Knowledge 只提供方法，不影响 Gate 权威。

M3 Summary 来源链在复制的隔离数据库中完成了有预算上限的真实实验：旧摘要进入首个真实 Provider 上下文且其答案持久依赖摘要；模拟源摘要依赖的消息 digest 变化后，摘要被标记 INVALID，旧摘要和依赖回答都从后续上下文排除。最终运行实际预留 3 次请求，低于 4 次硬上限。此前一次 Provider 超时和两次准备失败均原样保留；本实验只证明该隔离来源变更路径，不代表通用 Summary 压缩质量，沿用 M3 未完成状态，不宣称 M3 闭环完成。详见 [`runs/summary-20261023T085730Z/RESULTS.json`](runs/summary-20261023T085730Z/RESULTS.json)。

## 验证

- 完整后端与既有安全回归（最终源码）：`.venv/Scripts/python.exe -m pytest -q --basetemp=.runtime/m4-03/pytest-full-final-postreview`，`275 passed in 252.58s`；原始日志：[`runs/pytest-full-final-postreview-20261023.log`](runs/pytest-full-final-postreview-20261023.log)。S3 定向测试在最终改动后为 12/12，通过日志见 [`runs/pytest-s3-final-20261023.log`](runs/pytest-s3-final-20261023.log)。首次系统 Python 缺依赖的失败日志以及此前通过日志都已保留。
- 新 Memory 中文相关性回归：`1 passed, 11 deselected`；日志：[`runs/pytest-memory-chinese-relevance-final-20261023.log`](runs/pytest-memory-chinese-relevance-final-20261023.log)。
- 前端生产构建：通过；日志：[`runs/frontend-build-final-20261023.log`](runs/frontend-build-final-20261023.log)。
- MCP stdio `tools/list` / `tools/call` 与租户边界负例：通过；日志：[`runs/mcp-stdio-final-20261023.log`](runs/mcp-stdio-final-20261023.log)。
- 原有 S1 新鲜真实 401→200 smoke 与 DISABLED 负例：通过；日志：[`runs/s1-smoke-final-20261023.log`](runs/s1-smoke-final-20261023.log)。
- 真实 Edge Web → DeepSeek → MCP stdio → HTTP 接收方 → SQLite Queue/Receipt → API 重启与页面刷新 → 追问：最终运行通过，日志和原始数据位于 [`runs/web-20261023T101521Z/`](runs/web-20261023T101521Z/)。两次重启后刷新遇到 Vite proxy 短暂 502 的失败尝试也单独保留；最终自动化按受限轮询恢复。
- 提交前 `git diff --check` 通过；只检查本任务文件，用户的 `开发目录/` 未暂存、未修改。

可复跑命令和本地边界见 [`RUNBOOK.md`](RUNBOOK.md)；冻结行级结果见 [`RESULTS.json`](RESULTS.json)；失败历史见 [`FAILURES.md`](FAILURES.md)；源码学习与面试材料见 [`SOURCE_STUDY.md`](SOURCE_STUDY.md) 与 [`INTERVIEW.md`](INTERVIEW.md)。

本报告没有宣布 M4-03 最终 PASS，等待主 Agent 独立验收。
